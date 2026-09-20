# -*- coding: utf-8 -*-
"""Pipeline de pré-processamento e modelagem supervisionada no grão do aluno.

Código promovido do notebook `notebooks/desenv_03_pipeline_modelagem.ipynb`,
onde o desenvolvimento está documentado célula a célula, com os conceitos
aplicados e as evidências de execução.

O que este script faz:
1. lê a tabela analítica gravada pelo `prod_01` na área `ml/` do data lake e a
   lista de variáveis fechada na análise exploratória;
2. retira a rede privada da modelagem, que não é alvo da meta pactuada
   (decisão D-011);
3. agrupa os alunos que compartilham exatamente as mesmas variáveis, o que
   reduz a base sem perder informação: cada grupo vira duas linhas, uma por
   classe, ponderadas pelo número de alunos;
4. monta o pipeline de pré-processamento, com indicadores de ausência,
   imputação pela mediana da UF, codificação one-hot e, nos modelos lineares,
   logaritmo e padronização (decisão D-011);
5. mede três referências que não aprendem nada, entre elas `repetir 2023` e a
   melhor previsão possível, que estabelece o teto desta tarefa;
6. faz a busca aleatória de hiperparâmetros em três famílias, com validação
   cruzada agrupada por município;
7. escolhe a família pelo critério declarado, treina no treino inteiro, mede na
   partição de validação e registra a receita.

O que não foi promovido: a análise de acréscimo e falta por bloco de hipótese
(seção 4 do notebook), que é diagnóstico de desenvolvimento, e as figuras.

Execução:
    python src/modeling/prod_03_pipeline_modelagem.py
    (no Windows, se o comando python não for reconhecido, use o launcher py:
    py src/modeling/prod_03_pipeline_modelagem.py)

    --usar-busca-salva  reaproveita reports/busca_hiperparametros.csv e pula a
                        etapa mais lenta, útil para refazer só a escolha final

Propriedades:
- Replicabilidade: semente fixa nas partes da validação cruzada, na busca de
  hiperparâmetros e nos modelos; a mesma execução produz o mesmo resultado.
- Contra vazamento: toda estatística de pré-processamento é aprendida apenas no
  treino, dentro do pipeline, e a validação cruzada agrupa por município, de
  modo que nenhuma parte vê um município que outra usou para treinar.
- Verificações executáveis: presença das variáveis, invariância dentro do grupo,
  preservação de alunos e taxa no agrupamento e ausência de células vazias
  depois do pré-processamento interrompem a execução com código de saída 1.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pydata_google_auth
from google.cloud import storage
from sklearn.base import BaseEstimator, TransformerMixin, clone
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.model_selection import GroupKFold, ParameterSampler
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, StandardScaler

RAIZ = Path(__file__).resolve().parents[2]
ESCOPOS = ["https://www.googleapis.com/auth/cloud-platform"]

# ---------------------------------------------------------------------------
# Desenho da modelagem
# ---------------------------------------------------------------------------
SEMENTE = 42                  # replicabilidade: mesma semente, mesmas partes
PARTES_VALIDACAO = 5          # partes da validação cruzada, agrupadas por município
CHAVE_GRUPO = ["particao", "id_municipio", "rede_nome"]
REDE_FORA = "Privada"         # fora da meta pactuada (D-011)

# Espaço de busca de cada família, com o número de combinações sorteadas
FAMILIAS = {
    "regressão logística": {
        "linear": True,
        "fabrica": lambda p: LogisticRegression(max_iter=3000, **p),
        "espaco": {"C": [float(c) for c in np.logspace(-3, 2, 10)]},
        "combinacoes": 10},
    "gradient boosting": {
        "linear": False,
        "fabrica": lambda p: HistGradientBoostingClassifier(
            random_state=SEMENTE, early_stopping=False, **p),
        "espaco": {"learning_rate": [0.02, 0.05, 0.1, 0.2],
                   "max_iter": [100, 200, 400],
                   "max_leaf_nodes": [7, 15, 31, 63],
                   "min_samples_leaf": [10, 20, 50, 100, 200],
                   "l2_regularization": [0.0, 0.1, 1.0, 10.0]},
        "combinacoes": 20},
    "random forest": {
        "linear": False,
        "fabrica": lambda p: RandomForestClassifier(
            random_state=SEMENTE, n_jobs=-1, **p),
        "espaco": {"n_estimators": [200, 400],
                   "max_depth": [None, 8, 12, 20],
                   "min_samples_leaf": [2, 5, 10, 20, 50],
                   "max_features": ["sqrt", 0.3, 0.5]},
        "combinacoes": 12},
}
CRITERIO = ("menor log-loss na validação cruzada; a regressão logística vence "
            "se ficar a menos de um desvio da melhor")

# Saídas
SAIDA_BUSCA = RAIZ / "reports" / "busca_hiperparametros.csv"
SAIDA_REGISTRO = RAIZ / "reports" / "modelo_escolhido.json"
SAIDA_COMPARACAO = RAIZ / "reports" / "comparacao_modelos.csv"


# ---------------------------------------------------------------------------
# Acesso ao lake
# ---------------------------------------------------------------------------
def carregar_config() -> dict:
    """Lê config/config.json; orienta o executor caso não exista."""
    caminho = RAIZ / "config" / "config.json"
    if not caminho.exists():
        sys.exit(
            "Arquivo config/config.json nao encontrado.\n"
            "Copie config/config.example.json para config/config.json e "
            "aponte para o projeto e o bucket da fase anterior."
        )
    return json.loads(caminho.read_text(encoding="utf-8"))


class Lake:
    """Leitura das tabelas já materializadas no data lake."""

    def __init__(self, cfg: dict):
        self.projeto = cfg["projeto_gcp"]
        self.bucket = cfg["bucket_lake"]
        credenciais = pydata_google_auth.get_user_credentials(ESCOPOS)
        self.credenciais = credenciais.with_quota_project(self.projeto)
        self.cliente = storage.Client(project=self.projeto,
                                      credentials=self.credenciais)

    def ler(self, area: str, tabela: str) -> pd.DataFrame:
        """Lê a partição mais recente de uma tabela, a partir da memória."""
        particoes = sorted({
            b.name.split("/")[2]
            for b in self.cliente.list_blobs(self.bucket, prefix=f"{area}/{tabela}/")
            if len(b.name.split("/")) > 2
        })
        if not particoes:
            sys.exit(f"Tabela '{tabela}' nao encontrada em {area}/. "
                     "Execute antes src/preprocessing/prod_01_base_analitica.py")
        caminho = f"{area}/{tabela}/{particoes[-1]}/{tabela}.parquet"
        blob = self.cliente.bucket(self.bucket).blob(caminho)
        return pd.read_parquet(io.BytesIO(blob.download_as_bytes()))


# ---------------------------------------------------------------------------
# Preparação da base
# ---------------------------------------------------------------------------
def carregar_base(lake: Lake) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Tabela analítica sem a rede privada, lista de variáveis e o desenho delas."""
    abt = lake.ler("ml", "abt_alfabetizacao")
    lista = pd.read_csv(RAIZ / "reports" / "variaveis_modelagem.csv",
                        index_col="variavel")
    entram = lista[lista["situacao"] == "entra"]
    desenho = {
        "categoricas": entram.index[entram["tipo"] == "categórica"].tolist(),
        "numericas": entram.index[entram["tipo"] == "numérica"].tolist(),
        # indicador de ausência e logaritmo, como a análise exploratória determinou
        "indicadores": {nome: variavel for variavel, nome
                        in entram["indicador_ausencia"].dropna().items()},
        "com_log": entram.index[entram["transformacao"].notna()].tolist(),
    }
    desenho["variaveis"] = desenho["numericas"] + desenho["categoricas"]

    faltam = [v for v in desenho["variaveis"] if v not in abt.columns]
    if faltam:
        sys.exit(f"Variaveis da lista ausentes na base: {faltam}. "
                 "Reexecute o prod_01 e a secao 12 do desenv_02.")

    privada = abt["rede_nome"] == REDE_FORA
    colunas = ["particao", "id_municipio", "alvo"] + desenho["variaveis"]
    return abt.loc[~privada, colunas].copy(), lista, desenho


def agrupar_alunos(abt: pd.DataFrame, desenho: dict) -> pd.DataFrame:
    """Agrupa os alunos com as mesmas variáveis em duas linhas ponderadas.

    Alunos da mesma rede, no mesmo município, têm valores idênticos em todas as
    variáveis. Cada grupo desses vira duas linhas, uma com alvo 1 e outra com
    alvo 0, cada uma pesando pelo número de alunos que tem. O modelo enxerga a
    mesma informação com uma fração das linhas.
    """
    invariantes = desenho["numericas"] + ["sigla_uf", "nome_regiao"]
    variacao = (abt.groupby(CHAVE_GRUPO, observed=True)[invariantes]
                .nunique(dropna=False).max())
    variam = variacao[variacao > 1]
    if len(variam):
        sys.exit(f"Variaveis que variam dentro do grupo: {variam.to_dict()}")

    grupos = (abt.groupby(CHAVE_GRUPO, observed=True)
              .agg(alunos=("alvo", "size"), alfabetizados=("alvo", "sum"),
                   **{v: (v, "first") for v in invariantes})
              .reset_index())
    sim = grupos.assign(alvo=1, peso=grupos["alfabetizados"])
    nao = grupos.assign(alvo=0, peso=grupos["alunos"] - grupos["alfabetizados"])
    dados = (pd.concat([sim, nao], ignore_index=True)
             .query("peso > 0")
             .drop(columns=["alunos", "alfabetizados"])
             .reset_index(drop=True))

    # Trava: o agrupamento preserva o número de alunos e a taxa de cada partição
    pesados = dados.assign(p=dados["alvo"] * dados["peso"])
    alunos_agrupados = dados.groupby("particao")["peso"].sum()
    taxa_agrupada = (pesados.groupby("particao")["p"].sum() / alunos_agrupados)
    if not (np.allclose(abt.groupby("particao").size(), alunos_agrupados)
            and np.allclose(abt.groupby("particao")["alvo"].mean(), taxa_agrupada)):
        sys.exit("O agrupamento alterou o numero de alunos ou a taxa.")
    return dados


def separar(dados: pd.DataFrame, particao: str, variaveis: list) -> tuple:
    """Variáveis, resposta, peso e município de uma partição."""
    d = dados[dados["particao"] == particao]
    return d[variaveis], d["alvo"], d["peso"], d["id_municipio"]


# ---------------------------------------------------------------------------
# Pipeline de pré-processamento
# ---------------------------------------------------------------------------
class PreparadorAusencias(BaseEstimator, TransformerMixin):
    """Cria os indicadores de ausência e imputa pela mediana da UF.

    As medianas são aprendidas no fit, só com os dados de treino, e aplicadas
    no transform. A UF sem valor para uma variável recebe a mediana nacional.
    """

    def __init__(self, numericas: list, indicadores: dict, coluna_uf: str = "sigla_uf"):
        self.numericas = numericas
        self.indicadores = indicadores
        self.coluna_uf = coluna_uf

    def fit(self, X, y=None):
        valores = X[self.numericas].astype("float64")
        self.medianas_uf_ = valores.groupby(X[self.coluna_uf]).median()
        self.medianas_nacionais_ = valores.median()
        return self

    def transform(self, X):
        X = X.copy()
        # os indicadores vêm antes da imputação, que apaga o sinal da ausência
        for nome, variavel in self.indicadores.items():
            X[nome] = X[variavel].isna().astype("int64")
        valores = X[self.numericas].astype("float64")
        da_uf = self.medianas_uf_.reindex(X[self.coluna_uf]).set_index(X.index)
        X[self.numericas] = valores.fillna(da_uf).fillna(self.medianas_nacionais_)
        return X


def montar_preprocessamento(desenho: dict, linear: bool,
                            variaveis: list | None = None) -> Pipeline:
    """Pré-processamento completo; linear=True acrescenta logaritmo e padronização."""
    usar = set(variaveis or desenho["variaveis"])
    numericas = [v for v in desenho["numericas"] if v in usar]
    categoricas = [v for v in desenho["categoricas"] if v in usar]
    indicadores = {n: v for n, v in desenho["indicadores"].items() if v in usar}
    com_log = [v for v in desenho["com_log"] if v in usar]
    sem_log = [v for v in numericas if v not in com_log] + list(indicadores)
    if linear:
        passos = [("log", Pipeline([
                      ("log1p", FunctionTransformer(np.log1p, feature_names_out="one-to-one")),
                      ("escala", StandardScaler())]), com_log),
                  ("numericas", StandardScaler(), sem_log)]
    else:
        passos = [("numericas", "passthrough", com_log + sem_log)]
    passos.append(("categoricas",
                   OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                   categoricas))
    colunas = ColumnTransformer(passos, verbose_feature_names_out=False)
    colunas.set_output(transform="pandas")
    return Pipeline([("ausencias", PreparadorAusencias(numericas, indicadores)),
                     ("colunas", colunas)])


def montar_modelo(desenho: dict, estimador, linear: bool,
                  variaveis: list | None = None) -> Pipeline:
    """Pré-processamento e modelo num único pipeline."""
    return Pipeline([("preparo", montar_preprocessamento(desenho, linear, variaveis)),
                     ("modelo", estimador)])


def conferir_preprocessamento(desenho: dict, X_treino: pd.DataFrame) -> int:
    """Roda as duas versões no treino e confere que nada sai vazio."""
    saidas = {}
    for nome, linear in [("linear", True), ("arvore", False)]:
        saida = montar_preprocessamento(desenho, linear).fit(X_treino).transform(X_treino)
        vazias = int(saida.isna().sum().sum())
        if vazias:
            sys.exit(f"Pre-processamento {nome} deixou {vazias} celulas vazias.")
        saidas[nome] = saida
    if sorted(saidas["linear"].columns) != sorted(saidas["arvore"].columns):
        sys.exit("As duas versoes do pre-processamento geraram colunas diferentes.")
    return saidas["linear"].shape[1]


# ---------------------------------------------------------------------------
# Validação
# ---------------------------------------------------------------------------
def medir(y, p, w=None) -> dict:
    """AUC, log-loss e Brier; sem pesos, cada linha pesa igual.

    O `prod_03` sempre pondera pelo número de alunos; o `prod_04`, que trabalha
    no grão da rede, chama sem peso, e por isso o argumento é opcional.
    """
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return {"auc": roc_auc_score(y, p, sample_weight=w),
            "log_loss": log_loss(y, p, sample_weight=w),
            "brier": brier_score_loss(y, p, sample_weight=w)}


def resumir(por_parte: list) -> dict:
    """Média e desvio das medidas entre as partes da validação cruzada."""
    d = pd.DataFrame(por_parte)
    return {"auc": d["auc"].mean(), "auc_desvio": d["auc"].std(),
            "log_loss": d["log_loss"].mean(), "log_loss_desvio": d["log_loss"].std(),
            "brier": d["brier"].mean(),
            "auc_partes": d["auc"].tolist()}


def validar(modelo, partes: list, X, y, w) -> dict:
    """Treina em todas as partes menos uma e mede na que ficou de fora."""
    por_parte = []
    for i_treino, i_teste in partes:
        m = clone(modelo)
        peso = w.iloc[i_treino].to_numpy()
        m.fit(X.iloc[i_treino], y.iloc[i_treino],
              modelo__sample_weight=peso / peso.mean())
        p = m.predict_proba(X.iloc[i_teste])[:, 1]
        por_parte.append(medir(y.iloc[i_teste], p, w.iloc[i_teste]))
    return resumir(por_parte)


def melhor_previsao_possivel(municipio, rede, y, w) -> np.ndarray:
    """A taxa real de 2024 da rede no município, calculada com a resposta.

    É o teto da tarefa: nenhum modelo que só enxergue rede e município pode
    ordenar melhor do que isso, porque alunos do mesmo grupo são idênticos.
    """
    d = pd.DataFrame({"municipio": np.asarray(municipio), "rede": np.asarray(rede),
                      "sim": np.asarray(y) * np.asarray(w), "alunos": np.asarray(w)})
    grupo = d.groupby(["municipio", "rede"])
    return (grupo["sim"].transform("sum") / grupo["alunos"].transform("sum")).to_numpy()


def medir_referencias(partes: list, X, y, w, municipio) -> dict:
    """As três referências que não aprendem nada, nas mesmas partes."""
    resultados = {}
    for tipo in ["constante", "repetir 2023", "melhor previsão possível"]:
        por_parte = []
        for i_treino, i_teste in partes:
            y_t, w_t = y.iloc[i_teste], w.iloc[i_teste]
            taxa_do_treino = np.average(y.iloc[i_treino], weights=w.iloc[i_treino])
            if tipo == "constante":
                p = np.full(len(y_t), taxa_do_treino)
            elif tipo == "repetir 2023":
                p = (X["rede_taxa_ant"].iloc[i_teste] / 100).fillna(taxa_do_treino).to_numpy()
            else:
                p = melhor_previsao_possivel(municipio.iloc[i_teste],
                                             X["rede_nome"].iloc[i_teste], y_t, w_t)
            por_parte.append(medir(y_t, p, w_t))
        resultados[tipo] = resumir(por_parte)
    return resultados


# ---------------------------------------------------------------------------
# Busca, escolha e registro
# ---------------------------------------------------------------------------
def buscar_hiperparametros(desenho: dict, partes: list, X, y, w) -> pd.DataFrame:
    """Busca aleatória nas três famílias, com validação cruzada em cada combinação."""
    linhas = []
    for familia, f in FAMILIAS.items():
        inicio = time.time()
        for parametros in ParameterSampler(f["espaco"], n_iter=f["combinacoes"],
                                           random_state=SEMENTE):
            medidas = validar(montar_modelo(desenho, f["fabrica"](parametros), f["linear"]),
                              partes, X, y, w)
            linhas.append({"familia": familia, "parametros": parametros, **medidas})
        print(f"        {familia:<22} {f['combinacoes']:>3} combinacoes em "
              f"{time.time() - inicio:.0f} s", flush=True)
    return pd.DataFrame(linhas)


def escolher_familia(melhores: pd.DataFrame) -> tuple[str, str]:
    """Aplica o critério declarado antes de rodar e devolve a família e a razão."""
    vencedora = melhores["log_loss"].idxmin()
    distancia = (melhores.loc["regressão logística", "log_loss"]
                 - melhores.loc[vencedora, "log_loss"])
    tolerancia = melhores.loc[vencedora, "log_loss_desvio"]
    if distancia <= tolerancia:
        return "regressão logística", (
            f"a regressao logistica ficou a {distancia:.4f} de log-loss da melhor "
            f"({vencedora}), dentro da tolerancia de {tolerancia:.4f}")
    return vencedora, (f"{vencedora} tem a menor log-loss e a regressao logistica "
                       f"ficou a {distancia:.4f}, acima da tolerancia de {tolerancia:.4f}")


def treinar_final(desenho: dict, familia: str, parametros: dict, X, y, w) -> Pipeline:
    """Treina a combinação escolhida no treino inteiro, com os pesos normalizados."""
    f = FAMILIAS[familia]
    modelo = montar_modelo(desenho, f["fabrica"](parametros), f["linear"])
    return modelo.fit(X, y, modelo__sample_weight=(w / w.mean()).to_numpy())


def avaliar_validacao(finais: dict, X, y, w, municipio, taxa_treino: float) -> pd.DataFrame:
    """Mede os finalistas e as referências na partição de validação."""
    previsoes = {familia: m.predict_proba(X)[:, 1] for familia, m in finais.items()}
    previsoes["repetir 2023"] = (X["rede_taxa_ant"] / 100).fillna(taxa_treino).to_numpy()
    previsoes["melhor previsão possível"] = melhor_previsao_possivel(
        municipio, X["rede_nome"], y, w)
    validacao = pd.DataFrame({nome: medir(y, p, w) for nome, p in previsoes.items()}).T
    teto = validacao.loc["melhor previsão possível", "auc"]
    validacao["pct_do_caminho"] = (100 * (validacao["auc"] - 0.5) / (teto - 0.5)).round(0)
    return validacao.sort_values("log_loss")


def registrar(escolhida: str, melhores: pd.DataFrame, validacao: pd.DataFrame,
              referencias: pd.DataFrame, desenho: dict) -> None:
    """Grava a receita do modelo e a comparação entre modelos e referências."""
    registro = {
        "familia": escolhida,
        "parametros": melhores.loc[escolhida, "parametros"],
        "criterio": CRITERIO,
        "validacao_cruzada": {k: round(float(melhores.loc[escolhida, k]), 5)
                              for k in ["auc", "auc_desvio", "log_loss",
                                        "log_loss_desvio", "brier"]},
        "validacao": {k: round(float(validacao.loc[escolhida, k]), 5)
                      for k in ["auc", "log_loss", "brier"]},
        "semente": SEMENTE,
        "variaveis": desenho["variaveis"],
    }
    SAIDA_REGISTRO.write_text(json.dumps(registro, ensure_ascii=False, indent=2),
                              encoding="utf-8")
    comparacao = pd.concat(
        {"validacao_cruzada": referencias[["auc", "log_loss", "brier"]]
         .combine_first(melhores[["auc", "log_loss", "brier"]]),
         "validacao": validacao[["auc", "log_loss", "brier"]]}, axis=1)
    comparacao.round(5).to_csv(SAIDA_COMPARACAO, encoding="utf-8")


# ---------------------------------------------------------------------------
# Orquestração
# ---------------------------------------------------------------------------
def main() -> int:
    # o console do Windows usa cp1252 por padrao e quebraria os acentos, inclusive
    # os da ajuda do argparse
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--usar-busca-salva", action="store_true",
                        help="reaproveita reports/busca_hiperparametros.csv")
    args = parser.parse_args()

    cfg = carregar_config()
    inicio = datetime.now(timezone.utc)
    print(f"Modelagem no grao do aluno iniciada em {inicio.isoformat()}")
    print(f"Lake: gs://{cfg['bucket_lake']}/   semente: {SEMENTE}")
    print()

    print("[1/6] carregando a base e a lista de variaveis...", flush=True)
    lake = Lake(cfg)
    abt, lista, desenho = carregar_base(lake)
    print(f"        {len(abt):,} alunos, {len(desenho['variaveis'])} variaveis "
          f"({len(desenho['numericas'])} numericas, "
          f"{len(desenho['categoricas'])} categoricas)")

    print("[2/6] agrupando os alunos com as mesmas variaveis...", flush=True)
    dados = agrupar_alunos(abt, desenho)
    X_treino, y_treino, w_treino, mun_treino = separar(dados, "treino", desenho["variaveis"])
    X_validacao, y_validacao, w_validacao, mun_validacao = separar(
        dados, "validacao", desenho["variaveis"])
    print(f"        {len(abt):,} alunos em {len(dados):,} linhas ponderadas; "
          f"treino com {len(X_treino):,} linhas de {mun_treino.nunique():,} municipios")

    print("[3/6] conferindo o pre-processamento...", flush=True)
    colunas = conferir_preprocessamento(desenho, X_treino)
    print(f"        {colunas} colunas entram no modelo, nenhuma celula vazia")

    print("[4/6] medindo as referencias na validacao cruzada...", flush=True)
    partes = list(GroupKFold(n_splits=PARTES_VALIDACAO, shuffle=True,
                             random_state=SEMENTE)
                  .split(X_treino, y_treino, groups=mun_treino))
    resultados = medir_referencias(partes, X_treino, y_treino, w_treino, mun_treino)
    referencias = pd.DataFrame(resultados).T[["auc", "auc_desvio", "log_loss", "brier"]].astype(float)
    teto = referencias.loc["melhor previsão possível", "auc"]
    referencias["pct_do_caminho"] = (100 * (referencias["auc"] - 0.5) / (teto - 0.5)).round(0)
    print(f"        repetir 2023 faz AUC {referencias.loc['repetir 2023', 'auc']:.4f}; "
          f"o teto da tarefa e {teto:.4f}")

    print("[5/6] buscando hiperparametros nas tres familias...", flush=True)
    if args.usar_busca_salva and SAIDA_BUSCA.exists():
        busca = pd.read_csv(SAIDA_BUSCA)
        busca["parametros"] = busca["parametros"].map(json.loads)
        print(f"        {len(busca)} combinacoes lidas de {SAIDA_BUSCA.name}")
    else:
        busca = buscar_hiperparametros(desenho, partes, X_treino, y_treino, w_treino)
        busca.assign(parametros=busca["parametros"].map(json.dumps)).to_csv(
            SAIDA_BUSCA, index=False, encoding="utf-8")
        print(f"        {len(busca)} combinacoes registradas em {SAIDA_BUSCA.name}")

    print("[6/6] escolhendo, treinando e medindo na validacao...", flush=True)
    melhores = (busca.loc[busca.groupby("familia")["log_loss"].idxmin()]
                .set_index("familia").sort_values("log_loss"))
    escolhida, razao = escolher_familia(melhores)
    finais = {familia: treinar_final(desenho, familia, linha["parametros"],
                                     X_treino, y_treino, w_treino)
              for familia, linha in melhores.iterrows()}
    taxa_treino = float(np.average(y_treino, weights=w_treino))
    validacao = avaliar_validacao(finais, X_validacao, y_validacao, w_validacao,
                                  mun_validacao, taxa_treino)
    registrar(escolhida, melhores, validacao, referencias, desenho)
    ordem_cv = list(melhores.index)
    ordem_val = [f for f in validacao.index if f in FAMILIAS]
    confirma = "confirma" if ordem_val[0] == ordem_cv[0] else "nao confirma"
    print(f"        {escolhida}: AUC {validacao.loc[escolhida, 'auc']:.4f} na validacao; "
          f"a validacao {confirma} a validacao cruzada")

    duracao = (datetime.now(timezone.utc) - inicio).total_seconds() / 60
    print()
    print("=" * 64)
    print("RESUMO DA EXECUCAO")
    print(f"  Linhas ponderadas:    {len(dados):,} de {len(abt):,} alunos")
    print(f"  Familia escolhida:    {escolhida}")
    print(f"  Criterio:             {razao}")
    print(f"  Validacao cruzada:    AUC {melhores.loc[escolhida, 'auc']:.4f}   "
          f"log-loss {melhores.loc[escolhida, 'log_loss']:.4f}")
    print(f"  Validacao:            AUC {validacao.loc[escolhida, 'auc']:.4f}   "
          f"log-loss {validacao.loc[escolhida, 'log_loss']:.4f}")
    print(f"  Referencia 2023:      AUC {validacao.loc['repetir 2023', 'auc']:.4f}")
    print(f"  Teto da tarefa:       AUC {validacao.loc['melhor previsão possível', 'auc']:.4f}")
    print(f"  Registro:             {SAIDA_REGISTRO.relative_to(RAIZ)}")
    print(f"  Comparacao:           {SAIDA_COMPARACAO.relative_to(RAIZ)}")
    print(f"  Duracao:              {duracao:.1f} min")
    print("  Status final:         SUCESSO")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    sys.exit(main())

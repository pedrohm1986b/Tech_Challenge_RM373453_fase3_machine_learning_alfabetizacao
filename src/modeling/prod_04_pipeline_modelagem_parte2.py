# -*- coding: utf-8 -*-
"""Curadoria de variáveis e modelagem no grão da rede de cada município.

Código promovido do notebook
`notebooks/desenv_04_pipeline_modelagem_parte2.ipynb`, onde o desenvolvimento
está documentado célula a célula, com os conceitos aplicados e as evidências de
execução.

Por que este modelo existe: no grão do aluno, todas as variáveis disponíveis
são iguais para as crianças da mesma rede, o que impõe um teto à tarefa
(medido no `prod_03`). Este script muda a unidade prevista para a rede de
ensino de cada município, que é o grão das variáveis e o grão da decisão de
política (decisão D-013).

O que este script faz:
1. lê a tabela analítica da área `ml/` e agrega os alunos em uma linha por rede
   de cada município, com a taxa ponderada pelo peso do INEP e a resposta
   definida pela meta nacional de 2024;
2. faz a curadoria das variáveis em duas etapas, calculadas só no treino
   (decisão D-015):
   etapa A, sem olhar a resposta, tira ausentes demais, quase constantes, VIF
   acima do limite e pares de correlação alta;
   etapa B, com seleção por estabilidade, faz eliminação regressiva por
   permutação da log-loss em cinco rodadas com divisões diferentes e mantém
   quem fica no melhor conjunto em pelo menos quatro delas;
3. acrescenta UF e região como ponto de partida, fora da seleção, porque não
   mudam de um ano para o outro;
4. compara três famílias com validação cruzada agrupada por município, escolhe
   pelo critério declarado antes de rodar e confirma na partição de validação;
5. mede o modelo final na partição de teste, contra três referências, e
   registra a matriz de confusão e os recortes de diagnóstico.

O que não foi promovido: a tabela de evidência por tema (seção 2.1 do
notebook), que é leitura de desenvolvimento, e as figuras.

Execução:
    python src/modeling/prod_04_pipeline_modelagem_parte2.py
    (no Windows, se o comando python não for reconhecido, use o launcher py:
    py src/modeling/prod_04_pipeline_modelagem_parte2.py)

    --usar-curadoria-salva  reaproveita reports/curadoria_variaveis.csv e pula
                            a etapa B, que é a parte lenta
    --usar-busca-salva      reaproveita reports/busca_hiperparametros_rede.csv

Propriedades:
- Replicabilidade: semente fixa nas partes da validação cruzada, nas cinco
  rodadas da etapa B, na busca de hiperparâmetros e nos modelos.
- Contra vazamento: a curadoria usa apenas as redes do treino, o
  pré-processamento é aprendido dentro do pipeline e as partições separam
  municípios, de modo que as duas redes de um município caem sempre do mesmo
  lado.
- Verificações executáveis: colunas presentes, invariância dentro da rede,
  preservação do número de alunos na agregação e cobertura dos temas
  interrompem a execução com código de saída 1.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss, roc_auc_score
from sklearn.model_selection import GroupKFold, ParameterSampler
from sklearn.pipeline import Pipeline

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prod_03_pipeline_modelagem import (  # noqa: E402  (o pipeline vem da etapa anterior)
    RAIZ, Lake, carregar_config, medir, montar_modelo,
)

# ---------------------------------------------------------------------------
# Desenho da modelagem
# ---------------------------------------------------------------------------
META_2024 = 59.9              # meta nacional pactuada para a rede pública
MIN_ALUNOS_ESTAVEL = 20       # abaixo disso, a taxa da rede oscila por tamanho de amostra
REDE_FORA = "Privada"         # fora da meta pactuada (D-011)
CHAVE_REDE = ["particao", "id_municipio", "rede_nome"]
TERRITORIO = ["sigla_uf", "nome_regiao"]   # ponto de partida, fora da seleção (D-015)
SEMENTE = 42
PARTES_VALIDACAO = 5

# Etapa A: limites declarados antes de rodar
LIMITE_AUSENTES = 0.20        # fração de redes sem valor
LIMITE_CONSTANTE = 0.90       # fração de redes no valor mais comum
LIMITE_VIF = 10.0
LIMITE_CORRELACAO = 0.80      # em módulo, Spearman

# Etapa B: seleção por estabilidade
RODADAS = 5
MINIMO_RODADAS = 4            # entra quem fica no melhor conjunto em 4 das 5 rodadas
REPETICOES_EMBARALHAMENTO = 2
# o instrumento da eliminação é fixo, e não o modelo final: serve só para ordenar variáveis
PARAMETROS_INSTRUMENTO = {"min_samples_leaf": 10, "max_leaf_nodes": 15, "max_iter": 200,
                          "learning_rate": 0.02, "l2_regularization": 0.1}

FAMILIAS = {
    "regressão logística": {
        "linear": True, "combinacoes": 10,
        "fabrica": lambda p: LogisticRegression(max_iter=3000, **p),
        "espaco": {"C": [float(c) for c in np.logspace(-3, 2, 10)]}},
    "gradient boosting": {
        "linear": False, "combinacoes": 12,
        "fabrica": lambda p: HistGradientBoostingClassifier(
            random_state=SEMENTE, early_stopping=False, **p),
        "espaco": {"learning_rate": [0.02, 0.05, 0.1, 0.2], "max_iter": [100, 200, 400],
                   "max_leaf_nodes": [7, 15, 31, 63], "min_samples_leaf": [10, 20, 50, 100],
                   "l2_regularization": [0.0, 0.1, 1.0, 10.0]}},
    "random forest": {
        "linear": False, "combinacoes": 10,
        "fabrica": lambda p: RandomForestClassifier(random_state=SEMENTE, n_jobs=-1, **p),
        "espaco": {"n_estimators": [200, 400], "max_depth": [None, 8, 12, 20],
                   "min_samples_leaf": [2, 5, 10, 20, 50], "max_features": ["sqrt", 0.3, 0.5]}},
}
CRITERIO = ("menor log-loss na validação cruzada; a regressão logística vence "
            "se ficar a menos de um desvio da melhor")
SO_2023 = ["rede_taxa_ant"]   # a referência sem modelo

SAIDA_CURADORIA = RAIZ / "reports" / "curadoria_variaveis.csv"
SAIDA_BUSCA = RAIZ / "reports" / "busca_hiperparametros_rede.csv"
SAIDA_REGISTRO = RAIZ / "reports" / "modelo_rede_escolhido.json"
SAIDA_TESTE = RAIZ / "reports" / "avaliacao_teste_rede.csv"


# ---------------------------------------------------------------------------
# Preparação da base no grão da rede
# ---------------------------------------------------------------------------
def carregar_base(lake: Lake) -> tuple[pd.DataFrame, dict]:
    """Tabela analítica sem a rede privada e o desenho das variáveis."""
    abt = lake.ler("ml", "abt_alfabetizacao")
    lista = pd.read_csv(RAIZ / "reports" / "variaveis_modelagem.csv", index_col="variavel")
    entram = lista[lista["situacao"] == "entra"]
    desenho = {
        "categoricas": entram.index[entram["tipo"] == "categórica"].tolist(),
        "numericas": entram.index[entram["tipo"] == "numérica"].tolist(),
        "indicadores": {nome: variavel for variavel, nome
                        in entram["indicador_ausencia"].dropna().items()},
        "com_log": entram.index[entram["transformacao"].notna()].tolist(),
        "dicionario": pd.read_csv(RAIZ / "reports" / "dicionario_dados.csv",
                                  index_col="variavel"),
    }
    desenho["variaveis"] = desenho["numericas"] + desenho["categoricas"]
    # UF e região entram no modelo como ponto de partida, e não pela seleção (D-015)
    desenho["candidatas"] = [v for v in desenho["variaveis"] if v not in TERRITORIO]

    faltam = [v for v in desenho["variaveis"] + ["peso_aluno"] if v not in abt.columns]
    if faltam:
        sys.exit(f"Colunas ausentes na base: {faltam}")

    privada = abt["rede_nome"] == REDE_FORA
    colunas = ["particao", "id_municipio", "alvo", "peso_aluno"] + desenho["variaveis"]
    return abt.loc[~privada, colunas].copy(), desenho


def agregar_por_rede(abt: pd.DataFrame, desenho: dict) -> pd.DataFrame:
    """Uma linha por rede de cada município, com a taxa ponderada e a resposta.

    A taxa usa o peso amostral do INEP, o mesmo cálculo da taxa oficial, para
    que o alvo seja comparável ao indicador publicado.
    """
    invariantes = desenho["numericas"] + TERRITORIO
    variacao = (abt.groupby(CHAVE_REDE, observed=True)[invariantes]
                .nunique(dropna=False).max())
    if (variacao > 1).any():
        sys.exit(f"Variaveis que variam dentro da rede: {variacao[variacao > 1].to_dict()}")

    abt = abt.assign(peso_alfabetizados=abt["peso_aluno"] * abt["alvo"])
    redes = (abt.groupby(CHAVE_REDE, observed=True)
             .agg(alunos=("alvo", "size"), alfabetizados=("alvo", "sum"),
                  peso_total=("peso_aluno", "sum"),
                  peso_alfabetizados=("peso_alfabetizados", "sum"),
                  **{v: (v, "first") for v in invariantes})
             .reset_index())
    redes["taxa_real"] = 100 * redes["peso_alfabetizados"] / redes["peso_total"]
    redes["bateu_meta"] = (redes["taxa_real"] >= META_2024).astype(int)
    if redes["alunos"].sum() != len(abt):
        sys.exit("A base das redes nao soma os alunos da base.")
    return redes


def separar_redes(redes: pd.DataFrame, particoes: list, variaveis: list) -> tuple:
    """Variáveis, resposta, alunos e município das redes das partições pedidas."""
    d = redes[redes["particao"].isin(particoes)]
    return d[variaveis], d["bateu_meta"], d["alunos"], d["id_municipio"]


# ---------------------------------------------------------------------------
# Curadoria, etapa A: redundância, sem olhar a resposta
# ---------------------------------------------------------------------------
def grao(v: str) -> str:
    """De onde vem a medida: da rede, do município ou do estado."""
    return {"esc": "rede", "rede": "rede", "turma": "rede",
            "uf": "estado"}.get(v.split("_")[0], "município")


def vif(treino: pd.DataFrame, variaveis: list) -> pd.Series:
    """1 / (1 - R²) de cada variável explicada por todas as outras."""
    X = treino[variaveis].astype("float64")
    X = ((X - X.median()) / X.std()).fillna(0.0).to_numpy()
    resultado = {}
    for j, v in enumerate(variaveis):
        outras = np.column_stack([np.ones(len(X)), np.delete(X, j, axis=1)])
        coef, *_ = np.linalg.lstsq(outras, X[:, j], rcond=None)
        residuo = X[:, j] - outras @ coef
        r2 = 1 - residuo.var() / X[:, j].var()
        resultado[v] = np.inf if r2 >= 1 - 1e-9 else 1 / (1 - r2)
    return pd.Series(resultado)


def etapa_a(treino: pd.DataFrame, desenho: dict) -> tuple[list, list]:
    """Tira as variáveis redundantes e devolve as que ficam, com o registro das saídas."""
    dicionario, candidatas = desenho["dicionario"], [
        v for v in desenho["candidatas"] if v in desenho["numericas"]]

    def ano(v: str) -> int:
        """O ano mais recente citado na referência da variável."""
        texto = str(dicionario.loc[v, "referencia"]) if v in dicionario.index else ""
        anos = [int(a) for a in re.findall(r"(?:19|20)\d{2}", texto)]
        return max(anos) if anos else 0

    def derivada(v: str) -> list:
        """As variáveis do modelo que aparecem na fórmula desta."""
        formula = dicionario.loc[v, "formula"] if v in dicionario.index else ""
        formula = formula if isinstance(formula, str) else ""
        return [w for w in desenho["candidatas"] if w != v and re.search(rf"\b{w}\b", formula)]

    def ordem_de_saida(v: str) -> tuple:
        """Quanto maior, mais cedo a variável sai num empate, na ordem declarada."""
        return (len(derivada(v)) > 0, grao(v) != "rede", -ano(v), treino[v].isna().mean())

    saidas = []   # (variável, regra, número que justifica, observação)

    # Regras 1 e 2: qualidade da própria variável
    for v in list(candidatas):
        ausentes = treino[v].isna().mean()
        mais_comum = treino[v].value_counts(normalize=True).iloc[0]
        if ausentes > LIMITE_AUSENTES:
            saidas.append((v, "1. muitos ausentes", f"{100 * ausentes:.1f}% sem valor", ""))
            candidatas.remove(v)
        elif mais_comum >= LIMITE_CONSTANTE:
            saidas.append((v, "2. quase não varia",
                           f"{100 * mais_comum:.0f}% das redes no mesmo valor", ""))
            candidatas.remove(v)

    # Regra 3: VIF, retirando uma por vez até nenhuma passar do limite
    while True:
        valores = vif(treino, candidatas)
        acima = valores[valores > LIMITE_VIF]
        if acima.empty:
            break
        sai = max(acima.index, key=lambda v: (ordem_de_saida(v), acima[v]))
        base = derivada(sai)
        valor = "infinito" if np.isinf(acima[sai]) else f"VIF {acima[sai]:.1f}"
        saidas.append((sai, "3. explicada pelas outras (VIF)", valor,
                       ("é calculada a partir de " + " e ".join(base)) if base else ""))
        candidatas.remove(sai)

    # Regra 4: pares quase iguais
    while True:
        corr = treino[candidatas].corr(method="spearman").abs().to_numpy(copy=True)
        np.fill_diagonal(corr, 0)
        i, j = np.unravel_index(np.nanargmax(corr), corr.shape)
        if corr[i, j] <= LIMITE_CORRELACAO:
            break
        a, b = candidatas[i], candidatas[j]
        sai, fica = (a, b) if ordem_de_saida(a) >= ordem_de_saida(b) else (b, a)
        saidas.append((sai, "4. par quase igual", f"correlação {corr[i, j]:.2f}", f"fica {fica}"))
        candidatas.remove(sai)

    ficam = candidatas + [v for v in desenho["candidatas"] if v not in desenho["numericas"]]
    return ficam, saidas


# ---------------------------------------------------------------------------
# Curadoria, etapa B: seleção por estabilidade
# ---------------------------------------------------------------------------
def etapa_b(treino: pd.DataFrame, desenho: dict, variaveis_a: list) -> tuple:
    """Eliminação regressiva repetida em cinco rodadas com divisões diferentes.

    Em cada passo, mede quanto cada variável faz falta quando embaralhada e
    elimina a que faz menos. A rodada guarda o conjunto de menor log-loss, e
    entra no modelo quem aparece em pelo menos MINIMO_RODADAS conjuntos.
    """
    treino_X, treino_y = treino[desenho["variaveis"]], treino["bateu_meta"]

    def instrumento(variaveis: list) -> Pipeline:
        return montar_modelo(desenho, HistGradientBoostingClassifier(
            random_state=SEMENTE, early_stopping=False, **PARAMETROS_INSTRUMENTO),
            False, variaveis)

    def colunas_de(variavel: str, colunas: list) -> list:
        """As colunas preparadas que vêm de uma variável: ela, o indicador e o one-hot."""
        indicadores = [n for n, v in desenho["indicadores"].items() if v == variavel]
        return [c for c in colunas
                if c == variavel or c in indicadores or c.startswith(variavel + "_")]

    def passo(variaveis: list, dobras: list, gerador) -> tuple:
        """Log-loss de cada parte e quanto cada variável faz falta quando embaralhada."""
        perdas, falta = [], {v: [] for v in variaveis}
        for i_treino, i_medir in dobras:
            modelo = instrumento(variaveis).fit(treino_X.iloc[i_treino], treino_y.iloc[i_treino])
            preparada = modelo.named_steps["preparo"].transform(treino_X.iloc[i_medir])
            arvores, y_medir = modelo.named_steps["modelo"], treino_y.iloc[i_medir]

            def prever(X):
                return np.clip(arvores.predict_proba(X)[:, 1], 1e-6, 1 - 1e-6)

            base = log_loss(y_medir, prever(preparada))
            perdas.append(base)
            for v in variaveis:
                colunas = colunas_de(v, list(preparada.columns))
                for _ in range(REPETICOES_EMBARALHAMENTO):
                    embaralhada = preparada.copy()
                    embaralhada[colunas] = embaralhada[colunas].to_numpy()[
                        gerador.permutation(len(embaralhada))]
                    falta[v].append(log_loss(y_medir, prever(embaralhada)) - base)
        return np.array(perdas), pd.Series({v: np.mean(f) for v, f in falta.items()})

    def eliminar(semente: int) -> pd.DataFrame:
        """Uma rodada completa, com a sua própria divisão e o seu embaralhamento."""
        dobras = list(GroupKFold(n_splits=PARTES_VALIDACAO, shuffle=True, random_state=semente)
                      .split(treino_X, treino_y, groups=treino["id_municipio"]))
        gerador = np.random.default_rng(semente)
        atuais, curva = list(variaveis_a), []
        while atuais:
            perdas, falta = passo(atuais, dobras, gerador)
            curva.append({"variaveis": len(atuais), "log_loss": perdas.mean(),
                          "sai": falta.idxmin(), "conjunto": list(atuais)})
            atuais.remove(falta.idxmin())
        return pd.DataFrame(curva).set_index("variaveis").sort_index()

    inicio = time.time()
    rodadas = {}
    for r in range(RODADAS):
        rodadas[r + 1] = eliminar(SEMENTE + r)
        print(f"        rodada {r + 1} de {RODADAS}: {time.time() - inicio:.0f} s", flush=True)

    escolhidos = {r: curva.loc[curva["log_loss"].idxmin(), "conjunto"] for r, curva in rodadas.items()}
    frequencia = pd.Series(0, index=variaveis_a)
    for conjunto in escolhidos.values():
        frequencia[conjunto] += 1
    # até que passo cada variável sobreviveu, em média: maior = saiu mais tarde
    sobrevivencia = pd.DataFrame({r: {linha["sai"]: n for n, linha in curva.iterrows()}
                                  for r, curva in rodadas.items()}).mean(axis=1)
    selecionadas = [v for v in sobrevivencia.sort_values().index
                    if frequencia[v] >= MINIMO_RODADAS]
    return selecionadas, frequencia


def registrar_curadoria(saidas: list, variaveis_a: list, selecionadas: list,
                        frequencia: pd.Series) -> None:
    """Grava o que saiu em cada etapa e por quê."""
    linhas = [{"variavel": v, "etapa": "A", "situacao": "sai", "motivo": regra, "numero": valor}
              for v, regra, valor, _ in saidas]
    linhas += [{"variavel": v, "etapa": "B",
                "situacao": "fica" if v in selecionadas else "sai",
                "motivo": "" if v in selecionadas
                          else f"pouco estável: fica em menos de {MINIMO_RODADAS} das {RODADAS} rodadas",
                "numero": f"{int(frequencia[v])} de {RODADAS} rodadas"} for v in variaveis_a]
    pd.DataFrame(linhas).to_csv(SAIDA_CURADORIA, index=False, encoding="utf-8")


def ler_curadoria_salva(desenho: dict) -> list:
    """Recupera as variáveis selecionadas de uma execução anterior."""
    if not SAIDA_CURADORIA.exists():
        sys.exit(f"{SAIDA_CURADORIA.name} nao encontrado; rode sem --usar-curadoria-salva.")
    registro = pd.read_csv(SAIDA_CURADORIA)
    ficam = registro.loc[registro["situacao"] == "fica", "variavel"].tolist()
    ausentes = [v for v in ficam if v not in desenho["variaveis"]]
    if ausentes:
        sys.exit(f"A curadoria salva cita variaveis fora da base: {ausentes}")
    return ficam


# ---------------------------------------------------------------------------
# Modelos: validação cruzada, escolha e registro
# ---------------------------------------------------------------------------
def fazer_validador(X, y, municipio):
    """Devolve a função que valida um modelo nas cinco partes, cada rede pesando igual."""
    partes = list(GroupKFold(n_splits=PARTES_VALIDACAO, shuffle=True, random_state=SEMENTE)
                  .split(X, y, groups=municipio))

    def validar(modelo) -> dict:
        por_parte = []
        for i_treino, i_medir in partes:
            y_m = y.iloc[i_medir]
            if modelo is None:            # referência constante
                p = np.full(len(y_m), y.iloc[i_treino].mean())
            else:
                p = clone(modelo).fit(X.iloc[i_treino], y.iloc[i_treino]).predict_proba(
                    X.iloc[i_medir])[:, 1]
            por_parte.append(medir(y_m, p))
        d = pd.DataFrame(por_parte)
        return {"auc": d["auc"].mean(), "auc_desvio": d["auc"].std(),
                "log_loss": d["log_loss"].mean(), "log_loss_desvio": d["log_loss"].std(),
                "brier": d["brier"].mean()}

    return validar


def buscar_hiperparametros(desenho: dict, validar, variaveis: list) -> pd.DataFrame:
    """Busca aleatória nas três famílias, com as variáveis finais."""
    linhas = []
    for familia, f in FAMILIAS.items():
        inicio = time.time()
        for parametros in ParameterSampler(f["espaco"], n_iter=f["combinacoes"],
                                           random_state=SEMENTE):
            linhas.append({"familia": familia, "parametros": parametros,
                           **validar(montar_modelo(desenho, f["fabrica"](parametros),
                                                   f["linear"], variaveis))})
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
    return vencedora, (f"{vencedora} tem a menor log-loss e a regressao logistica ficou a "
                       f"{distancia:.4f}, acima da tolerancia de {tolerancia:.4f}")


def matriz_de_confusao(y, p, limiar: float = 0.5) -> tuple[pd.DataFrame, dict]:
    """Linhas: o que aconteceu. Colunas: o que o modelo previu. Mais a sensibilidade."""
    nao_cumpriu = (y == 0).to_numpy()
    previu_nao = p < limiar
    matriz = pd.DataFrame(
        [[int((~nao_cumpriu & ~previu_nao).sum()), int((~nao_cumpriu & previu_nao).sum())],
         [int((nao_cumpriu & ~previu_nao).sum()), int((nao_cumpriu & previu_nao).sum())]],
        index=["aconteceu: cumpriu", "aconteceu: nao cumpriu"],
        columns=["modelo: cumpre", "modelo: nao cumpre"])
    acertou_nao = int((previu_nao & nao_cumpriu).sum())
    medidas = {"sensibilidade": 100 * acertou_nao / nao_cumpriu.sum(),
               "precisao": 100 * acertou_nao / max(previu_nao.sum(), 1)}
    return matriz, medidas


# ---------------------------------------------------------------------------
# Orquestração
# ---------------------------------------------------------------------------
def main() -> int:
    # o console do Windows usa cp1252 por padrao e quebraria os acentos
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--usar-curadoria-salva", action="store_true",
                        help="reaproveita reports/curadoria_variaveis.csv")
    parser.add_argument("--usar-busca-salva", action="store_true",
                        help="reaproveita reports/busca_hiperparametros_rede.csv")
    args = parser.parse_args()

    cfg = carregar_config()
    inicio = datetime.now(timezone.utc)
    print(f"Modelagem no grao da rede iniciada em {inicio.isoformat()}")
    print(f"Lake: gs://{cfg['bucket_lake']}/   meta de 2024: {META_2024}%   semente: {SEMENTE}")
    print()

    print("[1/6] carregando a base e agregando por rede...", flush=True)
    lake = Lake(cfg)
    abt, desenho = carregar_base(lake)
    redes = agregar_por_rede(abt, desenho)
    treino = redes[redes["particao"] == "treino"]
    print(f"        {len(redes):,} redes em {redes['id_municipio'].nunique():,} municipios, "
          f"{int(redes['alunos'].sum()):,} alunos")
    print(f"        treino {len(treino):,} | validacao "
          f"{int((redes['particao'] == 'validacao').sum()):,} | teste "
          f"{int((redes['particao'] == 'teste').sum()):,} redes")

    print("[2/6] curadoria, etapa A: tirando a redundancia...", flush=True)
    variaveis_a, saidas = etapa_a(treino, desenho)
    print(f"        saem {len(saidas)} das {len(desenho['candidatas'])}; "
          f"ficam {len(variaveis_a)} para a etapa B")

    print("[3/6] curadoria, etapa B: selecao por estabilidade...", flush=True)
    if args.usar_curadoria_salva:
        selecionadas = ler_curadoria_salva(desenho)
        frequencia = pd.Series(RODADAS, index=variaveis_a)
        print(f"        {len(selecionadas)} variaveis lidas de {SAIDA_CURADORIA.name}")
    else:
        selecionadas, frequencia = etapa_b(treino, desenho, variaveis_a)
        registrar_curadoria(saidas, variaveis_a, selecionadas, frequencia)
        print(f"        ficam {len(selecionadas)} variaveis; registro em {SAIDA_CURADORIA.name}")

    variaveis_finais = selecionadas + TERRITORIO
    X_treino, y_treino, _, mun_treino = separar_redes(redes, ["treino"], desenho["variaveis"])
    X_validacao, y_validacao, alunos_validacao, _ = separar_redes(
        redes, ["validacao"], desenho["variaveis"])
    X_final, y_final, _, _ = separar_redes(redes, ["treino", "validacao"], desenho["variaveis"])
    X_teste, y_teste, alunos_teste, mun_teste = separar_redes(
        redes, ["teste"], desenho["variaveis"])
    validar = fazer_validador(X_treino, y_treino, mun_treino)

    print("[4/6] buscando hiperparametros nas tres familias...", flush=True)
    if args.usar_busca_salva and SAIDA_BUSCA.exists():
        busca = pd.read_csv(SAIDA_BUSCA)
        busca["parametros"] = busca["parametros"].map(json.loads)
        print(f"        {len(busca)} combinacoes lidas de {SAIDA_BUSCA.name}")
    else:
        busca = buscar_hiperparametros(desenho, validar, variaveis_finais)
        busca.assign(parametros=busca["parametros"].map(json.dumps)).to_csv(
            SAIDA_BUSCA, index=False, encoding="utf-8")
        print(f"        {len(busca)} combinacoes registradas em {SAIDA_BUSCA.name}")
    melhores = (busca.loc[busca.groupby("familia")["log_loss"].idxmin()]
                .set_index("familia").sort_values("log_loss"))

    print("[5/6] escolhendo a familia e confirmando na validacao...", flush=True)
    escolhida, razao = escolher_familia(melhores)

    def fabricar(familia: str, variaveis: list | None = None) -> Pipeline:
        f = FAMILIAS[familia]
        return montar_modelo(desenho, f["fabrica"](melhores.loc[familia, "parametros"]),
                             f["linear"], variaveis if variaveis is not None else variaveis_finais)

    sem_territorio_cv = validar(fabricar(escolhida, selecionadas))
    candidatos = {f: fabricar(f).fit(X_treino, y_treino) for f in melhores.index}
    candidatos["sem território"] = fabricar(escolhida, selecionadas).fit(X_treino, y_treino)
    candidatos["só a taxa de 2023"] = montar_modelo(
        desenho, LogisticRegression(max_iter=3000), True, SO_2023).fit(X_treino, y_treino)
    estaveis = (alunos_validacao >= MIN_ALUNOS_ESTAVEL).to_numpy()
    validacao = pd.DataFrame({
        nome: {**medir(y_validacao, m.predict_proba(X_validacao)[:, 1]),
               "auc_redes_20_alunos_ou_mais": roc_auc_score(
                   y_validacao[estaveis], m.predict_proba(X_validacao)[estaveis, 1])}
        for nome, m in candidatos.items()}).T.astype(float).sort_values("auc", ascending=False)
    print(f"        {escolhida}: AUC {validacao.loc[escolhida, 'auc']:.4f} na validacao; "
          f"o territorio acrescenta "
          f"{melhores.loc[escolhida, 'auc'] - sem_territorio_cv['auc']:+.4f} de AUC")

    registro = {
        "alvo": f"a rede bateu a meta nacional de 2024 ({META_2024}%)",
        "familia": escolhida, "parametros": melhores.loc[escolhida, "parametros"],
        "criterio": CRITERIO,
        "selecao_de_variaveis": "etapa A (redundância) e etapa B (seleção por estabilidade)",
        "validacao_cruzada": {k: round(float(melhores.loc[escolhida, k]), 5)
                              for k in ["auc", "auc_desvio", "log_loss",
                                        "log_loss_desvio", "brier"]},
        "validacao": {k: round(float(validacao.loc[escolhida, k]), 5)
                      for k in ["auc", "log_loss", "brier", "auc_redes_20_alunos_ou_mais"]},
        "semente": SEMENTE, "variaveis": variaveis_finais,
    }
    SAIDA_REGISTRO.write_text(json.dumps(registro, ensure_ascii=False, indent=2),
                              encoding="utf-8")

    print("[6/6] medindo o modelo final na particao de teste...", flush=True)
    finais = {"modelo final": fabricar(escolhida).fit(X_final, y_final),
              "sem território": fabricar(escolhida, selecionadas).fit(X_final, y_final),
              "só a taxa de 2023": montar_modelo(desenho, LogisticRegression(max_iter=3000),
                                                 True, SO_2023).fit(X_final, y_final)}
    prob = {nome: m.predict_proba(X_teste)[:, 1] for nome, m in finais.items()}
    prob["constante"] = np.full(len(y_teste), y_final.mean())
    estaveis_teste = (alunos_teste >= MIN_ALUNOS_ESTAVEL).to_numpy()
    ordem = ["constante", "só a taxa de 2023", "sem território", "modelo final"]
    teste = pd.DataFrame({
        nome: {**medir(y_teste, prob[nome]),
               "auc_redes_20_alunos_ou_mais": roc_auc_score(y_teste[estaveis_teste],
                                                            prob[nome][estaveis_teste])}
        for nome in ordem}).T.astype(float)
    teste.round(5).to_csv(SAIDA_TESTE, encoding="utf-8")
    matriz, medidas_teste = matriz_de_confusao(y_teste, prob["modelo final"])
    print(f"        AUC {teste.loc['modelo final', 'auc']:.4f} em {mun_teste.nunique():,} "
          f"municipios que nenhuma etapa viu")

    duracao = (datetime.now(timezone.utc) - inicio).total_seconds() / 60
    print()
    print("=" * 68)
    print("RESUMO DA EXECUCAO")
    print(f"  Redes:                {len(redes):,} em "
          f"{redes['id_municipio'].nunique():,} municipios")
    print(f"  Curadoria:            {len(desenho['candidatas'])} -> {len(variaveis_a)} "
          f"(etapa A) -> {len(selecionadas)} (etapa B) + {len(TERRITORIO)} de territorio")
    print(f"  Familia escolhida:    {escolhida}")
    print(f"  Criterio:             {razao}")
    print(f"  Validacao cruzada:    AUC {melhores.loc[escolhida, 'auc']:.4f}   "
          f"log-loss {melhores.loc[escolhida, 'log_loss']:.4f}")
    print(f"  Validacao:            AUC {validacao.loc[escolhida, 'auc']:.4f}")
    print(f"  Teste:                AUC {teste.loc['modelo final', 'auc']:.4f}   "
          f"log-loss {teste.loc['modelo final', 'log_loss']:.4f}   "
          f"sensibilidade {medidas_teste['sensibilidade']:.1f}%")
    print(f"  Referencia 2023:      AUC {teste.loc['só a taxa de 2023', 'auc']:.4f}")
    print()
    print("  MATRIZ DE CONFUSAO NO TESTE")
    for linha in matriz.to_string().splitlines():
        print(f"    {linha}")
    print()
    print(f"  Registro:             {SAIDA_REGISTRO.relative_to(RAIZ)}")
    print(f"  Curadoria:            {SAIDA_CURADORIA.relative_to(RAIZ)}")
    print(f"  Avaliacao:            {SAIDA_TESTE.relative_to(RAIZ)}")
    print(f"  Duracao:              {duracao:.1f} min")
    print("  Status final:         SUCESSO")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    sys.exit(main())

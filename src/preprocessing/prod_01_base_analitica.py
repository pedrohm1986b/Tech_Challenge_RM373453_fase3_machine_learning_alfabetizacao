# -*- coding: utf-8 -*-
"""Construção da tabela analítica (ABT) para a modelagem de alfabetização.

Código promovido do notebook `notebooks/desenv_01_base_analitica.ipynb`, onde
o desenvolvimento está documentado célula a célula, com os conceitos aplicados
e as evidências de execução.

O que este script faz:
1. lê a configuração em `config/config.json` (ver `config/config.example.json`);
2. verifica o contrato do data lake construído na fase anterior, sem reexecutar
   aquela pipeline (decisão D-002);
3. isola a população modelável: alunos presentes na avaliação, únicos com
   variável resposta observável (decisão D-001);
4. monta o contexto defasado em três níveis, sempre anterior ao ciclo do aluno
   (decisão D-003): a rede que o atende, o município e o benchmark estadual
   da mesma rede;
5. acrescenta o porte do ciclo corrente, informação prévia à avaliação porque
   vem do cadastro escolar;
6. integra tudo, audita a tabela contra vazamento de dados e separa treino,
   validação e teste por município;
7. grava a tabela analítica em `ml/` no data lake e exporta o dicionário de
   variáveis em `reports/`.

Execução:
    python src/preprocessing/prod_01_base_analitica.py
    (no Windows, se o comando python não for reconhecido, use o launcher py:
    py src/preprocessing/prod_01_base_analitica.py)

Propriedades:
- Replicabilidade: a partição usa semente fixa; a mesma execução produz a
  mesma separação entre treino, validação e teste.
- Verificações executáveis: contrato do lake, contagem preservada nos joins,
  auditoria contra vazamento, integridade da partição e reconciliação da
  gravação interrompem a execução com código de saída 1 em caso de violação.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pydata_google_auth
from google.cloud import storage
from sklearn.model_selection import GroupShuffleSplit

# ---------------------------------------------------------------------------
# Constantes do desenho da base
# ---------------------------------------------------------------------------
CICLO_ALVO = 2024
CICLO_ANTERIOR = CICLO_ALVO - 1
SEMENTE = 42

# Redes de ensino no grão do aluno que possuem contexto próprio
REDES_COM_CONTEXTO = ["2", "3"]  # estadual e municipal

# Contrato exigido da fase anterior
CONTRATO = {
    ("silver", "alunos"): ["ano", "id_municipio", "rede_nome", "presente",
                           "alfabetizado", "proficiencia", "peso_aluno"],
    ("silver", "municipio"): ["ano", "id_municipio", "rede", "rede_nome",
                              "sigla_uf", "nome_regiao",
                              "taxa_alfabetizacao", "media_portugues"],
    ("gold", "indicador_municipio"): ["ano", "id_municipio", "taxa",
                                      "percentual_participacao",
                                      "taxa_ajustada", "alunos_presentes",
                                      "meta_taxa", "origem"],
}

# Colunas que jamais podem virar variável explicativa
PROIBIDAS = {
    "proficiencia": "a variável resposta é derivada dela (nota >= 743)",
    "alfabetizado": "é a própria variável resposta, em outro formato",
    "presente": "constante na população modelada",
    "peso_aluno": "metadado amostral, reservado à ponderação",
}

DESCRICOES = {
    "ano": "ciclo da avaliação (chave)",
    "id_municipio": "código IBGE do município (chave)",
    "rede_nome": "rede de ensino que atende o aluno",
    "rede_taxa_ant": "taxa de alfabetização da rede do aluno, no município, no ciclo anterior",
    "rede_media_portugues_ant": "proficiência média em português da rede do aluno no ciclo anterior",
    "uf_rede_taxa_ant": "mediana da taxa da mesma rede entre os municípios da UF (benchmark)",
    "rede_vs_uf": "distância entre a taxa da rede do aluno e o benchmark estadual da rede",
    "rede_vs_municipio": "diferença entre a taxa da rede do aluno e a do município no ciclo anterior",
    "mun_taxa_ant": "taxa de alfabetização do município (rede pública) no ciclo anterior",
    "mun_participacao_ant": "percentual de participação na avaliação anterior",
    "mun_taxa_ajustada_ant": "taxa anterior com ausentes contados como não alfabetizados",
    "mun_alunos_ant": "alunos presentes no município no ciclo anterior (porte defasado)",
    "sigla_uf": "unidade da federação",
    "nome_regiao": "região do país",
    "mun_meta_ciclo": "meta pactuada para o ciclo corrente (informação prévia)",
    "mun_gap_meta": "distância entre a meta do ciclo e a taxa do ciclo anterior",
    "rede_porte_atual": "alunos avaliáveis na rede do aluno, no município, no ciclo corrente",
    "mun_porte_atual": "alunos avaliáveis no município no ciclo corrente",
    "rede_peso_no_municipio": "fração dos alunos do município atendida pela rede do aluno",
    "alvo": "variável resposta: 1 se alfabetizado, 0 caso contrário",
    "peso_aluno": "peso amostral do INEP (ponderação, não é atributo)",
    "particao": "conjunto de destino: treino, validacao ou teste",
}

# Relações determinísticas entre variáveis, para a seleção na etapa seguinte
RELACOES = {
    "rede_vs_municipio": "= rede_taxa_ant - mun_taxa_ant",
    "rede_vs_uf": "= rede_taxa_ant - uf_rede_taxa_ant",
    "mun_gap_meta": "= mun_meta_ciclo - mun_taxa_ant",
    "rede_peso_no_municipio": "= rede_porte_atual / mun_porte_atual",
    "mun_taxa_ajustada_ant": "= mun_taxa_ant * mun_participacao_ant / 100",
}

ESCOPOS = ["https://www.googleapis.com/auth/cloud-platform"]
RAIZ = Path(__file__).resolve().parents[2]


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
    """Leitura das camadas do lake e gravação da tabela analítica."""

    def __init__(self, cfg: dict):
        self.bucket = cfg["bucket_lake"]
        self.credenciais = pydata_google_auth.get_user_credentials(ESCOPOS)
        self.credenciais = self.credenciais.with_quota_project(
            cfg["projeto_gcp"])
        self.cliente = storage.Client(project=cfg["projeto_gcp"],
                                      credentials=self.credenciais)

    def garantir_credencial(self) -> None:
        """Renova o token expirado e limpa o cache do gcsfs."""
        import google.auth.transport.requests
        import gcsfs
        if not self.credenciais.valid:
            self.credenciais.refresh(google.auth.transport.requests.Request())
            gcsfs.GCSFileSystem.clear_instance_cache()

    def ultima_particao(self, area: str, tabela: str) -> str | None:
        particoes = sorted({
            b.name.split("/")[2]
            for b in self.cliente.list_blobs(self.bucket,
                                             prefix=f"{area}/{tabela}/")
            if len(b.name.split("/")) > 2
        })
        return particoes[-1] if particoes else None

    def ler(self, area: str, tabela: str, **kwargs) -> pd.DataFrame:
        self.garantir_credencial()
        particao = self.ultima_particao(area, tabela)
        if particao is None:
            sys.exit(
                f"Tabela '{tabela}' nao encontrada em {area}/ "
                f"(gs://{self.bucket}/{area}/{tabela}/).\n"
                "Execute antes a pipeline da fase anterior (repositorio "
                "Tech_Challenge_RM373453_pipeline_alfabetizacao)."
            )
        caminho = (f"gs://{self.bucket}/{area}/{tabela}/{particao}/"
                   f"{tabela}.parquet")
        return pd.read_parquet(caminho,
                               storage_options={"token": self.credenciais},
                               **kwargs)

    def gravar_ml(self, df: pd.DataFrame, tabela: str) -> dict:
        self.garantir_credencial()
        momento = datetime.now(timezone.utc)
        df = df.copy()
        df["_processing_timestamp"] = momento.isoformat()
        destino = (f"gs://{self.bucket}/ml/{tabela}/"
                   f"data_processamento={momento:%Y-%m-%d}/{tabela}.parquet")
        df.to_parquet(destino, index=False,
                      storage_options={"token": self.credenciais})
        return {"destino": destino, "linhas": len(df)}


# ---------------------------------------------------------------------------
# Etapas da construção
# ---------------------------------------------------------------------------
def verificar_contrato(lake: Lake) -> None:
    """Confere que o lake da fase anterior tem o que este projeto exige."""
    pendencias = []
    for (area, tabela), colunas in CONTRATO.items():
        particao = lake.ultima_particao(area, tabela)
        if particao is None:
            pendencias.append(f"{area}/{tabela} ausente")
            continue
        disponiveis = set(lake.ler(area, tabela).columns)
        faltantes = [c for c in colunas if c not in disponiveis]
        if faltantes:
            pendencias.append(f"{area}/{tabela}: faltam {faltantes}")
    if pendencias:
        sys.exit(
            "Pre-requisitos nao atendidos: " + "; ".join(pendencias) + ".\n"
            "Execute a pipeline da fase anterior antes de prosseguir."
        )


def isolar_populacao(df_alunos: pd.DataFrame) -> pd.DataFrame:
    """Alunos presentes: os únicos com variável resposta observável (D-001)."""
    df = df_alunos[df_alunos["presente"]].copy()
    df["alvo"] = (df["alfabetizado"].astype(str) == "1").astype(int)
    return df


def montar_contexto_rede(mun: pd.DataFrame) -> pd.DataFrame:
    """Retrato da rede do aluno no ciclo anterior, com benchmark estadual."""
    ctx = mun.loc[
        (mun["ano"] == CICLO_ANTERIOR)
        & (mun["rede"].astype(str).isin(REDES_COM_CONTEXTO)),
        ["id_municipio", "rede_nome", "taxa_alfabetizacao", "media_portugues"],
    ].rename(columns={"taxa_alfabetizacao": "rede_taxa_ant",
                      "media_portugues": "rede_media_portugues_ant"})

    uf = (mun.loc[mun["ano"] == CICLO_ANTERIOR, ["id_municipio", "sigla_uf"]]
          .drop_duplicates())
    ctx = ctx.merge(uf, on="id_municipio", how="left")

    benchmark = (ctx.groupby(["sigla_uf", "rede_nome"], observed=True)
                 ["rede_taxa_ant"].median()
                 .rename("uf_rede_taxa_ant").reset_index())
    ctx = ctx.merge(benchmark, on=["sigla_uf", "rede_nome"], how="left")
    ctx["rede_vs_uf"] = ctx["rede_taxa_ant"] - ctx["uf_rede_taxa_ant"]
    return ctx.drop(columns="sigla_uf")


def montar_contexto_municipio(gold: pd.DataFrame,
                              mun: pd.DataFrame) -> pd.DataFrame:
    """Retrato do município no ciclo anterior e meta pactuada para o corrente."""
    ctx = gold.loc[
        (gold["ano"] == CICLO_ANTERIOR) & (gold["origem"] == "oficial_inep"),
        ["id_municipio", "taxa", "percentual_participacao", "taxa_ajustada",
         "alunos_presentes"],
    ].rename(columns={"taxa": "mun_taxa_ant",
                      "percentual_participacao": "mun_participacao_ant",
                      "taxa_ajustada": "mun_taxa_ajustada_ant",
                      "alunos_presentes": "mun_alunos_ant"})

    territorio = mun.loc[
        (mun["ano"] == CICLO_ANTERIOR) & (mun["rede"].astype(str) == "5"),
        ["id_municipio", "sigla_uf", "nome_regiao"]]
    ctx = ctx.merge(territorio, on="id_municipio", how="left")

    metas = gold.loc[
        (gold["ano"] == CICLO_ALVO) & (gold["origem"] == "oficial_inep"),
        ["id_municipio", "meta_taxa"]].rename(
            columns={"meta_taxa": "mun_meta_ciclo"})
    ctx = ctx.merge(metas, on="id_municipio", how="left")
    ctx["mun_gap_meta"] = ctx["mun_meta_ciclo"] - ctx["mun_taxa_ant"]
    return ctx


def montar_porte(df_alunos: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Porte do ciclo corrente: alunos avaliáveis (cadastro, informação prévia)."""
    cadastro = df_alunos[df_alunos["ano"] == CICLO_ALVO]
    porte_rede = (cadastro.groupby(["id_municipio", "rede_nome"], observed=True)
                  .size().rename("rede_porte_atual").reset_index())
    porte_mun = (cadastro.groupby("id_municipio", observed=True)
                 .size().rename("mun_porte_atual").reset_index())
    return porte_rede, porte_mun


def integrar(populacao: pd.DataFrame, ctx_rede: pd.DataFrame,
             ctx_mun: pd.DataFrame, porte_rede: pd.DataFrame,
             porte_mun: pd.DataFrame) -> pd.DataFrame:
    """Une aluno, rede, município e porte, preservando a contagem de linhas."""
    abt = populacao[populacao["ano"] == CICLO_ALVO].copy()
    antes = len(abt)
    for tabela, chaves in [(ctx_rede, ["id_municipio", "rede_nome"]),
                           (ctx_mun, ["id_municipio"]),
                           (porte_rede, ["id_municipio", "rede_nome"]),
                           (porte_mun, ["id_municipio"])]:
        abt = abt.merge(tabela, on=chaves, how="left")
        if len(abt) != antes:
            sys.exit(f"Join alterou a contagem de linhas: {antes:,} -> "
                     f"{len(abt):,}. Verifique chaves duplicadas.")
    abt["rede_vs_municipio"] = abt["rede_taxa_ant"] - abt["mun_taxa_ant"]
    abt["rede_peso_no_municipio"] = (abt["rede_porte_atual"]
                                     / abt["mun_porte_atual"])
    return abt


def auditar(abt: pd.DataFrame, features: list) -> None:
    """Auditoria contra vazamento: colunas proibidas e correlações extremas."""
    invasoras = [c for c in features if c in PROIBIDAS]
    if invasoras:
        sys.exit(f"Auditoria reprovada: variaveis proibidas no modelo: "
                 f"{invasoras}.")

    numericas = [c for c in features if pd.api.types.is_numeric_dtype(abt[c])]
    correl = abt[numericas + ["alvo"]].corr()["alvo"].drop("alvo")
    extremas = correl[correl.abs() > 0.9]
    if len(extremas):
        sys.exit(f"Auditoria reprovada: correlacao suspeita com a resposta em "
                 f"{list(extremas.index)}.")


def particionar(abt: pd.DataFrame) -> pd.DataFrame:
    """Separa treino, validação e teste por município (D-001, terceira defesa)."""
    grupos = abt["id_municipio"]
    divisor = GroupShuffleSplit(n_splits=1, train_size=0.6,
                                random_state=SEMENTE)
    _, idx_resto = next(divisor.split(abt, groups=grupos))
    resto = abt.iloc[idx_resto]
    divisor2 = GroupShuffleSplit(n_splits=1, train_size=0.5,
                                 random_state=SEMENTE)
    idx_val, _ = next(divisor2.split(resto, groups=resto["id_municipio"]))

    abt = abt.copy()
    abt["particao"] = "treino"
    abt.iloc[idx_resto, abt.columns.get_loc("particao")] = "teste"
    abt.iloc[idx_resto[idx_val], abt.columns.get_loc("particao")] = "validacao"

    atravessam = (abt.groupby("id_municipio")["particao"].nunique() > 1).sum()
    if atravessam:
        sys.exit(f"Particao reprovada: {atravessam} municipios em mais de uma "
                 "particao.")
    return abt


# Colunas de controle da gravação, que não descrevem o dado analítico.
# A partição reaparece como coluna quando o arquivo é relido do lake.
METADADOS = ["_processing_timestamp", "data_processamento"]


def exportar_dicionario(df_abt: pd.DataFrame) -> Path:
    """Gera o dicionário de variáveis com as relações determinísticas."""
    variaveis = [c for c in df_abt.columns if c not in METADADOS]
    sem_descricao = [v for v in variaveis if v not in DESCRICOES]
    if sem_descricao:
        sys.exit(f"Dicionario desatualizado: sem descricao para "
                 f"{sem_descricao}.")

    dicionario = pd.DataFrame({"variavel": variaveis})
    dicionario["descricao"] = dicionario["variavel"].map(DESCRICOES)
    dicionario["derivada_de"] = dicionario["variavel"].map(RELACOES).fillna("")
    dicionario["tipo"] = [str(df_abt[v].dtype) for v in dicionario["variavel"]]
    dicionario["% preenchido"] = [
        round(100 * df_abt[v].notna().mean(), 1)
        for v in dicionario["variavel"]]

    destino = RAIZ / "reports" / "dicionario_abt.csv"
    dicionario.to_csv(destino, index=False, encoding="utf-8")
    return destino


# ---------------------------------------------------------------------------
# Orquestração
# ---------------------------------------------------------------------------
def main() -> int:
    cfg = carregar_config()
    lake = Lake(cfg)
    inicio = datetime.now(timezone.utc)

    print(f"Construcao da tabela analitica iniciada em {inicio.isoformat()}")
    print(f"Lake: gs://{cfg['bucket_lake']}/   ciclo alvo: {CICLO_ALVO}")
    print()

    print("[1/6] verificando o contrato do lake...", flush=True)
    verificar_contrato(lake)
    print(f"        {len(CONTRATO)} tabelas conferidas")

    print("[2/6] isolando a populacao modelavel...", flush=True)
    df_alunos = lake.ler("silver", "alunos",
                         columns=["ano", "id_municipio", "rede_nome",
                                  "presente", "alfabetizado", "proficiencia",
                                  "peso_aluno"])
    populacao = isolar_populacao(df_alunos)
    print(f"        {len(populacao):,} alunos presentes de "
          f"{len(df_alunos):,} avaliaveis")

    print("[3/6] montando o contexto defasado...", flush=True)
    mun = lake.ler("silver", "municipio",
                   columns=["ano", "id_municipio", "rede", "rede_nome",
                            "taxa_alfabetizacao", "media_portugues",
                            "sigla_uf", "nome_regiao"])
    gold = lake.ler("gold", "indicador_municipio")
    ctx_rede = montar_contexto_rede(mun)
    ctx_mun = montar_contexto_municipio(gold, mun)
    porte_rede, porte_mun = montar_porte(df_alunos)
    print(f"        {len(ctx_rede):,} retratos de rede, "
          f"{len(ctx_mun):,} de municipio")

    print("[4/6] integrando e auditando...", flush=True)
    abt = integrar(populacao, ctx_rede, ctx_mun, porte_rede, porte_mun)
    features = (["rede_nome"]
                + [c for c in ctx_rede.columns
                   if c not in ("id_municipio", "rede_nome")]
                + [c for c in ctx_mun.columns if c != "id_municipio"]
                + ["rede_porte_atual", "mun_porte_atual",
                   "rede_vs_municipio", "rede_peso_no_municipio"])
    auditar(abt, features)
    print(f"        {len(abt):,} observacoes, {len(features)} variaveis, "
          "auditoria aprovada")

    print("[5/6] separando treino, validacao e teste...", flush=True)
    abt = particionar(abt)
    resumo_particao = abt["particao"].value_counts().to_dict()
    print(f"        {resumo_particao}")

    print("[6/6] gravando e reconciliando...", flush=True)
    colunas = (["ano", "id_municipio"] + features
               + ["alvo", "peso_aluno", "particao"])
    entrega = lake.gravar_ml(abt[colunas], "abt_alfabetizacao")
    relido = pd.read_parquet(entrega["destino"],
                             storage_options={"token": lake.credenciais})
    reconciliacao = "OK" if len(relido) == entrega["linhas"] else "DIVERGIU"
    caminho_dicionario = exportar_dicionario(relido)
    print(f"        {entrega['linhas']:,} linhas gravadas, "
          f"reconciliacao {reconciliacao}")

    duracao = (datetime.now(timezone.utc) - inicio).total_seconds() / 60
    print()
    print("=" * 62)
    print("RESUMO DA EXECUCAO")
    print(f"  Tabela analitica:     {entrega['linhas']:,} linhas  "
          f"{reconciliacao}")
    print(f"  Variaveis:            {len(features)} explicativas")
    print(f"  Particoes:            {resumo_particao}")
    print(f"  Destino:              {entrega['destino']}")
    print(f"  Dicionario:           {caminho_dicionario.relative_to(RAIZ)}")
    print(f"  Duracao:              {duracao:.1f} min")
    status = "FALHA" if reconciliacao != "OK" else "SUCESSO"
    print(f"  Status final:         {status}")
    print("=" * 62)
    return 1 if status == "FALHA" else 0


if __name__ == "__main__":
    sys.exit(main())

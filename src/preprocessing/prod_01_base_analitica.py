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
4. monta o contexto defasado da rede que atende o aluno, do seu município e do
   benchmark estadual da mesma rede (decisão D-003), e acrescenta o porte do
   cadastro escolar, informação anterior à prova (decisão D-004);
5. enriquece a base com fontes públicas externas (Censo Escolar, PIB municipal,
   Atlas do Desenvolvimento Humano, Atlas da Violência e Sistema de Informação
   sobre Mortalidade), materializadas no lake para reuso (decisão D-005);
6. integra tudo, audita a tabela contra vazamento de dados e separa treino,
   validação e teste por município;
7. grava a tabela analítica em `ml/` e publica o dicionário de dados em
   `reports/`.

Execução:
    python src/preprocessing/prod_01_base_analitica.py
    (no Windows, se o comando python não for reconhecido, use o launcher py:
    py src/preprocessing/prod_01_base_analitica.py)

    --refazer-externas  reconsulta as fontes públicas, ignorando o cache

Propriedades:
- Replicabilidade: a partição usa semente fixa; a mesma execução produz a
  mesma separação entre treino, validação e teste.
- Verificações executáveis: contrato do lake, contagem preservada nos joins,
  auditoria contra vazamento, integridade da partição, consistência do
  dicionário e reconciliação da gravação interrompem a execução com código de
  saída 1 em caso de violação.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pandas_gbq
import pydata_google_auth
from google.cloud import storage
from sklearn.model_selection import GroupShuffleSplit

# ---------------------------------------------------------------------------
# Desenho da base
# ---------------------------------------------------------------------------
CICLO_ALVO = 2024
CICLO_ANTERIOR = CICLO_ALVO - 1
ANO_PIB = CICLO_ALVO - 3        # o PIB municipal tem cerca de dois anos de defasagem
ANO_VIOLENCIA = 2019            # último ciclo disponível no SIM
SEMENTE = 42

REDES_COM_CONTEXTO = ["2", "3"]  # estadual e municipal, no código da fonte

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

PROIBIDAS = {
    "proficiencia": "a variável resposta é derivada dela (nota >= 743)",
    "alfabetizado": "é a própria variável resposta, em outro formato",
    "presente": "constante na população modelada",
    "peso_aluno": "metadado amostral, reservado à ponderação",
}

# Variáveis do ciclo corrente admitidas por serem anteriores à prova
EX_ANTE_DO_CICLO = {"rede_porte_atual", "mun_porte_atual",
                    "rede_peso_no_municipio", "mun_meta_ciclo", "mun_gap_meta"}
DERIVADAS_DE_CONTEXTO = {"rede_vs_municipio", "rede_vs_uf",
                         "esc_salas_por_aluno", "esc_pct_transporte"}
CATEGORICAS = {"rede_nome", "sigla_uf", "nome_regiao"}

FAMILIAS = {
    "aluno": ["rede_nome"],
    "desempenho anterior": [
        "rede_taxa_ant", "rede_media_portugues_ant", "uf_rede_taxa_ant",
        "rede_vs_uf", "rede_vs_municipio", "mun_taxa_ant",
        "mun_participacao_ant", "mun_taxa_ajustada_ant", "mun_alunos_ant",
        "mun_meta_ciclo", "mun_gap_meta"],
    "território": ["sigla_uf", "nome_regiao"],
    "porte e oferta": [
        "rede_porte_atual", "mun_porte_atual", "rede_peso_no_municipio",
        "esc_quantidade", "esc_salas_por_aluno", "turma_media_alunos"],
    "infraestrutura escolar": [
        "esc_pct_rural", "esc_pct_agua_rede", "esc_pct_esgoto_rede",
        "esc_pct_energia_rede", "esc_pct_internet", "esc_pct_biblioteca",
        "esc_pct_lab_informatica", "esc_pct_quadra", "esc_pct_alimentacao",
        "esc_pct_transporte"],
    "profissionais de apoio": [
        "esc_pct_coordenador", "esc_pct_psicologo",
        "esc_pct_assistente_social"],
    "contexto socioeconômico": [
        "mun_pib_per_capita", "mun_pct_agropecuaria", "mun_pct_servicos",
        "mun_populacao", "mun_idhm", "mun_idhm_educacao", "mun_idhm_renda",
        "mun_renda_per_capita", "mun_gini", "mun_analfabetismo_adulto",
        "mun_expectativa_estudo", "mun_ivs", "mun_ivs_infraestrutura",
        "mun_ivs_capital_humano", "mun_taxa_homicidio"],
}
FEATURES = [v for grupo in FAMILIAS.values() for v in grupo]

ESCOPOS = ["https://www.googleapis.com/auth/cloud-platform"]
RAIZ = Path(__file__).resolve().parents[2]
METADADOS_GRAVACAO = ["_processing_timestamp", "data_processamento"]


# Metadados de cada variável: bloco temático, fonte, referência temporal,
# natureza (medida direta, derivada de outras, ou aproximação de um conceito
# que não se mede diretamente) e a fórmula, quando houver.
METADADOS_VARIAVEIS = [
    # (variavel, bloco, fonte, referencia, natureza, descricao, formula)
    ("ano", "chave", "Silver, camada de alunos", str(CICLO_ALVO), "direta",
     "ciclo da avaliação", ""),
    ("id_municipio", "chave", "Silver, camada de alunos", str(CICLO_ALVO), "direta",
     "código IBGE do município", ""),
    ("alvo", "resposta", "Silver, camada de alunos", str(CICLO_ALVO), "derivada",
     "1 se o aluno foi classificado como alfabetizado", "proficiência >= 743"),
    ("peso_aluno", "ponderação", "Silver, camada de alunos", str(CICLO_ALVO), "direta",
     "peso amostral calibrado pelo INEP, reservado à ponderação", ""),
    ("particao", "controle", "construída neste notebook", str(CICLO_ALVO), "derivada",
     "conjunto de destino: treino, validação ou teste", "sorteio por município"),

    ("rede_nome", "aluno", "Silver, camada de alunos", str(CICLO_ALVO), "direta",
     "rede de ensino que atende o aluno", ""),

    ("rede_taxa_ant", "desempenho anterior", "Silver, indicador municipal por rede",
     str(CICLO_ANTERIOR), "direta", "taxa de alfabetização da rede do aluno no município", ""),
    ("rede_media_portugues_ant", "desempenho anterior", "Silver, indicador municipal por rede",
     str(CICLO_ANTERIOR), "direta", "proficiência média em português da rede", ""),
    ("uf_rede_taxa_ant", "desempenho anterior", "Silver, indicador municipal por rede",
     str(CICLO_ANTERIOR), "derivada", "benchmark: mediana da mesma rede entre os municípios da UF",
     "mediana por UF e rede"),
    ("rede_vs_uf", "desempenho anterior", "Silver, indicador municipal por rede",
     str(CICLO_ANTERIOR), "derivada", "posição da rede diante do padrão do seu estado",
     "rede_taxa_ant - uf_rede_taxa_ant"),
    ("rede_vs_municipio", "desempenho anterior", "Silver, indicador municipal por rede",
     str(CICLO_ANTERIOR), "derivada", "posição da rede diante do seu município",
     "rede_taxa_ant - mun_taxa_ant"),
    ("mun_taxa_ant", "desempenho anterior", "Gold, indicador municipal",
     str(CICLO_ANTERIOR), "direta", "taxa de alfabetização do município na rede pública", ""),
    ("mun_participacao_ant", "desempenho anterior", "Gold, indicador municipal",
     str(CICLO_ANTERIOR), "direta", "percentual de alunos presentes na avaliação anterior", ""),
    ("mun_taxa_ajustada_ant", "desempenho anterior", "Gold, indicador municipal",
     str(CICLO_ANTERIOR), "derivada", "taxa com ausentes contados como não alfabetizados",
     "mun_taxa_ant * mun_participacao_ant / 100"),
    ("mun_alunos_ant", "desempenho anterior", "Gold, indicador municipal",
     str(CICLO_ANTERIOR), "direta", "alunos presentes no município no ciclo anterior", ""),
    ("mun_meta_ciclo", "desempenho anterior", "Gold, metas pactuadas",
     f"{CICLO_ALVO}, pactuada previamente", "direta",
     "meta de alfabetização pactuada para o ciclo corrente", ""),
    ("mun_gap_meta", "desempenho anterior", "Gold, metas pactuadas",
     f"{CICLO_ANTERIOR} e {CICLO_ALVO}", "derivada", "esforço requerido para atingir a meta",
     "mun_meta_ciclo - mun_taxa_ant"),

    ("sigla_uf", "território", "IBGE, diretório de municípios", "estável", "direta",
     "unidade da federação", ""),
    ("nome_regiao", "território", "IBGE, diretório de municípios", "estável", "direta",
     "região do país", ""),

    ("rede_porte_atual", "porte e oferta", "Silver, camada de alunos",
     f"{CICLO_ALVO}, cadastro prévio", "derivada",
     "alunos avaliáveis na rede do aluno no município", "contagem de matriculados"),
    ("mun_porte_atual", "porte e oferta", "Silver, camada de alunos",
     f"{CICLO_ALVO}, cadastro prévio", "derivada",
     "alunos avaliáveis no município", "contagem de matriculados"),
    ("rede_peso_no_municipio", "porte e oferta", "Silver, camada de alunos",
     str(CICLO_ALVO), "derivada", "fração dos alunos do município atendida pela rede",
     "rede_porte_atual / mun_porte_atual"),
    ("esc_quantidade", "porte e oferta", "INEP, Censo Escolar", str(CICLO_ANTERIOR),
     "direta", "escolas da rede no município", ""),
    ("esc_salas_por_aluno", "porte e oferta", "INEP, Censo Escolar", str(CICLO_ANTERIOR),
     "proxy", "densidade física: espaço disponível por aluno, na falta de metragem",
     "salas em uso / rede_porte_atual"),
    ("turma_media_alunos", "porte e oferta", "INEP, Censo Escolar, turmas",
     str(CICLO_ANTERIOR), "direta", "tamanho médio da turma do 2º ano, a série avaliada", ""),

    ("esc_pct_rural", "infraestrutura", "INEP, Censo Escolar", str(CICLO_ANTERIOR),
     "direta", "percentual de escolas da rede em zona rural", ""),
    ("esc_pct_agua_rede", "infraestrutura", "INEP, Censo Escolar", str(CICLO_ANTERIOR),
     "direta", "escolas com abastecimento de água pela rede pública", ""),
    ("esc_pct_esgoto_rede", "infraestrutura", "INEP, Censo Escolar", str(CICLO_ANTERIOR),
     "direta", "escolas com esgotamento sanitário pela rede pública", ""),
    ("esc_pct_energia_rede", "infraestrutura", "INEP, Censo Escolar", str(CICLO_ANTERIOR),
     "direta", "escolas com energia elétrica da rede pública", ""),
    ("esc_pct_internet", "infraestrutura", "INEP, Censo Escolar", str(CICLO_ANTERIOR),
     "direta", "escolas com acesso à internet", ""),
    ("esc_pct_biblioteca", "infraestrutura", "INEP, Censo Escolar", str(CICLO_ANTERIOR),
     "direta", "escolas com biblioteca", ""),
    ("esc_pct_lab_informatica", "infraestrutura", "INEP, Censo Escolar", str(CICLO_ANTERIOR),
     "direta", "escolas com laboratório de informática", ""),
    ("esc_pct_quadra", "infraestrutura", "INEP, Censo Escolar", str(CICLO_ANTERIOR),
     "direta", "escolas com quadra de esportes", ""),
    ("esc_pct_alimentacao", "infraestrutura", "INEP, Censo Escolar", str(CICLO_ANTERIOR),
     "direta", "escolas que oferecem alimentação aos alunos", ""),
    ("esc_pct_transporte", "infraestrutura", "INEP, Censo Escolar", str(CICLO_ANTERIOR),
     "proxy", "dependência de transporte escolar, aproximação da distância entre aluno e escola",
     "alunos transportados / rede_porte_atual"),

    ("esc_pct_coordenador", "profissionais", "INEP, Censo Escolar", str(CICLO_ANTERIOR),
     "direta", "escolas com coordenador pedagógico", ""),
    ("esc_pct_psicologo", "profissionais", "INEP, Censo Escolar", str(CICLO_ANTERIOR),
     "direta", "escolas com psicólogo", ""),
    ("esc_pct_assistente_social", "profissionais", "INEP, Censo Escolar", str(CICLO_ANTERIOR),
     "direta", "escolas com assistente social", ""),

    ("mun_pib_per_capita", "socioeconômico", "IBGE, PIB municipal", str(ANO_PIB),
     "derivada", "riqueza produzida por habitante", "PIB / população"),
    ("mun_pct_agropecuaria", "socioeconômico", "IBGE, PIB municipal", str(ANO_PIB),
     "proxy", "peso da agropecuária, aproximação do caráter rural da economia",
     "valor adicionado agropecuário / valor adicionado total"),
    ("mun_pct_servicos", "socioeconômico", "IBGE, PIB municipal", str(ANO_PIB),
     "proxy", "peso dos serviços, aproximação do caráter urbano da economia",
     "valor adicionado de serviços / valor adicionado total"),
    ("mun_populacao", "socioeconômico", "IBGE, estimativa populacional", str(ANO_PIB),
     "direta", "população do município", ""),
    ("mun_idhm", "socioeconômico", "PNUD, Atlas do Desenvolvimento Humano", "2010",
     "direta", "índice de desenvolvimento humano municipal", ""),
    ("mun_idhm_educacao", "socioeconômico", "PNUD, Atlas do Desenvolvimento Humano", "2010",
     "direta", "dimensão educação do IDHM", ""),
    ("mun_idhm_renda", "socioeconômico", "PNUD, Atlas do Desenvolvimento Humano", "2010",
     "direta", "dimensão renda do IDHM", ""),
    ("mun_renda_per_capita", "socioeconômico", "PNUD, Atlas do Desenvolvimento Humano", "2010",
     "direta", "renda domiciliar por habitante", ""),
    ("mun_gini", "socioeconômico", "PNUD, Atlas do Desenvolvimento Humano", "2010",
     "direta", "desigualdade na distribuição da renda", ""),
    ("mun_analfabetismo_adulto", "socioeconômico", "PNUD, Atlas do Desenvolvimento Humano",
     "2010", "proxy", "analfabetismo entre adultos, aproximação do capital cultural do domicílio", ""),
    ("mun_expectativa_estudo", "socioeconômico", "PNUD, Atlas do Desenvolvimento Humano",
     "2010", "direta", "expectativa de anos de estudo", ""),
    ("mun_ivs", "socioeconômico", "IPEA, Atlas da Violência", "2010", "direta",
     "índice de vulnerabilidade social", ""),
    ("mun_ivs_infraestrutura", "socioeconômico", "IPEA, Atlas da Violência", "2010",
     "direta", "vulnerabilidade de infraestrutura urbana", ""),
    ("mun_ivs_capital_humano", "socioeconômico", "IPEA, Atlas da Violência", "2010",
     "direta", "vulnerabilidade de capital humano", ""),
    ("mun_taxa_homicidio", "socioeconômico", "DataSUS, Sistema de Informação sobre Mortalidade",
     str(ANO_VIOLENCIA), "proxy", "óbitos por agressão por cem mil habitantes, aproximação da exposição à violência",
     "óbitos CID X85 a Y09 * 100000 / população"),
]

COLUNAS_META = ["variavel", "bloco", "fonte", "referencia", "natureza",
                "descricao", "formula"]


# ---------------------------------------------------------------------------
# Consultas às fontes públicas (decisão D-005)
# ---------------------------------------------------------------------------
CONSULTAS = {
    "censo_escolar": f"""
        SELECT id_municipio, rede,
               COUNT(*) AS esc_quantidade,
               ROUND(100 * AVG(IF(tipo_localizacao = 'Rural', 1, 0)), 1) AS esc_pct_rural,
               ROUND(100 * AVG(COALESCE(agua_rede_publica, 0)), 1) AS esc_pct_agua_rede,
               ROUND(100 * AVG(COALESCE(esgoto_rede_publica, 0)), 1) AS esc_pct_esgoto_rede,
               ROUND(100 * AVG(COALESCE(energia_rede_publica, 0)), 1) AS esc_pct_energia_rede,
               ROUND(100 * AVG(COALESCE(internet, 0)), 1) AS esc_pct_internet,
               ROUND(100 * AVG(COALESCE(biblioteca, 0)), 1) AS esc_pct_biblioteca,
               ROUND(100 * AVG(COALESCE(laboratorio_informatica, 0)), 1) AS esc_pct_lab_informatica,
               ROUND(100 * AVG(COALESCE(quadra_esportes, 0)), 1) AS esc_pct_quadra,
               ROUND(100 * AVG(COALESCE(alimentacao, 0)), 1) AS esc_pct_alimentacao,
               ROUND(100 * AVG(COALESCE(profissional_coordenador, 0)), 1) AS esc_pct_coordenador,
               ROUND(100 * AVG(COALESCE(profissional_psicologo, 0)), 1) AS esc_pct_psicologo,
               ROUND(100 * AVG(COALESCE(profissional_assistente_social, 0)), 1) AS esc_pct_assistente_social,
               SUM(quantidade_sala_utilizada) AS esc_salas,
               SUM(quantidade_matricula_utiliza_transporte_publico) AS esc_alunos_transporte
        FROM `basedosdados.br_inep_censo_escolar.escola`
        WHERE ano = {CICLO_ANTERIOR} AND rede IN ('2', '3')
        GROUP BY id_municipio, rede
    """,
    # Nesta tabela a rede vem por extenso; a etapa 15 é o 2º ano do fundamental
    "turmas_2ano": f"""
        SELECT id_municipio,
               CASE rede WHEN 'estadual' THEN 'Estadual'
                         WHEN 'municipal' THEN 'Municipal' END AS rede_nome,
               ROUND(AVG(quantidade_matriculas), 1) AS turma_media_alunos
        FROM `basedosdados.br_inep_censo_escolar.turma`
        WHERE ano = {CICLO_ANTERIOR}
          AND rede IN ('estadual', 'municipal')
          AND etapa_ensino = '15'
        GROUP BY id_municipio, rede_nome
    """,
    "economia_municipal": f"""
        SELECT p.id_municipio,
               ROUND(p.pib / NULLIF(pop.populacao, 0), 0) AS mun_pib_per_capita,
               ROUND(100 * p.va_agropecuaria / NULLIF(p.va, 0), 1) AS mun_pct_agropecuaria,
               ROUND(100 * p.va_servicos / NULLIF(p.va, 0), 1) AS mun_pct_servicos,
               pop.populacao AS mun_populacao
        FROM `basedosdados.br_ibge_pib.municipio` p
        JOIN `basedosdados.br_ibge_populacao.municipio` pop
          ON p.id_municipio = pop.id_municipio AND p.ano = pop.ano
        WHERE p.ano = {ANO_PIB}
    """,
    "desenvolvimento_humano": """
        SELECT a.id_municipio,
               a.idhm AS mun_idhm, a.idhm_e AS mun_idhm_educacao,
               a.idhm_r AS mun_idhm_renda, a.renda_pc AS mun_renda_per_capita,
               a.indice_gini AS mun_gini,
               a.taxa_analfabetismo_18_mais AS mun_analfabetismo_adulto,
               a.expectativa_anos_estudo AS mun_expectativa_estudo,
               v.ivs AS mun_ivs,
               v.ivs_infraestrutura_urbana AS mun_ivs_infraestrutura,
               v.ivs_capital_humano AS mun_ivs_capital_humano
        FROM `basedosdados.mundo_onu_adh.municipio` a
        LEFT JOIN (
            SELECT id_municipio, AVG(ivs) AS ivs,
                   AVG(ivs_infraestrutura_urbana) AS ivs_infraestrutura_urbana,
                   AVG(ivs_capital_humano) AS ivs_capital_humano
            FROM `basedosdados.br_ipea_avs.municipio`
            WHERE ano = 2010 GROUP BY id_municipio
        ) v ON a.id_municipio = v.id_municipio
        WHERE a.ano = 2010
    """,
    "violencia_municipal": f"""
        SELECT id_municipio, SUM(numero_obitos) AS obitos_agressao
        FROM `basedosdados.br_ms_sim.municipio_causa`
        WHERE ano = {ANO_VIOLENCIA}
          AND REGEXP_CONTAINS(causa_basica, r'^(X8[5-9]|X9[0-9]|Y0[0-9])')
        GROUP BY id_municipio
    """,
}


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
    """Leitura das camadas do lake, consulta às fontes públicas e gravação."""

    def __init__(self, cfg: dict):
        self.projeto = cfg["projeto_gcp"]
        self.bucket = cfg["bucket_lake"]
        self.credenciais = pydata_google_auth.get_user_credentials(ESCOPOS)
        self.credenciais = self.credenciais.with_quota_project(self.projeto)
        self.cliente = storage.Client(project=self.projeto,
                                      credentials=self.credenciais)

    def ultima_particao(self, area: str, tabela: str) -> str | None:
        particoes = sorted({
            b.name.split("/")[2]
            for b in self.cliente.list_blobs(self.bucket,
                                             prefix=f"{area}/{tabela}/")
            if len(b.name.split("/")) > 2
        })
        return particoes[-1] if particoes else None

    def ler(self, area: str, tabela: str, **kwargs) -> pd.DataFrame:
        """Lê uma tabela do lake pela biblioteca oficial, sem I/O assíncrono."""
        particao = self.ultima_particao(area, tabela)
        if particao is None:
            sys.exit(
                f"Tabela '{tabela}' nao encontrada em {area}/ "
                f"(gs://{self.bucket}/{area}/{tabela}/).\n"
                "Execute antes a pipeline da fase anterior (repositorio "
                "Tech_Challenge_RM373453_pipeline_alfabetizacao)."
            )
        blob = self.cliente.bucket(self.bucket).blob(
            f"{area}/{tabela}/{particao}/{tabela}.parquet")
        return pd.read_parquet(io.BytesIO(blob.download_as_bytes()), **kwargs)

    def fonte_externa(self, nome: str, refazer: bool = False) -> pd.DataFrame:
        """Consulta uma fonte pública uma única vez e a mantém no lake."""
        caminho = f"ml/externas/{nome}/{nome}.parquet"
        blob = self.cliente.bucket(self.bucket).blob(caminho)
        if blob.exists() and not refazer:
            dados = pd.read_parquet(io.BytesIO(blob.download_as_bytes()))
            origem = "cache"
        else:
            dados = pandas_gbq.read_gbq(CONSULTAS[nome],
                                        project_id=self.projeto,
                                        credentials=self.credenciais,
                                        progress_bar_type=None)
            dados.to_parquet(f"gs://{self.bucket}/{caminho}", index=False,
                             storage_options={"token": self.credenciais})
            origem = "consultada"
        print(f"        {nome:<24} {len(dados):>7,} linhas  ({origem})")
        return dados

    def gravar_ml(self, df: pd.DataFrame, tabela: str) -> dict:
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
        if lake.ultima_particao(area, tabela) is None:
            pendencias.append(f"{area}/{tabela} ausente")
            continue
        faltantes = [c for c in colunas if c not in lake.ler(area, tabela).columns]
        if faltantes:
            pendencias.append(f"{area}/{tabela}: faltam {faltantes}")
    if pendencias:
        sys.exit("Pre-requisitos nao atendidos: " + "; ".join(pendencias)
                 + ".\nExecute a pipeline da fase anterior antes de prosseguir.")


def isolar_populacao(df_alunos: pd.DataFrame) -> pd.DataFrame:
    """Alunos presentes: os únicos com variável resposta observável (D-001)."""
    df = df_alunos[df_alunos["presente"]].copy()
    df["alvo"] = (df["alfabetizado"].astype(str) == "1").astype(int)
    return df


def montar_contexto_rede(mun: pd.DataFrame) -> pd.DataFrame:
    """Desempenho da rede do aluno e seu benchmark estadual (D-003)."""
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
    """Desempenho do município no ciclo anterior e meta pactuada."""
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
    """Porte do cadastro escolar, informação anterior à prova (D-004)."""
    cadastro = df_alunos[df_alunos["ano"] == CICLO_ALVO]
    porte_rede = (cadastro.groupby(["id_municipio", "rede_nome"], observed=True)
                  .size().rename("rede_porte_atual").reset_index())
    porte_mun = (cadastro.groupby("id_municipio", observed=True)
                 .size().rename("mun_porte_atual").reset_index())
    return porte_rede, porte_mun


def preparar_externas(lake: Lake, refazer: bool) -> dict:
    """Traz as fontes públicas e as ajusta ao vocabulário da base (D-005)."""
    censo = lake.fonte_externa("censo_escolar", refazer)
    censo["rede_nome"] = censo["rede"].map({"2": "Estadual", "3": "Municipal"})
    censo = censo.drop(columns="rede")

    turmas = lake.fonte_externa("turmas_2ano", refazer)
    economia = lake.fonte_externa("economia_municipal", refazer)
    desenvolvimento = lake.fonte_externa("desenvolvimento_humano", refazer)

    violencia = lake.fonte_externa("violencia_municipal", refazer)
    # Município sem registro não é desconhecido: não houve óbito por agressão
    violencia = economia[["id_municipio", "mun_populacao"]].merge(
        violencia, on="id_municipio", how="left")
    violencia["obitos_agressao"] = violencia["obitos_agressao"].fillna(0)
    violencia["mun_taxa_homicidio"] = (
        100_000 * violencia["obitos_agressao"]
        / violencia["mun_populacao"]).round(1)
    violencia = violencia[["id_municipio", "mun_taxa_homicidio"]]

    return {"censo": censo, "turmas": turmas, "economia": economia,
            "desenvolvimento": desenvolvimento, "violencia": violencia}


def integrar(populacao: pd.DataFrame, ctx_rede: pd.DataFrame,
             ctx_mun: pd.DataFrame, porte_rede: pd.DataFrame,
             porte_mun: pd.DataFrame, externas: dict) -> pd.DataFrame:
    """Reúne todas as fontes preservando a contagem de linhas."""
    abt = populacao[populacao["ano"] == CICLO_ALVO].copy()
    antes = len(abt)
    fontes = [
        ("contexto da rede", ctx_rede, ["id_municipio", "rede_nome"]),
        ("contexto do município", ctx_mun, ["id_municipio"]),
        ("porte da rede", porte_rede, ["id_municipio", "rede_nome"]),
        ("porte do município", porte_mun, ["id_municipio"]),
        ("censo escolar", externas["censo"], ["id_municipio", "rede_nome"]),
        ("turmas", externas["turmas"], ["id_municipio", "rede_nome"]),
        ("economia", externas["economia"], ["id_municipio"]),
        ("desenvolvimento humano", externas["desenvolvimento"], ["id_municipio"]),
        ("violência", externas["violencia"], ["id_municipio"]),
    ]
    for rotulo, tabela, chaves in fontes:
        abt = abt.merge(tabela, on=chaves, how="left")
        if len(abt) != antes:
            sys.exit(f"O join com '{rotulo}' alterou a contagem: "
                     f"{antes:,} -> {len(abt):,}. Verifique chaves duplicadas.")

    abt["rede_vs_municipio"] = abt["rede_taxa_ant"] - abt["mun_taxa_ant"]
    abt["rede_peso_no_municipio"] = (abt["rede_porte_atual"]
                                     / abt["mun_porte_atual"])
    abt["esc_salas_por_aluno"] = abt["esc_salas"] / abt["rede_porte_atual"]
    abt["esc_pct_transporte"] = (100 * abt["esc_alunos_transporte"]
                                 / abt["rede_porte_atual"]).clip(upper=100)
    return abt.drop(columns=["esc_salas", "esc_alunos_transporte"])


def auditar(abt: pd.DataFrame) -> None:
    """Auditoria contra vazamento nas três frentes documentadas."""
    ausentes = [v for v in FEATURES if v not in abt.columns]
    if ausentes:
        sys.exit(f"Variaveis declaradas mas ausentes na tabela: {ausentes}")

    invasoras = [c for c in FEATURES if c in PROIBIDAS]
    if invasoras:
        sys.exit(f"Auditoria reprovada: variaveis proibidas: {invasoras}")

    permitidas = EX_ANTE_DO_CICLO | DERIVADAS_DE_CONTEXTO | CATEGORICAS
    suspeitas = [c for c in FEATURES
                 if not c.endswith("_ant")
                 and not c.startswith(("esc_", "mun_", "turma_", "uf_"))
                 and c not in permitidas]
    if suspeitas:
        sys.exit(f"Auditoria reprovada: variaveis sem justificativa temporal: "
                 f"{suspeitas}")

    numericas = [c for c in FEATURES if pd.api.types.is_numeric_dtype(abt[c])]
    correl = abt[numericas + ["alvo"]].corr()["alvo"].drop("alvo")
    extremas = correl[correl.abs() > 0.9]
    if len(extremas):
        sys.exit(f"Auditoria reprovada: correlacao suspeita com a resposta em "
                 f"{list(extremas.index)}")


def particionar(abt: pd.DataFrame) -> pd.DataFrame:
    """Separa treino, validação e teste por município."""
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


def publicar_dicionario(df_abt: pd.DataFrame) -> Path:
    """Dicionário de dados: bloco, fonte, referência, natureza e fórmula."""
    dicionario = pd.DataFrame(METADADOS_VARIAVEIS, columns=COLUNAS_META)

    na_tabela = [c for c in df_abt.columns if c not in METADADOS_GRAVACAO]
    sem_descricao = [v for v in na_tabela if v not in set(dicionario["variavel"])]
    orfas = [v for v in dicionario["variavel"] if v not in na_tabela]
    if sem_descricao or orfas:
        sys.exit(f"Dicionario desatualizado. Sem descricao: {sem_descricao}. "
                 f"Descricoes sem variavel: {orfas}.")

    dicionario["tipo"] = [str(df_abt[v].dtype) for v in dicionario["variavel"]]
    dicionario["preenchimento"] = [
        round(100 * df_abt[v].notna().mean(), 1)
        for v in dicionario["variavel"]]
    dicionario["distintos"] = [df_abt[v].nunique()
                               for v in dicionario["variavel"]]
    destino = RAIZ / "reports" / "dicionario_dados.csv"
    dicionario.to_csv(destino, index=False, encoding="utf-8")
    return destino


# ---------------------------------------------------------------------------
# Orquestração
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refazer-externas", action="store_true",
                        help="reconsulta as fontes publicas, ignorando o cache")
    args = parser.parse_args()

    # o console do Windows usa cp1252 por padrao e quebraria os acentos
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    cfg = carregar_config()
    lake = Lake(cfg)
    inicio = datetime.now(timezone.utc)

    print(f"Construcao da tabela analitica iniciada em {inicio.isoformat()}")
    print(f"Lake: gs://{cfg['bucket_lake']}/   ciclo alvo: {CICLO_ALVO}")
    print()

    print("[1/7] verificando o contrato do lake...", flush=True)
    verificar_contrato(lake)
    print(f"        {len(CONTRATO)} tabelas conferidas")

    print("[2/7] isolando a populacao modelavel...", flush=True)
    df_alunos = lake.ler("silver", "alunos",
                         columns=["ano", "id_municipio", "rede_nome",
                                  "presente", "alfabetizado", "proficiencia",
                                  "peso_aluno"])
    populacao = isolar_populacao(df_alunos)
    print(f"        {len(populacao):,} alunos presentes de "
          f"{len(df_alunos):,} avaliaveis")

    print("[3/7] montando o contexto defasado...", flush=True)
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

    print("[4/7] trazendo as fontes externas...", flush=True)
    externas = preparar_externas(lake, args.refazer_externas)

    print("[5/7] integrando e auditando...", flush=True)
    abt = integrar(populacao, ctx_rede, ctx_mun, porte_rede, porte_mun,
                   externas)
    auditar(abt)
    print(f"        {len(abt):,} observacoes, {len(FEATURES)} variaveis em "
          f"{len(FAMILIAS)} familias, auditoria aprovada")

    print("[6/7] separando treino, validacao e teste...", flush=True)
    abt = particionar(abt)
    resumo_particao = abt["particao"].value_counts().to_dict()
    print(f"        {resumo_particao}")

    print("[7/7] gravando e publicando o dicionario...", flush=True)
    colunas = (["ano", "id_municipio"] + FEATURES
               + ["alvo", "peso_aluno", "particao"])
    entrega = lake.gravar_ml(abt[colunas], "abt_alfabetizacao")
    relido = pd.read_parquet(entrega["destino"],
                             storage_options={"token": lake.credenciais})
    reconciliacao = "OK" if len(relido) == entrega["linhas"] else "DIVERGIU"
    caminho_dicionario = publicar_dicionario(abt[colunas])
    print(f"        {entrega['linhas']:,} linhas gravadas, "
          f"reconciliacao {reconciliacao}")

    duracao = (datetime.now(timezone.utc) - inicio).total_seconds() / 60
    print()
    print("=" * 64)
    print("RESUMO DA EXECUCAO")
    print(f"  Tabela analitica:     {entrega['linhas']:,} linhas  "
          f"{reconciliacao}")
    print(f"  Variaveis:            {len(FEATURES)} explicativas")
    for familia, variaveis in FAMILIAS.items():
        print(f"      {familia:<26} {len(variaveis):>2}")
    print(f"  Particoes:            {resumo_particao}")
    print(f"  Destino:              {entrega['destino']}")
    print(f"  Dicionario:           {caminho_dicionario.relative_to(RAIZ)}")
    print(f"  Duracao:              {duracao:.1f} min")
    status = "FALHA" if reconciliacao != "OK" else "SUCESSO"
    print(f"  Status final:         {status}")
    print("=" * 64)
    return 1 if status == "FALHA" else 0


if __name__ == "__main__":
    sys.exit(main())

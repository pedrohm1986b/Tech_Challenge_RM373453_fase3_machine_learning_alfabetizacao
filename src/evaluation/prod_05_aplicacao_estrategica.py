# -*- coding: utf-8 -*-
"""Aplicação estratégica: as cinco perguntas de negócio sobre o modelo pronto.

Código promovido do notebook
`notebooks/desenv_05_aplicacao_estrategica.ipynb`, onde o desenvolvimento está
documentado célula a célula, com os conceitos aplicados e as evidências de
execução.

Este script não escolhe nada: ele reconstrói o modelo pela receita registrada
em `reports/modelo_rede_escolhido.json` e confere, antes de seguir, que a AUC
reproduzida no teste é a mesma registrada pelo `prod_04`.

As cinco perguntas e o que cada uma grava:
1. quais fatores mais impactam a alfabetização: dependência parcial de cada
   alavanca, com o ponto de partida fixo, em `fatores_meta_2024.csv`;
2. quais municípios apresentam maior risco: as redes que o modelo apontou e que
   de fato não cumpriram, ordenadas pelo quanto cada uma move a taxa nacional,
   em `redes_risco_2024.csv`;
3. quais regiões possuem padrões semelhantes: a distribuição de probabilidade
   de cada região e a sobreposição entre elas, em `semelhanca_regioes.csv`;
4. como prever quem pode não atingir metas futuras: o resultado observado em
   cada faixa de probabilidade, medido no teste, e a contagem de municípios do
   país em cada faixa, em `faixas_probabilidade.csv`;
5. quais variáveis possuem maior influência: importância por permutação,
   variável a variável e em bloco, em `influencia_variaveis_rede.csv` e
   `influencia_blocos_rede.csv`.

Onde cada coisa é medida (decisão D-014): o desempenho do modelo usa apenas a
partição de teste, a única em que a previsão é honesta; as análises que
descrevem o país usam todas as redes, e a partição de cada uma vai gravada nos
arquivos para que qualquer leitura possa ser refeita só com o teste.

O que não foi promovido: as figuras e as tabelas formatadas em HTML, que são
material de leitura do notebook, entre elas o mapa municipal.

Execução:
    python src/evaluation/prod_05_aplicacao_estrategica.py
    (no Windows, se o comando python não for reconhecido, use o launcher py:
    py src/evaluation/prod_05_aplicacao_estrategica.py)

    --amostra-dependencia N  redes sorteadas para a dependência parcial
                             (padrão 2000; quanto maior, mais lento)

Propriedades:
- Replicabilidade: a semente vem do registro do modelo e vale para o
  reajuste, para a amostra da dependência parcial e para as permutações.
- Trava de integridade: se a AUC reproduzida no teste divergir da registrada, a
  execução para com código de saída 1, porque as respostas deixariam de
  corresponder ao modelo documentado.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.inspection import partial_dependence, permutation_importance
from sklearn.metrics import log_loss, roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "modeling"))
from prod_03_pipeline_modelagem import (  # noqa: E402  (o pipeline vem da etapa 4)
    RAIZ, Lake, carregar_config, montar_modelo,
)
from prod_04_pipeline_modelagem_parte2 import (  # noqa: E402
    META_2024, TERRITORIO, agregar_por_rede, carregar_base, separar_redes,
)

# ---------------------------------------------------------------------------
# Desenho da análise
# ---------------------------------------------------------------------------
# O ponto de partida fica no modelo e fora da análise das alavancas (D-015)
PONTO_DE_PARTIDA = ["rede_taxa_ant", "uf_rede_taxa_ant", "mun_participacao_ant",
                    "sigla_uf", "nome_regiao"]
REGIOES = ["Norte", "Nordeste", "Centro-Oeste", "Sudeste", "Sul"]
FAIXAS = [0, 25, 50, 75, 100]      # faixas de probabilidade, em %
ROTULOS_FAIXA = ["até 25%", "25 a 50%", "50 a 75%", "acima de 75%"]
PEDACOS_SILHUETA = np.arange(0, 101, 10)
REPETICOES_PERMUTACAO = 10
LIMIAR = 0.5

# Quem consegue mover cada fator, a direção esperada declarada antes de medir
# (+ mais é melhor, - mais é pior, ? sem expectativa) e a pasta parceira
FATORES = {   # nome, quem mexe, direção esperada, motivo, pasta parceira
    "mun_indice_pre_escola": ("Oferta de pré-escola", "educação", "+",
                              "quem passou pela pré-escola chega ao 1º ano familiarizado com "
                              "letras e sons", ""),
    "esc_horas_aula_diarias": ("Horas-aula por dia", "educação", "+",
                               "mais tempo de aula dá mais contato com a leitura", ""),
    "esc_pct_biblioteca_ou_sala_leitura": ("Escolas com biblioteca", "educação", "+",
                                           "dá acesso a livros fora da sala de aula", ""),
    "esc_pct_quadra": ("Escolas com quadra", "educação", "+",
                       "indica escola com estrutura completa", ""),
    "esc_pct_docentes_alto_esforco": ("Professores sobrecarregados", "educação", "-",
                                      "sobra menos tempo para cada turma", ""),
    "mun_pct_maes_adolescentes": ("Mães adolescentes", "outra pasta", "-",
                                  "mãe adolescente tem, em média, menos escolaridade e menos "
                                  "apoio", "saúde e assistência social"),
    "esc_inse_medio": ("Nível socioeconômico das famílias", "outra pasta", "+",
                       "famílias com mais escolaridade e renda apoiam mais a leitura; é alavanca "
                       "de prazo longo, porque a política de renda muda a família antes de mudar "
                       "o indicador", "assistência social e renda"),
    "mun_pct_vulner_deslocamento_1h": ("Pobres com mais de 1 hora de deslocamento", "outra pasta",
                                       "-", "longos deslocamentos cansam a família; o dado é de "
                                       "2010 e aponta o problema, mas está velho para medir a "
                                       "situação atual", "mobilidade e transporte"),
    "mun_densidade_demografica": ("Densidade demográfica", "outra pasta", "+",
                                  "com a população concentrada, a escola fica mais perto; a "
                                  "densidade não muda, mas a distância que ela representa se "
                                  "trata com a localização das escolas e o transporte",
                                  "planejamento urbano e transporte"),
    "mun_idade_mediana": ("Idade mediana da população", "outra pasta", "+",
                          "população mais jovem indica fecundidade alta, com mais crianças por "
                          "família e gravidez precoce, e expectativa de vida menor, por mortes "
                          "violentas e problemas de saúde", "saúde e segurança pública"),
    "mun_populacao": ("População do município", "território", "?",
                      "porte pode trazer estrutura ou complexidade", ""),
}
NOMES_PONTO_DE_PARTIDA = {
    "rede_taxa_ant": "Taxa da própria rede em 2023",
    "uf_rede_taxa_ant": "Taxa da mesma rede no estado em 2023",
    "mun_participacao_ant": "Participação na avaliação em 2023",
    "sigla_uf": "Unidade da federação", "nome_regiao": "Região",
}

REGISTRO_MODELO = RAIZ / "reports" / "modelo_rede_escolhido.json"
AVALIACAO_TESTE = RAIZ / "reports" / "avaliacao_teste_rede.csv"
SAIDA_FATORES = RAIZ / "reports" / "fatores_meta_2024.csv"
SAIDA_RISCO = RAIZ / "reports" / "redes_risco_2024.csv"
SAIDA_REGIOES = RAIZ / "reports" / "semelhanca_regioes.csv"
SAIDA_FAIXAS = RAIZ / "reports" / "faixas_probabilidade.csv"
SAIDA_INFLUENCIA = RAIZ / "reports" / "influencia_variaveis_rede.csv"
SAIDA_BLOCOS = RAIZ / "reports" / "influencia_blocos_rede.csv"


# ---------------------------------------------------------------------------
# O modelo do prod_04, reconstruído pela receita
# ---------------------------------------------------------------------------
def reconstruir_modelo(desenho: dict, X_final, y_final, X_teste, y_teste):
    """Refaz o modelo registrado e confere que ele reproduz a AUC do teste."""
    if not REGISTRO_MODELO.exists():
        sys.exit(f"{REGISTRO_MODELO.name} nao encontrado; rode antes "
                 "src/modeling/prod_04_pipeline_modelagem_parte2.py")
    registro = json.loads(REGISTRO_MODELO.read_text(encoding="utf-8"))
    if registro["familia"] != "random forest":
        sys.exit(f"A receita registrada e '{registro['familia']}'; este script monta "
                 "a random forest escolhida no prod_04. Revise a fabrica do modelo.")
    semente = registro["semente"]
    modelo = montar_modelo(desenho, RandomForestClassifier(
        random_state=semente, n_jobs=-1, **registro["parametros"]), False, registro["variaveis"])
    modelo.fit(X_final, y_final)

    auc = roc_auc_score(y_teste, modelo.predict_proba(X_teste)[:, 1])
    esperada = pd.read_csv(AVALIACAO_TESTE, index_col=0).loc["modelo final", "auc"]
    if abs(auc - esperada) > 1e-4:
        sys.exit(f"O modelo nao reproduz o prod_04: AUC {auc:.5f} contra {esperada:.5f}. "
                 "Rode os dois scripts na mesma base.")
    return modelo, registro, semente


# ---------------------------------------------------------------------------
# Pergunta 1: quais fatores mais impactam a alfabetização
# ---------------------------------------------------------------------------
def efeito(modelo, dados: pd.DataFrame, desenho: dict, variaveis: list,
           variavel: str, baixo: float, alto: float) -> float:
    """Pontos de probabilidade entre o valor baixo e o alto, com o resto como está."""
    X = dados[variaveis].copy()
    numericas = [v for v in desenho["numericas"] if v in X.columns]
    X[numericas] = X[numericas].astype("float64")   # a dependência parcial não aceita inteiro
    r = partial_dependence(modelo, X, [variavel], grid_resolution=21, kind="average",
                           response_method="predict_proba")
    return 100 * float(np.diff(np.interp([baixo, alto], r["grid_values"][0], r["average"][0]))[0])


def responder_fatores(modelo, redes: pd.DataFrame, desenho: dict, variaveis: list,
                      fatores_analisados: list, amostra: int, semente: int) -> pd.DataFrame:
    """Direção e tamanho do efeito de cada alavanca, com o ponto de partida fixo."""
    faltam = [v for v in fatores_analisados if v not in FATORES]
    if faltam:
        sys.exit(f"Fatores do modelo sem descricao editorial: {faltam}")
    sorteadas = redes.sample(min(amostra, len(redes)), random_state=semente)
    linhas = []
    for v in fatores_analisados:
        baixo, alto = redes[v].quantile([.25, .75])
        valor = efeito(modelo, sorteadas, desenho, variaveis, v, baixo, alto)
        # robustez: em quantas regiões o efeito mantém o mesmo sinal
        regioes = sum(np.sign(efeito(modelo, redes[redes["nome_regiao"] == r], desenho,
                                     variaveis, v, baixo, alto)) == np.sign(valor)
                      for r in REGIOES)
        nome, quem, sinal, motivo, pasta = FATORES[v]
        obtido = "+" if valor >= 0 else "-"
        linhas.append({"variavel": v, "nome": nome, "quem": quem, "sinal": sinal,
                       "motivo": motivo, "pasta": pasta, "baixo": baixo, "alto": alto,
                       "efeito_pp": valor, "regioes": regioes,
                       "confere": "sem expectativa" if sinal == "?"
                                  else ("sim" if sinal == obtido else "nao")})
    fatores = pd.DataFrame(linhas).set_index("variavel")
    ordem = fatores["quem"].map({"educação": 0, "outra pasta": 1, "território": 2})
    fatores = (fatores.assign(ordem=ordem, absoluto=fatores["efeito_pp"].abs())
               .sort_values(["ordem", "absoluto"], ascending=[True, False])
               .drop(columns=["ordem", "absoluto"]))
    fatores.round(4).to_csv(SAIDA_FATORES, encoding="utf-8")
    return fatores


# ---------------------------------------------------------------------------
# Pergunta 2: quais municípios apresentam maior risco
# ---------------------------------------------------------------------------
def responder_risco(lake: Lake, redes: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """As redes apontadas que de fato não cumpriram, pelo impacto na taxa nacional."""
    apontadas = redes["p_cumprir"] < LIMIAR
    acertos = redes[apontadas & (redes["bateu_meta"] == 0)].copy()

    # a taxa nacional é a mesma conta da oficial: alfabetizados sobre o total, com o peso do INEP
    peso_nacional = redes["peso_total"].sum()
    taxa_nacional = 100 * redes["peso_alfabetizados"].sum() / peso_nacional
    # quanto o país subiria se aquela rede chegasse exatamente à meta
    acertos["ganho_pp"] = (100 * (META_2024 / 100 * acertos["peso_total"]
                                  - acertos["peso_alfabetizados"]) / peso_nacional)

    diretorio = lake.ler("bronze", "diretorio_municipio")[["id_municipio", "nome"]]
    lista = acertos.merge(diretorio, on="id_municipio", how="left").sort_values(
        "ganho_pp", ascending=False)
    if lista["nome"].isna().any():
        sys.exit("Ha municipio sem nome no diretorio.")
    lista["ganho_acumulado"] = lista["ganho_pp"].cumsum()
    lista["taxa_nacional_se_cumprissem"] = taxa_nacional + lista["ganho_acumulado"]
    lista[["id_municipio", "nome", "sigla_uf", "rede_nome", "alunos", "taxa_real", "risco",
           "ganho_pp", "ganho_acumulado", "particao"]].to_csv(
        SAIDA_RISCO, index=False, encoding="utf-8")

    ganho_total = lista["ganho_pp"].sum()
    resumo = {
        "apontadas": int(apontadas.sum()), "confirmadas": len(lista),
        "alunos": int(lista["alunos"].sum()), "taxa_nacional": taxa_nacional,
        "taxa_se_todas_cumprissem": taxa_nacional + ganho_total,
        "quinze_primeiras_pp": float(lista["ganho_pp"].head(15).sum()),
        "quinze_primeiras_pct_do_ganho": float(100 * lista["ganho_pp"].head(15).sum() / ganho_total),
        "redes_para_metade_do_ganho": int((lista["ganho_pp"].cumsum() < ganho_total / 2).sum() + 1),
    }
    return lista, resumo


# ---------------------------------------------------------------------------
# Pergunta 3: quais regiões possuem padrões semelhantes
# ---------------------------------------------------------------------------
def responder_regioes(redes: pd.DataFrame) -> tuple[pd.DataFrame, list]:
    """Silhueta de cada região e sobreposição par a par entre elas.

    A sobreposição soma, faixa a faixa, a menor das duas frações: 100% seria a
    mesma distribuição, e 0% nenhuma rede na mesma faixa.
    """
    silhuetas = {}
    for regiao in REGIOES:
        d = redes[redes["nome_regiao"] == regiao]
        contagem, _ = np.histogram(d["p_cumprir_pct"], bins=PEDACOS_SILHUETA)
        silhuetas[regiao] = contagem / contagem.sum()

    perfil = []
    for regiao in REGIOES:
        d = redes[redes["nome_regiao"] == regiao]
        partes = pd.cut(d["p_cumprir_pct"], FAIXAS, include_lowest=True,
                        labels=ROTULOS_FAIXA).value_counts(normalize=True)
        linha = {"regiao": regiao, "redes": len(d), "alunos": int(d["alunos"].sum()),
                 "taxa_mediana_2024": d["taxa_real"].median(),
                 "prob_mediana_pct": d["p_cumprir_pct"].median()}
        linha.update({f"pct_{r}": 100 * partes.get(r, 0) for r in ROTULOS_FAIXA})
        linha.update({f"sobreposicao_{outra}":
                      100 * np.minimum(silhuetas[regiao], silhuetas[outra]).sum()
                      for outra in REGIOES})
        perfil.append(linha)
    tabela = pd.DataFrame(perfil).set_index("regiao")
    tabela.round(3).to_csv(SAIDA_REGIOES, encoding="utf-8")

    pares = sorted(((a, b, 100 * np.minimum(silhuetas[a], silhuetas[b]).sum())
                    for i, a in enumerate(REGIOES) for b in REGIOES[i + 1:]),
                   key=lambda x: x[2], reverse=True)
    return tabela, pares


# ---------------------------------------------------------------------------
# Pergunta 4: como prever quem pode não atingir metas futuras
# ---------------------------------------------------------------------------
def responder_faixas(redes: pd.DataFrame, redes_teste: pd.DataFrame) -> pd.DataFrame:
    """O resultado observado em cada faixa, no teste, e o país inteiro em cada faixa.

    O acerto por faixa só é honesto onde o modelo nunca viu a resposta, por isso
    vem do teste; a contagem de municípios cobre o país, com a ressalva da D-014.
    """
    faixa_teste = pd.cut(redes_teste["p_modelo_pct"], FAIXAS, include_lowest=True,
                         labels=ROTULOS_FAIXA)
    # o município recebe a média das suas redes, ponderada pelos alunos
    municipios = redes.groupby("id_municipio").apply(
        lambda d: pd.Series({"p_cumprir_pct": np.average(d["p_cumprir_pct"], weights=d["alunos"]),
                             "alunos": d["alunos"].sum()}), include_groups=False)
    faixa_municipio = pd.cut(municipios["p_cumprir_pct"], FAIXAS, include_lowest=True,
                             labels=ROTULOS_FAIXA)

    linhas = []
    for rotulo in ROTULOS_FAIXA:
        d = redes_teste[faixa_teste == rotulo]
        m = municipios[faixa_municipio == rotulo]
        linhas.append({
            "faixa": rotulo, "redes_teste": len(d), "alunos_teste": int(d["alunos"].sum()),
            "taxa_mediana_2024": d["taxa_real"].median(),
            "nao_cumpriram_pct": 100 * (d["bateu_meta"] == 0).mean(),
            "cumpriram_pct": 100 * (d["bateu_meta"] == 1).mean(),
            "municipios_pais": len(m), "alunos_pais": int(m["alunos"].sum()),
            "pct_dos_municipios": 100 * len(m) / len(municipios),
            "pct_dos_alunos": 100 * m["alunos"].sum() / municipios["alunos"].sum(),
        })
    tabela = pd.DataFrame(linhas).set_index("faixa")
    tabela.round(3).to_csv(SAIDA_FAIXAS, encoding="utf-8")
    return tabela


def acerto_por_trajetoria(redes_teste: pd.DataFrame) -> dict:
    """Quanto o modelo acerta nas redes que permaneceram e nas que mudaram de lado."""
    tinha = redes_teste["rede_taxa_ant"]
    com_2023 = redes_teste[tinha.notna()]
    estava_acima = com_2023["rede_taxa_ant"] >= META_2024
    ficou_acima = com_2023["bateu_meta"] == 1
    permaneceu = estava_acima == ficou_acima
    acertou = (com_2023["p_modelo_pct"] >= 100 * LIMIAR) == ficou_acima
    return {"permanencia_redes": int(permaneceu.sum()),
            "permanencia_acerto": 100 * acertou[permaneceu].mean(),
            "mudanca_redes": int((~permaneceu).sum()),
            "mudanca_acerto": 100 * acertou[~permaneceu].mean()}


# ---------------------------------------------------------------------------
# Pergunta 5: quais variáveis possuem maior influência
# ---------------------------------------------------------------------------
def responder_influencia(modelo, X_teste, y_teste, variaveis: list, semente: int,
                         fatores_analisados: list) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Importância por permutação, variável a variável e em bloco.

    Variáveis parentes dividem o crédito quando embaralhadas uma a uma, e por
    isso a medida em bloco embaralha o grupo inteiro de uma vez, preservando a
    relação interna e destruindo só a ligação do grupo com a resposta.
    """
    X = X_teste[variaveis]
    resultado = permutation_importance(modelo, X, y_teste,
                                       scoring=["neg_log_loss", "roc_auc"],
                                       n_repeats=REPETICOES_PERMUTACAO,
                                       random_state=semente, n_jobs=-1)
    individual = pd.DataFrame(
        {"piora_log_loss": resultado["neg_log_loss"].importances_mean,
         "piora_auc": resultado["roc_auc"].importances_mean}, index=X.columns)
    individual["papel"] = ["ponto de partida" if v in PONTO_DE_PARTIDA else "alavanca"
                           for v in individual.index]
    individual["nome"] = [FATORES.get(v, (NOMES_PONTO_DE_PARTIDA.get(v, v),))[0]
                          for v in individual.index]
    individual = individual.sort_values("piora_log_loss", ascending=False)
    individual.round(5).to_csv(SAIDA_INFLUENCIA, encoding="utf-8")

    gerador = np.random.default_rng(semente)
    prob = modelo.predict_proba(X)[:, 1]
    auc_cheio, perda_cheia = roc_auc_score(y_teste, prob), log_loss(y_teste, prob)
    taxas = [v for v in PONTO_DE_PARTIDA if v not in TERRITORIO]
    blocos = {"sem o ponto de partida": PONTO_DE_PARTIDA,
              "sem as alavancas": fatores_analisados,
              "sem o território": TERRITORIO,
              "sem as medidas de 2023": taxas}
    # a curadoria pode não selecionar alguma variável do ponto de partida; cada bloco
    # fica com as que existem no modelo, e um bloco vazio é descartado
    blocos = {nome: [c for c in colunas if c in X.columns] for nome, colunas in blocos.items()}
    blocos = {nome: colunas for nome, colunas in blocos.items() if colunas}
    linhas = [{"medida": "modelo completo", "variaveis_embaralhadas": len(variaveis),
               "auc": auc_cheio, "log_loss": perda_cheia,
               "queda_auc": 0.0, "piora_log_loss": 0.0}]
    for nome, colunas in blocos.items():
        medidas = []
        for _ in range(REPETICOES_PERMUTACAO):
            embaralhado = X.copy()
            embaralhado[colunas] = embaralhado[colunas].to_numpy()[
                gerador.permutation(len(embaralhado))]
            p = modelo.predict_proba(embaralhado)[:, 1]
            medidas.append((roc_auc_score(y_teste, p), log_loss(y_teste, p)))
        auc, perda = np.mean(medidas, axis=0)
        linhas.append({"medida": nome, "variaveis_embaralhadas": len(colunas),
                       "auc": auc, "log_loss": perda,
                       "queda_auc": auc_cheio - auc, "piora_log_loss": perda - perda_cheia})
    em_bloco = pd.DataFrame(linhas).set_index("medida")
    em_bloco.round(5).to_csv(SAIDA_BLOCOS, encoding="utf-8")
    return individual, em_bloco


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
    parser.add_argument("--amostra-dependencia", type=int, default=2000,
                        help="redes sorteadas para a dependencia parcial (padrao 2000)")
    args = parser.parse_args()

    cfg = carregar_config()
    inicio = datetime.now(timezone.utc)
    print(f"Aplicacao estrategica iniciada em {inicio.isoformat()}")
    print(f"Lake: gs://{cfg['bucket_lake']}/   meta de 2024: {META_2024}%")
    print()

    print("[1/7] carregando a base e reconstruindo o modelo registrado...", flush=True)
    lake = Lake(cfg)
    abt, desenho = carregar_base(lake)
    redes = agregar_por_rede(abt, desenho)
    X_final, y_final, _, _ = separar_redes(redes, ["treino", "validacao"], desenho["variaveis"])
    X_teste, y_teste, _, _ = separar_redes(redes, ["teste"], desenho["variaveis"])
    modelo, registro, semente = reconstruir_modelo(desenho, X_final, y_final, X_teste, y_teste)
    variaveis = registro["variaveis"]
    fatores_analisados = [v for v in variaveis if v not in PONTO_DE_PARTIDA]
    print(f"        {registro['familia']}, {len(variaveis)} variaveis; AUC no teste confere "
          f"com o registro ({registro['validacao']['auc']:.4f} na validacao)")

    # a previsão de todas as redes descreve o país; o desempenho vem só do teste (D-014)
    redes["p_cumprir"] = modelo.predict_proba(redes[desenho["variaveis"]])[:, 1]
    redes["p_cumprir_pct"] = 100 * redes["p_cumprir"]
    redes["risco"] = 100 * (1 - redes["p_cumprir"])
    redes_teste = redes[redes["particao"] == "teste"].copy()
    redes_teste["p_modelo_pct"] = 100 * modelo.predict_proba(X_teste)[:, 1]

    print("[2/7] pergunta 1: os fatores, com o ponto de partida fixo...", flush=True)
    fatores = responder_fatores(modelo, redes, desenho, desenho["variaveis"],
                                fatores_analisados, args.amostra_dependencia, semente)
    maior = fatores["efeito_pp"].abs().idxmax()
    print(f"        {len(fatores)} fatores; maior efeito: {fatores.loc[maior, 'nome']} "
          f"({fatores.loc[maior, 'efeito_pp']:+.1f} pp); {SAIDA_FATORES.name}")

    print("[3/7] pergunta 2: as redes de maior risco...", flush=True)
    lista, risco = responder_risco(lake, redes)
    print(f"        {risco['apontadas']:,} apontadas, {risco['confirmadas']:,} confirmadas, "
          f"{risco['alunos']:,} alunos; {SAIDA_RISCO.name}")

    print("[4/7] pergunta 3: a semelhanca entre as regioes...", flush=True)
    regioes, pares = responder_regioes(redes)
    print(f"        par mais parecido: {pares[0][0]} e {pares[0][1]} ({pares[0][2]:.0f}%); "
          f"mais diferente: {pares[-1][0]} e {pares[-1][1]} ({pares[-1][2]:.0f}%)")

    print("[5/7] pergunta 4: o resultado por faixa de probabilidade...", flush=True)
    faixas = responder_faixas(redes, redes_teste)
    trajetoria = acerto_por_trajetoria(redes_teste)
    print(f"        faixa mais baixa: {faixas.loc[ROTULOS_FAIXA[0], 'nao_cumpriram_pct']:.0f}% "
          f"nao cumpriram; faixa mais alta: "
          f"{faixas.loc[ROTULOS_FAIXA[-1], 'nao_cumpriram_pct']:.0f}%")

    print("[6/7] pergunta 5: a influencia de cada variavel...", flush=True)
    individual, em_bloco = responder_influencia(modelo, X_teste, y_teste, variaveis,
                                                semente, fatores_analisados)
    print(f"        lidera {individual.index[0]}; sem o ponto de partida a AUC cai para "
          f"{em_bloco.loc['sem o ponto de partida', 'auc']:.4f}")

    print("[7/7] consolidando...", flush=True)
    duracao = (datetime.now(timezone.utc) - inicio).total_seconds() / 60
    print()
    print("=" * 72)
    print("RESUMO DA EXECUCAO")
    print(f"  Modelo:               {registro['familia']}, {len(variaveis)} variaveis")
    print(f"  Redes:                {len(redes):,}, das quais "
          f"{len(redes_teste):,} na particao de teste")
    print()
    print("  P1  fatores de maior efeito, com o ponto de partida fixo")
    for v, f in fatores.head(3).iterrows():
        print(f"        {f['nome']:<42} {f['efeito_pp']:+.1f} pp "
              f"({f['regioes']} de 5 regioes)")
    print("  P2  risco educacional")
    print(f"        {risco['confirmadas']:,} redes confirmadas, {risco['alunos']:,} alunos")
    print(f"        taxa nacional {risco['taxa_nacional']:.1f}% -> "
          f"{risco['taxa_nacional'] + risco['quinze_primeiras_pp']:.2f}% com as 15 primeiras "
          f"({risco['quinze_primeiras_pct_do_ganho']:.0f}% do ganho)")
    print(f"        metade do ganho exige {risco['redes_para_metade_do_ganho']:,} redes; "
          f"todas levariam a {risco['taxa_se_todas_cumprissem']:.1f}%")
    print("  P3  regioes semelhantes")
    for a, b, valor in pares[:2]:
        print(f"        {a} e {b}: {valor:.0f}% de sobreposicao")
    print("  P4  resultado por faixa de probabilidade, no teste")
    for rotulo, linha in faixas.iterrows():
        print(f"        {rotulo:<14} {linha['redes_teste']:>4.0f} redes   "
              f"{linha['nao_cumpriram_pct']:>3.0f}% nao cumpriram")
    print(f"        acerto em permanencias {trajetoria['permanencia_acerto']:.0f}% contra "
          f"mudancas {trajetoria['mudanca_acerto']:.0f}%")
    print("  P5  influencia das variaveis")
    for v, linha in individual.head(3).iterrows():
        print(f"        {linha['nome']:<42} {linha['piora_log_loss']:.4f} de log-loss")
    print()
    for caminho in [SAIDA_FATORES, SAIDA_RISCO, SAIDA_REGIOES, SAIDA_FAIXAS,
                    SAIDA_INFLUENCIA, SAIDA_BLOCOS]:
        print(f"  Gravado:              {caminho.relative_to(RAIZ)}")
    print(f"  Duracao:              {duracao:.1f} min")
    print("  Status final:         SUCESSO")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())

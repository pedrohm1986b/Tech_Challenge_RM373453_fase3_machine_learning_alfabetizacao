# Predição e Inteligência Analítica para a Alfabetização no Brasil

Modelo supervisionado de machine learning para prever a alfabetização de alunos do 2º ano do ensino fundamental, construído sobre o data lake desenvolvido na Fase 2, com interpretabilidade e aplicação a políticas públicas educacionais.

> Tech Challenge da Fase 3 (Machine Learning) · Pós-graduação IA para Devs · FIAP POS TECH

---

## Sumário

1. [Contexto do problema](#1-contexto-do-problema)
2. [Objetivo analítico](#2-objetivo-analítico)
3. [Base de dados](#3-base-de-dados)
4. [Premissas e ressalvas](#4-premissas-e-ressalvas)
5. [Análise exploratória](#5-análise-exploratória) 🚧
6. [Etapas de modelagem](#6-etapas-de-modelagem) 🚧
7. [Escolha do algoritmo](#7-escolha-do-algoritmo) 🚧
8. [Métricas de avaliação](#8-métricas-de-avaliação) 🚧
9. [Interpretação dos resultados](#9-interpretação-dos-resultados) 🚧
10. [Insights encontrados](#10-insights-encontrados) 🚧
11. [Limitações do projeto](#11-limitações-do-projeto) 🚧
12. [Aplicação prática para políticas públicas](#12-aplicação-prática-para-políticas-públicas) 🚧
13. [Evoluções futuras](#13-evoluções-futuras) 🚧
14. [Como executar](#14-como-executar) 🚧
15. [Estrutura do repositório](#15-estrutura-do-repositório)

🚧 = seção em construção, preenchida conforme a evolução do projeto.

---

## 1. Contexto do problema

A alfabetização na idade certa é um dos fundamentos do desenvolvimento educacional e social do país, e o **Indicador Criança Alfabetizada** (INEP) acompanha o percentual de crianças alfabetizadas até o final do 2º ano do ensino fundamental, com o critério de proficiência mínima de 743 pontos na escala Saeb.

Compreender apenas os dados já observados, porém, não basta para apoiar decisões. Gestores públicos precisam **antecipar riscos**, identificar territórios vulneráveis e saber **quais fatores pesam mais** sobre o resultado educacional, para direcionar recursos antes que o ciclo se encerre. É esse deslocamento — do dado descritivo para a inteligência preditiva — que este projeto trata.

O contexto completo do indicador, seus impactos e a metodologia de cálculo estão documentados na [fase anterior deste trabalho](https://github.com/pedrohm1986b/Tech_Challenge_RM373453_pipeline_alfabetizacao).

## 2. Objetivo analítico

Desenvolver um **modelo supervisionado de classificação** capaz de prever se um aluno será considerado **alfabetizado ou não alfabetizado**, a partir de variáveis educacionais, territoriais e socioeconômicas, com três exigências que orientam todo o desenho:

- **Pipeline reproduzível:** pré-processamento integrado ao modelo, com tratamento explícito de valores faltantes, transformação de variáveis e prevenção de vazamento de dados (*data leakage*);
- **Interpretabilidade:** identificar quais variáveis mais influenciam a predição, com Feature Importance e SHAP;
- **Aplicação estratégica:** responder perguntas de negócio (fatores de maior impacto, municípios em maior risco, territórios com padrões semelhantes e projeção de atingimento de metas), não apenas maximizar métricas.

## 3. Base de dados

A base provém do **data lake construído na Fase 2** deste Tech Challenge, alimentado pelo dataset público *Avaliação da Alfabetização* (INEP, via Base dos Dados) e pelo diretório de municípios do IBGE, organizado em Arquitetura Medalhão:

| Camada de origem | Grão | Papel neste projeto |
|---|---|---|
| **Silver** | aluno avaliado | fornece a **unidade de predição** e a variável resposta |
| **Gold** | município × ano | fornece o **contexto** territorial e temporal (indicador, meta, distância, participação, região) |
| **Fontes externas** | município | enriquecimento socioeconômico (IDHM, Censo Escolar, FUNDEB e afins) |

O detalhamento da divisão de papéis entre as camadas está na seção seguinte.

## 4. Premissas e ressalvas

🚧 Em construção. Documentará a premissa do grão de modelagem (a linha vem da Silver, o contexto vem da Gold), o tratamento de vazamento por agregação temporal, a população de treino (alunos presentes na avaliação) e o papel do peso amostral. As decisões estão registradas no [diário de decisões](docs/decisoes.md).

## 5. Análise exploratória

🚧 Em construção.

## 6. Etapas de modelagem

🚧 Em construção.

## 7. Escolha do algoritmo

🚧 Em construção.

## 8. Métricas de avaliação

🚧 Em construção.

## 9. Interpretação dos resultados

🚧 Em construção.

## 10. Insights encontrados

🚧 Em construção.

## 11. Limitações do projeto

🚧 Em construção.

## 12. Aplicação prática para políticas públicas

🚧 Em construção.

## 13. Evoluções futuras

🚧 Em construção.

## 14. Como executar

🚧 Em construção.

## 15. Estrutura do repositório

```
├── data/                  # dados locais de trabalho (não versionados)
├── notebooks/             # desenvolvimento e análise, célula a célula
├── src/
│   ├── preprocessing/     # preparação de dados e engenharia de atributos
│   ├── modeling/          # treinamento e otimização dos modelos
│   ├── evaluation/        # métricas, validação e interpretabilidade
│   └── visualization/     # gráficos e visualizações
├── reports/               # relatórios e resultados consolidados
├── images/                # imagens utilizadas na documentação
├── docs/                  # diário de decisões e documentação técnica
├── config/                # configuração de acesso ao lake (exemplo versionado)
├── requirements.txt
└── README.md
```

---

Desenvolvido por Pedro Henrique Martinez Bertolo (RM373453) · Tech Challenge Fase 3 · FIAP POS TECH

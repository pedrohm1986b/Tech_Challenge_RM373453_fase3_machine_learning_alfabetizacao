# Predição e Inteligência Analítica para a Alfabetização no Brasil

Modelo supervisionado de machine learning para prever a alfabetização de alunos do 2º ano do ensino fundamental, construído sobre o data lake desenvolvido na Fase 2, com interpretabilidade e aplicação a políticas públicas educacionais.

> Tech Challenge da Fase 3 (Machine Learning) · Pós-graduação IA para Devs · FIAP POS TECH

---

## Sumário

1. [Contexto do problema](#1-contexto-do-problema)
2. [Objetivo analítico](#2-objetivo-analítico)
3. [Base de dados](#3-base-de-dados)
4. [Premissas e ressalvas](#4-premissas-e-ressalvas) 🚧
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

A base provém do **data lake construído na Fase 2** deste Tech Challenge, alimentado pelo dataset público *Avaliação da Alfabetização* (INEP, via Base dos Dados) e pelo diretório de municípios do IBGE, organizado em Arquitetura Medalhão. Cada camada do lake tem um grão e um propósito próprios, e a escolha de qual delas sustenta a modelagem é a primeira decisão do projeto.

### 3.1 O grão da modelagem

O objetivo analítico é prever a alfabetização **de um aluno**, e um modelo supervisionado exige uma linha por unidade a prever. As duas camadas disponíveis respondem a perguntas diferentes:

| Camada | Grão | Volume | Natureza |
|---|---|---:|---|
| **Silver** | aluno avaliado | 3.866.814 linhas | dados curados no grão do fato |
| **Gold** | município × ano | 11.629 linhas | produto de dados agregado, pronto para consumo |

A camada Gold foi construída como **produto de dados**: sua taxa de alfabetização é a média ponderada `Σ(peso × alfabetizado) / Σ(peso)` por município e ano, modelada para consulta, painéis e comparação com metas. Ela responde *"como está o município"*. A camada Silver preserva o registro individual e responde *"o que aconteceu com cada aluno"*, que é a pergunta deste projeto.

Três razões sustentam a escolha da Silver como base da modelagem:

1. **A agregação é irreversível.** A taxa municipal é a média daquilo que se quer explicar: a variação entre alunos da mesma rede e do mesmo município foi dissolvida nela e não pode ser recuperada. Modelar sobre a Gold seria resolver outro problema (regressão sobre a taxa), com três ordens de grandeza a menos de observações;
2. **A arquitetura medalhão prevê esse uso.** A camada Silver é, por definição, a camada limpa, validada e integrada, indicada para engenharia de atributos e machine learning; a camada Gold é a camada agregada, destinada ao consumo analítico;
3. **Evitar vazamento de dados exige separar os papéis.** A taxa municipal de um ano é calculada com os próprios alunos daquele ano. Usá-la como variável explicativa de um desses alunos entregaria a resposta ao modelo pela porta dos fundos.

### 3.2 O papel de cada camada

A Gold não fica de fora: ela muda de papel. As variáveis territoriais e temporais que o objetivo analítico exige não existem no grão do aluno, e sim no do município. É a Gold que as fornece, sempre **defasadas em relação ao ciclo do aluno** (a situação do município no ciclo anterior), o que também neutraliza o vazamento descrito acima.

| Origem | Papel na modelagem | O que entrega |
|---|---|---|
| **Silver** | a linha e a variável resposta | aluno, presença, proficiência, peso amostral, rede, município e ano |
| **Gold** | o contexto territorial e temporal, defasado | indicador municipal do ciclo anterior, meta pactuada, distância da meta, participação, UF e região |
| **Fontes externas** | o enriquecimento socioeconômico | IDHM, PIB per capita, Censo Escolar, FUNDEB e afins, por município |

Em síntese: **o aluno vem da Silver, o contexto dele vem da Gold.** O registro completo dessa decisão, com as alternativas consideradas, está na **D-001** do [diário de decisões](docs/decisoes.md).

## 4. Premissas e ressalvas

Três consequências da decisão sobre o grão de modelagem (seção 3) valem como premissas declaradas deste trabalho:

- **A população modelada são os alunos presentes na avaliação.** Alunos ausentes não têm proficiência registrada e, portanto, não têm variável resposta observável. A flag de presença criada na fase anterior isola essa população de forma explícita;
- **A não participação fica fora do escopo preditivo.** O modelo prevê a alfabetização de quem realizou a prova. O efeito da ausência sobre o indicador foi tratado na fase anterior por uma taxa ajustada, e permanece registrado aqui como limitação;
- **O peso amostral exige decisão própria.** O campo `peso_aluno`, calibrado pelo INEP, pode entrar como ponderação no treinamento ou ser reservado à leitura agregada dos resultados. A escolha afeta a comparabilidade com as taxas oficiais e será registrada no diário de decisões.

🚧 As demais premissas serão acrescentadas conforme as etapas de preparação e modelagem avançarem.

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

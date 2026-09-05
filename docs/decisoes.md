# Diário de Decisões

Registro das decisões relevantes do projeto, com contexto e justificativa. Cada decisão indica a data, a escolha realizada e as alternativas consideradas. Este documento alimenta as seções de premissas, limitações e interpretação do README.

A numeração recomeça nesta fase; as decisões da fase anterior (D-001 a D-014) estão no [repositório da pipeline de dados](https://github.com/pedrohm1986b/Tech_Challenge_RM373453_pipeline_alfabetizacao/blob/main/docs/decisoes.md) e são citadas quando relevantes.

---

## D-001 · Grão de modelagem: a linha vem da Silver, o contexto vem da Gold

**Data:** 12/07/2026 · **Etapa:** Fundação

**Decisão:** a base de modelagem combina duas camadas do data lake da Fase 2, cada uma no seu papel. A **camada Silver** fornece a unidade de predição (o aluno avaliado) e a variável resposta. A **camada Gold** fornece as variáveis de contexto territorial e temporal (indicador municipal, meta pactuada, distância da meta, participação e região), sempre defasadas em relação ao ciclo do aluno. As fontes externas acrescentam o enriquecimento socioeconômico, no grão do município.

**Contexto:** o enunciado determina que os dados sejam provenientes da camada Gold construída na Fase 2 e, ao mesmo tempo, que o modelo preveja se **um aluno** será alfabetizado. A Gold, porém, é um produto de dados agregado por município e ano (11.629 linhas), enquanto a unidade de predição pedida existe apenas na Silver (3,86 milhões de alunos avaliados, com a classificação de alfabetização disponível).

**Justificativa:**

1. **O grão da unidade de predição é dado pelo problema.** Um modelo supervisionado exige uma linha por unidade a prever. Treinar sobre a Gold resolveria um problema diferente do enunciado (regressão sobre a taxa municipal), com três ordens de grandeza a menos de observações;
2. **A agregação é irreversível.** A taxa municipal é a média ponderada daquilo que se quer explicar; a variação entre alunos da mesma rede e do mesmo município foi dissolvida nela e não pode ser recuperada;
3. **Usar a taxa do próprio ciclo como atributo do aluno seria vazamento de dados.** A taxa municipal de um ano é calculada com os próprios alunos daquele ano. Por isso as variáveis municipais entram defasadas (ciclo anterior) e a separação entre treino, validação e teste respeita o corte temporal. O enunciado exige o tratamento de *data leakage*, e esta é a principal fonte dele neste desenho;
4. **A arquitetura medalhão prevê esse uso.** A camada Silver é a camada limpa, validada e integrada, indicada para engenharia de atributos e machine learning; a camada Gold é a camada pronta para consumo, agregada para relatórios, painéis e análise de negócio;
5. **A Gold permanece insumo obrigatório, com papel definido.** As variáveis territoriais e temporais pedidas pelo enunciado não existem no grão do aluno: existem no grão do município, e é a Gold que as fornece.

**Alternativas consideradas:** modelar diretamente sobre a Gold, prevendo a taxa municipal (descartada por resolver problema distinto do enunciado e perder a variação individual); usar a Silver isoladamente, sem contexto municipal (descartada por abrir mão das variáveis territoriais e socioeconômicas que o enunciado pede e que sustentam a aplicação estratégica).

**Consequências registradas:** a população de treino são os alunos presentes na avaliação, únicos com variável resposta observável (a flag `presente` da decisão D-011 da fase anterior já os isola); o uso do peso amostral `peso_aluno` exige decisão própria; e a não participação permanece fora do escopo preditivo, constando nas limitações do projeto.

---

## Decisões pendentes

Os identificadores são atribuídos apenas quando a decisão é tomada, para evitar renumerações.

| Tema | Etapa prevista |
|---|---|
| Uso do peso amostral no treinamento | Modelagem |
| Estratégia de validação e corte temporal | Modelagem |
| Algoritmo de referência e critério de escolha | Modelagem |
| Métrica principal de avaliação | Avaliação |
| Fontes externas de enriquecimento a incorporar | Preparação de dados |

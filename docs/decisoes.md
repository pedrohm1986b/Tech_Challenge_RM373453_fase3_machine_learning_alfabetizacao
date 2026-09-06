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

## D-002 · Dependência entre as fases: verificação de contrato, sem reexecução

**Data:** 12/07/2026 · **Etapa:** Base analítica

**Decisão:** este projeto **verifica** a existência e o formato das camadas do data lake construído na fase anterior, mas **não reexecuta** aquela pipeline. A primeira seção de cada artefato confere o contrato (tabelas, partições e colunas exigidas) e interrompe a execução com mensagem orientando o que rodar, caso algo falte. O pré-requisito fica documentado na seção Como Executar do README, com o endereço do repositório anterior.

**Contexto:** a pipeline de dados da fase anterior é *upstream* deste projeto de machine learning. Havia a alternativa de embutir a execução daquela pipeline no início dos notebooks, para garantir que as camadas existissem.

**Justificativa:** reexecutar a pipeline de origem acoplaria os dois repositórios (qualquer mudança lá quebraria a execução aqui), duplicaria a responsabilidade sobre a ingestão e acrescentaria cerca de quinze minutos a cada rodada. A verificação de contrato entrega a mesma garantia com falha explicativa: quem executa sabe exatamente o que falta e onde obter. É o mesmo padrão já adotado na fase anterior, em que a transformação confere a existência da camada anterior e orienta a execução do script correspondente.

**Alternativas consideradas:** embutir a execução da pipeline anterior (descartada pelo acoplamento e pelo custo de tempo); versionar os dados neste repositório (descartada por contrariar a separação entre código e dados adotada desde a fase anterior). Fica registrada, para a etapa de documentação, a possibilidade de abrir a leitura pública do bucket, o que dispensaria a execução da fase anterior por quem apenas avalia o projeto.

---

## D-003 · Contexto no grão da rede do aluno, além do município

**Data:** 12/07/2026 · **Etapa:** Base analítica

**Decisão:** o contexto defasado que acompanha cada aluno é montado em dois níveis: o desempenho da **rede de ensino que o atende** (estadual ou municipal) no ciclo anterior, e o retrato do **município como um todo** (rede pública agregada), acrescidos da diferença entre os dois. A versão inicial usava apenas o agregado municipal e foi substituída.

**Contexto:** a camada Gold da fase anterior consolida o indicador na rede pública agregada, por decisão daquela fase, em que o objetivo era comparar territórios com as metas pactuadas. Ao reaproveitá-la como contexto de um modelo no grão do aluno, todos os alunos de um mesmo município recebiam valores idênticos, independentemente da rede em que estudam.

**Justificativa:** a verificação nos dados mostrou que as redes divergem de forma expressiva dentro do mesmo município. Nos 1.083 municípios em que as redes estadual e municipal foram medidas em 2023, a diferença entre suas taxas tem desvio padrão de 19,5 pontos percentuais e supera 10 pontos em 58% dos casos. Tratar essas realidades como uma só descartaria variação relevante e atribuiria ao aluno um contexto que não é o seu. Além do ganho de precisão, o contexto por rede **amplia a cobertura**: a rede municipal está presente em praticamente todos os municípios avaliados, e a junção pelos dois níveis alcança cerca de 98% dos alunos, contra 89,2% do agregado municipal.

**Alternativas consideradas:** manter apenas o agregado municipal, herdado da fase anterior (descartada pela perda de variação e de cobertura); usar apenas o contexto da rede, sem o municipal (descartada porque o município acrescenta participação, porte e clima educacional do território, que a rede isolada não expressa).

**Consequência registrada:** a rede privada, com 24 alunos nesta base, não possui contexto de rede correspondente no ciclo anterior. Somada à ausência de massa estatística, isso reforça seu tratamento como categoria residual na etapa de pré-processamento.

---

## D-004 · Porte do ciclo corrente como variável, por ser informação prévia

**Data:** 12/07/2026 · **Etapa:** Base analítica

**Decisão:** o porte da rede e do município no **ciclo que se quer prever** entra como variável explicativa, ao lado das variáveis defasadas. O porte é medido pelo número de alunos **avaliáveis**, isto é, os registros do cadastro da avaliação, presentes e ausentes. O número de alunos **presentes** do ciclo corrente permanece fora do modelo.

**Contexto:** a versão inicial da tabela analítica trazia apenas o porte do ciclo anterior, por precaução contra vazamento. A revisão da regra mostrou que a precaução era excessiva em um caso e insuficiente em outro.

**Justificativa:** o critério que separa uma variável legítima de um vazamento é o momento em que a informação passa a existir, e não o ciclo a que ela se refere. O total de alunos a avaliar vem do cadastro escolar e está definido **antes** da aplicação da prova, sem qualquer dependência do resultado: é informação prévia, como a meta pactuada. Já o total de **presentes** só se conhece depois da aplicação, porque depende do comparecimento, e por isso continua excluído. Além da correção conceitual, o porte corrente resolve duas fragilidades do porte defasado: ele não envelhece entre ciclos e é calculado da própria base de alunos, alcançando a totalidade das observações, contra 76,9% do defasado, que depende da disponibilidade dos microdados do ano anterior.

**Alternativas consideradas:** manter apenas o porte defasado (descartada pela perda de cobertura e pelo envelhecimento da informação); usar o total de presentes do ciclo corrente (descartada por ser informação posterior à aplicação da prova).

**Consequência registrada:** da mesma estrutura nasce a fração do município atendida pela rede do aluno, que distingue quem estuda na rede predominante do território de quem está em uma rede minoritária. As três variáveis de porte permanecem como candidatas: a correlação linear com a variável resposta é próxima de zero para todas elas, e a análise exploratória avaliará se há efeito não linear que justifique mantê-las.

---

## Decisões pendentes

Os identificadores são atribuídos apenas quando a decisão é tomada, para evitar renumerações.

| Tema | Etapa prevista |
|---|---|
| Uso do peso amostral no treinamento | Modelagem |
| Seleção de variáveis: quais derivadas permanecem, dada a redundância determinística | Análise exploratória |
| Estratégia de validação e corte temporal | Modelagem |
| Algoritmo de referência e critério de escolha | Modelagem |
| Métrica principal de avaliação | Avaliação |
| Fontes externas de enriquecimento a incorporar | Preparação de dados |

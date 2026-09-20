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

## D-005 · Fontes externas consultadas na origem, com industrialização recomendada

**Data:** 12/07/2026 · **Etapa:** Base analítica

**Decisão:** as fontes públicas usadas no enriquecimento (Censo Escolar, PIB municipal, Atlas do Desenvolvimento Humano, Atlas da Violência e Sistema de Informação sobre Mortalidade) são consultadas diretamente na origem, com a agregação por município e rede feita na própria consulta, e o resultado agregado é guardado em uma área de modelagem do data lake. Elas **não** passam pelas camadas do medalhão nesta fase. Fica registrada a recomendação de incorporá-las à arquitetura medalhão quando forem promovidas a uso recorrente.

**Contexto:** o data lake construído na fase anterior organiza as fontes em camadas: a Bronze preserva o dado bruto como chegou, e a Silver entrega o dado curado e integrado. As fontes externas deste projeto seguem caminho diferente: são lidas da origem, agregadas na consulta e materializadas já no formato de uso.

**Justificativa:** esta etapa é de **prototipação analítica**, e o propósito das fontes externas é responder a uma pergunta ainda em aberto, se elas carregam informação útil para prever a alfabetização. Industrializar a ingestão de cinco fontes antes de saber quais permanecerão no modelo final significaria construir infraestrutura para dados que podem ser descartados na seleção de variáveis. O resultado agregado é materializado no lake e reutilizado nas execuções seguintes, o que preserva a reprodutibilidade sem repetir o custo de consulta. A separação de papéis é a usual entre ciência e engenharia de dados: a análise demonstra o valor da variável, a engenharia a torna um ativo permanente.

**Recomendação registrada para a evolução do projeto:** as fontes que se mostrarem relevantes na análise de importância dos modelos devem ser incorporadas ao data lake pelo time de engenharia de dados, seguindo o padrão da fase anterior. A ingestão levaria o dado bruto no grão de origem para a camada Bronze, com carimbo de ingestão e reconciliação de contagens; a agregação por município e rede, hoje embutida na consulta, passaria a ser uma transformação explícita na camada Silver. Isso preservaria o grão original, permitindo reagregações futuras sem novo acesso à fonte, e tornaria auditável a lógica de transformação.

**Alternativas consideradas:** ingerir as cinco fontes na camada Bronze antes de conhecer sua utilidade (descartada pelo custo de construir infraestrutura para variáveis possivelmente descartáveis); consultar a origem a cada execução, sem materializar (descartada por comprometer a reprodutibilidade e repetir custo de leitura).

---

## D-006 · Seleção de variáveis guiada por hipóteses declaradas

**Data:** 07/09/2026 · **Etapa:** Base analítica

**Decisão:** toda variável explicativa da base precisa responder a uma hipótese declarada previamente em [`hipoteses.md`](hipoteses.md), com mecanismo proposto, previsão e critério de falseamento escritos **antes** da medição. O vínculo é materializado como a coluna `hipotese` do dicionário de dados, e uma trava no código interrompe a execução se alguma variável ficar sem hipótese atribuída.

**Contexto:** a primeira rodada de enriquecimento reuniu trinta e uma variáveis externas escolhidas por plausibilidade. Ao mapeá-las contra hipóteses, ficou evidente que algumas haviam entrado sem mecanismo articulado: PIB per capita, renda e IDHM não cabiam em nenhuma das hipóteses formuladas, e precisaram de uma nova (H9) escrita para acomodá-las. Antes disso, eu vinha produzindo diagnósticos avulsos sobre a base sem hipótese que os justificasse.

**Justificativa:** análise exploratória sem hipótese prévia é pescaria: com quarenta e nove variáveis e 1,85 milhão de observações, sempre haverá algum padrão estatisticamente notável, e a interpretação passa a ser construída depois de ver o resultado. Declarar antes o que se espera, e o que falsearia a expectativa, é o que separa achado de coincidência garimpada. Há um caso concreto disso registrado na H4: anotei antes de medir que um gradiente positivo para tamanho de turma deve ser lido como marcador de urbanidade, e não como "turma grande ajuda", justamente para não reinterpretar o sinal depois de vê-lo.

O ganho prático é duplo. A análise exploratória passa a se organizar por hipótese em vez de por tipo de gráfico, e cada resultado remete à pergunta que responde. E as hipóteses ficam disponíveis para a etapa de interpretabilidade: a importância das variáveis no modelo pode ser lida contra o que se esperava, em vez de narrada a posteriori.

**Consequência registrada:** as nove hipóteses cobrem quarenta variáveis; as nove restantes são controles de escala, território e rede, rotulados como tal. A H8 (inércia territorial) foi declarada explicitamente como hipótese **concorrente**: se ela dominar e as demais não acrescentarem poder preditivo, o resultado será reportado como achado, e não dissolvido na métrica agregada.

---

## D-007 · Exclusão da distribuição por níveis de proficiência, por vazamento

**Data:** 07/09/2026 · **Etapa:** Base analítica

**Decisão:** as nove colunas `proporcao_aluno_nivel_0` a `proporcao_aluno_nivel_8` da camada Silver, que descrevem a distribuição dos alunos pelos níveis de proficiência, **não** entram na base analítica.

**Contexto:** essas colunas descrevem a forma da distribuição de desempenho da rede, e não apenas a sua média. Seriam um enriquecimento valioso do contexto: duas redes com a mesma taxa de alfabetização podem ter distribuições muito distintas, uma concentrada perto do corte e outra polarizada.

**Justificativa:** a verificação nos dados mostrou que elas existem **apenas para o ciclo de 2024**, com zero linhas preenchidas em 2023. Como o contexto do modelo é defasado por construção, usá-las significaria descrever o aluno com a distribuição de desempenho do próprio ciclo que se quer prever, calculada a partir das notas dos próprios alunos que se está tentando classificar. É vazamento tão direto quanto usar a proficiência, apenas menos evidente, porque chega disfarçado de "contexto da rede".

**Registro do método:** este caso é a evidência concreta do tratamento de vazamento que o trabalho exige. A defesa não foi uma declaração genérica de cuidado: foram nove variáveis atraentes, identificadas, verificadas contra a disponibilidade temporal e descartadas por essa razão. O mesmo critério da D-004 se aplica aqui, na direção oposta: o que decide não é o ano da fonte, e sim o momento em que a informação passa a existir.

**Consequência registrada:** o campo `meta_taxa` da mesma tabela também só existe em 2024, e é obtido da camada Gold, que é a sua fonte curada.

---

## D-008 · Censo Escolar restrito às escolas em atividade

**Data:** 13/09/2026 · **Etapa:** Base analítica

**Decisão:** as variáveis de escola são calculadas apenas sobre as escolas em atividade no Censo Escolar (`tipo_situacao_funcionamento = 1`).

**Contexto:** o cadastro do Censo Escolar mantém as escolas paralisadas e extintas, que são 16,5% das escolas das redes estadual e municipal, com matrícula, salas e campos de infraestrutura em branco. A primeira versão da consulta as contava como escolas sem água, sem energia e sem biblioteca.

**Justificativa:** o defeito puxava para baixo as variáveis de infraestrutura em 43% das combinações de município e rede; na energia elétrica, a distorção mediana nessas combinações era de 25 pontos percentuais. Uma escola que não funciona não descreve a oferta da rede. O defeito foi encontrado na análise exploratória, ao comparar a infraestrutura das redes estadual e municipal.

**Alternativas consideradas:** manter as escolas inativas, tratando os campos em branco como ausentes (descartada: elas continuariam contando no número de escolas da rede, sem oferecer ensino).

---

## D-009 · Indicadores docentes da edição de 2022

**Data:** 13/09/2026 · **Etapa:** Base analítica

**Decisão:** a formação, a regularidade e o esforço docente e as horas-aula diárias vêm da edição de 2022 dos indicadores educacionais do INEP, e não da de 2023.

**Contexto:** a publicação de 2023 e 2024 dessa tabela está corrompida na origem: os cinco grupos de formação docente, que deveriam somar 100%, somam entre 287% e 500%, e as horas-aula aparecem zeradas. As edições de 2019 a 2022 estão consistentes, com somas exatas de 100%.

**Justificativa:** 2022 é a edição íntegra mais recente, e continua anterior à avaliação de 2024. Uma trava no código confere a soma dos grupos de formação antes de aceitar o dado, para que uma publicação corrompida não entre na base sem aviso.

**Alternativas consideradas:** usar 2023 com correção proporcional das somas (descartada: não há como saber qual parte do dado está errada).

---

## D-010 · Conjunto de variáveis para a modelagem

**Data:** 14/09/2026 · **Etapa:** Análise exploratória

**Decisão:** seguem para a modelagem 43 das 65 variáveis explicativas (40 numéricas e 3 categóricas), acompanhadas de 4 indicadores de ausência. A lista, com o motivo de cada entrada e saída, está em `reports/variaveis_modelagem.csv`. Saem 19 variáveis redundantes e as 3 da H5.

**Contexto:** a análise exploratória mostrou que as 62 variáveis numéricas se reduzem a 43 conceitos, agrupando as variáveis cujas correlações entre si passam todas de 0,8 (seção 10.1). Com todas as variáveis, 19 têm fator de inflação da variância acima de 10.

**Justificativa:** um representante por grupo elimina a multicolinearidade (o maior fator de inflação cai para 7,7) e evita que a importância de um conceito se reparta entre variáveis redundantes. O representante é a variável mais correlacionada com a resposta, com três trocas: a taxa da rede em 2023 no lugar da taxa ajustada do município, porque falta para 0,9% dos alunos do treino, contra 23,8%, e distingue a rede estadual da municipal (D-003); a população no lugar do número de escolas, por ser mais fácil de interpretar; e a densidade demográfica no lugar do peso da agropecuária, por ser a medida direta do conceito da H1. A H5 sai por ser a única hipótese sem evidência de relação com a resposta (seção 11.2). A H8 permanece: é uma defasagem da própria resposta, legítima porque existe antes da prova, e é a referência contra a qual se mede o ganho das demais hipóteses (D-006).

**Alternativas consideradas:** manter as 62 variáveis numéricas (descartada pela redundância); escolher variável a variável pela correlação com a resposta (descartada: a unidade de decisão é o conceito e a hipótese); excluir também os conceitos sem gradiente de outras hipóteses (descartada: a análise é bivariada, e o que eles acrescentam em combinação com os demais é medido na modelagem).

---

## D-011 · Tratamento das variáveis no pipeline

**Data:** 14/09/2026 · **Etapa:** Análise exploratória

**Decisão:**

1. as variáveis ausentes são imputadas pela mediana da UF, ajustada só na partição de treino, com um indicador de ausência por bloco do desempenho anterior: rede sem histórico, município sem indicador oficial, município sem microdados e município sem meta;
2. nos modelos lineares, as variáveis com assimetria positiva acima de 2 recebem transformação logarítmica e, em seguida, todas as variáveis numéricas são padronizadas, com média zero e desvio um calculados no treino; nos modelos de árvore, nenhuma das duas é aplicada;
3. rede, UF e região recebem codificação one-hot; a UF não vista no treino, o Distrito Federal, recebe zero nas colunas de UF, e a região supre a informação;
4. os 24 alunos da rede privada ficam fora da modelagem;
5. o Rio Grande do Sul é mantido, sem indicador próprio, e o desempenho do modelo no estado é examinado à parte na avaliação.

**Justificativa:** as ausências vêm em blocos de origem conhecida e carregam pouca informação sobre o desfecho (diferença de 1,7 a 3,8 pontos na taxa, seção 7.4), o que justifica imputar e sinalizar, e não descartar; a UF está completa, o que torna a imputação por estado aplicável a todos os alunos. O logaritmo e a padronização não são alternativas, e sim passos complementares: a padronização põe as variáveis na mesma escala, o que a regularização da regressão logística exige, mas não muda a forma da distribuição; o logaritmo comprime as caudas longas, que de outro modo dariam a poucos municípios muito grandes, ricos ou densos um peso desproporcional sobre o coeficiente. Os modelos de árvore usam apenas a ordem dos valores e dispensam os dois. A rede privada não tem contexto de rede no ciclo anterior nem massa estatística (D-003). A queda do Rio Grande do Sul em 2024 coincide com as enchentes do ano da avaliação, e a UF já identifica o estado.

**Alternativas consideradas:** imputar pela mediana nacional (descartada: os municípios de um mesmo estado compartilham política e contexto); excluir os alunos com alguma ausência (descartada: 26,3% da base); criar um indicador para o Rio Grande do Sul (descartada por ser redundante com a UF); usar só a padronização, sem logaritmo (descartada: a padronização não corrige a assimetria).

---

## D-012 · Modelo escolhido e uso no nível da rede

**Data:** 14/09/2026 · **Etapa:** Modelagem

**Decisão:** o modelo escolhido é a regressão logística, com C de 0,167, sobre as 43 variáveis da D-010 e o pré-processamento da D-011. Ele prevê a probabilidade de cada aluno ser alfabetizado, e é usado e avaliado no nível da rede em cada município: a taxa prevista de cada rede é comparada com a meta nacional pactuada para 2024, de 59,9%.

**Contexto:** três famílias de modelos (regressão logística, gradient boosting e Random Forest) foram comparadas em 42 combinações de hiperparâmetros, com validação cruzada em cinco partes agrupadas por município, dentro da partição de treino. As três empataram dentro da oscilação da validação: log-loss entre 0,6324 e 0,6335, com desvio de cerca de 0,009 entre as partes. A AUC máxima possível com estas variáveis, a da melhor previsão possível, é de 0,683 na validação cruzada e de 0,671 na partição de validação, onde a logística alcança 0,644.

**Justificativa:** o critério foi declarado antes de ver a partição de validação: vence a menor log-loss na validação cruzada, e a regressão logística é escolhida se ficar a menos de um desvio da vencedora. O gradient boosting teve a menor log-loss, e a logística ficou a 0,0011 dele. Ela é a mais simples e interpretável das três, e as suas probabilidades são calibradas: a maior distância entre a taxa prevista e a observada, em dez faixas de alunos, é de 3,9 pontos. O uso no nível da rede decorre dos dados: todas as variáveis são iguais para os alunos da mesma rede no mesmo município, e por isso a previsão aluno a aluno tem valor limitado, enquanto a taxa prevista por município erra 6,9 pontos na mediana, contra 9,0 de repetir o resultado do ano anterior.

**Escolhas de implementação registradas:**

1. o treino é feito sobre os grupos de município e rede, com duas linhas por grupo, uma por classe, e peso igual ao número de alunos de cada uma; o resultado é o mesmo do treino aluno a aluno, em uma fração do tempo;
2. no treino, os pesos são normalizados para média 1, para que a regularização corresponda ao número de grupos, que é o número efetivo de observações distintas;
3. o gradient boosting é o do scikit-learn, da mesma família do XGBoost, o que dispensa dependência externa;
4. as configurações da análise por bloco de hipótese são comparadas parte a parte, porque todas usam as mesmas cinco partes;
5. o peso amostral do INEP não entra no treino; ele entra quando as taxas previstas são agregadas e comparadas às taxas oficiais, que são ponderadas por ele.

**Alternativas consideradas:** o gradient boosting (menor log-loss, por uma diferença dentro da oscilação da validação; descartado pelo critério); o XGBoost (não instalado; a troca é de uma linha, se necessária); um modelo com o município ou a rede como linha (descartado: o enunciado pede a previsão do aluno, e a agregação dessas previsões responde às perguntas sobre redes e municípios).

---

## D-013 · Alvo no nível da rede

**Data:** 15/09/2026, revista em 19/09/2026 · **Etapa:** Modelagem (parte 2)

**Decisão:** o modelo do `desenv_04` muda a unidade de predição e a pergunta. A linha passa a ser a **rede de um município** (municipal ou estadual) e a resposta passa a ser **se a taxa de alfabetização daquela rede em 2024 alcançou a meta nacional de 59,9%**, a pactuada no Compromisso Nacional Criança Alfabetizada. A previsão continua probabilística: o modelo devolve a probabilidade de a rede cumprir a meta. As variáveis, o tratamento do território e a família do modelo da rede estão na D-015.

**Contexto:** o `desenv_03` mostrou que no grão do aluno as variáveis explicam pouco, porque todas elas são iguais para os alunos da mesma rede no mesmo município: cerca de 90% da diferença de resultado está entre alunos da mesma rede, e a AUC máxima possível é de 0,701 no teste. A D-012 já usava o modelo agregado por rede para responder às perguntas de negócio. A mudança aqui é tirar a consequência disso: se a decisão do gestor é sobre a rede, e a leitura é a comparação com a meta, o modelo deve prever diretamente isso. São 6.535 redes com resposta conhecida, 3.893 delas no treino, e 42,9% ficaram abaixo da meta em 2024. O país ficou em 59,2%, logo abaixo da meta.

**Justificativa:** cada modelo, medido no seu próprio escopo e na partição de teste, mostra onde os dados têm informação. O modelo do aluno alcança 0,673 de AUC entre alunos, contra 0,643 de repetir a taxa de 2023, um ganho de 0,030, perto do limite de 0,701 da tarefa. O modelo da rede alcança 0,886 entre redes, contra 0,769 de repetir 2023, um ganho de 0,117, sem limite estrutural. As duas AUCs não se comparam como número, porque medem tarefas diferentes, mas o grão da rede é onde as variáveis descrevem exatamente a unidade prevista.

**Escolhas de implementação registradas:**

1. a taxa de cada rede é calculada com o peso amostral do INEP, como a taxa oficial, e a resposta é essa taxa comparada com 59,9%;
2. cada rede pesa igual no treino e na validação cruzada, porque a rede é a unidade de decisão;
3. as redes com menos de 20 alunos permanecem na base, com leitura separada: nelas a própria resposta é instável;
4. o contexto continua defasado (2023 para o ciclo de 2024) e a partição continua por município, com a mesma semente do `desenv_03`, o que mantém o controle de vazamento da D-007;
5. a rede privada continua fora (D-011), agora com 24 alunos;
6. o modelo é lido por dois prismas: a AUC, que mede a ordenação das redes sem depender de limiar, e a sensibilidade, que mede quantas redes em problema ele encontra. A acurácia não serve para julgar o modelo, porque a meta fica em cima da média do país e 18% das redes estão a menos de 5 pontos dela, onde um erro pequeno troca o lado da classificação;
7. o limiar de 50% usado na classificação é o padrão, e não uma escolha ótima.

**Relação com o enunciado:** o enunciado pede a previsão do aluno, e ela está entregue no `desenv_03`, com o limite de desempenho medido e declarado. O `desenv_04` é a extensão que responde às perguntas de negócio do próprio enunciado, que são sobre municípios, regiões e metas, e não sobre alunos individualmente.

**Alternativas consideradas:** manter o alvo no aluno como modelo principal (descartada: as variáveis não distinguem alunos da mesma rede, e o modelo fica preso a um limite baixo); a escola como unidade (descartada: o `id_escola` da base é uma máscara refeita a cada ano, sem correspondência com o Censo Escolar).

---

## D-014 · Todas as redes na aplicação estratégica, com a ressalva declarada

**Data:** 20/09/2026 · **Etapa:** Aplicação estratégica

**Decisão:** as análises do `desenv_05` que **descrevem o país** (a lista de redes em risco, o mapa municipal e o perfil das regiões) usam as 6.535 redes, com o modelo registrado no `desenv_04` aplicado diretamente, e declaram a ressalva de que nas redes de treino ele já tinha visto a resposta. As análises que **medem desempenho** (o resultado por faixa de probabilidade, o acerto em permanências e mudanças e a influência das variáveis) são feitas apenas nas 1.330 redes da partição de teste.

**Contexto:** responder quais municípios estão em risco e quais regiões se parecem exige falar do país inteiro, e não de 20% dele. Medir o quanto o modelo acerta, ao contrário, só é honesto onde ele nunca viu a resposta. São dois usos diferentes da mesma previsão.

**Justificativa:** separar os dois usos resolve a tensão sem criar um modelo novo nem um artifício de cálculo. Onde o número precisa ser honesto, vale o teste; onde é preciso cobrir o território, vale a base toda com o aviso explícito. A partição de cada rede é gravada em `reports/redes_risco_2024.csv`, de modo que qualquer leitura pode ser refeita só com as redes de teste.

**Limitação, declarada:** a lista de risco e o mapa têm acerto mais fácil nas redes que participaram do treino, e por isso descrevem o quadro com um contorno um pouco mais nítido do que uma aplicação real teria. Nenhuma conclusão da seção depende dessa diferença: as ordens de prioridade e os agrupamentos se mantêm quando conferidos na partição de teste.

**Como explicar em uma frase:** o modelo cobre o país inteiro quando a pergunta é onde estão os problemas, e fica restrito aos municípios que nunca viu quando a pergunta é o quanto ele acerta.

**Alternativas consideradas:** previsão fora da amostra em cinco partes, cada parte prevista por um modelo treinado nas outras quatro (descartada: acrescenta um artifício que precisa ser explicado e defendido, sem mudar nenhuma conclusão); usar apenas a partição de teste em tudo (descartada: 1.330 redes não descrevem 5.570 municípios, e o mapa ficaria vazio na maior parte do território).

---

## D-015 · Curadoria das variáveis, território como ponto de partida e escolha do modelo da rede

**Data:** 19/09/2026 · **Etapa:** Modelagem (parte 2)

**Decisão:** o modelo da rede usa **14 variáveis selecionadas mais a UF e a região**, e a família escolhida é a **Random Forest**.

**1. As 14 variáveis** vêm de um procedimento objetivo, calculado só na partição de treino, registrado na seção 2 do `desenv_04` e em `reports/curadoria_variaveis.csv`:

- **etapa A, sem olhar a resposta:** saem as variáveis com mais de 20% de ausentes, as que têm 90% ou mais das redes no mesmo valor, as explicadas pelas outras juntas (VIF acima de 10) e uma de cada par com correlação acima de 0,8. Nos empates, sai primeiro a variável calculada a partir de outras, depois a do município ou do estado, depois a mais antiga e, por fim, a com mais ausentes. Saíram 5: energia e alimentação na escola (quase não variam), a posição da rede diante da UF (diferença exata entre duas outras), o IVS (par do INSE) e a distância da meta municipal (par da taxa da rede);
- **etapa B, seleção por estabilidade:** uma eliminação passo a passo, em que a cada passo sai a variável que menos piora a log-loss quando embaralhada, repetida em cinco rodadas com divisões diferentes dos municípios. Em cada rodada fica o conjunto de menor log-loss, e entram no modelo as variáveis presentes nele em pelo menos quatro das cinco rodadas.

As 14 são: taxa da rede e taxa da mesma rede na UF em 2023, participação na avaliação de 2023, população, densidade, idade mediana, deslocamento de 1 hora, nível socioeconômico das famílias, mães adolescentes, oferta de pré-escola, horas-aula, biblioteca, quadra e professores com alto esforço.

**2. A UF e a região ficam fora da seleção e entram no modelo como ponto de partida.** Elas não mudam de um ano para o outro e, por isso, funcionam como a inércia: ajudam a explicar quem permanece onde está, e não quem muda. Como a inércia, ficam **no modelo**, e ficam **fora da análise das alavancas** no `desenv_05`.

**3. O critério de escolha da família é o original do `desenv_03`**, declarado antes de rodar: vence a menor log-loss na validação cruzada, e a regressão logística é preferida se ficar a menos de um desvio da vencedora. A condição sobre a AUC ponderada por alunos, que chegou a ser acrescentada depois de ver os resultados, foi retirada. Pelo critério, vence a Random Forest, com 400 árvores de até 12 níveis, no mínimo 5 redes por folha e 30% das variáveis sorteadas em cada divisão.

**Contexto:** as variáveis tinham sido escolhidas uma a uma, por hipótese, no grão do aluno, onde todas tinham pouco poder e a redundância quase não aparecia. Com o alvo na rede (D-013), várias versões do mesmo tema passaram a dividir o crédito entre si, e o modelo ficou difícil de explicar. A análise de redundância do `desenv_02` também não pegava combinações exatas, porque comparava as variáveis só de duas em duas.

**Justificativa:** na validação cruzada, a Random Forest alcança 0,897 de AUC e 0,401 de log-loss, praticamente empatada com o gradient boosting (0,402); a regressão logística fica a 0,015 de log-loss, acima do desvio de 0,011. Sem a UF e a região, a AUC cai 0,008. No teste, o modelo alcança 0,886 de AUC e 0,417 de log-loss, contra 0,877 do modelo anterior, com as 41 variáveis herdadas, e 0,769 de repetir 2023. A sensibilidade para as redes que não cumprem a meta é de 76,2%, e a maior distância entre probabilidade prevista e fração observada, numa faixa, é de 8,3 pontos.

**Limitações, declaradas:**

1. o Norte fica subestimado em 11 pontos, mesmo com a UF no modelo: a região tem poucas redes, e as árvores não chegam a aprender o patamar dela;
2. duas variáveis selecionadas funcionam como marcas do território, e não como alavancas: a idade mediana da população e o deslocamento de 1 hora, que é de 2010;
3. a eliminação passo a passo depende da ordem; a repetição em cinco rodadas reduz esse efeito, mas não o elimina;
4. a contribuição das variáveis foi medida com o gradient boosting na configuração da primeira versão do modelo da rede, usado como instrumento. A família e os hiperparâmetros finais foram escolhidos depois, sobre as variáveis selecionadas.

**Escolhas de implementação registradas:**

1. o instrumento da seleção tem os hiperparâmetros fixados no código, para que uma nova execução do notebook não use o registro reescrito pela seção 3;
2. a variante sem o bloco de inércia sai do `desenv_04`, porque servia à interpretação, que é escopo do `desenv_05`;
3. a variante sem território entra na comparação, para medir o que ele acrescenta.

**Alternativas consideradas:** manter as 41 variáveis (descartada: desempenho igual ou pior, com redundância que impede a explicação); uma variável por tema, escolhida por conceito (descartada: sem critério objetivo para escolher entre candidatas parecidas); a regra de um desvio na eliminação, que escolheria 4 variáveis (descartada: responde a outra pergunta, a do modelo mais simples que prevê igual, e deixaria o modelo sem nenhuma condição da rede para analisar); o melhor ponto de uma única rodada (descartada: depende da ordem de eliminação); o modelo sem território (descartada: perde 0,008 de AUC na validação cruzada e 0,009 no teste, e o território já fica fora da análise das alavancas, como a inércia).

---

## Decisões pendentes

Os identificadores são atribuídos apenas quando a decisão é tomada, para evitar renumerações.

| Tema | Etapa prevista |
|---|---|
| Métrica principal de avaliação | Avaliação |
| Fontes externas de enriquecimento a incorporar | Preparação de dados |

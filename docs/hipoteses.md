# Hipóteses de Trabalho

Este documento registra as hipóteses que orientam a análise exploratória, **antes** de qualquer medição. Cada uma declara o mecanismo proposto, as variáveis que a representam, o que se espera observar se for verdadeira, o que a falsearia e os limites do desenho que impedem conclusão causal.

A ordem importa: a análise exploratória testa estas hipóteses e reporta o resultado, favorável ou não. Achado que não responde a uma hipótese declarada aqui entra como observação exploratória, rotulada como tal.

**Uma ressalva que vale para todas.** A base é observacional e o contexto está no grão (município, rede). Nada aqui estabelece causalidade: no máximo, estabelece associação compatível ou incompatível com o mecanismo proposto. As recomendações de política pública que o trabalho vier a fazer devem ser lidas como priorização de investigação, não como prescrição causal.

---

## H1 · Deslocamento e desgaste

**Enunciado:** alunos de redes com maior presença rural têm menor probabilidade de serem alfabetizados, e o mecanismo é o custo do deslocamento até a escola.

**Mecanismo proposto:** menor adensamento populacional implica maior distância entre a residência e a escola. Essa distância é percorrida em território de infraestrutura viária e de transporte mais precária. O aluno gasta tempo e energia no trajeto, chega à sala em pior condição de aprendizagem e dispõe de menos tempo de estudo fora da escola. Um aluno da zona urbana do **mesmo município** está, tipicamente, mais próximo da sua escola e não paga esse custo.

**Variáveis observáveis:**

| Variável | O que representa |
|---|---|
| `esc_pct_alunos_zona_rural` | fração dos alunos que **residem** em zona rural |
| `esc_pct_rural` | fração dos alunos do 2º ano que **estudam** em escola rural |
| `esc_pct_transporte` | fração dos alunos que dependem de transporte escolar |

**O que se espera observar:** gradiente negativo entre cada uma delas e a taxa de alfabetização. Se o mecanismo for de fato o deslocamento, e não a ruralidade em si, então:

1. `esc_pct_transporte` deve carregar sinal próprio, e não apenas repetir a ruralidade — é a variável mais próxima do ato de se deslocar;
2. a zona de **residência** deve importar tanto ou mais que a localização da **escola**, porque quem paga o custo é quem mora longe, não quem estuda em prédio rural;
3. o efeito deve persistir entre municípios de condição socioeconômica semelhante.

**O que a falsearia:** ausência de gradiente; gradiente não monotônico sem explicação; ou desaparecimento do efeito ao comparar municípios de renda e IDHM semelhantes — o que indicaria que a ruralidade estava apenas marcando pobreza.

**Limite do desenho, declarado:** a comparação decisiva seria entre aluno rural e aluno urbano **dentro do mesmo município**, que isola o mecanismo dos confundidores territoriais. Ela não é possível aqui: os microdados públicos do INEP não trazem a escola do aluno, apenas município e rede. Trabalhamos com a proporção da rede, que é uma diluição do contraste que queríamos. Isso enfraquece o teste e precisa constar nas limitações.

**Confundidor conhecido:** ruralidade correlaciona com pobreza, com menor escolaridade dos pais e com menor infraestrutura. Um efeito observado pode pertencer a qualquer um deles.

---

## H2 · Infraestrutura básica da escola

**Enunciado:** redes cujas escolas têm infraestrutura básica mais precária apresentam menor taxa de alfabetização.

**Mecanismo proposto:** ausência de água tratada, esgoto e energia confiável afeta a frequência (adoecimento, desconforto) e a permanência do aluno em sala. É um piso material abaixo do qual a atividade pedagógica é prejudicada, independentemente da qualidade do ensino.

**Variáveis observáveis:** `esc_pct_agua_rede`, `esc_pct_esgoto_rede`, `esc_pct_energia_rede`, `esc_pct_alimentacao`.

**O que se espera observar:** gradiente positivo, com **efeito de piso** — a diferença entre 40% e 60% de cobertura deve importar mais que a diferença entre 90% e 100%. Se o mecanismo for material, e não apenas marcador de riqueza, a relação deve ser côncava, não linear.

**O que a falsearia:** relação linear ao longo de toda a faixa, que sugeriria marcador de renda em vez de efeito material; ou ausência de gradiente na faixa baixa de cobertura, justamente onde o mecanismo deveria operar.

---

## H3 · Recursos pedagógicos complementares

**Enunciado:** biblioteca, laboratório de informática, quadra e internet estão associados a maior alfabetização, com efeito menor que o da infraestrutura básica.

**Mecanismo proposto:** são recursos que ampliam o repertório e o tempo de contato com a leitura, mas atuam **acima** do piso material. Uma biblioteca não compensa a falta de água.

**Variáveis observáveis:** `esc_pct_biblioteca`, `esc_pct_lab_informatica`, `esc_pct_quadra`, `esc_pct_internet`.

**O que se espera observar:** gradiente positivo, mais fraco que o de H2. Entre eles, **biblioteca deve ser o mais forte para alfabetização especificamente** — é o único diretamente ligado à leitura.

**O que a falsearia:** biblioteca com efeito igual ou menor que quadra esportiva, o que indicaria que essas variáveis são apenas proxies de orçamento municipal, sem relação com o mecanismo pedagógico.

---

## H4 · Densidade da sala e atenção individual

**Enunciado:** turmas menores e maior disponibilidade de espaço por aluno favorecem a alfabetização.

**Mecanismo proposto:** alfabetizar exige acompanhamento individual do professor. Quanto mais alunos por turma, menor o tempo de atenção que cada criança recebe num momento em que a intervenção individualizada é decisiva.

**Variáveis observáveis:** `turma_media_alunos`, `esc_salas_por_aluno`.

**O que se espera observar:** gradiente negativo para o tamanho da turma.

**O que a falsearia — e este é o ponto delicado:** turmas pequenas são características de escolas rurais e de municípios pequenos, que tendem a ir pior. Se o gradiente vier **positivo** (turma maior, melhor resultado), a leitura provável não é "turma grande ajuda", e sim que o tamanho da turma está funcionando como marcador de urbanidade. Registro esta expectativa **antes** de medir, justamente para não reinterpretar o sinal depois de vê-lo.

---

## H5 · Suporte especializado ao aluno

**Enunciado:** a presença de coordenador pedagógico, psicólogo e assistente social está associada a maior alfabetização.

**Mecanismo proposto:** o coordenador organiza e acompanha a prática docente; psicólogo e assistente social atuam sobre barreiras não pedagógicas — dificuldades de aprendizagem, vulnerabilidade familiar, evasão — que atingem justamente os alunos em maior risco.

**Variáveis observáveis:** `esc_pct_coordenador`, `esc_pct_psicologo`, `esc_pct_assistente_social`.

**O que se espera observar:** coordenador com maior cobertura e efeito mais estável, por ser função quase universal; psicólogo e assistente social com cobertura baixa e concentrada em redes maiores.

**O que a falsearia:** efeito forte de psicólogo e assistente social sem controle por porte — provavelmente estariam marcando capacidade orçamentária da rede, não a atuação do profissional.

---

## H6 · Capital cultural do domicílio

**Enunciado:** o nível educacional dos adultos do município condiciona a alfabetização das crianças.

**Mecanismo proposto:** a criança que convive com adultos leitores encontra material escrito em casa, recebe apoio na lição e vê a leitura como prática cotidiana. É um insumo que a escola não fornece e que a política escolar não alcança diretamente.

**Variáveis observáveis:** `mun_analfabetismo_adulto`, `mun_expectativa_estudo`, `mun_idhm_educacao`.

**O que se espera observar:** entre as variáveis socioeconômicas, estas devem ser as mais fortes — a transmissão educacional entre gerações é um dos achados mais consistentes da literatura educacional.

**O que a falsearia:** desempenho abaixo do de variáveis puramente econômicas (PIB, renda), o que sugeriria que o que opera é recurso material, não capital cultural.

**Limitação séria, declarada:** estas variáveis têm referência **2010**, do Censo Demográfico. A criança avaliada em 2024 nasceu por volta de 2017. A defasagem é grande, e a variável descreve a geração dos pais e não a atual — o que, para esta hipótese específica, é até defensável, mas precisa estar escrito.

---

## H7 · Vulnerabilidade social e violência

**Enunciado:** municípios de maior vulnerabilidade social e exposição à violência apresentam menor alfabetização.

**Mecanismo proposto:** violência no entorno reduz a frequência escolar, desorganiza a rotina familiar e produz estresse crônico, que a literatura associa a prejuízo em funções cognitivas relevantes para a aprendizagem da leitura.

**Variáveis observáveis:** `mun_ivs`, `mun_ivs_infraestrutura`, `mun_ivs_capital_humano`, `mun_taxa_homicidio`, `mun_gini`.

**O que se espera observar:** gradiente negativo, mais forte para o IVS de capital humano que para o de infraestrutura.

**O que a falsearia:** ausência de gradiente para a taxa de homicídio entre municípios de IVS semelhante, o que indicaria que a violência letal, medida no grão municipal, é grosseira demais para captar a exposição vivida pela criança.

**Limitação:** a taxa de homicídio é de 2019 e o IVS de 2010. Municípios sem registro de óbito por agressão foram tratados como zero, e não como ausente — decisão defensável para município pequeno, mas que introduz ruído.

---

## H8 · Inércia territorial (hipótese concorrente)

**Enunciado:** o desempenho passado do território prevê o desempenho futuro melhor que qualquer condição observável atual.

**Mecanismo proposto:** o desempenho anterior sintetiza tudo que não conseguimos medir — qualidade da gestão, formação e permanência do corpo docente, prática pedagógica, coesão da rede — além dos próprios fatores socioeconômicos. É um resumo comprimido do território.

**Variáveis observáveis:** `rede_taxa_ant`, `mun_taxa_ant`, `rede_media_portugues_ant`, `uf_rede_taxa_ant`.

**Por que ela está aqui:** esta é a hipótese **contra a qual as outras competem**. Se ela vencer com folga e as demais não acrescentarem nada, o resultado do trabalho é um modelo de persistência: verdadeiro, com boa métrica e de baixa utilidade para política pública, porque nenhum gestor pode alterar o passado.

Declarar isso desde já tem função: se for esse o resultado, ele será reportado como achado, e não escondido atrás da métrica. E o achado tem valor próprio — diria que as condições observáveis do território, medidas no grão municipal, não acrescentam ao que a história já informa, e que avançar exigiria dados no grão da escola ou do aluno.

**O que a tornaria menos dominante:** as variáveis de H1 a H7 acrescentarem poder preditivo sobre um modelo que já contenha o desempenho anterior. É esse acréscimo, e não a força isolada de cada variável, que responde se o enriquecimento se justificou.

---

## H9 · Recursos materiais do território

**Enunciado:** municípios mais ricos apresentam maior alfabetização.

**Mecanismo proposto:** a riqueza do território opera por duas vias. Do lado da oferta, amplia a capacidade de investimento da rede — infraestrutura, formação e remuneração docente, material pedagógico. Do lado da demanda, melhora as condições materiais do domicílio: alimentação, saúde, moradia e tempo disponível dos adultos para acompanhar a criança.

**Variáveis observáveis:** `mun_pib_per_capita`, `mun_renda_per_capita`, `mun_idhm_renda`, `mun_idhm`.

**O que se espera observar:** gradiente positivo, com **retorno decrescente** — a diferença entre um município muito pobre e um pobre deve pesar mais que a diferença entre um rico e um muito rico.

**O que a falsearia — e é um risco real:** o PIB per capita municipal é distorcido por municípios de baixa população com grande atividade extrativa ou industrial, onde a riqueza produzida não é apropriada pela população local. Se o gradiente do PIB divergir do gradiente da renda per capita, a leitura correta é que o PIB está medindo produção e não bem-estar, e ele deve ceder lugar à renda.

**Relação com as outras hipóteses:** esta é a hipótese que concorre com H6. Se o capital cultural (H6) sobreviver ao controle por riqueza (H9), o mecanismo educacional se sustenta como distinto do econômico. Se não sobreviver, o que estávamos chamando de capital cultural era renda.

---

## Como estas hipóteses serão testadas

1. **Descritiva por faixas**, no grão do aluno: taxa de alfabetização por faixa de cada variável, com a contagem de alunos em cada faixa. Responde à forma da relação, inclusive quando ela não é monotônica.
2. **Força de associação com desfecho binário**, por instrumento adequado a alvo binário, e não apenas por correlação linear.
3. **Redundância entre as variáveis**, para saber quantos conceitos distintos existem de fato entre as 49 colunas.
4. **Ganho incremental sobre H8**, na etapa de modelagem: o teste que de fato decide se o enriquecimento se justifica.

Os resultados vivem em `notebooks/desenv_02_analise_exploratoria.ipynb`, cada um remetendo à hipótese que responde.

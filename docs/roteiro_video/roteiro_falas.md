# Roteiro de falas — Vídeo executivo (5 min)

Narração palavra a palavra, cronometrada, para gravar por cima do deck (`deck.html`).
Tom: executivo e instrutivo, apresentação de resultado. Os tempos da tabela usam 140 palavras por minuto, que é o ritmo pausado; o seu ritmo medido no roteiro da Fase 2 é mais rápido, cerca de 180, o que deixa folga.
As marcações **[clicar em X]** são as ações no deck durante a narração. Nos dois slides interativos, cada clique acompanha um trecho da fala.

## Mapa de tempo

| # | Slide | Palavras | Tempo | Acumulado |
|---|---|---:|---:|---:|
| 1 | Capa | 31 | 0:13 | 0:13 |
| 2 | Contexto | 51 | 0:22 | 0:35 |
| 3 | **Pipeline de desenvolvimento** | 156 | **1:07** | 1:42 |
| 4 | A virada de grão | 97 | 0:42 | 2:24 |
| 5 | O modelo da rede | 75 | 0:32 | 2:56 |
| 6 | **As cinco respostas** | 223 | **1:36** | 4:31 |
| 7 | O que o modelo não faz | 60 | 0:26 | 4:57 |
| 8 | Fecho | 44 | 0:19 | 5:16 |

**Total: 737 palavras.** A régua importa mais que a estimativa: o roteiro da Fase 2 tinha **906 palavras** nos mesmos 5 minutos, o que dá o seu ritmo real de cerca de **180 palavras por minuto**. Nessa régua, este roteiro dá **4:05**, com folga de quase um minuto; a 140 palavras por minuto, daria 5:16. O ensaio cronometrado decide. Se faltar tempo, os cortes saem nesta ordem: o terceiro parágrafo do slide 5, a resposta 5 do slide 6 e o segundo parágrafo do slide 4.

---

## Slide 1 · Capa — 0:13

> Olá pessoal, tudo bem? Me chamo Pedro, e hoje apresento o Tech Challenge da terceira fase: um modelo de machine learning que prevê o cumprimento da meta de alfabetização, rede por rede. Vamo lá?

---

## Slide 2 · Contexto — 0:22

> Em 2024, o Brasil chegou a 59,2% das crianças alfabetizadas ao fim do segundo ano. A meta era 59,9%. Faltaram sete décimos de ponto.
>
> Só que esse número sai quando o ciclo já acabou. O gestor precisa saber quais redes chegam à meta e quais precisam de apoio, enquanto ainda dá tempo de agir.

*Entrega: pausar depois de "sete décimos de ponto". A última frase é a ponte para a pipeline.*

---

## Slide 3 · Pipeline de desenvolvimento — 1:07  ⟵ principal

**Abertura, sem clique (0:06)**

> Antes do resultado, o caminho: a decisão tomada em cada etapa.

**[clicar em BASE] (0:22)**

> A linha vem do microdado do aluno e o contexto vem do município, sempre defasado: 2024 é previsto com dado de 2023.
>
> E aqui veio a primeira decisão. O lake da fase anterior traz quase só a resposta. Sem enriquecimento, a única variável explicativa seria a taxa do ano anterior, e o modelo só saberia repetir o passado. Por isso trouxemos sete fontes públicas, do Censo Escolar ao Atlas do Desenvolvimento Humano.

**[clicar em EXPLORAÇÃO, depois em PIPELINE]**

> Cada variável entrou com hipótese escrita antes da medição, e o pré-processamento vive dentro do pipeline, com partição por município: nada é aprendido fora do treino.

**[clicar em MODELO 1, depois MODELO 2 e APLICAÇÃO] (0:15)**

> O primeiro modelo seguiu o enunciado à risca e tentou prever cada criança. Ele nos mostrou um limite, que é o ponto central do projeto. O segundo mudou a unidade para a rede de cada município, e a aplicação responde as cinco perguntas sobre o modelo pronto.

*Entrega: é o slide de demonstrar domínio. Clicar só ao terminar a frase anterior.*

---

## Slide 4 · A virada de grão — 0:42

> Nenhuma das nossas fontes descreve a criança: todas têm grão de escola, rede ou município. Duas crianças da mesma sala chegam ao modelo idênticas, e ainda assim uma é alfabetizada e a outra não.
>
> Medimos isso: 90% da variação está dentro da rede, e o máximo alcançável ali são 0,70 de AUC. O modelo chegou a 0,673, colado no teto e a três centésimos de repetir o ano anterior.
>
> Mudando a unidade para a rede, ele vai a 0,886, e a distância para a regra trivial quadruplica. O que isso mostra é onde os dados têm informação.

*Entrega: falar devagar em "90% da variação está dentro da rede". É a frase que justifica o projeto inteiro.*

---

## Slide 5 · O modelo da rede — 0:32

> Três passos. Curadoria: de 41 para 14 variáveis, em duas etapas objetivas, e com 14 mais o território ele prevê melhor do que com as 41.
>
> Escolha: três famílias comparadas pelo critério declarado antes de rodar. Venceu a random forest.
>
> Leitura: não usamos acurácia, porque a meta fica em cima da média do país. Lemos por AUC e sensibilidade: 0,886 contra 0,769 de repetir o ano anterior, encontrando três de cada quatro redes em problema.

---

## Slide 6 · As cinco respostas — 1:36  ⟵ principal

**[clicar em FATORES] (0:16)**

> O que mais pesa. Entre redes que partiram do mesmo lugar, os maiores efeitos estão fora da escola: gravidez na adolescência, nível socioeconômico, estrutura etária. Dentro da escola, pré-escola e biblioteca. Isso não tira a responsabilidade da educação: coloca parte da solução em outras pastas.

**[clicar em RISCO] (0:22)**

> Onde agir. O modelo aponta 2.380 redes que não cumpriram a meta, com 820 mil crianças. E aqui vem o número que muda uma conversa de orçamento: se só as quinze primeiras chegassem à meta, o país passaria de 59,2% para 60,45%, acima da meta. Mas elas valem um quinto do problema: metade do ganho exige 134 redes. Um plano só para capitais não muda o mapa.

**[clicar em REGIÕES] (0:13)**

> Quais territórios se parecem. Norte e Nordeste formam um bloco; Centro-Oeste e Sudeste, o oposto. E a diferença entre eles não é de natureza, é de grau: os mesmos fatores em posições diferentes da régua.

**[clicar em PREVISÃO] (0:17)**

> Como prever os próximos ciclos. A probabilidade vem em faixas com confiabilidade conhecida: das redes com até 25% de chance, 89% não cumpriram; acima de 75%, só 9%. Isso permite dosar, intervir onde o aviso é firme e acompanhar onde ainda pode virar.

**[clicar em VARIÁVEIS] (0:15)**

> E o que mais pesa no modelo é de onde a rede partiu: sem isso, ele cai para o nível do acaso. A inércia manda, e romper inércia é o trabalho da política.

*Entrega: respiro entre uma resposta e outra. Desacelerar em 60,45%, 89% e 9%.*

---

## Slide 7 · O que o modelo não faz — 0:26

> Três limites. Ele acerta 91% das redes que continuam onde estavam e 54% das que mudam de lado: é mais frágil onde a política age. Mostra associação, não causa. E enxerga o resultado, não o contexto: o Rio Grande do Sul aparece com muitas redes em risco em 2024, o ano das enchentes, e o modelo não sabe da enchente.

*Entrega: ritmo mais ágil. O quarto cartão fica na tela sem ser lido.*

---

## Slide 8 · Fecho — 0:19

> Fica uma lista nominal de redes ordenada por impacto, um mapa de onde o problema se concentra e uma régua de prioridade com confiabilidade medida. Repetindo o método a cada ciclo, dá para saber onde apoiar antes que o ano termine. Obrigado.

*Entrega: feche com calma. "Obrigado" após uma pausa curta.*

---

## Notas gerais de gravação

- **Ensaie com cronômetro.** A tabela usa 140 palavras por minuto, o ritmo pausado. No seu ritmo da Fase 2, cerca de 180, sobra quase um minuto. Cronometre os slides 3 e 6 isolados primeiro;
- **Um clique por frase concluída.** A transição visual pontua a fala, nunca a interrompe;
- **Antes de gravar**, deixe o slide 3 na etapa "Base" e o slide 6 na pergunta "Fatores", que são os estados iniciais;
- **Números que não podem sair errados:** 59,2% contra 59,9%; 0,673 com teto de 0,701; 0,886 contra 0,769; 2.380 redes e 820 mil alunos; 60,45% com quinze redes; 89% e 9% nas faixas extremas; 91% contra 54% em permanência e mudança.

# Plano do projeto

Roteiro das etapas de desenvolvimento, com a entrega esperada de cada uma e as decisões que nascem no caminho. O plano é atualizado conforme as etapas avançam, e cada etapa entra na branch principal por Pull Request própria, com o [diário de decisões](decisoes.md) revisado ao final.

## Etapas

| # | Etapa | Entrega | Decisões previstas | Status |
|---|---|---|---|---|
| 0 | Fundação | repositório, estrutura, README evolutivo e diário iniciado | grão de modelagem (D-001) | ✅ concluída |
| 1 | Base analítica | tabela de modelagem: alunos presentes da camada Silver, com o contexto municipal da camada Gold defasado, e verificação explícita contra vazamento | seleção das variáveis de contexto, defasagem temporal, uso do peso amostral | ✅ concluída |
| 2 | Análise exploratória | distribuições, correlações, perfis por rede e território, e as hipóteses analíticas que orientam a modelagem | variáveis candidatas a transformação e engenharia de atributos | ✅ concluída |
| 3 | Enriquecimento externo | incorporação de fontes socioeconômicas públicas, guiada pelas hipóteses da etapa anterior | quais fontes entram e com qual justificativa | ✅ concluída |
| 4 | Pipeline de pré-processamento | imputação, codificação de categóricas e escalonamento integrados ao modelo, com Scikit-learn | estratégias de imputação e de codificação | ✅ concluída |
| 5 | Modelagem supervisionada | modelo de referência, modelos candidatos e otimização, com validação de corte temporal | algoritmo escolhido e critério da escolha | ✅ concluída |
| 6 | Avaliação e interpretabilidade | métricas adequadas ao alvo, importância por permutação e dependência parcial | métrica principal de avaliação | ✅ concluída |
| 7 | Aplicação estratégica | respostas às perguntas de negócio: fatores de maior impacto, municípios em maior risco, territórios com padrões semelhantes, projeção de atingimento de metas e variáveis mais influentes | critérios de classificação de risco | ✅ concluída |
| 8 | Documentação final | README completo, relatórios e visualizações consolidadas | n/d | ✅ concluída |
| 9 | Vídeo executivo | apresentação de até 5 minutos, simulando reunião com gestores públicos | n/d | ✅ concluída |

## Convenções de trabalho

**Desenvolvimento e produção.** Cada componente é desenvolvido em um notebook (prefixo `desenv_`, em `notebooks/`), célula a célula, com os conceitos aplicados e as evidências de execução salvas. Quando validado, o código é promovido para um script (prefixo `prod_`, na subpasta correspondente de `src/`), que é a versão reproduzível da etapa. Os pares compartilham o mesmo nome-base.

| Desenvolvimento (`notebooks/`) | Produção (`src/`) | Etapa |
|---|---|---|
| `desenv_01_base_analitica.ipynb` | `preprocessing/prod_01_base_analitica.py` | 1 |
| `desenv_02_analise_exploratoria.ipynb` | (sem par: análise) | 2 |
| `desenv_03_pipeline_modelagem.ipynb` | `modeling/prod_03_pipeline_modelagem.py` | 4 e 5 |
| `desenv_04_pipeline_modelagem_parte2.ipynb` | `modeling/prod_04_pipeline_modelagem_parte2.py` | 5 e 6 |
| `desenv_05_aplicacao_estrategica.ipynb` | `evaluation/prod_05_aplicacao_estrategica.py` | 7 |


**Promoção concluída.** Todas as etapas têm o seu par em `src/`. O `prod_04` reaproveita o pipeline do `prod_03`, e o `prod_05` reconstrói o modelo pela receita registrada, com trava que confere a AUC no teste antes de seguir.

Os três scripts foram **executados de ponta a ponta contra o data lake** e reproduzem os notebooks: o `prod_03` em 15,7 min, escolhendo a regressão logística pelo mesmo critério; o `prod_04` em 23,2 min, com a mesma curadoria de 41 para 14 variáveis, a mesma família e AUC de 0,8856 no teste, com a matriz de confusão idêntica; e o `prod_05` em 4,4 min, com todas as respostas de negócio iguais às do notebook. As únicas diferenças nos artefatos são ruído de ponto flutuante no décimo quinto dígito e nomes de colunas.

**Versionamento.** Toda etapa nasce em branch própria e chega à branch principal por Pull Request com descrição e comentário de revisão. As decisões analíticas relevantes são registradas no diário antes do merge.

## Restrição temporal a resolver na etapa 1

A camada Silver cobre os ciclos de **2023 e 2024**. Como as variáveis de contexto municipal entram defasadas (situação do município no ciclo anterior), os alunos de 2023 não têm contexto disponível, e apenas o ciclo de 2024 reúne aluno e contexto completos. Isso condiciona o desenho da validação e será tratado como decisão explícita na etapa 1, com as alternativas registradas no diário.

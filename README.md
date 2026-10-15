# 🔎 BI Swiss Knife

### Análise de dados, inteligência semântica e arquitetura de dashboards — processamento local

O **BI Swiss Knife** é uma ferramenta em desenvolvimento para automatizar etapas iniciais de projetos de Business Intelligence (BI).

Desenvolvido em Python, o projeto analisa arquivos de dados, avalia sua qualidade, identifica possíveis significados para tabelas e colunas, sugere oportunidades de análise e propõe uma arquitetura inicial para dashboards.

A ferramenta foi concebida para ajudar analistas a compreender os dados antes de iniciar a modelagem e a construção de relatórios em plataformas como o Power BI.

O objetivo é reduzir o trabalho manual de exploração, diagnóstico e planejamento analítico, oferecendo resultados estruturados, rastreáveis e que possam ser validados pelo usuário.

**Versão funcional de referência:** V3 — Dashboard Architect.

**Status do projeto:** em desenvolvimento.

---

## 📌 Sumário

- [1. Visão geral](#-1-visão-geral)
- [2. Problema que o projeto resolve](#-2-problema-que-o-projeto-resolve)
- [3. Funcionalidades implementadas](#-3-funcionalidades-implementadas)
- [4. Data Analyzer](#-4-data-analyzer)
- [5. Semantic Intelligence](#-5-semantic-intelligence)
- [6. Insight Discovery](#-6-insight-discovery)
- [7. Dashboard Architect](#-7-dashboard-architect)
- [8. Relatórios e exportações](#-8-relatórios-e-exportações)
- [9. Arquitetura e tecnologias](#-9-arquitetura-e-tecnologias)
- [10. Privacidade e segurança](#-10-privacidade-e-segurança)
- [11. Instalação e execução](#-11-instalação-e-execução)
- [12. Limitações conhecidas](#-12-limitações-conhecidas)
- [13. Roadmap](#-13-roadmap)
- [14. Público-alvo](#-14-público-alvo)
- [15. Visão de futuro](#-15-visão-de-futuro)

---

## 🎯 1. Visão geral

O BI Swiss Knife procura responder a quatro perguntas fundamentais:

1. **O que existe nos meus dados?**
2. **Qual é a qualidade dos dados disponíveis?**
3. **Quais análises podem ser realizadas?**
4. **Como organizar essas análises em um dashboard?**

Para isso, combina análise estrutural, estatísticas descritivas, regras semânticas e heurísticas de priorização.

O resultado é uma análise estruturada que pode auxiliar o profissional de dados desde a exploração inicial até o planejamento de um projeto de BI.

### Fluxo geral

```text
                 EXCEL / CSV
                     |
                     v
               DATA ANALYZER
                     |
                     v
              QUALIDADE DOS DADOS
                     |
                     v
              MODELO SEMÂNTICO
                     |
                     v
              DESCOBERTA DE INSIGHTS
                     |
                     v
              KPIs E CÁLCULOS CANDIDATOS
                     |
                     v
              DASHBOARD BLUEPRINT
                     |
                     v
              RELATÓRIOS E RESULTADOS
```

O sistema utiliza regras e algoritmos implementados no próprio projeto. As sugestões são produzidas a partir das características observadas nos dados e precisam ser validadas conforme o contexto de negócio.

---

## 💡 2. Problema que o projeto resolve

Em projetos de BI, grande parte do esforço acontece antes da construção dos gráficos.

O analista normalmente precisa:

- Examinar arquivos e planilhas.
- Identificar tabelas, colunas e registros.
- Verificar valores ausentes e possíveis duplicidades.
- Investigar inconsistências de tipos e formatos.
- Entender o significado das colunas.
- Identificar medidas, dimensões e campos de data.
- Avaliar possíveis relacionamentos entre tabelas.
- Descobrir quais análises são viáveis.
- Selecionar indicadores relevantes.
- Planejar a estrutura das páginas do dashboard.

O BI Swiss Knife busca automatizar parte dessas atividades e transformar os resultados em informações que facilitem as próximas etapas do trabalho.

### Proposta de valor

**Transformar arquivos de dados em um diagnóstico estruturado e em um ponto de partida para a construção de soluções de Business Intelligence.**

A ferramenta não pretende substituir o Power BI nem o conhecimento do analista. Sua proposta é facilitar o trabalho anterior à implementação do dashboard.

---

## 🚀 3. Funcionalidades implementadas

A evolução do projeto está organizada em três etapas principais.

| Versão | Componente | Objetivo |
|---|---|---|
| V1 | Data Analyzer | Analisar a estrutura e a qualidade dos dados. |
| V2 | Semantic Intelligence | Inferir o significado das tabelas e colunas e identificar oportunidades de análise. |
| V3 | Dashboard Architect | Organizar indicadores e oportunidades em uma proposta inicial de dashboard. |

### Principais capacidades da versão de referência

- Análise estrutural de arquivos e planilhas.
- Avaliação da qualidade dos dados.
- Estatísticas descritivas e identificação de possíveis anomalias.
- Classificação semântica de colunas.
- Identificação de dimensões, medidas e datas.
- Identificação de possíveis identificadores e relacionamentos.
- Geração de oportunidades de análise.
- Priorização de insights candidatos.
- Sugestão de KPIs.
- Identificação de possíveis cálculos derivados.
- Recomendações iniciais de visualizações.
- Geração de Dashboard Blueprint.
- Produção de relatórios técnicos e executivos.

O conteúdo efetivamente apresentado depende dos dados analisados e dos recursos disponíveis na versão executada.

---

## 🔍 4. Data Analyzer

O Data Analyzer constitui a base do sistema.

Sua função é examinar a estrutura dos arquivos e identificar características que ajudem o usuário a compreender a qualidade e as limitações dos dados.

### 4.1 Análise estrutural

Pode identificar:

- Planilhas presentes no arquivo.
- Colunas e registros.
- Tipos de dados inferidos.
- Características gerais das tabelas.
- Informações necessárias para as etapas posteriores da análise.

### 4.2 Qualidade dos dados

A análise considera indicadores como:

- **Completude:** preenchimento dos campos.
- **Unicidade:** repetição de valores e características de unicidade.
- **Consistência:** compatibilidade entre valores e padrões observados.
- **Validade:** compatibilidade com os formatos e tipos esperados.

O sistema também identifica pontos de atenção, como valores ausentes, diferenças em relação ao tipo inferido, possíveis misturas de tipos e registros repetidos.

### 4.3 Estatísticas descritivas

Conforme o tipo de dado e os recursos utilizados, a análise pode considerar:

- Valores mínimos e máximos.
- Média e mediana.
- Dispersão dos valores.
- Quartis e percentis.
- Quantidade de valores distintos.
- Frequência de valores ausentes.
- Possíveis valores atípicos.

Esses indicadores ajudam a identificar características que merecem investigação.

### 4.4 Pontuação de qualidade

O sistema pode produzir uma pontuação geral de qualidade e resultados por dimensão.

Essa pontuação é baseada em regras heurísticas. Ela não representa uma garantia absoluta de que os dados estejam corretos.

Uma tabela auxiliar ou destinada a preenchimento, por exemplo, pode apresentar características diferentes de uma tabela transacional sem que isso represente necessariamente um erro.

---

## 🧠 5. Semantic Intelligence

O componente de inteligência semântica procura inferir o papel analítico das tabelas e colunas.

A classificação utiliza evidências estruturais, nomes dos campos, tipos de dados, características estatísticas e regras implementadas no sistema.

### 5.1 Classificação semântica

Entre os papéis que podem ser identificados estão:

| Papel | Finalidade |
|---|---|
| Dimensão | Agrupar, segmentar ou categorizar análises. |
| Medida | Representar um valor que pode ser analisado quantitativamente. |
| Data | Permitir análises temporais quando houver informação suficiente. |
| Identificador | Representar um código ou campo que identifica uma entidade ou registro. |
| Desconhecido | Evitar uma classificação forçada quando as evidências são insuficientes. |

A classificação também pode considerar níveis de confiança e justificativas.

### 5.2 Identificadores e chaves

Uma coluna identificadora não é necessariamente uma chave primária.

O sistema procura distinguir o papel semântico do campo de sua possível utilização como chave.

A unicidade, isoladamente, não é suficiente para concluir que uma coluna identifica corretamente uma entidade.

### 5.3 Relacionamentos

O sistema pode avaliar possíveis relacionamentos a partir das características disponíveis.

Essas relações são candidatas e precisam ser validadas antes de serem utilizadas em um modelo de dados.

### 5.4 Cálculos candidatos

Quando encontra medidas compatíveis, o sistema pode sugerir cálculos derivados.

Por exemplo:

- Percentual de cobertura.
- Percentual de risco descoberto.

Essas sugestões são baseadas em evidências estruturais e nos nomes das medidas.

A fórmula definitiva deve ser confirmada conforme as regras de negócio.

---

## 💡 6. Insight Discovery

O Insight Discovery procura identificar perguntas analíticas que podem ser respondidas a partir das dimensões e medidas encontradas.

### 6.1 Tipos de oportunidade

Entre as possibilidades estão:

- Comparações entre categorias.
- Rankings.
- Análises temporais.
- Distribuições.
- Segmentações.
- Indicadores de acompanhamento.
- Análises de composição.
- Investigação de valores atípicos.
- Tabelas de detalhamento.

A disponibilidade de cada oportunidade depende das características dos dados.

### 6.2 Exemplo

Se o sistema identificar uma dimensão `Diretoria` e uma medida `Custo da Folha`, poderá sugerir:

**Pergunta analítica:** Quais diretorias concentram maior custo da folha?

**Dimensão:** Diretoria.

**Medida:** Custo da Folha.

**Visualização candidata:** gráfico de barras ou colunas.

Essa sugestão indica uma possibilidade de análise. Ela não significa que o sistema já calculou a participação de cada diretoria nem que tenha identificado uma anomalia ou um problema de negócio.

### 6.3 Priorização

As oportunidades podem receber níveis de prioridade e indicadores de confiança ou relevância.

Essas classificações ajudam a organizar as sugestões, mas não substituem a avaliação do analista.

A qualidade da priorização e a eliminação de sugestões redundantes continuam sendo pontos importantes de evolução do projeto.

---

## 📊 7. Dashboard Architect

O Dashboard Architect representa a evolução da ferramenta em direção ao planejamento de dashboards.

A partir das informações estruturadas pela análise, o sistema produz uma proposta inicial de organização das oportunidades analíticas.

### 7.1 Dashboard Blueprint

O Blueprint pode incluir:

- Título do dashboard.
- Objetivo analítico.
- Páginas recomendadas.
- Finalidade de cada página.
- Indicadores priorizados.
- Perguntas de negócio.
- Dimensões e medidas utilizadas.
- Sugestões de visualizações.
- Filtros candidatos.
- Alertas e limitações relevantes.

### 7.2 Exemplo conceitual

```text
DASHBOARD BLUEPRINT
         |
         +-- Visão Geral
         |      +-- Indicadores principais
         |      +-- Perguntas prioritárias
         |
         +-- Análise Comparativa
         |      +-- Comparações por categoria
         |      +-- Rankings
         |
         +-- Análise Temporal
         |      +-- Evolução de indicadores
         |      +-- Comparação entre períodos
         |
         +-- Detalhamento
                +-- Tabelas analíticas
                +-- Segmentações
```

Essa estrutura é ilustrativa. As páginas efetivamente sugeridas variam conforme os dados encontrados.

### 7.3 Resumo executivo

A versão de referência também produz um resumo orientado ao usuário, separando informações como:

- Visão geral da análise.
- Qualidade dos dados.
- O que foi identificado estruturalmente.
- Oportunidades de análise.
- Indicadores priorizados.
- Proposta de dashboard.
- Detalhes técnicos e pontos de atenção.

É importante distinguir uma descoberta factual de uma pergunta analítica sugerida.

Uma pergunta como "Quais diretorias concentram maior custo da folha?" representa uma oportunidade de investigação, não uma conclusão sobre os valores encontrados.

### 7.4 Validação humana

O Dashboard Blueprint deve ser tratado como uma proposta inicial.

Antes da construção do dashboard, o analista precisa validar:

- As regras de negócio.
- As fórmulas dos indicadores.
- Os relacionamentos.
- Os filtros.
- A relevância das páginas sugeridas.
- A interpretação dos resultados.

**O BI Swiss Knife não gera automaticamente um arquivo PBIX nesta versão.**

---

## 📄 8. Relatórios e exportações

A ferramenta organiza os resultados para consulta, análise técnica e compartilhamento.

### JSON

O relatório estruturado pode conter informações como:

- Resumo da análise.
- Resultados de qualidade.
- Modelo semântico.
- Dimensões e medidas identificadas.
- Oportunidades de análise.
- KPIs candidatos.
- Cálculos derivados candidatos.
- Dashboard Blueprint.
- Evidências, justificativas e alertas.

O JSON também pode servir como contexto para uma IA externa, caso o usuário decida compartilhar o relatório e esteja autorizado a fazê-lo.

### PDF executivo

O relatório executivo pode apresentar:

- Resumo da análise.
- Pontuação de qualidade.
- Principais pontos de atenção.
- Oportunidades de análise.
- Dashboard recomendado.
- Indicadores priorizados.
- Detalhes técnicos complementares.

### HTML

Quando disponibilizado pela versão executada, o relatório HTML permite consultar os resultados em uma interface navegável.

Os formatos disponíveis e o conteúdo de cada exportação dependem da implementação utilizada.

---

## 🛠️ 9. Arquitetura e tecnologias

O BI Swiss Knife utiliza uma arquitetura local baseada em Python e componentes web.

### Tecnologias principais

| Tecnologia | Finalidade |
|---|---|
| Python | Linguagem principal e execução das análises. |
| FastAPI | Backend e disponibilização dos recursos HTTP. |
| Pandas | Manipulação e análise de dados tabulares. |
| OpenPyXL | Leitura e processamento de arquivos Excel. |
| Pydantic | Validação e estruturação de dados. |
| Pytest | Testes automatizados. |
| HTML | Estrutura da interface. |
| CSS | Estilização da interface. |
| JavaScript | Interatividade do frontend. |

A relação definitiva de dependências deve ser consultada no arquivo `requirements.txt` do repositório.

### Organização lógica

A arquitetura separa responsabilidades entre componentes de análise, serviços, modelos, segurança, interface e testes.

Essa separação facilita a manutenção e a evolução das funcionalidades.

A estrutura física exata dos diretórios deve ser consultada no código-fonte da versão utilizada.

---

## 🔐 10. Privacidade e segurança

O projeto prioriza o processamento local dos arquivos.

A proposta é executar as análises no próprio computador, sem depender de APIs externas de inteligência artificial.

### Princípios de segurança considerados

- Validação dos arquivos recebidos.
- Tratamento controlado de arquivos enviados.
- Proteção contra caminhos de arquivo indevidos.
- Cuidados com arquivos temporários.
- Não execução de macros.
- Não execução de conteúdo ativo das planilhas.
- Não acompanhamento de relacionamentos externos do arquivo.
- Não atualização de conexões externas durante a análise.
- Não recalcular fórmulas do Excel durante a leitura.

Quando aplicável, a leitura de fórmulas utiliza os valores armazenados em cache no arquivo.

### Importante

Processamento local não significa ausência absoluta de riscos.

O usuário continua responsável por controlar o acesso aos arquivos originais, relatórios exportados e diretórios utilizados pela aplicação.

Antes de utilizar a ferramenta com informações confidenciais, é necessário verificar a configuração da versão instalada e as políticas de segurança aplicáveis ao ambiente.

---

## ▶️ 11. Instalação e execução

O projeto está sendo desenvolvido para execução local em ambiente Windows.

### Pré-requisitos

- Python em uma versão compatível com o projeto.
- Git.
- Acesso aos arquivos do repositório.
- Dependências listadas no `requirements.txt`.

### Preparação do ambiente

Clone o repositório:

```powershell
git clone URL_DO_REPOSITORIO
```

Entre na pasta criada:

```powershell
cd NOME_DA_PASTA
```

Crie um ambiente virtual:

```powershell
python -m venv .venv
```

Ative o ambiente no PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Instale as dependências:

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### Inicialização

O comando de inicialização deve corresponder ao ponto de entrada efetivamente configurado no projeto.

Antes de publicar instruções definitivas de execução, confirme o arquivo responsável por iniciar o FastAPI e o mecanismo utilizado para servir o frontend.

Não presuma que o comando padrão do Uvicorn funcionará sem verificar a estrutura real da aplicação.

### Arquivos analisados

Os arquivos Excel ou CSV são selecionados externamente pelo usuário, conforme os recursos disponibilizados pela interface.

Eles não devem ser confundidos com os arquivos do código-fonte ou com eventuais arquivos de teste utilizados durante o desenvolvimento.

---

## ⚠️ 12. Limitações conhecidas

O BI Swiss Knife está em desenvolvimento e utiliza inferências baseadas em regras e heurísticas.

É importante considerar as seguintes limitações:

- Classificações semânticas podem precisar de correção.
- Uma pontuação elevada de qualidade não garante correção para todas as regras de negócio.
- Uma oportunidade de análise não representa necessariamente uma descoberta relevante.
- Sugestões de relacionamentos precisam ser validadas.
- Fórmulas de indicadores candidatos precisam ser confirmadas.
- Resultados calculados por amostragem devem ser interpretados considerando essa limitação.
- Uma coluna identificadora não é necessariamente uma chave primária.
- O sistema pode gerar oportunidades redundantes.
- A arquitetura recomendada pode exigir ajustes para refletir os objetivos reais do negócio.
- O sistema não substitui a validação do analista.
- Não há geração automática de arquivos PBIX documentada nesta versão.
- A integração com modelos de linguagem locais ainda pertence ao planejamento futuro.

A evolução do projeto deverá melhorar progressivamente a relevância das sugestões, a explicabilidade e a utilidade prática dos relatórios.

---

## 🗺️ 13. Roadmap

O desenvolvimento está organizado em cinco etapas conceituais.

### V1 — Data Analyzer

**Status: implementada.**

Objetivos:
- Análise estrutural.
- Avaliação de qualidade.
- Estatísticas descritivas.
- Identificação de pontos de atenção.
- Geração de relatórios de diagnóstico.

### V2 — Semantic Intelligence

**Status: implementada.**

Objetivos:
- Classificação semântica.
- Identificação de dimensões e medidas.
- Identificação de datas e identificadores.
- Avaliação de relacionamentos candidatos.
- Descoberta de oportunidades de análise.
- Sugestão de indicadores e cálculos candidatos.

### V3 — Dashboard Architect

**Status: implementada em evolução.**

Objetivos:
- Resumo executivo.
- Priorização de oportunidades analíticas.
- Sugestões de KPIs.
- Organização das análises.
- Geração do Dashboard Blueprint.
- Recomendações iniciais de páginas, filtros e visualizações.

A evolução desta etapa busca melhorar a relevância das sugestões, reduzir redundâncias e separar com maior clareza descobertas factuais de oportunidades de análise.

### V4 — Power BI Assistant

**Status: planejada.**

Possíveis objetivos:
- Apoio à modelagem dimensional.
- Sugestões de medidas DAX.
- Apoio à preparação de dados com Power Query.
- Orientação sobre relacionamentos e cardinalidade.
- Apoio à implementação de indicadores.
- Acompanhamento da construção do dashboard.

Essas funcionalidades não devem ser consideradas disponíveis até serem implementadas e testadas.

### V5 — Private BI Intelligence

**Status: planejada.**

Possíveis objetivos:
- Integração com modelos de linguagem executados localmente.
- Interpretação contextual dos resultados.
- Explicações em linguagem natural.
- Assistência avançada para análise de dados.
- Automação de tarefas de preparação e desenvolvimento de BI.
- Avaliação de mecanismos para preservar a privacidade durante o uso de inteligência artificial.

A arquitetura futura deverá definir quais informações podem ser fornecidas aos modelos e como os dados sensíveis serão protegidos.

---

## 👥 14. Público-alvo

O projeto busca atender profissionais que trabalham com:

- Business Intelligence.
- Análise de dados.
- Excel e CSV.
- Power BI.
- Preparação e transformação de dados.
- Engenharia e modelagem de dados.
- Desenvolvimento de indicadores.
- Planejamento de dashboards.

Também pode ser útil para profissionais que recebem arquivos de diferentes origens e precisam compreender sua estrutura e suas possibilidades analíticas antes de iniciar um projeto de BI.

---

## 🔭 15. Visão de futuro

A visão do BI Swiss Knife é evoluir de uma ferramenta de diagnóstico para um assistente de desenvolvimento de Business Intelligence.

A proposta de longo prazo combina quatro capacidades:

1. **Entender os dados:** estrutura, qualidade e características estatísticas.
2. **Interpretar os dados:** semântica, medidas, dimensões e relacionamentos.
3. **Planejar as análises:** indicadores, perguntas de negócio e arquitetura de dashboards.
4. **Apoiar a implementação:** modelagem, DAX, Power Query e automação.

A integração com inteligência artificial local é uma possibilidade futura para ampliar a interpretação dos resultados sem transformar o envio de dados para serviços externos em um requisito da ferramenta.

A evolução será incremental, com foco em utilidade prática, explicabilidade, segurança e validação humana.

---

## 👨‍💻 Sobre o projeto

O BI Swiss Knife é um projeto de desenvolvimento voltado à aplicação prática de conhecimentos em Python, análise de dados, qualidade de dados e Business Intelligence.

O projeto explora como automatizar tarefas que normalmente exigem trabalho manual do analista, desde o diagnóstico de arquivos até o planejamento de dashboards.

**Status:** em desenvolvimento.

**Versão de referência:** V3 — Dashboard Architect.

**Foco atual:** aprimorar a qualidade das oportunidades analíticas e a utilidade do Dashboard Blueprint.

---

## 📌 Aviso

O BI Swiss Knife é uma ferramenta em desenvolvimento.

Os resultados produzidos devem ser interpretados conforme as características dos dados, as regras de negócio e os objetivos de cada análise.

As classificações, recomendações e fórmulas sugeridas precisam ser validadas antes de serem utilizadas em decisões empresariais.

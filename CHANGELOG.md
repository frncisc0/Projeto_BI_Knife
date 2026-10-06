# Changelog

## 3.0.0 — 2026-10-06

- Nova camada Human-Centered BI no mesmo payload, derivada do AnalysisResult e dos blocos de descoberta já calculados.
- Visão Geral, Descobertas e Análises possíveis apresentam qualidade, achados e avisos em linguagem clara antes dos detalhes técnicos.
- Dashboard Architect agrupa insights finais em páginas por tema, limita visuais e KPIs, seleciona filtros relevantes e registra interações somente quando há relação de alta confiança.
- PDF e HTML começam pelo resumo executivo, qualidade, descobertas, pontos de atenção, oportunidades e dashboard; diagnósticos completos continuam disponíveis como camada técnica.
- Interface V3.0 separa entendimento, análise, dashboard, detalhes técnicos e segurança.
- Roadmap alinhado a V1 Data Analyzer, V2 Semantic Intelligence, V3 Human-Centered BI, V4 Power BI Assistant e V5 Private BI Intelligence/Automation.

## 2.2.0 — 2026-10-05

- Scoring composto de relevância com pesos explícitos para aderência semântica, importância da medida, utilidade, qualidade, cardinalidade, sinal de negócio e confiança.
- Dedupe semântico de análises e KPIs equivalentes entre abas, mantendo a sugestão de maior qualidade.
- Prioridade HIGH/MEDIUM/LOW considera confiança, qualidade e força das evidências; KPIs auxiliares fracos deixam de ocupar a seleção principal.
- Visão de insights limitada a Top 12 com opção para consultar demais resultados deduplicados; Blueprint executivo limitado aos cinco melhores.
- Perguntas de negócio refinadas e justificativas ampliadas com evidências semânticas e de preenchimento.
- Testes para scoring, deduplicação, prioridade e seleção do Blueprint.

## 2.1.0 — 2026-10-04

- Interface com navegação para visão geral, diagnóstico, semântica, análises, KPIs, blueprint e segurança.
- Insights ordenados por relevance score heurístico, com filtros de prioridade e tipo e perguntas de negócio mais específicas.
- Tendências condicionadas a cobertura mensal, número de datas distintas e completude; outliers sugeridos somente quando presentes no AnalysisResult.
- Candidatos a cálculos e Dashboard Blueprint visíveis na interface sem execução de fórmulas ou DAX.

## 0.3.0 — 2026-10-02

### Added
- XLSX/XLSM with detected macros, connection definitions, external links, ActiveX or embedded objects can be profiled without executing those contents; DTD/ENTITY and invalid packages remain rejected.
- Excel reports include security metadata and per-worksheet processing status, allowing partial results when one sheet fails.
- Excel profiling has a configurable combined cell cap across worksheets to bound retained samples.
- Excel ingestion policy documented in `docs/xlsx-ingestion.md`.
- Diagnóstico estruturado com qualidade, confiança de tipos, chaves simples/compostas e sugestões de tabela.
- Estatísticas agregadas, sazonalidade de datas e detecção explicável de outliers IQR.
- Limites de linhas, colunas, células, timeout e tamanho de relatório; relatórios identificam amostragem.
- Confiança de possíveis relacionamentos é reduzida quando a cobertura usa tabelas ou valores amostrados.
- Configuração de delimitador, separador decimal e cabeçalho CSV.
- Detecção conservadora evita publicar valores da primeira linha como nomes de colunas quando o cabeçalho é ambíguo.
- Escolha explícita de cabeçalho para CSVs ambíguos e inferência reforçada por sinais de schema e tipos estáveis.
- Tipos físicos e inferidos separados de papéis semânticos heurísticos.
- Qualidade exibe dimensões e motivos; valores ausentes são descritos como itens para avaliar, não como erro automático.
- Relacionamentos podem ser verificados entre CSVs do mesmo lote com limite temporário de memória e exclusão de campos sensíveis.
- Exportação JSON, CSV-resumo e HTML sem valores de células ou rótulos de categoria.
- Proteção de estatísticas para colunas com nomes que sugerem dado pessoal/financeiro e testes de privacidade/logs.
- Leitura XLSX read-only, sem recalcular fórmulas ou seguir relações externas; provedor NoAI padrão.
- Validação em fluxo recusa declarações DTD/ENTITY em partes XML de XLSX antes da leitura.

## 0.2.0 — 2026-10-02

### Added
- Seleção e análise de múltiplos arquivos CSV/XLSX, incluindo pastas arrastadas ou selecionadas.
- Relatório de lote com erros por arquivo, limites configuráveis e exportação JSON agrupada.

## 0.1.0 — 2026-10-02

### Added
- Aplicação local com upload de CSV/XLSX e interface de diagnóstico.
- Perfil de colunas, estatísticas básicas, qualidade e sugestões de relacionamento.
- Exportação de relatório JSON.
- Documentação inicial de arquitetura, segurança e roadmap.
- Testes com dados sintéticos.

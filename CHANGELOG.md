# Changelog

## 0.3.0 — 2026-10-02

### Added
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

# Arquitetura

```text
Frontend estático (HTML/CSS/JS)
        ↓ HTTP local
API FastAPI (app/api)
        ↓
Serviço de análise (app/services)
        ↓
Leitores e analisadores (app/analyzers)
        ↓
AnalysisResult / contratos Pydantic (app/models)
        ↓
Semantic Layer (app/semantic)
        ↓
Insight Discovery + Dashboard Architect (app/insights, app/blueprint)
        ↓
Human-Centered Summary (app/services/human_summary_service.py)
        ↓
JSON → HTML / PDF offline
```

## Camadas

- **Frontend:** escolhe arquivos/pastas, configura CSV e apresenta contratos JSON. Valores são inseridos no DOM somente com escape e não há prévia de linhas.
- **API:** valida a entrada, converte erros conhecidos em respostas seguras e encaminha o caso de uso.
- **Serviços:** coordenam a leitura uma única vez, perfil, serialização e geração dos relatórios.
- **Analisadores:** inferem tipos, métricas de qualidade e estatísticas sem rótulos ou amostras de células no resultado.
- **Semantic Layer:** organiza os papéis já presentes no `AnalysisResult`; ignora campos marcados como sensíveis e não relê arquivos nem DataFrames.
- **Insight Discovery:** cruza campos da mesma aba, avalia score composto, deduplica análises semanticamente equivalentes entre abas, prioriza até 60 sugestões finais e explica cada sugestão; não chama serviços externos nem calcula valores derivados.
- **Human-Centered BI:** `app/services/human_summary_service.py` traduz o AnalysisResult, qualidade, avisos e insights existentes em explicações simples, oportunidades agrupadas e referências por ID. Não analisa linhas, não relê arquivos e não inventa resultados de negócio.
- **Dashboard Architect:** agrupa insights finais em uma Visão Geral e páginas temáticas coerentes; evita repetir insights, omite páginas isoladas de prioridade média, seleciona KPIs priorizados e filtros apenas de dimensões relevantes com cardinalidade controlada. Filtros cruzados só são sugeridos para relações de alta confiança; não infere hierarquias a partir de nomes.
- **Interface V3.0:** apresenta primeiro resumo, qualidade, descobertas, pontos de atenção, oportunidades e dashboard recomendado. Diagnóstico detalhado, semântica, prioridades e evidências ficam em Análise técnica; segurança permanece em área própria. O score numérico continua fora da experiência executiva.
- **Relatórios:** o JSON preserva todos os blocos V1/V2 e acrescenta `human_summary`; PDF e HTML começam pela camada executiva e mantêm os diagnósticos completos em seção avançada.
- **Schemas:** definem os contratos independentes dos DataFrames usados internamente.
- **Segurança/configuração:** concentram validação de arquivo, limites e padrões.

## Decisões

FastAPI foi escolhido por oferecer uma API local simples e validação de contratos; Pandas atende CSV/XLSX/XLSM e OpenPyXL lê planilhas em modo read-only, com valores em cache e sem seguir links. O validador inspeciona o pacote OOXML e registra macros, definições de conexão, links externos, ActiveX e objetos incorporados; essas detecções não executam nem atualizam o conteúdo. DTD/ENTITY, pacote inválido, XML de relacionamento malformado e excesso de expansão continuam sendo recusados. Uploads são processados em memória (o multipart pode usar spool temporário que é fechado após cada arquivo); não há persistência da análise. O perfil é limitado por linhas, colunas, células, abas e tempo, contando linhas CSV por chunks e registrando quando métricas vêm de amostra. Falhas isoladas em abas são representadas no relatório e não impedem a análise das demais. Novos leitores devem produzir o mesmo modelo padronizado sem acoplar a interface ao Pandas.

`AnalysisReport` é o resultado da análise e contém metadados, qualidade, tabelas, perfis, possíveis chaves, relacionamentos e anomalias. `report_payload` acrescenta semantic model, insights, KPIs, Blueprint e resumo humano a partir do mesmo objeto, sem reler o arquivo. A camada humana usa os IDs dos insights finais para manter rastreabilidade. As exportações JSON, HTML e PDF são projeções do mesmo payload. Os relatórios não incluem valores individuais de células. Alertas mantêm a severidade original e avisos de segurança distinguem detecção de execução: macros, fórmulas e relações externas continuam sem execução/acesso. A aplicação não possui banco nem serviço externo; o `NoAIProvider` permanece padrão.

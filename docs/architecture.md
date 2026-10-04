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
Insight Discovery + Dashboard Blueprint (app/insights, app/blueprint)
        ↓
JSON → HTML / PDF offline
```

## Camadas

- **Frontend:** escolhe arquivos/pastas, configura CSV e apresenta contratos JSON. Valores são inseridos no DOM somente com escape e não há prévia de linhas.
- **API:** valida a entrada, converte erros conhecidos em respostas seguras e encaminha o caso de uso.
- **Serviços:** coordenam a leitura uma única vez, perfil, serialização e geração dos relatórios.
- **Analisadores:** inferem tipos, métricas de qualidade e estatísticas sem rótulos ou amostras de células no resultado.
- **Semantic Layer:** organiza os papéis já presentes no `AnalysisResult`; ignora campos marcados como sensíveis e não relê arquivos nem DataFrames.
- **Insight Discovery:** cruza campos da mesma aba com evidência suficiente, aplica confiança/prioridade e explica cada sugestão; não chama serviços externos nem calcula valores derivados.
- **Dashboard Blueprint:** organiza sugestões elegíveis em páginas, KPIs candidatos e filtros para revisão; não gera dashboard final.
- **Schemas:** definem os contratos independentes dos DataFrames usados internamente.
- **Segurança/configuração:** concentram validação de arquivo, limites e padrões.

## Decisões

FastAPI foi escolhido por oferecer uma API local simples e validação de contratos; Pandas atende CSV/XLSX/XLSM e OpenPyXL lê planilhas em modo read-only, com valores em cache e sem seguir links. O validador inspeciona o pacote OOXML e registra macros, definições de conexão, links externos, ActiveX e objetos incorporados; essas detecções não executam nem atualizam o conteúdo. DTD/ENTITY, pacote inválido, XML de relacionamento malformado e excesso de expansão continuam sendo recusados. Uploads são processados em memória (o multipart pode usar spool temporário que é fechado após cada arquivo); não há persistência da análise. O perfil é limitado por linhas, colunas, células, abas e tempo, contando linhas CSV por chunks e registrando quando métricas vêm de amostra. Falhas isoladas em abas são representadas no relatório e não impedem a análise das demais. Novos leitores devem produzir o mesmo modelo padronizado sem acoplar a interface ao Pandas.

`AnalysisReport` é o resultado da análise e contém metadados, qualidade, tabelas, perfis, possíveis chaves, relacionamentos e anomalias. `report_payload` acrescenta semantic model, insights, KPIs e blueprint usando somente esse objeto já calculado. As exportações JSON, HTML e PDF são projeções do mesmo payload e não reabrem o arquivo. Os novos blocos contêm nomes de campos e estatísticas estruturais, não valores individuais de células. Relacionamentos entre medidas são filtrados da camada semântica. A aplicação não possui banco porque não mantém histórico. O `NoAIProvider` é o padrão; não existe chamada de IA ou rede externa.

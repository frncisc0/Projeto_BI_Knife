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
Contratos Pydantic (app/models)
        ↓
Relatório estruturado sem valores de células
```

## Camadas

- **Frontend:** escolhe arquivos/pastas, configura CSV e apresenta contratos JSON. Valores são inseridos no DOM somente com escape e não há prévia de linhas.
- **API:** valida a entrada, converte erros conhecidos em respostas seguras e encaminha o caso de uso.
- **Serviços:** coordenam a leitura, perfil e geração do resultado padronizado.
- **Analisadores:** inferem tipos, métricas de qualidade e estatísticas sem rótulos ou amostras de células no resultado.
- **Schemas:** definem o contrato independente dos DataFrames usados internamente.
- **Segurança/configuração:** concentram validação de arquivo, limites e padrões.

## Decisões

FastAPI foi escolhido por oferecer uma API local simples e validação de contratos; Pandas atende CSV/XLSX e OpenPyXL lê XLSX em modo read-only, com valores em cache e sem seguir links. Uploads são processados em memória (o multipart pode usar spool temporário que é fechado após cada arquivo); não há persistência da análise. O perfil é limitado por linhas, colunas e células, contando linhas CSV por chunks e registrando quando métricas vêm de amostra. Novos leitores devem produzir o mesmo modelo padronizado sem acoplar a interface ao Pandas.

`AnalysisReport` é o contrato exportável e contém metadados, qualidade, tabelas, perfis, possíveis chaves, relacionamentos e anomalias. Não inclui valores de células. JSON, CSV-resumo e HTML são gerados no navegador a pedido; a aplicação não possui banco porque não mantém histórico. O `NoAIProvider` é o padrão; não existe chamada de IA ou rede externa.

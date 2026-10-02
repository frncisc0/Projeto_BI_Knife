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
```

## Camadas

- **Frontend:** envia o arquivo e apresenta somente contratos JSON; não conhece Pandas.
- **API:** valida a entrada, converte erros conhecidos em respostas seguras e encaminha o caso de uso.
- **Serviços:** coordenam a leitura, perfil e geração do resultado padronizado.
- **Analisadores:** inferem tipos, métricas de qualidade e estatísticas sem depender da interface.
- **Schemas:** definem o contrato independente dos DataFrames usados internamente.
- **Segurança/configuração:** concentram validação de arquivo, limites e padrões.

## Decisões

FastAPI foi escolhido por oferecer uma API local simples e validação de contratos; Pandas atende CSV/XLSX na V1 e OpenPyXL lê XLSX sem executar macros. O upload é analisado em memória e não persiste em diretório, reduzindo resíduos, com o custo de limitar o tamanho prático dos arquivos. Uma fonte nova poderá implementar o leitor e produzir o mesmo modelo `FileAnalysis` sem acoplar a interface ao Pandas.

O relatório JSON é a primeira representação exportável. A aplicação não possui banco porque a V1 não mantém histórico.

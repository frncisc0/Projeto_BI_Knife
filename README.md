# BI Swiss Knife

Aplicação local para inspecionar arquivos `.xlsx` e `.csv`, visualizar estrutura, qualidade básica e estatísticas. A versão atual é **0.2.0**, em desenvolvimento.

## Requisitos

- Python 3.10 ou superior.
- Instalação inicial das dependências. Depois disso, a análise roda localmente e não precisa de internet.

## Instalação e execução

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Abra http://127.0.0.1:8000. O servidor escuta somente no loopback por padrão. Use `BI_MAX_FILE_SIZE_MB` para ajustar o limite (100 MB por padrão), `BI_MAX_ROWS_TO_PREVIEW` para limitar a prévia e `BI_MAX_CATEGORY_DISPLAY` para limitar frequências exibidas.

## Funcionalidades

- Upload local de vários CSV e XLSX, inclusive ao soltar pastas, com descoberta de abas.
- Seleção de arquivos múltiplos ou pasta; subpastas também são percorridas ao arrastar a pasta (Chrome/Edge).
- Lotes de até 50 arquivos, 100 MB por arquivo e 500 MB no total por padrão; arquivos com erro são informados sem interromper os demais.
- Perfil de colunas com tipos inferidos, nulos, distintos, repetidos, valores inconsistentes e candidatas a chave.
- Estatísticas numéricas, intervalos de datas, frequências e prévia limitada.
- Contagem de linhas duplicadas e sugestões heurísticas de relacionamentos entre abas.
- Exportação de relatório JSON pelo navegador.
- Interface em português e sem recursos externos obrigatórios.

## Verificação

```powershell
python -m pytest
```

Os dados de teste são sintéticos. Consulte [docs/architecture.md](docs/architecture.md), [SECURITY.md](SECURITY.md) e [docs/roadmap.md](docs/roadmap.md).

## Limitações atuais

A planilha e o CSV são carregados integralmente em memória. A inferência de tipos e os relacionamentos são heurísticos e devem ser revisados antes de decisões de negócio. A API está limitada a uma análise por requisição; não há persistência de histórico.

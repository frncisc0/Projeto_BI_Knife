# 11 — Estratégia de testes

## 1. Situação atual (FATO)

| Suíte | Testes | Tempo | Cobre bem | Não cobre |
|---|---|---|---|---|
| `tests/unit` | 91 | ~8 s | Estrutura do relatório, nomes de arquivo, progresso, regressões V1.1, resumo humano | Correção numérica com dados brasileiros |
| `tests/integration` | 28 | ~3 s | Ingestão CSV/XLSX, lote | Arquivos grandes, desempenho |
| `tests/security` | 12 | ~1 s | Sem rede, sem vazamento em log, original intacto, sensíveis fora de relacionamentos | Salário, nome e dados bancários (D2) |
| `tests/frontend` | 1 (Node) | < 1 s | Nomes de relatório | Interface |
| **Total** | **131 + 1** | **~15 s** | | |

**Lição da auditoria:** os 6 defeitos confirmados passaram pelos 131 testes, porque eles verificam **forma**, não **valor**. A estratégia abaixo corrige isso.

## 2. Pirâmide-alvo

```text
            ▲  e2e (Playwright): 5–10 jornadas            — por release
           ▲▲▲ desempenho e memória: 3 benchmarks         — noturno
         ▲▲▲▲▲ integração + conjunto-ouro: 30+ arquivos    — todo PR
     ▲▲▲▲▲▲▲▲▲ unitários + property-based: regras puras    — todo PR
   ▲▲▲▲▲▲▲▲▲▲▲ segurança/privacidade: canário, rede, macro — todo PR
```

## 3. Tipos de teste

### 3.1 Conjunto-ouro (prioridade máxima)
Pasta `tests/golden/`. Cada caso = `arquivo` + `expected.json` com as métricas que **um humano conferiu**.

Casos mínimos (v1):
1. CSV `;` + vírgula decimal + cp1252 (padrão Excel BR)
2. CSV `,` + ponto decimal + UTF-8 (padrão internacional)
3. Datas ISO, com dias ≤ 12 (reproduz D1)
4. Datas `dd/mm/aaaa` e `mm/dd/yyyy` ambíguas
5. Valores `R$ 1.234`, `1.234.567`, `1.234,56` (D4)
6. Códigos `P12`, `AB-1001`, `00123` (D3)
7. Planilha de RH com salário, nome, conta, CPF (D2)
8. Arquivo ordenado por data com 1 milhão de linhas (D5)
9. XLSX com cabeçalho na linha 4 e título acima
10. XLSX com 3 abas, uma vazia e uma com erro
11. Modelo estrela: `fato_vendas` + `dim_cliente` + `dim_produto` + `dim_data`
12. Chave órfã (5% e 30%)
13. N:N entre duas tabelas
14. Nulos disfarçados (`-`, `n/d`, `#N/D`)
15. Encoding corrompido (`Ã©`)

### 3.2 Property-based (Hypothesis)
- Para qualquer número `x` formatado em BR (`1.234.567,89`), `parse_number_br(fmt(x)) == x`.
- Para qualquer data `d`, `parse_date(d.isoformat()) == d`.
- Para qualquer pipeline válido, aplicar → serializar → reaplicar = mesmo resultado (idempotência da serialização).

### 3.3 Equivalência SQL × M (Fase 3)
- **Snapshot** do M gerado por operação (detecta mudanças involuntárias).
- **Validação manual registrada**: para cada operação, executar o M no Power BI Desktop com o caso-ouro e comparar com a saída do DuckDB. Resultado anotado em `tests/m_validation.md` (data, versão do Power BI, ok ou falhou).

### 3.4 Segurança e privacidade (manter e ampliar)
- Teste canário (doc 07, seção 4) em JSON, HTML, PDF, XLSX e logs.
- Um teste por afirmação do `SECURITY.md`.
- Macro com efeito observável não executa (CI Windows).
- Fuzzing de CSV e XLSX (arquivos aleatórios ou truncados não derrubam o processo).
- Requisição sem token ou com Host inválido → recusada (Fase 1/6).

### 3.5 Desempenho (noturno)
| Benchmark | Meta |
|---|---|
| CSV 1 milhão × 20, perfil 100% | < 20 s |
| CSV 1 GB | RAM < 2 GB |
| Pipeline de 10 operações em 1 milhão de linhas | < 10 s |

### 3.6 e2e (Playwright, por release)
Importar → confirmar formato → ver diagnóstico → aceitar 2 correções → copiar M → exportar PDF.

## 4. Regras
1. **Bug corrigido = teste que falhava antes** (regressão).
2. Funcionalidade nova só entra com testes (regra 11 do briefing).
3. Cobertura mínima de 80% em `domain/`; sem meta para `api/` e `desktop/`.
4. O CI bloqueia o merge se lint, testes ou canário falharem.
5. Testes não podem acessar a rede (fixture global que bloqueia `socket`).

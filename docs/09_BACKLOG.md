# 09 — Backlog priorizado

Ordenado por **ordem de execução recomendada**. Estimativas em horas de trabalho efetivo (sem contar o calendário).
Sugestão: cadastrar cada linha como *issue* no GitHub, com o rótulo de prioridade e um *milestone* por fase.

| # | ID | Item | Fase | Prior. | Est. (h) | Critério de pronto |
|---|---|---|---|---|---|---|
| 1 | BK-001 | Teste + correção: datas ISO com dia/mês trocados (D1) | 0.5 | P0 | 4 | `2024-01-10` → máx. correto; teste no conjunto-ouro |
| 2 | BK-002 | Teste + correção: sensíveis (salário, nome, conta, agência, pix, nascimento) (D2) | 0.5 | P0 | 6 | O JSON de `rh.csv` não contém estatística de salário |
| 3 | BK-003 | Alinhar o SECURITY.md ao comportamento real | 0.5 | P0 | 1 | Cada afirmação tem um teste correspondente |
| 4 | BK-004 | Código alfanumérico ≠ número (D3) | 0.5 | P0 | 3 | `P12`, `AB-1001` → código |
| 5 | BK-005 | Milhar BR `1.234` / `1.234.567` (D4) | 0.5 | P0 | 4 | Hypothesis: 1.000 casos gerados corretos |
| 6 | BK-006 | CSV: amostragem por reservoir + `sampling_method` correto (D5) | 0.5 | P0 | 4 | Arquivo ordenado: amostra cobre o período todo |
| 7 | BK-007 | README "Como instalar e executar" | 0.5 | P0 | 1 | Usuário novo roda o app seguindo só o README |
| 8 | BK-008 | `TrustedHostMiddleware` + bind 127.0.0.1 | 0.5 | P1 | 2 | Requisição com Host estranho → 400 |
| 9 | BK-009 | `requirements-dev.txt` (pytest e ruff fora do runtime) | 0.5 | P2 | 0,5 | — |
| 10 | BK-010 | `pyproject.toml` + ruff + lockfile com hashes | 1 | P0 | 3 | `ruff check` limpo |
| 11 | BK-011 | GitHub Actions windows-latest (lint, testes, cobertura, pip-audit) | 1 | P0 | 4 | Badge verde no README |
| 12 | BK-012 | Conjunto-ouro v1 (15 arquivos + JSON esperado) | 1 | P0 | 10 | Teste compara métricas-chave |
| 13 | BK-013 | Decompor `analyze_file` (A1) | 1 | P0 | 12 | Nenhuma função > 80 linhas; testes verdes |
| 14 | BK-014 | Remover duplicações (A2) | 1 | P1 | 4 | `_cardinality`/`_norm` únicos; validação de upload em 1 lugar |
| 15 | BK-015 | Settings via pydantic-settings | 1 | P1 | 3 | Teste muda o limite por variável de ambiente sem reimportar |
| 16 | BK-016 | Log em arquivo rotativo + filtro anti-PII | 1 | P1 | 4 | Teste canário nos logs |
| 17 | BK-017 | Endpoints pesados em threadpool (D6) | 1 | P1 | 2 | Health < 200 ms durante a análise |
| 18 | BK-018 | Unificar limiares de nulos (atenção/moderado/crítico distintos) | 1 | P2 | 1 | — |
| 19 | BK-019 | CONTRIBUTING + Conventional Commits | 1 | P1 | 1 | — |
| 20 | BK-020 | Frontend: `app.js` em módulos ES | 1 | P2 | 8 | Sem regressão no teste e2e manual |
| 21 | BK-021 | `engine/` DuckDB + Parquet temporário | 2 | P0 | 16 | CSV de 1 GB importado com < 2 GB de RAM |
| 22 | BK-022 | Perfil SQL de 100% das linhas | 2 | P0 | 16 | Métricas = conjunto-ouro |
| 23 | BK-023 | `session/` + limpeza + SQLite de metadados | 2 | P0 | 12 | Teste de crash → limpeza na reinicialização |
| 24 | BK-024 | Upload em stream para disco | 2 | P1 | 4 | Upload de 100 MB sem pico de RAM |
| 25 | BK-025 | Detecção de formato de data/número + diálogo | 2 | P0 | 12 | Casos ambíguos perguntam |
| 26 | BK-026 | Política de sensíveis (3 níveis + override do usuário) | 2 | P0 | 10 | Testes por categoria |
| 27 | BK-027 | Prévia local mascarada | 2 | P1 | 8 | Colunas sensíveis mostram `•••` |
| 28 | BK-028 | Catálogo de regras de qualidade (doc 10) + `Issue` | 2 | P0 | 16 | 1 teste positivo e 1 negativo por regra |
| 29 | BK-029 | Relacionamentos CSV×XLSX + cardinalidade | 2 | P1 | 6 | Conjunto-ouro estrela |
| 30 | BK-030 | Shell da UI + tela "Entender" | 2 | P1 | 20 | Revisão de UX com 2 usuários |
| 31 | BK-031 | `Operation` + `Pipeline` | 3 | P0 | 8 | Serializa, valida e versiona |
| 32 | BK-032 | 9 operações MVP em SQL | 3 | P0 | 24 | Teste por operação |
| 33 | BK-033 | Gerador M por operação + snapshots | 3 | P0 | 24 | Validação manual no Power BI registrada |
| 34 | BK-034 | Prévia antes/depois | 3 | P0 | 8 | — |
| 35 | BK-035 | Desfazer e refazer | 3 | P1 | 4 | — |
| 36 | BK-036 | Exportar o arquivo limpo + proteção contra CSV injection | 3 | P0 | 6 | Célula `=CMD` exportada como `'=CMD` |
| 37 | BK-037 | Tela "Corrigir" | 3 | P0 | 30 | — |
| 38 | BK-038 | Modelo estrela por evidência | 4a | P0 | 12 | Conjunto-ouro estrela correto |
| 39 | BK-039 | Calendário + DAX básico | 4a | P1 | 10 | DAX formatado sem erro |
| 40 | BK-040 | Checklist "vai quebrar seu dashboard" | 4a | P1 | 6 | — |
| 41 | BK-041 | Tela "Power BI" | 4a | P1 | 12 | — |
| 42 | BK-042 | Relatório XLSX | 5 | P1 | 8 | — |
| 43 | BK-043 | Transformações e modelo no PDF/HTML | 5 | P1 | 6 | — |
| 44 | BK-044 | Histórico de sessões | 5 | P2 | 10 | — |
| 45 | BK-045 | Teste canário em todos os formatos | 5 | P0 | 4 | — |
| 46 | BK-046 | Launcher (porta, token, pywebview) | 6 | P0 | 10 | — |
| 47 | BK-047 | PyInstaller + Inno Setup | 6 | P0 | 12 | Instala em VM limpa |
| 48 | BK-048 | Guia do usuário + FAQ | 6 | P0 | 6 | — |
| 49 | BK-049 | Ficha de segurança para a TI corporativa | 6 | P1 | 3 | — |
| 50 | BK-050 | Release 1.0 com SHA-256 | 6 | P0 | 2 | — |
| — | BK-1xx | Fuzzy matching, conflitos, tendências, Pareto | 4b | P2 | 60+ | Pós-MVP |
| — | BK-2xx | Merge/append/agrupamento via M | — | P3 | 80+ | Só com demanda comprovada |
| — | BK-3xx | IA local opt-in (textos) | — | P3 | 30+ | Só depois do 1.0 |

**Total estimado do MVP (BK-001 a BK-050): ≈ 400 h**, ou ≈ 470 h com 15–20% de margem para imprevistos. São cerca de 8 a 9 meses a 10 h por semana, coerente com o roadmap.

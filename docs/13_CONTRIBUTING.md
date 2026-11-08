# 13 — Como contribuir (inclusive você, daqui a 6 meses)

## 1. Fluxo de trabalho
1. Toda mudança começa por uma *issue* (ID do backlog: `BK-0xx`).
2. Branch a partir de `main`: `tipo/BK-0xx-descricao-curta` (ex.: `fix/BK-001-datas-iso`).
3. PR pequeno (idealmente < 400 linhas alteradas), com testes.
4. O CI precisa estar verde (lint, testes, canário de privacidade).
5. Merge por *squash*, com mensagem no padrão abaixo.

> Hoje o branch principal se chama `master`. Sugestão: renomear para `main` na Fase 1 (o GitHub redireciona os links antigos).

## 2. Mensagens de commit (Conventional Commits, em português)

```
<tipo>(<escopo>): <o que muda, no imperativo>

<por quê — opcional>
Refs: BK-0xx
```

| Tipo | Quando |
|---|---|
| `feat` | Funcionalidade nova para o usuário |
| `fix` | Correção de defeito |
| `refactor` | Mudança interna sem alterar comportamento |
| `test` | Só testes |
| `docs` | Só documentação |
| `chore` | Build, CI, dependências |
| `perf` | Desempenho |

Exemplos:
- ✅ `fix(profiling): corrige inversão de dia/mês em datas ISO`
- ✅ `feat(cleaning): adiciona operação parse_number_br com tradução M`
- ❌ `att11`, `a`, `tt9` (histórico atual; não diz nada a quem lê o repositório, inclusive recrutadores)

## 3. Padrões de código
- Python 3.12, `ruff format` + `ruff check` (configurados no `pyproject.toml`).
- Funções de domínio puras, < 80 linhas, com type hints.
- Nada de `print`; use `logging` e **nunca** registre valores de células.
- Mensagens ao usuário em português; nomes de código em inglês (padrão atual mantido).
- Toda regra de qualidade e toda operação de limpeza é documentada no doc 10 ou no doc 04.

## 4. Definition of Done
- [ ] Testes novos cobrindo o comportamento (e o bug, se for `fix`)
- [ ] Conjunto-ouro atualizado se o resultado esperado mudou (com justificativa no PR)
- [ ] Canário de privacidade verde
- [ ] Documentação atualizada (CHANGELOG, docs/ correspondente)
- [ ] Nenhuma dependência nova sem justificativa no PR
- [ ] Nenhuma chamada de rede

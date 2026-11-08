# 06 — Experiência do usuário e interface

## 1. Avaliação da interface atual (FATO)

**O que funciona bem**
- Visual coeso (tema escuro, verde de destaque) e linguagem em português claro.
- O resumo vem antes do detalhe: a V3.0 abre com "Como estão os dados?", "O que encontramos" e "Pontos de atenção".
- Diálogo para cabeçalho ambíguo, barra de progresso real (vinda do backend) com tempo decorrido e estimado.
- "Por que isso foi sugerido?" em cada insight, o que gera confiança.
- Escape consistente de HTML (não há XSS óbvio).

**Problemas**
| # | Problema | Efeito no usuário |
|---|---|---|
| U1 | Layout de **landing page** (hero gigante "Entenda seus dados…") para uma **ferramenta de trabalho** | Na 2ª vez em diante, o usuário rola a tela à toa; os resultados ficam abaixo da área de upload |
| U2 | Sem navegação persistente: tudo numa página só, trocando `innerHTML` | Não há como voltar, comparar ou ver "onde estou" |
| U3 | A aba técnica "Colunas" tem **15 colunas** numa tabela | Sobrecarga; quem precisa disso é a minoria |
| U4 | **Nenhuma prévia dos dados** | O usuário não consegue confirmar se a interpretação (tipos, cabeçalho) está certa; é o maior obstáculo para confiar no resultado |
| U5 | Problemas aparecem como **texto**, sem ação | "33 valores inválidos" e depois? Falta o botão "Corrigir" |
| U6 | Score numérico escondido "da experiência executiva", mas aparece por componente | Mensagem ambígua: tem nota ou não tem? |
| U7 | Sem histórico | Reanalisar o mesmo arquivo amanhã = começar do zero |

## 2. Princípios da nova experiência

1. **Ferramenta, não site:** abre direto na área de trabalho, sem hero.
2. **Fluxo em 4 passos visíveis:** Importar → Entender → Corrigir → Levar ao Power BI.
3. **Resposta primeiro:** cada tela começa com uma frase-veredito.
4. **Todo problema tem uma ação** (corrigir, ignorar, ver detalhe).
5. **Profundidade sob demanda:** o técnico fica em painéis expansíveis, não em tabelas de 15 colunas.
6. **Privacidade visível:** um selo "Local · nada sai deste computador" sempre presente, e colunas sensíveis com cadeado.

## 3. Estrutura de navegação

```text
┌──────────────┬──────────────────────────────────────────────────────────┐
│ ⌁ BI KNIFE   │  vendas_2025 ▸ Entender                 🔒 Local  [Exportar]│
│              ├──────────────────────────────────────────────────────────┤
│ ⌂ Início     │  ① Importar ── ② Entender ── ③ Corrigir ── ④ Power BI      │
│ ＋ Nova      │  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│              │                                                          │
│ SESSÃO ATUAL │              (conteúdo do passo atual)                    │
│ ▸ Entender   │                                                          │
│ ▸ Corrigir 3 │                                                          │
│ ▸ Power BI   │                                                          │
│ ▸ Exportar   │                                                          │
│              │                                                          │
│ RECENTES     │                                                          │
│ · rh_out.csv │                                                          │
│ · pedidos    │                                                          │
│              │                                                          │
│ ⚙ Config.    │                                                          │
└──────────────┴──────────────────────────────────────────────────────────┘
```

## 4. Telas

### 4.1 Início (dashboard inicial)
```text
┌──────────────────────────────────────────────────────────────┐
│  Solte arquivos CSV ou Excel aqui      [Escolher arquivos]   │
│  ou uma pasta inteira                  [Escolher pasta]      │
├──────────────────────────────────────────────────────────────┤
│  Sessões recentes                                            │
│  vendas_2025 (3 arquivos)   ontem   Com ajustes   [Abrir]    │
│  rh_outubro.csv             12/10   Pronto        [Abrir]    │
└──────────────────────────────────────────────────────────────┘
```

### 4.2 Importar (confirmação)
Só aparece quando há ambiguidade; senão, vai direto para "Entender".
```text
┌ Confirme como ler "vendas.csv" ──────────────────────────────┐
│ Delimitador [; ▾]  Decimal [, ▾]  Milhar [. ▾]  Datas [dd/mm/aaaa ▾] │
│ ┌──────────┬────────────┬──────────┬──────────┐              │
│ │pedido_id │ data       │ produto  │ valor    │  ← prévia    │
│ │ código   │ data ✓     │ código ✓ │ moeda ✓  │  ← tipo      │
│ ├──────────┼────────────┼──────────┼──────────┤              │
│ │ 1001     │ 10/01/2025 │ P12      │ 1.234,00 │              │
│ │ 1002     │ 11/01/2025 │ P900     │   80,00  │              │
│ └──────────┴────────────┴──────────┴──────────┘              │
│ ⚠ As datas podem ser dd/mm ou mm/dd. Qual é o caso?          │
│                                  [Cancelar] [Importar →]     │
└──────────────────────────────────────────────────────────────┘
```

### 4.3 Entender (painel de diagnóstico)
```text
┌───────────────────────────────────────────────────────────────┐
│ 🟡 Pode usar com 3 ajustes                                     │
│ 1.000.000 linhas · 10 colunas · 3 tabelas · perfil de 100%    │
├──────────┬──────────┬──────────┬──────────┬─────────┬─────────┤
│Completude│Unicidade │Validade  │Consist.  │Integrid.│Padroniz.│
│  98%     │ 100%     │  91% ⚠   │  95%     │ 88% ⚠   │  97%    │
├───────────────────────────────────────────────────────────────┤
│ Problemas que afetam o dashboard              [Corrigir todos]│
│ 🔴 "valor" está como texto em 12% das linhas → somas erradas  │
│ 🟡 412 pedidos sem cliente correspondente → totais por cliente│
│ 🟡 "data" com 2 formatos misturados                           │
├───────────────────────────────────────────────────────────────┤
│ Colunas            [Buscar coluna…]                           │
│ ▸ pedido_id   código   100% preenchido  único        🔑        │
│ ▸ cliente_cpf código   🔒 sensível — estatísticas ocultas      │
│ ▸ valor       moeda    min 1,02 · máx 4.999,83 · média 2.506  │
└───────────────────────────────────────────────────────────────┘
```
Cada coluna expande num cartão com distribuição (mini-histograma), padrão detectado, motivo do tipo e problemas.

### 4.4 Corrigir (área de transformação)
```text
┌──────────────────────────────┬────────────────────────────────┐
│ Correções sugeridas          │ Prévia: "valor"                │
│ ☑ Converter "valor" p/ número│  antes        depois           │
│   (formato BR)  12% linhas   │  "1.234"   →  1234,00          │
│ ☑ Datas → dd/mm/aaaa         │  "R$ 80"   →  80,00            │
│ ☐ Remover 14 linhas duplic.  │  "n/d"     →  (vazio) ⚠        │
│ ＋ Adicionar correção        │                                │
├──────────────────────────────┴────────────────────────────────┤
│ Histórico de operações  ↶ Desfazer  ↷ Refazer                  │
│ 1. Converter valor (BR) ✓   2. Datas dd/mm/aaaa ✓              │
│ Score: 87 → 96                        [Ver script M] [Aplicar] │
└───────────────────────────────────────────────────────────────┘
```

### 4.5 Power BI (assistente)
- Diagrama do modelo estrela (fato no centro, dimensões ao redor, cardinalidade em cada linha).
- Abas: **Script M** · **Medidas DAX** · **Tabela Calendário** · **Checklist**, cada uma com o botão [Copiar].
- Blueprint de páginas (o que já existe), mais compacto.

### 4.6 Exportar
Escolha do que exportar (arquivo limpo, script M, relatório PDF/HTML/XLSX/JSON, log), com a nota "Relatórios não contêm valores dos seus dados".

## 5. Regras de interface

- **Estados obrigatórios** em toda tela: carregando (com etapa real), vazio, erro (com próximo passo) e sucesso.
- **Máximo de 3 níveis** de profundidade (tela → painel → detalhe).
- **Cores com significado fixo:** vermelho = vai causar número errado; amarelo = revisar; verde = ok; cinza = informativo.
- **Números no padrão BR** (`1.234,56`) em toda a interface.
- **Atalhos:** `Ctrl+O` importar, `Ctrl+Z`/`Ctrl+Y` desfazer/refazer, `Ctrl+E` exportar.
- **Acessibilidade:** contraste AA (verificar o cinza `#647068` atual sobre o fundo escuro, que provavelmente está abaixo de AA), foco visível, `aria-live` mantido.
- **Tema claro opcional:** ambientes corporativos costumam projetar a tela em reuniões, e o tema escuro rende mal em projetor.

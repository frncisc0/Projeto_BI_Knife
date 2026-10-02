# Ingestão segura de Excel

O BI Swiss Knife pode analisar dados armazenados em arquivos Excel que contenham elementos potencialmente ativos quando a leitura puder ser realizada com segurança. Conteúdo ativo nunca é executado e conexões externas nunca são atualizadas ou seguidas automaticamente.

## Fluxo de leitura

1. O validador confere a extensão `.xlsx`/`.xlsm`, a estrutura OOXML, o limite de tamanho expandido e as partes XML.
2. XML com DTD/ENTITY, relações malformadas e pacotes corrompidos são recusados antes do leitor de planilhas.
3. O inventário do ZIP registra apenas tipos detectáveis de conteúdo: projeto VBA, definição de conexão, links externos, ActiveX e objetos incorporados. Uma relação XML com `TargetMode=External` também é registrada de forma genérica.
4. OpenPyXL abre o arquivo com `read_only=True`, `data_only=True`, `keep_links=False` e `keep_vba=False`. O analisador percorre células armazenadas e não carrega VBA para execução, não recalcula fórmulas nem atualiza fontes.
5. Cada aba legível entra no pipeline comum de perfil, tipos, semântica, qualidade e relacionamentos. Uma falha isolada fica como `status: failed` na aba; as demais podem concluir e o arquivo fica `partial`.
6. O relatório registra `security.active_content_detected`, os tipos encontrados e que a ação foi `not_executed`. Relações externas não são seguidas; fórmulas usam apenas valores em cache. Se uma fórmula não tiver cache, o valor pode ser apresentado como ausente.

## Recusas de segurança

O arquivo inteiro é recusado quando não é um pacote Excel válido, está corrompido, contém XML DTD/ENTITY, possui metadados de relacionamento inválidos ou excede os limites configurados. Abertura do workbook ou leitura que falha antes de qualquer aba produzir resultado também impede análise útil. Uma falha durante a leitura de uma aba não bloqueia as outras abas.

O sistema não classifica a presença de macros ou conexões como prova de arquivo malicioso. Registra a detecção sem executar ou atualizar esses recursos. Nenhum componente do arquivo é extraído para o sistema de arquivos.

## Limites

- O limite inicial de upload é 100 MB e o limite expandido OOXML é 500 MB; ambos são configuráveis.
- Linhas, colunas, células, número de abas e tempo de profiling têm limites configuráveis existentes. `BI_MAX_XLSX_PROFILE_CELLS` limita a amostra combinada entre abas (padrão: 1.000.000 de células).
- A leitura usa memória para o upload e para as amostras dos DataFrames. O teto de células reduz essa retenção, mas não é um limite de memória rígido imposto pelo sistema operacional.
- OpenPyXL não recalcula fórmulas. O valor disponível é o cache salvo no arquivo; cache ausente não é recuperado por serviço externo.
- Recursos não reconhecidos pelo leitor podem não aparecer no inventário. Os tipos do relatório significam apenas o que foi detectado nas partes conhecidas do pacote.

## Teste manual do arquivo corporativo

No BI Swiss Knife, escolha o arquivo local `01-2026 Risco Trabalhista.xlsx` e execute a análise. Confirme no relatório:

- status `completed` ou `partial`, em vez de erro total se ao menos uma aba for legível;
- nome e status de cada aba, linhas e colunas analisadas;
- `security.active_content_detected` e `active_content_types` quando o pacote tiver recursos reconhecidos;
- `active_content_action: not_executed`, `external_relationships_followed: false` e `formulas_action: cached_values_only`;
- eventuais falhas isoladas listadas por aba.

O arquivo de 30 MB não está incluído no repositório nem foi disponibilizado nesta execução. Use uma cópia autorizada localmente para confirmar a estrutura específica desse workbook.

from __future__ import annotations

import re
import unicodedata
from typing import Any

from app.models.analysis_models import FileAnalysis, TableAnalysis
from app.models.discovery_models import (
    SemanticModel,
    StructuralColumn,
    StructuralHypothesis,
    TableStructureProfile,
)

ROLE_LABELS = {
    "identifier": "possível campo de identificação",
    "code": "possível código de identificação",
    "category": "categoria para agrupar informações",
    "measure": "medida que pode ser resumida",
    "date": "campo que indica uma data",
    "datetime": "campo que indica data e hora",
    "boolean": "campo com respostas do tipo sim ou não",
    "text": "campo descritivo",
    "unknown": "papel ainda não identificado",
}


def normalize_column_name(name: str) -> str:
    """Normalize common naming styles as a clue, without changing the source label."""
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name)
    normalized = unicodedata.normalize("NFKD", name.casefold())
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    tokens = re.findall(r"[a-z0-9]+", normalized)
    aliases = {"cod": "id", "codigo": "id", "identificador": "id", "dt": "data"}
    tokens = [aliases.get(token, token) for token in tokens]
    return " ".join(sorted(tokens))


def _column_confidence(table: TableAnalysis, column: Any) -> str:
    confidence = column.semantic_role_confidence
    if table.sampled and confidence == "high":
        return "medium"
    return confidence


def _structural_column(table: TableAnalysis, column: Any) -> StructuralColumn:
    confidence = _column_confidence(table, column)
    evidence = [
        f"O sistema classificou o campo como {ROLE_LABELS.get(column.semantic_role, 'papel não identificado')}.",
        f"{column.completeness_pct:.1f}% dos registros avaliados estão preenchidos.",
        f"Há {column.distinct_count} valores diferentes; a repetição observada é {column.cardinality}.",
    ]
    if column.key_candidate:
        evidence.extend(column.key_reasons)
    if column.inferred_type in {"data", "data/hora (texto)"}:
        evidence.append("Os valores puderam ser interpretados como datas.")
    limitations = ["O nome e o padrão dos valores não confirmam o significado de negócio deste campo."]
    if table.sampled:
        limitations.append("A avaliação foi feita sobre uma amostra; a unicidade pode mudar no arquivo completo.")
    return StructuralColumn(
        name=column.name,
        normalized_name=normalize_column_name(column.name),
        role=column.semantic_role,
        role_label=ROLE_LABELS.get(column.semantic_role, ROLE_LABELS["unknown"]),
        confidence=confidence,
        physical_type=column.physical_type,
        inferred_type=column.inferred_type,
        value_count=column.value_count,
        null_count=column.null_count,
        null_pct=column.null_pct,
        completeness_pct=column.completeness_pct,
        distinct_count=column.distinct_count,
        distinct_pct=column.distinct_pct,
        cardinality=column.cardinality,
        duplicate_count=column.duplicate_count,
        key_candidate=column.key_candidate,
        sensitive=column.sensitive,
        zero_count=column.zero_count,
        negative_count=column.negative_count,
        statistics=column.statistics.model_dump(mode="json", exclude_none=True),
        evidence=evidence,
        limitations=limitations,
    )


def _grain_hypothesis(table: TableAnalysis, columns: list[StructuralColumn]) -> StructuralHypothesis:
    single_key = next((candidate for candidate in table.key_candidates
                       if len(candidate.get("columns", [])) == 1), None)
    composite_key = next((candidate for candidate in table.key_candidates
                          if len(candidate.get("columns", [])) > 1), None)
    candidate = single_key or composite_key
    limitations = ["A estrutura não confirma a regra de negócio nem uma chave primária oficial."]
    if table.sampled:
        limitations.append("O arquivo foi amostrado; o padrão pode não representar todas as linhas.")
    if candidate:
        names = candidate["columns"]
        label = (f"Cada linha parece representar um registro separado, possivelmente identificado por {' + '.join(names)}.")
        confidence = candidate.get("confidence", "low")
        if confidence not in {"low", "medium", "high"}:
            confidence = "low"
        evidence = list(candidate.get("reasons", []))
        evidence.append("A combinação foi observada como candidata a identificar registros.")
        return StructuralHypothesis(label=label, confidence=confidence, evidence=evidence,
                                    limitations=limitations)

    roles = {column.role for column in columns}
    if "measure" in roles and ({"date", "datetime", "identifier"} & roles):
        return StructuralHypothesis(
            label="Cada linha pode representar uma ocorrência ou registro individual.",
            confidence="medium",
            evidence=["Há pelo menos uma medida e um campo de data ou identificação."],
            limitations=limitations,
        )
    return StructuralHypothesis(
        label="Não foi possível determinar com segurança o que cada linha representa.",
        confidence="low",
        evidence=["Os campos avaliados não formam um padrão estrutural suficientemente claro."],
        limitations=limitations,
    )


def _table_hypotheses(columns: list[StructuralColumn], sampled: bool) -> list[StructuralHypothesis]:
    roles = [column.role for column in columns]
    identifiers = roles.count("identifier") + roles.count("code")
    measures = roles.count("measure")
    dimensions = roles.count("category")
    dates = roles.count("date") + roles.count("datetime")
    evidence = []
    if identifiers:
        evidence.append(f"{identifiers} campo(s) podem ajudar a identificar registros ou entidades.")
    if measures:
        evidence.append(f"{measures} campo(s) podem ser resumidos como medidas.")
    if dimensions:
        evidence.append(f"{dimensions} campo(s) podem agrupar os registros por categoria.")
    if dates:
        evidence.append(f"{dates} campo(s) indicam datas ou períodos.")

    confidence = "medium" if evidence else "low"
    if sampled and confidence == "medium":
        confidence = "low"
    limits = ["A classificação descreve a estrutura, não o assunto ou a finalidade empresarial da tabela."]
    if sampled:
        limits.append("A classificação foi feita sobre uma amostra.")
    if measures and (identifiers or dates):
        label = "Os dados parecem conter registros ou ocorrências com medidas e campos de identificação ou data."
    elif identifiers and not measures:
        label = "Os dados podem formar um cadastro ou uma tabela de referência."
    elif measures and dimensions:
        label = "Os dados permitem resumir medidas por categorias; não dá para confirmar se já são um resumo agregado."
    else:
        label = "Não foi possível determinar com segurança um tipo estrutural para esta tabela."
        confidence = "low"
    return [StructuralHypothesis(label=label, confidence=confidence, evidence=evidence or [
        "Não foram encontrados sinais combinados suficientes para classificar a tabela.",
    ], limitations=limits)]


def _human_summary(table: TableAnalysis, columns: list[StructuralColumn]) -> str:
    descriptions = [
        ("campo(s) de identificação", sum(column.role in {"identifier", "code"} for column in columns)),
        ("categoria(s) para agrupar os dados", sum(column.role == "category" for column in columns)),
        ("medida(s) que podem ser resumidas", sum(column.role == "measure" for column in columns)),
        ("campo(s) de data", sum(column.role in {"date", "datetime"} for column in columns)),
        ("campo(s) descritivo(s)", sum(column.role == "text" for column in columns)),
    ]
    found = [f"{count} {label}" for label, count in descriptions if count]
    base = f"Esta tabela tem {table.rows_available or table.rows} registros e {table.columns} colunas."
    if found:
        base += " A estrutura contém " + ", ".join(found) + "."
    else:
        base += " Ainda não foi possível reconhecer claramente os papéis dos campos."
    if any(column.completeness_pct < 100 for column in columns):
        base += " Alguns campos têm valores sem preenchimento."
    if table.sampled:
        base += " As conclusões consideram uma amostra dos registros."
    return base


def build_table_structure_profiles(analysis: FileAnalysis, semantic: SemanticModel) -> list[TableStructureProfile]:
    """Create explanatory profiles from existing analysis metadata; never reads raw cells."""
    profiles = []
    relations = semantic.relationships
    foreign_keys = semantic.possible_foreign_keys
    for table in analysis.tables:
        columns = [_structural_column(table, column) for column in table.column_analyses]
        table_relations = [item for item in relations if item.get("source_table") == table.name
                           or item.get("target_table") == table.name]
        table_foreign_keys = [item for item in foreign_keys if item.get("source_table") == table.name
                              or item.get("target_table") == table.name]
        grain = _grain_hypothesis(table, columns)
        hypotheses = _table_hypotheses(columns, table.sampled)
        warnings = []
        if table.sampled:
            warnings.append("A estrutura foi avaliada por amostragem.")
        if table.columns > table.columns_analyzed:
            warnings.append(f"Foram avaliadas {table.columns_analyzed} de {table.columns} colunas.")
        if table.status not in {"completed", "completed_empty"}:
            warnings.append("A leitura da tabela não foi concluída integralmente.")
        if table.columns == 1:
            warnings.append("O arquivo possui apenas uma coluna; confira se o delimitador está correto.")
        evidence = [item for hypothesis in [grain, *hypotheses] for item in hypothesis.evidence]
        profile_confidence = "high" if grain.confidence == "high" and hypotheses[0].confidence == "high" else \
            "medium" if grain.confidence != "low" or hypotheses[0].confidence != "low" else "low"
        if table.sampled and profile_confidence == "high":
            profile_confidence = "medium"
        profiles.append(TableStructureProfile(
            table_name=table.name,
            row_count=table.rows_available or table.rows,
            evaluated_row_count=table.rows_analyzed,
            column_count=table.columns,
            summary=_human_summary(table, columns),
            grain_hypothesis=grain,
            table_type_hypotheses=hypotheses,
            columns=columns,
            candidate_keys=table.key_candidates,
            candidate_foreign_keys=table_foreign_keys,
            relationships=table_relations,
            temporal_columns=[column.name for column in columns if column.role in {"date", "datetime"}],
            measures=[column.name for column in columns if column.role == "measure"],
            dimensions=[column.name for column in columns if column.role == "category"],
            identifiers=[column.name for column in columns if column.role in {"identifier", "code"}],
            structural_warnings=warnings,
            confidence=profile_confidence,
            evidence=list(dict.fromkeys(evidence)),
            limitations=list(dict.fromkeys([*grain.limitations, *hypotheses[0].limitations])),
        ))
    return profiles

from app.analyzers.quality_analyzer import numeric_anomalies
from app.core.config import get_settings
from app.services.analysis_service import analyze_file


def test_csv_analysis_reports_nulls_duplicates_and_candidate_key():
    content = b"id,category,amount\n1,A,10\n2,B,20\n2,B,20\n3,,30\n"
    report = analyze_file("sample.csv", "csv", content, "utf-8")
    table = report.tables[0]
    assert table.rows == 4
    assert table.duplicate_rows == 1
    columns = {column.name: column for column in table.column_analyses}
    assert columns["id"].key_candidate is False
    assert columns["category"].null_count == 1
    assert columns["amount"].statistics.mean == 20


def test_empty_columns_are_profiled_without_returning_raw_preview():
    report = analyze_file("empty-column.csv", "csv", b"id,blank\n1,\n2,\n", "utf-8")
    blank = report.tables[0].column_analyses[1]
    assert blank.empty is True
    assert blank.null_count == 2
    assert "preview" not in report.tables[0].model_dump()


def test_numeric_text_statistics_and_inconsistent_value_detection():
    report = analyze_file("mixed.csv", "csv", b"amount\n10\n20\n30\n40\n50\n60\n70\n80\n90\nindefinido\n", "utf-8")
    amount = report.tables[0].column_analyses[0]
    assert amount.inferred_type == "moeda"
    assert amount.inconsistent_values == 1
    assert amount.statistics.mean == 50
    mismatch = next(alert for alert in report.quality.alerts if "diferem do tipo inferido" in alert["message"])
    assert mismatch["severity"] == "attention"
    assert mismatch["affected_columns"] == "amount"
    assert mismatch["recommendation"]


def test_relationship_suggestion_uses_unique_target_and_value_coverage():
    content = b"id,customer_id\n1,10\n2,20\n"
    report = analyze_file("sample.csv", "csv", content, "utf-8")
    assert report.relationships == []


def test_csv_options_handle_decimal_comma_and_headerless_files():
    report = analyze_file("european.csv", "csv", "item;valor\nA;1.234,50\n".encode(), "utf-8", header_mode="true")
    amount = report.tables[0].column_analyses[1]
    assert amount.inferred_type == "moeda"
    assert amount.statistics.mean == 1234.5
    assert report.settings["csv_delimiter"] == ";"

    no_header = analyze_file("no-header.csv", "csv", b"1;2\n3;4\n", "utf-8", ";", ".", "false")
    assert no_header.tables[0].rows == 2
    assert no_header.tables[0].columns == 2
    assert no_header.tables[0].column_analyses[0].name == "0"


def test_sampled_analysis_reports_total_and_profiled_rows(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "enable_sampling", True)
    monkeypatch.setattr(settings, "sample_size", 2)
    monkeypatch.setattr(settings, "max_cells_to_analyze", 100)
    report = analyze_file("sampled.csv", "csv", b"id\n1\n2\n3\n4\n", "utf-8")
    table = report.tables[0]
    assert table.rows == 4
    assert table.rows_analyzed == 2
    assert table.sampled is True
    assert any("amostrada" in warning for warning in report.warnings)


def test_composite_key_candidate_is_suggested():
    report = analyze_file("composite.csv", "csv", b"area,turno\nA,1\nA,2\nB,1\nB,2\n", "utf-8", header_mode="true")
    assert any(candidate["columns"] == ["area", "turno"] for candidate in report.tables[0].key_candidates)
    composite = next(candidate for candidate in report.tables[0].key_candidates if len(candidate["columns"]) == 2)
    assert composite["assessment"] == "possible_identifier"
    assert "não confirma uma chave" in composite["reasons"][0]


def test_matching_rank_columns_do_not_create_a_relationship():
    import pandas as pd
    from app.analyzers.relationship_analyzer import suggest_relationships

    frames = {
        "Classificacao": pd.DataFrame({"rank": [1, 2, 3]}),
        "Historico": pd.DataFrame({"rank": [1, 1, 2]}),
    }

    assert suggest_relationships(frames, []) == []


def test_empty_csv_rows_are_counted_and_reported():
    report = analyze_file("blank-rows.csv", "csv", b"id,nome\n1,Ana\n,\n2,Bia\n", "utf-8")
    assert report.tables[0].rows == 3
    assert report.tables[0].empty_rows == 1


def test_iqr_anomaly_is_explainable_and_does_not_include_outlier_value():
    series = __import__("pandas").Series(list(range(20)) + [500])
    anomaly = numeric_anomalies(series, "inteiro", "amount")[0]
    assert anomaly.method == "IQR"
    assert anomaly.count == 1
    assert "500" not in anomaly.model_dump_json()


def test_unique_measures_are_not_key_candidates_but_contract_id_is():
    report = analyze_file(
        "keys.csv", "csv",
        b"Contrato,Custo de Rescisao,Risco Total\nA-001,100,500\nA-002,200,600\nA-003,300,700\n",
        "utf-8", header_mode="true")
    columns = {column.name: column for column in report.tables[0].column_analyses}
    assert columns["Contrato"].key_candidate is True
    assert columns["Contrato"].key_assessment == "strong_candidate"
    for name in ("Custo de Rescisao", "Risco Total"):
        assert columns[name].key_candidate is False
        assert columns[name].key_assessment == "high_uniqueness_measure"


def test_contract_can_be_a_possible_identifier_without_being_asserted_as_a_key():
    rows = [f"A-{index:03d},{index * 10}" for index in range(1, 21)]
    rows[1] = "A-001,20"
    content = ("Contrato,Valor\n" + "\n".join(rows) + "\n").encode()
    report = analyze_file("contracts.csv", "csv", content, "utf-8", header_mode="true")
    contract = next(column for column in report.tables[0].column_analyses if column.name == "Contrato")

    assert contract.key_candidate is True
    assert contract.key_assessment == "possible_identifier"
    assert contract.key_confidence == "medium"

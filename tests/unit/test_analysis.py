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
    assert columns["amount"].statistics["mean"] == 20


def test_empty_columns_and_preview_are_safe():
    report = analyze_file("empty-column.csv", "csv", b"id,blank\n1,\n2,\n", "utf-8")
    blank = report.tables[0].column_analyses[1]
    assert blank.empty is True
    assert report.tables[0].preview[0]["blank"] is None


def test_numeric_text_statistics_and_inconsistent_value_detection():
    report = analyze_file("mixed.csv", "csv", b"amount\n10\n20\n30\n40\n50\n60\n70\n80\n90\nindefinido\n", "utf-8")
    amount = report.tables[0].column_analyses[0]
    assert amount.inferred_type == "numérico (texto)"
    assert amount.inconsistent_values == 1
    assert amount.statistics["mean"] == 50


def test_relationship_suggestion_uses_unique_target_and_value_coverage():
    content = b"id,customer_id\n1,10\n2,20\n"
    report = analyze_file("sample.csv", "csv", content, "utf-8")
    assert report.relationships == []

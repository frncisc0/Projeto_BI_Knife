from app.services.html_report_service import render_html_report
from app.services.pdf_report_service import render_pdf_report
from app.services.report_service import report_payload
from app.services.analysis_service import analyze_file


def _batch():
    report = analyze_file("test-report.csv", "csv",
                          b"Contrato,Valor\nCT-001,100\nCT-002,200\n", "utf-8", header_mode="true")
    payload = report_payload(report)
    payload["tables"][0]["column_analyses"][1]["top_values"] = [
        {"label": "PRIVATE_CATEGORY_SENTINEL", "count": 1, "percent": 50.0}]
    return {"file_count": 1, "results": [{"filename": "test-report.csv", "analysis": payload, "error": None}]}


def test_json_html_and_pdf_derive_from_same_analysis_payload():
    batch = _batch()
    html = render_html_report(batch)
    pdf = render_pdf_report(batch)

    assert batch["results"][0]["analysis"]["filename"] == "test-report.csv"
    assert "test-report.csv" in html
    assert b"%PDF-" in pdf and pdf.rstrip().endswith(b"%%EOF")
    assert "PRIVATE_CATEGORY_SENTINEL" not in html
    assert b"PRIVATE_CATEGORY_SENTINEL" not in pdf


def test_html_report_is_offline_expansible_and_contains_diagnostics():
    batch = _batch()
    report = batch["results"][0]["analysis"]
    report["security"] = {"macros_executed": False, "embedded_objects_executed": False,
                          "external_connections_accessed": False, "external_relationships_followed": False,
                          "external_connections_updated": False, "formulas_recalculated": False,
                          "formulas_action": "not_applicable"}
    report["security"]["active_content_detected"] = True
    report["security"]["active_content_types"] = ["macro"]
    report["tables"][0]["quality"]["alerts"] = [
        {"severity": "critical", "count": 2, "message": "Valores incompatíveis com o tipo inferido."},
        {"severity": "information", "count": 1, "message": "Valores ausentes observados."},
    ]
    html = render_html_report(batch)
    assert "Abas analisadas" in html
    assert "Qualidade geral" in html
    assert "Segurança da análise" in html
    assert "Identificadores avaliados" in html
    assert "<details" in html
    assert 'class="alert critical"' in html
    assert 'class="alert information"' in html
    assert "Conteúdo potencialmente ativo detectado" in html
    assert "Foi identificado, mas não executado" in html
    assert "https://" not in html
    assert "<script" not in html


def test_report_api_and_frontend_use_existing_payload_without_reanalysis():
    from app.api.routes import export_html_report, export_pdf_report

    batch = _batch()
    html_response = export_html_report(batch)
    pdf_response = export_pdf_report(batch)
    assert html_response.media_type.startswith("text/html")
    assert "test-report.csv" in html_response.body.decode("utf-8")
    assert pdf_response.media_type == "application/pdf"
    assert pdf_response.body.startswith(b"%PDF-")

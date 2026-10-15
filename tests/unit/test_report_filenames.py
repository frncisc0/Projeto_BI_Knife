from datetime import datetime, timezone

from app.services.report_filename_service import content_disposition, report_filename


STAMP = datetime(2026, 10, 14, 22, 51, 29, tzinfo=timezone.utc)


def test_csv_and_xlsx_report_names_keep_source_stem_and_report_extension():
    for source, extension, expected_stem in [
        ("conjunto-dados.csv", "pdf", "conjunto-dados"),
        ("Risco Trabalhista - 08-2026.xlsx", "html", "Risco Trabalhista - 08-2026"),
    ]:
        payload = {"results": [{"filename": source, "analysis": {"filename": source,
                                                                      "analyzed_at": STAMP.isoformat()}}]}
        assert report_filename(payload, extension) == f"{expected_stem}_2026-10-14_22-51-29_BI-Swiss-Knife.{extension}"


def test_report_names_preserve_accents_and_replace_invalid_windows_characters():
    payload = {"results": [{"filename": "C:/origem/Risco: São Paulo?.csv",
                            "analysis": {"analyzed_at": STAMP.isoformat()}}]}

    assert report_filename(payload, ".json") == "Risco_ São Paulo__2026-10-14_22-51-29_BI-Swiss-Knife.json"


def test_report_name_handles_windows_reserved_stems_and_empty_names():
    payload = {"results": [{"filename": "CON.csv", "analysis": {"analyzed_at": STAMP.isoformat()}}]}
    empty = {"results": [{"filename": "...csv", "analysis": {"analyzed_at": STAMP.isoformat()}}]}

    assert report_filename(payload, "pdf").startswith("_CON_")
    assert report_filename(empty, "pdf").startswith("arquivo_")


def test_combined_report_uses_the_requested_batch_name_and_latest_analysis_time():
    payload = {"results": [
        {"filename": "a.csv", "analysis": {"analyzed_at": "2026-10-14T21:00:00-03:00"}},
        {"filename": "b.xlsx", "analysis": {"analyzed_at": "2026-10-14T22:51:29-03:00"}},
    ]}

    assert report_filename(payload, "pdf") == "BI-Swiss-Knife_analise-combinada_2026-10-14_22-51-29.pdf"
    assert report_filename(payload, "json") == "BI-Swiss-Knife_analise-combinada_2026-10-14_22-51-29.json"


def test_content_disposition_encodes_unicode_names_safely():
    value = content_disposition("Risco São Paulo_2026-10-14_22-51-29_BI-Swiss-Knife.pdf")
    assert value.startswith("attachment; filename*=UTF-8''")
    assert "S%C3%A3o" in value

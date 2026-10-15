import json
from io import BytesIO

from openpyxl import Workbook
from app.core.config import get_settings
from app.services.analysis_service import analyze_file
from app.services.report_service import report_payload
from app.structure.builder import normalize_column_name


def test_structural_profile_explains_observations_without_raw_cell_values():
    report = analyze_file(
        "registros.csv", "csv",
        "Registro_ID,Cliente_ID,Data_Cadastro,Quantidade,Descrição\n"
        "R-001,C-10,2026-01-01,3,VALOR_PRIVADO_SENTINELA\n"
        "R-002,C-11,2026-01-02,5,Outro texto privado\n"
        "R-003,C-10,2026-01-03,2,Mais um texto\n".encode(),
        "utf-8", header_mode="true",
    )
    payload = report_payload(report)
    profile = payload["structure_profiles"][0]
    serialized = json.dumps(profile, ensure_ascii=False)

    assert profile["version"] == "1.0"
    assert profile["row_count"] == 3
    assert profile["column_count"] == 5
    assert profile["grain_hypothesis"]["confidence"] in {"low", "medium", "high"}
    assert "registro" in profile["summary"].lower()
    assert profile["candidate_keys"]
    assert "VALOR_PRIVADO_SENTINELA" not in serialized
    assert "R-001" not in serialized


def test_column_name_normalization_recognizes_common_id_and_date_styles():
    identifier_names = ["Cliente_ID", "CLIENTE_ID", "clienteId", "id_cliente", "codigo_cliente", "cod_cliente"]
    normalized_ids = {normalize_column_name(name) for name in identifier_names}
    date_names = ["Data_Cadastro", "data cadastro", "dt_cadastro", "DataCadastro"]
    normalized_dates = {normalize_column_name(name) for name in date_names}

    assert len(normalized_ids) == 1
    assert len(normalized_dates) == 1


def test_profile_reports_uncertainty_when_structure_does_not_support_a_grain():
    report = analyze_file("sem-grain.csv", "csv", b"Coluna A,Coluna B\na,b\nc,d\n", "utf-8", header_mode="true")
    profile = report_payload(report)["structure_profiles"][0]

    assert profile["grain_hypothesis"]["confidence"] == "low"
    assert "Não foi possível determinar com segurança" in profile["grain_hypothesis"]["label"]
    assert profile["limitations"]


def test_profile_reuses_composite_key_and_relationship_evidence():
    report = analyze_file(
        "competencias.csv", "csv",
        b"Contrato,Competencia,Valor\nA,2026-01,10\nA,2026-02,12\nB,2026-01,8\nB,2026-02,9\n",
        "utf-8", header_mode="true",
    )
    profile = report_payload(report)["structure_profiles"][0]
    composite = next((item for item in profile["candidate_keys"] if len(item["columns"]) > 1), None)

    assert composite is not None
    assert "Contrato" in composite["columns"]
    assert "Competencia" in composite["columns"]


def test_profile_is_created_from_excel_tables_too():
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Registros"
    sheet.append(["Registro_ID", "Categoria", "Valor"])
    sheet.append(["R-1", "A", 10])
    sheet.append(["R-2", "B", 15])
    buffer = BytesIO()
    workbook.save(buffer)
    payload = report_payload(analyze_file("registros.xlsx", "xlsx", buffer.getvalue()))

    assert payload["structure_profiles"][0]["table_name"] == "Registros"
    assert payload["structure_profiles"][0]["column_count"] == 3


def test_profile_confidence_decreases_when_the_table_is_sampled(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "enable_sampling", True)
    monkeypatch.setattr(settings, "sample_size", 2)
    monkeypatch.setattr(settings, "max_cells_to_analyze", 100)
    rows = "Registro_ID,Valor\n" + "\n".join(f"R-{index},{index * 10}" for index in range(1, 9)) + "\n"
    profile = report_payload(analyze_file("amostra.csv", "csv", rows.encode(), "utf-8",
                                          header_mode="true"))["structure_profiles"][0]

    assert profile["evaluated_row_count"] == 2
    assert profile["row_count"] == 8
    assert profile["confidence"] != "high"
    assert "amostra" in " ".join(profile["structural_warnings"]).lower()

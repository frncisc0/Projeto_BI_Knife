from io import BytesIO

from openpyxl import Workbook

from app.services.analysis_service import analyze_file


def test_xlsx_detects_sheets_and_relationships():
    workbook = Workbook()
    customers = workbook.active
    customers.title = "Clientes"
    customers.append(["id", "nome"])
    customers.append([10, "Ana"])
    customers.append([20, "Bia"])
    orders = workbook.create_sheet("Pedidos")
    orders.append(["pedido", "id"])
    orders.append([100, 10])
    orders.append([101, 20])
    buffer = BytesIO()
    workbook.save(buffer)

    report = analyze_file("sample.xlsx", "xlsx", buffer.getvalue())
    assert {table.name for table in report.tables} == {"Clientes", "Pedidos"}
    assert report.relationships
    assert report.relationships[0].coverage_pct == 100


def test_relationship_confidence_is_limited_when_tables_are_sampled(monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "enable_sampling", True)
    monkeypatch.setattr(settings, "sample_size", 1)

    workbook = Workbook()
    customers = workbook.active
    customers.title = "Clientes"
    customers.append(["cliente_id"])
    customers.append([10])
    customers.append([20])
    orders = workbook.create_sheet("Pedidos")
    orders.append(["cliente_id"])
    orders.append([10])
    orders.append([10])
    buffer = BytesIO()
    workbook.save(buffer)

    report = analyze_file("sampled.xlsx", "xlsx", buffer.getvalue())
    assert report.relationships
    assert report.relationships[0].confidence == "medium"
    assert "amostra" in report.relationships[0].reason

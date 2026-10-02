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

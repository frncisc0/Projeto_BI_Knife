"""Regenerates the golden input files.

The files are committed; run this only to recreate them deliberately:
    python tests/golden/build_inputs.py

Inputs are tiny on purpose: every expected value in test_golden.py was
calculated by hand from the rows below, not taken from the program output.
"""
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook

HERE = Path(__file__).parent / "inputs"

TEXT_FILES = {
    # (encoding, content)
    "br_excel.csv": ("cp1252",
        "id;categoria;cidade;valor;data_venda\n"
        "1;Eletrônicos;São Paulo;1.234,50;10/01/2024\n"
        "2;Móveis;Goiânia;80,00;05/02/2024\n"
        "3;Eletrônicos;São Paulo;2.500,00;15/03/2024\n"
        "4;Móveis;Brasília;;20/03/2024\n"
        "5;Eletrônicos;Goiânia;99,90;01/04/2024\n"),
    "intl.csv": ("utf-8",
        "order_id,product,amount,order_date\n"
        "A-1,Widget,10.50,2024-01-10\n"
        "A-2,Gadget,1000.25,2024-02-03\n"
        "A-3,Widget,7.00,2024-12-31\n"),
    "iso_low_days.csv": ("utf-8",
        "id,data\n1,2024-01-02\n2,2024-03-04\n3,2024-05-06\n4,2024-07-08\n"),
    "br_numbers.csv": ("utf-8",
        'id,preco\n1,R$ 1.234\n2,R$ 80\n3,"R$ 2.500,50"\n4,R$ 10.000\n'),
    "codes.csv": ("utf-8",
        "sku,descricao,qtd\nP12,Caneta,3\nAB-1001,Caderno,10\n00123,Borracha,7\nP900,Lapis,1\n"),
    "rh.csv": ("utf-8",
        "matricula,nome,salario,conta_bancaria,cpf,data_admissao,cargo\n"
        "1001,Ana Silva,5000.50,12345-6,111.222.333-44,2024-01-10,Analista\n"
        "1002,Bruno Lima,7200.00,98765-4,222.333.444-55,2023-05-02,Gerente\n"
        "1003,Caio Souza,3100.00,55555-1,333.444.555-66,2022-11-20,Analista\n"
        "1004,Dani Rocha,9100.00,44444-2,444.555.666-77,2021-03-15,Diretor\n"),
    "duplicates_nulls.csv": ("utf-8",
        "id,categoria,valor\n1,A,10\n2,B,20\n2,B,20\n3,,30\n4,C,\n"),
    "disguised_nulls.csv": ("utf-8",
        "id,status\n1,ativo\n2,n/d\n3,-\n4,inativo\n"),
    "fato_vendas.csv": ("utf-8",
        "venda_id,cliente_id,produto_id,valor\n"
        "1,1,10,100\n2,1,11,200\n3,2,10,150\n4,2,12,300\n5,3,11,120\n"
        "6,3,10,80\n7,1,12,90\n8,2,11,60\n9,3,12,40\n10,99,10,10\n"),
    "dim_cliente.csv": ("utf-8",
        "cliente_id,segmento\n1,Varejo\n2,Atacado\n3,Varejo\n"),
    "dim_produto.csv": ("utf-8",
        "produto_id,linha\n10,Papelaria\n11,Escritorio\n12,Informatica\n"),
}


def build_workbook(path: Path) -> None:
    workbook = Workbook()
    vendas = workbook.active
    vendas.title = "Vendas"
    vendas["A1"] = "Relatório de Vendas 2024"  # title above the table
    vendas.append([])
    vendas.append([])
    vendas.append(["pedido_id", "cliente_id", "valor", "data_pedido"])  # header on row 4
    vendas.append([101, 1, 50.0, datetime(2024, 1, 10)])
    vendas.append([102, 2, 75.5, datetime(2024, 2, 3)])
    vendas.append([103, 2, 20.0, datetime(2024, 3, 8)])
    clientes = workbook.create_sheet("Clientes")
    clientes.append(["cliente_id", "segmento"])
    clientes.append([1, "Varejo"])
    clientes.append([2, "Atacado"])
    workbook.create_sheet("Vazia")
    workbook.save(path)


if __name__ == "__main__":
    HERE.mkdir(exist_ok=True)
    for name, (encoding, content) in TEXT_FILES.items():
        (HERE / name).write_bytes(content.encode(encoding))
    build_workbook(HERE / "workbook.xlsx")
    print(f"{len(TEXT_FILES) + 1} arquivos gerados em {HERE}")

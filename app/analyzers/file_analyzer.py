from io import BytesIO

import pandas as pd

from app.core.exceptions import AnalysisError


def read_tables(content: bytes, file_type: str, csv_encoding: str | None) -> dict[str, pd.DataFrame]:
    try:
        if file_type == "xlsx":
            workbook = pd.ExcelFile(BytesIO(content), engine="openpyxl")
            return {name: workbook.parse(sheet_name=name) for name in workbook.sheet_names}
        frame = pd.read_csv(BytesIO(content), encoding=csv_encoding or "utf-8", sep=None, engine="python")
        return {"Dados": frame}
    except Exception as exc:
        raise AnalysisError("O arquivo foi validado, mas não pôde ser analisado. Verifique a estrutura e tente novamente.") from exc

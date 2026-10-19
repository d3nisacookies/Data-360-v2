"""Read any xlsx/xlsm/csv into plain tables: [{sheet, header_row, headers, rows}]."""
import csv
import io
from dataclasses import dataclass, field
from pathlib import Path

import openpyxl

MAX_ROWS = 200_000


@dataclass
class Table:
    sheet: str
    header_row: int  # 1-based row number in the sheet
    headers: list[str]
    rows: list[list] = field(default_factory=list)  # data rows after the header
    first_data_row: int = 0


def _find_header(rows: list[list]) -> int:
    """Index of the most header-like row among the first 15: most non-empty text cells."""
    best, best_i = -1, 0
    for i, r in enumerate(rows[:15]):
        texts = [c for c in r if isinstance(c, str) and c.strip() and not c.strip().startswith("=")]
        filled = [c for c in r if c not in (None, "")]
        score = len(texts) * 2 - (len(filled) - len(texts))
        if len(texts) >= 2 and score > best:
            best, best_i = score, i
    return best_i


def _table(sheet: str, raw: list[list]) -> Table | None:
    raw = [list(r) for r in raw]
    if not raw:
        return None
    h = _find_header(raw)
    headers = ["" if c is None else str(c).strip() for c in raw[h]]
    while headers and not headers[-1]:
        headers.pop()
    if len([x for x in headers if x]) < 2:
        return None
    rows = [r[:len(headers)] + [None] * (len(headers) - len(r)) for r in raw[h + 1:]]
    rows = [r for r in rows if any(c not in (None, "") for c in r)] if len(rows) < MAX_ROWS else rows[:MAX_ROWS]
    return Table(sheet=sheet, header_row=h + 1, headers=headers, rows=rows, first_data_row=h + 2)


def read_tables(path: str | Path) -> list[Table]:
    p = Path(path)
    ext = p.suffix.lower()
    if ext in (".xlsx", ".xlsm"):
        wb = openpyxl.load_workbook(p, read_only=True, data_only=True)
        out = []
        for ws in wb.worksheets:
            raw = []
            for i, r in enumerate(ws.iter_rows(values_only=True)):
                if i > MAX_ROWS:
                    break
                raw.append(list(r))
            t = _table(ws.title, raw)
            if t:
                out.append(t)
        wb.close()
        return out
    if ext in (".csv", ".txt"):
        data = p.read_bytes()
        for enc in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                text = data.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|") if text.strip() else csv.excel
        raw = [r for r in csv.reader(io.StringIO(text), dialect)]
        t = _table("CSV", raw)
        return [t] if t else []
    raise ValueError(f"Unsupported file type {ext}. Upload .xlsx, .xlsm or .csv")

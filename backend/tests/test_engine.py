"""Engine checks that don't need the API."""
from datetime import date
from pathlib import Path

import openpyxl
import pytest

from app.engine.core import Dataset, Rec, golden
from app.engine.values import differs, parse_number, parse_percent, validate_element
from app.ingest.detect import map_header

from .conftest import SAMPLES


def test_parse_numbers():
    assert parse_number("1.68bn") == 1.68e9
    assert parse_number("USD 175,000,000") == 175e6
    assert parse_number("SGD 135") == pytest.approx(100)
    assert parse_percent("2.68%") == pytest.approx(0.0268)
    assert parse_percent("150 bps") == pytest.approx(0.015)


def test_tolerances():
    assert not differs("Revenue", 1_000_000, 1_010_000)       # 1%: same
    assert differs("Revenue", 1.68e9, 1.85e9)                  # 9%: different
    assert differs("Facility_Amount", "300m", "310m")          # contractual amounts are exact
    assert not differs("Country", "US", "United States")
    assert not differs("External_Rating", "Baa1", "BBB+")


def test_header_mapping():
    assert map_header("Obligor")[0] == "Borrower_Name"
    assert map_header("Facility Limit")[0] == "Facility_Amount"
    assert map_header("Revenu")[0] == "Revenue"          # typo, fuzzy
    assert map_header("Favourite colour")[0] is None


def test_validity():
    assert validate_element("Amount", "500,000") == "No currency"
    assert validate_element("Code", "Term loan / RCF / Bridge") == "List of options, not a single value"
    assert validate_element("Code", "Internal grade e.g. 6-") == "Placeholder, not a real value"
    assert validate_element("Amount", "USD 1,000") is None


def test_golden_source_wins_over_majority():
    def rec(k, src, v):
        return Rec(key=k, source=src, zone="External", as_of=date(2026, 9, 1), flag="", upload_id=1, row=1, fields={"Registry_Status": v})
    ds = Dataset("X", [rec("a", "D&B", "Inactive"), rec("b", "Capital IQ", "Inactive"), rec("c", "Corporate Registry", "Active")],
                 [], [], [], date(2026, 10, 9))
    assert golden(ds, ["Registry_Status"])["Registry_Status"]["value"] == "Active"


def test_detects_every_seeded_defect(client, h):
    """The test dataset ships an answer key ('Data Quality Defects'); the engine never reads it.
    Every seeded defect should surface as an Assess issue on the same source and field."""
    from app.engine.reference import LABEL, name_key
    borrowers = {name_key(b["name"]): b["id"] for b in client.get("/api/borrowers", headers=h).json()}
    total = found = 0
    missed = []
    for f in sorted((SAMPLES / "external").glob("*.xlsx")):
        ws = openpyxl.load_workbook(f, read_only=True)["Data Quality Defects"]
        rows = [r for r in ws.iter_rows(min_row=2, values_only=True) if r[0]]
        if not rows:
            continue
        bid = borrowers[name_key(f.stem.split(" - ", 1)[1])]
        # assess the data as sourced (a fresh borrower view, before any Clean)
        from app.db import SessionLocal
        from app.models import Borrower
        from app.services import load_dataset
        from app.engine.assess import assess
        with SessionLocal() as db:
            res = assess(load_dataset(db, db.get(Borrower, bid), date(2026, 10, 9)), None)
        issues = [i for d in res["dims"].values() for i in d["issues"]]
        for _, _, src, field, typ, *_ in rows:
            total += 1
            lab = LABEL.get(field, field)
            ok = any((src in i["where"] and lab in i["detail"])
                     or (i["issue"] == "Conflicting values" and i["where"] == lab and src in i["detail"])
                     or (typ == "STALE" and i["issue"] == "Stale record" and src in i["where"])
                     or (typ == "INCONSISTENT" and i["issue"] == "Inconsistent record" and src in i["where"])
                     for i in issues)
            found += ok
            if not ok:
                missed.append((f.name, src, field, typ))
    assert total > 100
    assert found == total, missed

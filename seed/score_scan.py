"""Score a Data360 folder scan against the answer key written by make_scan_test.py.

Either fetch the last scan from a running Data360:
    python seed/score_scan.py scan-test-answer-key.json --url http://localhost:8080
(sign-in comes from ADMIN_EMAIL / ADMIN_PASSWORD in the environment or ./.env, or --email / --password)

or score a report downloaded from the Scan folder screen:
    python seed/score_scan.py scan-test-answer-key.json --report data360-scan-report.json

Standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path


def _env(name: str) -> str:
    if os.environ.get(name):
        return os.environ[name]
    for p in (Path.cwd() / ".env", Path(__file__).resolve().parent.parent / ".env"):
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith(name + "="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def fetch(url: str, email: str, password: str) -> dict:
    data = urllib.parse.urlencode({"username": email, "password": password}).encode()
    tok = json.load(urllib.request.urlopen(urllib.request.Request(url.rstrip("/") + "/api/auth/login", data=data)))["access_token"]
    req = urllib.request.Request(url.rstrip("/") + "/api/scan", headers={"Authorization": f"Bearer {tok}"})
    last = json.load(urllib.request.urlopen(req)).get("last")
    if not last:
        sys.exit("No scan has run yet. Open Data360 → Upload files → Scan folder.")
    return last


SUFFIXES = {"pte", "ltd", "limited", "inc", "llc", "lp", "sdn", "bhd", "co", "kk", "corp", "plc", "the"}


def norm(name: str) -> str:
    """Borrower name without case, punctuation or legal suffixes, as Data360 matches them."""
    words = "".join(c if c.isalnum() else " " for c in str(name).lower()).split()
    return " ".join(w for w in words if w not in SUFFIXES)


def score(key: dict, report: dict) -> dict:
    got = {f["path"]: f for f in report.get("files", [])}
    rows, groups = [], defaultdict(list)
    for k in key["files"]:
        r = got.get(k["path"])
        outcome = r["outcome"] if r else "skipped"
        if k["group"]:
            groups[k["group"]].append(outcome)
        if k["expect"] in ("loaded", "duplicate"):
            ok = outcome in ("loaded", "duplicate")          # which copy loads first depends on folder order
            if ok and k["borrowers"] and outcome == "loaded":
                found = {norm(b) for b in (r or {}).get("borrowers", [])}
                missing = [b for b in k["borrowers"] if norm(b) not in found]
                ok = not missing
                note = f"borrowers missing: {', '.join(missing)}" if missing else ""
            else:
                note = ""
        else:
            ok, note = outcome == k["expect"], ""
        rows.append({**k, "got": outcome, "ok": ok, "note": note or ((r or {}).get("note", "") if not ok else "")})
    # each group of identical files loads at most once
    for g, outs in groups.items():
        if outs.count("loaded") > 1:
            for r in rows:
                if r["group"] == g and r["got"] == "loaded":
                    r["ok"], r["note"] = False, "identical file loaded twice"
    extra = [p for p in got if p not in {k["path"] for k in key["files"]}]
    want_b, got_b = {norm(b) for b in key["borrowers"]}, {norm(b) for b in report.get("borrowers", [])}
    by = lambda e: [r for r in rows if r["expect"] == e]
    data_files = [r for r in rows if r["expect"] in ("loaded", "duplicate")]
    return {
        "rows": rows, "extra": extra,
        "found_data": (sum(r["ok"] for r in data_files), len(data_files)),
        "decoys_rejected": (sum(r["ok"] for r in by("not_recognised")), len(by("not_recognised"))),
        "documents_listed": (sum(r["ok"] for r in by("not_read_yet")), len(by("not_read_yet"))),
        "skipped_correctly": (sum(r["ok"] for r in by("skipped")), len(by("skipped"))),
        "borrowers_found": sorted(want_b & got_b), "borrowers_missed": sorted(want_b - got_b), "borrowers_unexpected": sorted(got_b - want_b),
        "passed": all(r["ok"] for r in rows) and want_b == got_b,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("key")
    ap.add_argument("--report")
    ap.add_argument("--url", default="http://localhost:8080")
    ap.add_argument("--email", default=None)
    ap.add_argument("--password", default=None)
    a = ap.parse_args()
    key = json.loads(Path(a.key).read_text(encoding="utf-8"))
    report = json.loads(Path(a.report).read_text(encoding="utf-8")) if a.report else \
        fetch(a.url, a.email or _env("ADMIN_EMAIL") or "admin@data360.local", a.password or _env("ADMIN_PASSWORD"))
    s = score(key, report)
    print(f"Scan of {report.get('root')} at {report.get('at')}\n")
    for r in s["rows"]:
        print(f"  {'PASS' if r['ok'] else 'FAIL'}  {r['path']}\n        expected {r['expect']}, got {r['got']}" + (f" ({r['note']})" if r["note"] else ""))
    if s["extra"]:
        print("\n  Files in the report that the answer key does not list:", *s["extra"], sep="\n    ")
    f = lambda t: f"{t[0]} of {t[1]}"
    print(f"\nData files found and loaded once : {f(s['found_data'])}")
    print(f"Decoys rejected                  : {f(s['decoys_rejected'])}")
    print(f"Documents listed for the AI step : {f(s['documents_listed'])}")
    print(f"System, hidden and other skipped : {f(s['skipped_correctly'])}")
    print(f"Borrowers found                  : {len(s['borrowers_found'])} of {len(key['borrowers'])}"
          + (f"; missed {', '.join(s['borrowers_missed'])}" if s["borrowers_missed"] else "")
          + (f"; unexpected {', '.join(s['borrowers_unexpected'])}" if s["borrowers_unexpected"] else ""))
    print("\nRESULT:", "PASS" if s["passed"] else "FAIL")
    sys.exit(0 if s["passed"] else 1)


if __name__ == "__main__":
    main()

"""Confidence stages for the battery: Sourced → After Clean → After Normalise.

Sourced and After Clean come from Assess (the cleaned data is re-scored). After Normalise
applies the same uplift rules as the demo: definitions close part of the remaining gap, and
the stage is provisional until a reviewer signs off the golden record.
"""
from .assess import DIMS, rate

STD = list(DIMS)


def _avg(d: dict) -> int | None:
    v = [d[k] for k in STD if d.get(k) is not None]
    return round(sum(v) / len(v)) if v else None


def cap_rating(stage: dict) -> dict:
    r = rate(stage["pct"])
    weak = sorted([k for k in STD if stage["dims"].get(k) is not None and stage["dims"][k] < 70], key=lambda k: stage["dims"][k])
    if r == "high" and weak:
        return {"r": "med", "cap": f"capped by {weak[0]} {stage['dims'][weak[0]]}"}
    return {"r": r, "cap": ""}


def stages(assess: dict | None, norm: dict | None) -> list[dict] | None:
    if not assess:
        return None
    out = []
    for i, s in enumerate(assess["stages"]):
        d = dict(s["dims"])
        why = {}
        if i:
            prev = assess["stages"][i - 1]["dims"]
            for k in STD:
                if d.get(k) != prev.get(k):
                    why[k] = assess["dims"][k]["basis"]
        out.append({"key": s["key"], "label": "Sourced" if s["key"] == "sourced" else s["label"], "dims": d, "pct": _avg(d),
                    "why": why, "provisional": s["key"] != "sourced"})
    if norm and norm.get("out"):
        O = norm["out"]
        d = dict(out[-1]["dims"])
        w = {}
        if "Master data" in O or "Semantic layer" in O:
            if d.get("Consistency") is not None:
                d["Consistency"] = round(d["Consistency"] + (100 - d["Consistency"]) * 0.5)
                w["Consistency"] = "Names, identifiers and terms resolved to one master record and definition (half the remaining gap)"
        if "Reporting dimensions" in O or "Metrics" in O:
            if d.get("Validity") is not None:
                d["Validity"] = round(d["Validity"] + (100 - d["Validity"]) * 0.5)
                w["Validity"] = "Codes, units and formats conformed to the reporting standards (half the remaining gap)"
        if "Metrics" in O and d.get("Business relevance") is not None:
            rows = O["Metrics"]["rows"]
            r = sum(1 for x in rows if x[4] != "—") / len(rows) if rows else 0
            d["Business relevance"] = round(d["Business relevance"] + (100 - d["Business relevance"]) * 0.25 * r)
            w["Business relevance"] = f"{round(r * 100)}% of certified metrics calculated for the memo (a quarter of the gap, scaled)"
        out.append({"key": "normalised", "label": "After Normalise", "dims": d, "pct": _avg(d), "why": w, "provisional": True})
    for s in out:
        s.update(cap_rating(s))
    return out


def breakdown(S: list[dict]) -> dict | None:
    if not S or len(S) < 2:
        return None
    rows = []
    for k in STD:
        cells = []
        for i, x in enumerate(S):
            v = x["dims"].get(k)
            dl = (v - S[i - 1]["dims"].get(k)) if i and v is not None and S[i - 1]["dims"].get(k) is not None else 0
            cells.append(f"{v if v is not None else '—'}{f' ({dl:+d})' if dl else ''}")
        why = "; ".join(f"{x['label']}: {x['why'][k]}" for x in S[1:] if x["why"].get(k)) or "No change"
        rows.append([k, *cells, why])
    rows.append(["Overall", *[f"{x['pct']}%" for x in S], ""])
    return {"head": ["Criterion", *[x["label"] for x in S], "Why it moved"], "rows": rows}

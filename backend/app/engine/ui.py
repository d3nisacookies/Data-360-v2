"""Small constructors for server-described screen sections (drawn by the React SectionView).

A section: {"title", "sub", "blocks": [...]}. Block types: headline, kpis, table, bars, notes,
hint, cards, gantt, pgantt, matrix, decision, flow, h3, range, search, assume, radio, ptrack.
Table cells are plain strings/numbers or dicts made by the helpers below.
"""


def chip(kind, text):
    return {"t": "chip", "kind": kind, "text": str(text)}


def bold(text, hint=""):
    return {"t": "bold", "text": str(text), "hint": str(hint or "")}


def mono(text):
    return {"t": "mono", "text": str(text)}


def hint(text):
    return {"t": "hint", "text": str(text)}


def bar(pct, tone="", text=""):
    return {"t": "bar", "pct": max(0, min(100, pct or 0)), "tone": tone, "text": str(text)}


def btn(label, action, arg=None, disabled=False, primary=False, confirm=""):
    return {"t": "btn", "label": label, "action": action, "arg": arg, "disabled": bool(disabled), "primary": primary, "confirm": confirm}


def select(action, arg, options, value="", placeholder="Choose…", disabled=False):
    return {"t": "select", "action": action, "arg": arg, "options": options, "value": value or "", "placeholder": placeholder, "disabled": bool(disabled)}


def uplift(now, to, tone=""):
    return {"t": "uplift", "now": now, "to": to, "tone": tone}


def table(head, rows, num=None, title="", small=False, row_class=None, flat=True):
    return {"type": "table", "title": title, "head": head, "rows": rows, "num": num or [], "small": small, "rowClass": row_class or [], "flat": flat}


def kpis(items, five=False):
    """items: [(value, label) or (value, label, tone)]"""
    return {"type": "kpis", "five": five, "items": [{"v": str(i[0]), "k": i[1], "tone": i[2] if len(i) > 2 else ""} for i in items]}


def headline(text):
    """**bold** segments are rendered bold."""
    return {"type": "headline", "text": text}


def notes(items):
    return {"type": "notes", "items": items}


def hint_block(text, tone=""):
    return {"type": "hint", "text": text, "tone": tone}


def h3(text):
    return {"type": "h3", "text": text}


def section(title, sub="", blocks=None, foot=None, id=None):
    return {"title": title, "sub": sub, "blocks": blocks or [], "foot": foot, "id": id}


IMP = {"High": "bad", "Medium": "warn", "Low": "idle"}
RAGC = {"g": ("ok", "Green"), "a": ("warn", "Amber"), "r": ("bad", "Red"), "na": ("idle", "No data")}


def heat(v):
    return "idle" if v is None else "ok" if v >= 85 else "warn" if v >= 60 else "bad"


def cell(text, cls="", title="", strong=False):
    """A plain cell with a CSS class (e.g. heat colours 'hc ok') and a tooltip."""
    return {"t": "cell", "text": str(text), "cls": cls, "title": str(title or ""), "strong": strong}


def num_input(action, arg, value, step="any", disabled=False, suffix=""):
    return {"t": "num", "action": action, "arg": arg, "value": value, "step": step, "disabled": bool(disabled), "suffix": suffix}


def group(*items):
    return {"t": "group", "items": list(items)}


def details(summary, blocks):
    return {"type": "details", "summary": summary, "blocks": blocks}

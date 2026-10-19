"""Check that every figure in a report was produced by a tool.

The agent is allowed to round (12.47 may be written "12,5" or "12"), to express
fractions as percentages (0.2 as "20%") and to drop signs, but not to invent or
compute numbers itself. Reports are in Italian, so "1.234,5" and "3,4" are
parsed as numbers too.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b")
_LIST_MARKER = re.compile(r"(?m)^\s*\d+[.)]\s")
_HEADING = re.compile(r"(?m)^#+.*$")
_NUMBER = re.compile(r"(?<![\w.,])(\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?)(\s?%)?")


@dataclass
class GroundingResult:
    numbers: list[str] = field(default_factory=list)
    ungrounded: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.ungrounded

    @property
    def grounded_share(self) -> float:
        return 1.0 if not self.numbers else 1 - len(self.ungrounded) / len(self.numbers)


def parse_number(token: str) -> tuple[float, int]:
    """Parse an Italian or English formatted number; returns value and decimals shown."""
    if "," in token:
        whole, dec = token.replace(".", "").split(",", 1)
        return float(f"{whole}.{dec}"), len(dec)
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", token):
        return float(token.replace(".", "")), 0
    if "." in token:
        return float(token), len(token.split(".", 1)[1])
    return float(token), 0


def extract_numbers(text: str) -> list[tuple[str, float, int, bool]]:
    """(raw, value, decimals, is_percent) for each figure in the text, skipping dates, years and list markers."""
    text = _DATE.sub(" ", text)
    text = _HEADING.sub(" ", text)
    text = _LIST_MARKER.sub(" ", text)
    out = []
    for m in _NUMBER.finditer(text):
        raw = m.group(0).strip()
        value, decimals = parse_number(m.group(1))
        is_percent = m.group(2) is not None
        if not is_percent and decimals == 0 and (value <= 10 or 2000 <= value <= 2100):
            continue  # small counts ("3 settimane") and years are not checked
        out.append((raw, value, decimals, is_percent))
    return out


def collect_values(obj) -> set[float]:
    """Every number in a nested tool result, plus its percentage form."""
    values: set[float] = set()

    def walk(x):
        if isinstance(x, bool) or x is None:
            return
        if isinstance(x, (int, float)):
            values.add(abs(float(x)))
            values.add(abs(float(x)) * 100)
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, (list, tuple)):
            for v in x:
                walk(v)
        elif isinstance(x, str):
            for _, v, _, _ in extract_numbers(x):
                values.add(v)

    walk(obj)
    return values


def check(report: str, tool_results: list) -> GroundingResult:
    sources = collect_values(tool_results)
    res = GroundingResult()
    for raw, value, decimals, _ in extract_numbers(report):
        res.numbers.append(raw)
        tol = 0.5 * 10 ** (-decimals) + 1e-9
        if not any(abs(value - s) <= tol for s in sources):
            res.ungrounded.append(raw)
    return res

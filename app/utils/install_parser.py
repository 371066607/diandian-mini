from __future__ import annotations

import re


INSTALL_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([KMB])\+\s*$", re.IGNORECASE)
PLAIN_INSTALL_RE = re.compile(r"^\s*([\d,]+)\+\s*$")
UNIT_MAP = {
    "K": 1_000,
    "M": 1_000_000,
    "B": 1_000_000_000,
}


def parse_installs(text: str | None) -> tuple[int | None, int | None]:
    if not text:
        return None, None

    plain_match = PLAIN_INSTALL_RE.match(text)
    if plain_match:
        return int(plain_match.group(1).replace(",", "")), None

    unit_match = INSTALL_RE.match(text)
    if not unit_match:
        return None, None

    amount = float(unit_match.group(1))
    unit = unit_match.group(2).upper()
    multiplier = UNIT_MAP[unit]
    return int(amount * multiplier), None


def parse_install_range(installs: str | None) -> tuple[int | None, int | None]:
    minimum, _ = parse_installs(installs)
    if minimum is None or not installs:
        return None, None
    match = INSTALL_RE.match(installs)
    if not match:
        return minimum, None
    unit = match.group(2).upper()
    maximum = minimum * 5 if unit != "B" else None
    return minimum, maximum

#!/usr/bin/env python3
"""Turn a RAW pasted sportsbook board into the ``(name, american)`` rows that
``gen_books`` wants, so a board never has to be retyped by hand.

WHY THIS EXISTS (cost): entering a hand book used to mean transcribing every
row of a ~40-driver board into a Python tuple list, per tier, per book. That
transcription is the single most expensive part of a race weekend — it is pure
retyping, it scales with board size, and every retyped row is a chance to fork
a driver or fat-finger a price. Pasting the board through this parser instead
keeps the raw text as the only thing that moves.

USAGE — paste the board verbatim into a triple-quoted string and hand it over:

    import parse_board as pb, gen_books as gb

    WIN = '''
    Ryan Blaney        +650
    Chase Elliott      +900
    Darrell Wallace Jr +2500
    '''
    gb.write_book("caesars.json", "Caesars", {"winner": (pb.rows(WIN), 1),
                                              "top3":   (pb.rows(T3), 3)})

Or straight from the shell, to eyeball what a paste parses to:

    python3 parse_board.py board.txt          # prints "Name  +650" per row
    pbpaste | python3 parse_board.py -        # from the clipboard

LAYOUTS HANDLED (books differ, and a screen-copy often splits columns):

    Ryan Blaney +650            name then odds, any run of whitespace or tabs
    +650 Ryan Blaney            odds then name
    Ryan Blaney | +650          separated by | or , or a tab
    Ryan Blaney                 name and odds on ALTERNATING lines, which is
    +650                        what copying a web board usually produces
    Ryan Blaney 7.50            decimal odds  (>= 1.01, converted to American)
    Ryan Blaney 13/2            fractional odds (converted to American)

Header/junk lines ("Driver", "To Win", "Odds", "Cup Series") are skipped. A
line that looks like a driver row but whose name is not a known driver RAISES,
matching gen_books' philosophy that a typo should fail loudly rather than
silently fork a driver into two rows — pass ``strict=False`` to collect the
misses in ``rows_with_errors()`` instead.

Run ``python3 parse_board.py`` with no arguments for a self-test.
"""

from __future__ import annotations

import re
import sys

import gen_books as gb

# A token that is unambiguously American odds: a sign followed by >=100.
_AMERICAN = re.compile(r"^[+−-]\s?\d{3,6}$")
# Bare integer >= 100 with no sign — some books drop the '+' on longshots.
_BARE_AMERICAN = re.compile(r"^\d{3,6}$")
_DECIMAL = re.compile(r"^\d{1,3}\.\d{1,3}$")
_FRACTIONAL = re.compile(r"^(\d{1,5})\s*/\s*(\d{1,5})$")
# Shape of a price token, for anchoring a split at either end of a line. This
# only has to be permissive enough to find the candidate; _american() is what
# actually decides whether it is a real price.
_PRICE_TOK = r"[+−-]?\d{1,6}(?:\.\d{1,3})?(?:\s*/\s*\d{1,5})?"

# Column headers and page chrome. A line is junk only when EVERY word in it is
# a chrome word (plus, optionally, short bare numbers like the "10" in "Top
# 10"). Testing per-word rather than per-line is what lets a two-word header
# such as "Driver    Odds" be dropped while "Ryan Blaney" — also two words,
# also priceless on its own line — survives to the alternating-layout branch.
# No driver name consists solely of these words, so no real row is lost.
_JUNK_WORDS = {
    "driver", "drivers", "odds", "price", "prices", "to", "win", "wins",
    "winner", "outright", "outrights", "top", "finish", "finishes", "market",
    "markets", "name", "selection", "selections", "bet", "bets", "wager",
    "wagers", "cup", "series", "xfinity", "truck", "trucks", "nascar", "race",
    "more", "show", "all", "of", "and", "the", "line", "lines", "board",
}
_WORD = re.compile(r"[a-z0-9]+")


def _is_junk(line: str) -> bool:
    s = line.strip()
    if not s or not re.search(r"[a-zA-Z0-9]", s):
        return True                          # blank or pure separator rule
    words = _WORD.findall(s.lower())
    if not words:
        return True
    for w in words:
        if w in _JUNK_WORDS:
            continue
        if w.isdigit() and len(w) <= 2:
            continue                         # the "10" in "Top 10"
        return False
    return True


def _american(tok: str):
    """American odds for a price token, or None if it isn't a price."""
    t = tok.strip().replace("−", "-").replace(" ", "")
    if _AMERICAN.match(t):
        return int(t.replace("+", ""))
    if _BARE_AMERICAN.match(t):
        return int(t)                       # unsigned 3+ digits: a '+' price
    if _DECIMAL.match(t):
        d = float(t)
        if d <= 1.0:
            return None
        # decimal -> american
        return round((d - 1) * 100) if d >= 2.0 else round(-100 / (d - 1))
    m = _FRACTIONAL.match(t)
    if m:
        num, den = int(m.group(1)), int(m.group(2))
        if den == 0:
            return None
        f = num / den
        return round(f * 100) if f >= 1.0 else round(-100 / f)
    return None


def _split(line: str):
    """Split a line into (name_part, price_token) in either order, or None."""
    s = line.strip().strip("|").strip()
    if not s:
        return None
    # Explicit separators first (| , tab), then fall back to whitespace runs.
    for sep in ("|", "\t", ","):
        if sep in s:
            parts = [p.strip() for p in s.split(sep) if p.strip()]
            break
    else:
        parts = [s]
    if len(parts) > 1:
        # An explicit separator already told us where the columns are.
        if _american(parts[-1]) is not None:
            return " ".join(parts[:-1]).strip(), parts[-1]
        if _american(parts[0]) is not None:
            return " ".join(parts[1:]).strip(), parts[0]
        return None
    # Single field: anchor on a price at either end. Anchoring explicitly (rather
    # than splitting on the last space) is what makes "+650 Ryan Blaney" work —
    # a trailing-space split would cut it as ("+650 Ryan", "Blaney").
    m = re.match(rf"^({_PRICE_TOK})\s+(.+)$", s)
    if m and _american(m.group(1)) is not None:
        return m.group(2).strip(), m.group(1)
    m = re.match(rf"^(.+?)\s+({_PRICE_TOK})$", s)
    if m and _american(m.group(2)) is not None:
        return m.group(1).strip(), m.group(2)
    return None


def _is_price_line(line: str) -> bool:
    return _american(line.strip()) is not None


def rows_with_errors(text: str):
    """Parse a board. Returns (rows, errors) — errors are (line, reason)."""
    rows, errors = [], []
    lines = [ln.strip() for ln in (text or "").splitlines()]
    i = 0
    while i < len(lines):
        line = lines[i]
        if _is_junk(line):
            i += 1
            continue
        pair = _split(line)
        if pair is None:
            # Alternating layout: a bare name whose price is the next usable line.
            if not _is_price_line(line):
                j = i + 1
                while j < len(lines) and not lines[j]:
                    j += 1
                if j < len(lines) and _is_price_line(lines[j]):
                    pair, i = (line, lines[j]), j
                else:
                    errors.append((line, "no price found"))
                    i += 1
                    continue
            else:
                i += 1                      # stray price with no name; skip
                continue
        name, tok = pair
        american = _american(tok)
        if not name:
            errors.append((line, "price with no driver name"))
        else:
            try:
                rows.append((gb.canon(name), american))
            except KeyError:
                errors.append((line, f"unknown driver {name!r}"))
        i += 1
    return rows, errors


def rows(text: str, strict: bool = True):
    """Parse a board into [(canonical_name, american), ...].

    Raises on any unparsed/unknown row so a bad paste fails loudly (same
    contract as gen_books.canon). Pass strict=False to skip bad rows.
    """
    parsed, errors = rows_with_errors(text)
    if errors and strict:
        detail = "\n".join(f"  {ln!r}: {why}" for ln, why in errors[:12])
        more = f"\n  (+{len(errors) - 12} more)" if len(errors) > 12 else ""
        raise ValueError(
            f"parse_board: {len(errors)} unparsed row(s); fix the paste or pass "
            f"strict=False:\n{detail}{more}")
    return parsed


def _selftest() -> None:
    one_line = """
    Driver              Odds
    Ryan Blaney         +650
    Chase Elliott       +900
    Darrell Wallace Jr  +2500
    Kyle Larson         -110
    """
    assert rows(one_line) == [("Ryan Blaney", 650), ("Chase Elliott", 900),
                              ("Bubba Wallace", 2500), ("Kyle Larson", -110)]

    alternating = """
    Ryan Blaney
    +650
    A.J. Allmendinger
    +5000
    """
    assert rows(alternating) == [("Ryan Blaney", 650), ("AJ Allmendinger", 5000)]

    odds_first = "+650 Ryan Blaney\n-110 Kyle Larson"
    assert rows(odds_first) == [("Ryan Blaney", 650), ("Kyle Larson", -110)]

    separators = "Ryan Blaney | +650\nKyle Larson,-110\nTy Gibbs\t+1400"
    assert rows(separators) == [("Ryan Blaney", 650), ("Kyle Larson", -110),
                                ("Ty Gibbs", 1400)]

    # decimal 7.5 -> +650; 1.91 -> -110; fractional 13/2 -> +650
    assert rows("Ryan Blaney 7.50") == [("Ryan Blaney", 650)]
    assert rows("Kyle Larson 1.91") == [("Kyle Larson", -110)]
    assert rows("Ryan Blaney 13/2") == [("Ryan Blaney", 650)]

    # Unsigned longshot, and accented/aliased canonicalization.
    assert rows("Cody Ware 25000") == [("Cody Ware", 25000)]
    assert rows("Daniel Suarez +1800") == [("Daniel Suárez", 1800)]
    assert rows("John Hunter Nemechek +6000") == [("John H. Nemechek", 6000)]

    # A typo must fail loudly, not silently fork a driver.
    try:
        rows("Ryan Blayne +650")
    except ValueError as e:
        assert "unknown driver" in str(e), e
    else:
        raise AssertionError("expected a typo to raise")

    # ...unless explicitly told not to.
    assert rows("Ryan Blayne +650\nKyle Larson -110", strict=False) == [("Kyle Larson", -110)]

    # No-vig round-trip through gen_books, the actual downstream contract.
    tier = gb.build_tier(rows(one_line), 1)
    assert abs(sum(d["novig"] for d in tier["drivers"]) - 1.0) < 1e-9
    print("parse_board self-test OK — 6 layouts, 3 odds formats, canon + no-vig round-trip")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        src = sys.stdin.read() if sys.argv[1] == "-" else open(sys.argv[1], encoding="utf-8").read()
        parsed, errors = rows_with_errors(src)
        for name, a in parsed:
            print(f"{name:24} {a:+d}")
        print(f"\n{len(parsed)} row(s)", file=sys.stderr)
        for ln, why in errors:
            print(f"  UNPARSED {ln!r}: {why}", file=sys.stderr)
        sys.exit(1 if errors else 0)
    _selftest()

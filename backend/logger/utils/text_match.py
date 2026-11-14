"""Forgiving term matching for the chat tools.

People refer to the same thing in many spellings: "Finches", "FinchesLab",
"Finches Lab", "finches-lab", "FinchesAI"; "CSE 257" vs "cse257"; "paper"
vs "papers". A plain case-insensitive substring test misses most of those,
which is why the chat used to come back empty for perfectly good questions.

TermMatcher compiles one search term into a regex that:
  - splits CamelCase and letter/digit boundaries in the *term*
    ("FinchesLab" -> finches + lab, "CSE257" -> cse + 257),
  - lets those parts be joined by any run of non-alphanumerics in the *text*
    (so "Finches Lab", "FinchesLab" and "finches-lab" all match),
  - anchors at a word start and treats a single long word as a prefix
    ("finch" matches "FinchesAI"), while short words (<= 3 chars, e.g. "MPI")
    must match a whole word,
  - accepts a simple singular/plural variant of the last part.
"""

from __future__ import annotations

import difflib
import re

_CAMEL_RE = re.compile(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Za-z])(?=\d)|(?<=\d)(?=[A-Za-z])")
_WORD_RE = re.compile(r"[a-z0-9]+")
_SEP = r"[\W_]*"


def _parts(term: str) -> list[str]:
    return _WORD_RE.findall(_CAMEL_RE.sub(" ", term).lower())


def _number_variants(word: str) -> list[str]:
    """The word plus a naive singular form (finches->finch, papers->paper,
    studies->study, classes->class). Only applied to words longer than 4 so
    short acronyms are left alone."""
    out = [word]
    if len(word) > 4:
        if word.endswith("ies"):
            out.append(word[:-3] + "y")
        elif word.endswith(("ches", "shes", "sses", "xes", "zes")):
            out.append(word[:-2])
        elif word.endswith("s") and not word.endswith("ss"):
            out.append(word[:-1])
    return out


class TermMatcher:
    """Compiled matcher for one search term. Falsy if the term has no
    searchable characters."""

    def __init__(self, term: str):
        self.term = (term or "").strip()
        parts = _parts(self.term)
        self.parts = parts
        if not parts:
            self.regex = None
            return
        *head, last = parts
        last_alt = "|".join(re.escape(v) for v in _number_variants(last))
        body = "".join(re.escape(p) + _SEP for p in head) + f"(?:{last_alt})"
        # A single short token ("mpi", "swl", "ai") must be a whole word, or it
        # matches inside unrelated words. Anything longer may be a prefix.
        # A trailing number is never a prefix: "CSE 257" must not hit "CSE 2570".
        whole_word = len(parts) == 1 and len(last) <= 3
        tail = r"\b" if whole_word else (r"(?!\d)" if last.isdigit() else "")
        self.regex = re.compile(r"\b" + body + tail, re.IGNORECASE)

    def __bool__(self) -> bool:
        return self.regex is not None

    def search(self, text: str | None) -> re.Match | None:
        if not self.regex or not text:
            return None
        return self.regex.search(text)

    def matches(self, text: str | None) -> bool:
        return self.search(text) is not None


def snippet(text: str, match: re.Match | None, width: int = 320) -> str:
    """A window of `text` centered on `match` (or its start), with ellipses.

    Daily narratives can be thousands of characters long; returning only the
    first 300 characters routinely cut off the very sentence that matched."""
    text = " ".join((text or "").split())
    if len(text) <= width:
        return text
    if match is None:
        return text[:width].rstrip() + "…"
    # Re-locate the match in the whitespace-collapsed text.
    m = re.search(re.escape(" ".join(match.group(0).split())), text, re.IGNORECASE)
    center = m.start() if m else 0
    start = max(0, center - width // 3)
    end = min(len(text), start + width)
    start = max(0, end - width)
    out = text[start:end].strip()
    return ("…" if start > 0 else "") + out + ("…" if end < len(text) else "")


def close_names(term: str, candidates: list[str], n: int = 6, cutoff: float = 0.6) -> list[str]:
    """Typo-tolerant suggestions ("Fiches" -> "FinchesLab") from a list of
    names, comparing on lowercased alphanumerics only."""
    key = "".join(_parts(term))
    if not key:
        return []
    by_key: dict[str, str] = {}
    for c in candidates:
        k = "".join(_parts(c))
        if k and k not in by_key:
            by_key[k] = c
    hits = difflib.get_close_matches(key, list(by_key), n=n, cutoff=cutoff)
    # Also surface names that merely start with the term ("fin" -> "FinchesLab").
    prefix = [k for k in by_key if k.startswith(key) and k not in hits]
    return [by_key[k] for k in hits + prefix][:n]

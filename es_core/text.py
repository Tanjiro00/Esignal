"""Text normalization and tokenization.

Deliberately free of domain vocabulary. The v1 pipeline encoded product names,
stop words and format markers as literal lists, which meant a genuinely new
product could not be recognized and every new niche required new code. Here the
only things removed are *structural*: markup, links, emoji and bracketed format
decorations. Whether a term is generic ("tutorial") or specific ("Seedance") is
decided later from corpus statistics, not from a list.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Iterator

_URL = re.compile(r"https?://\S+|www\.\S+")
_HANDLE = re.compile(r"[@#]\w+")
_BRACKETED = re.compile(r"[\(\[\{][^\)\]\}]{0,40}[\)\]\}]")
_SEPARATOR = re.compile(r"\s*[|·•—–]\s*")
_TOKEN = re.compile(r"[a-z0-9][a-z0-9+#.\-]*")
_REPEATED = re.compile(r"\s{2,}")

# A token that is only punctuation-ish noise once the pattern above ran.
_TRIM = "+#.-"


def strip_accents(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def normalize(value: str) -> str:
    """Lowercase, drop links/handles/bracketed decorations, collapse spacing."""

    text = strip_accents(value).lower()
    text = _URL.sub(" ", text)
    text = _HANDLE.sub(" ", text)
    text = _BRACKETED.sub(" ", text)
    text = _SEPARATOR.sub(" ", text)
    text = "".join(
        char if unicodedata.category(char)[0] not in {"S", "C"} else " " for char in text
    )
    return _REPEATED.sub(" ", text).strip()


def tokenize(value: str) -> tuple[str, ...]:
    """Return content tokens of a normalized string.

    Single characters are dropped because they carry no identifying power, but
    short product-like tokens ("v3", "o1", "gpt") are kept on purpose: those are
    exactly the shapes new model names take.
    """

    tokens: list[str] = []
    for match in _TOKEN.findall(normalize(value)):
        token = match.strip(_TRIM)
        if len(token) >= 2:
            tokens.append(token)
    return tuple(tokens)


def bigrams(tokens: Iterable[str]) -> Iterator[str]:
    previous: str | None = None
    for token in tokens:
        if previous is not None:
            yield f"{previous} {token}"
        previous = token


def terms(value: str, *, use_bigrams: bool = True) -> tuple[str, ...]:
    """Unigrams plus adjacent bigrams, deduplicated but order preserving."""

    tokens = tokenize(value)
    candidates: list[str] = list(tokens)
    if use_bigrams:
        candidates.extend(bigrams(tokens))
    seen: set[str] = set()
    ordered: list[str] = []
    for term in candidates:
        if term not in seen:
            seen.add(term)
            ordered.append(term)
    return tuple(ordered)


def jaccard(left: Iterable[str], right: Iterable[str]) -> float:
    first = set(left)
    second = set(right)
    if not first or not second:
        return 0.0
    return len(first & second) / len(first | second)


def containment(left: Iterable[str], right: Iterable[str]) -> float:
    """Share of the smaller token set contained in the larger one."""

    first = set(left)
    second = set(right)
    if not first or not second:
        return 0.0
    smaller, larger = (first, second) if len(first) <= len(second) else (second, first)
    return len(smaller & larger) / len(smaller)


__all__ = [
    "bigrams",
    "containment",
    "jaccard",
    "normalize",
    "strip_accents",
    "terms",
    "tokenize",
]

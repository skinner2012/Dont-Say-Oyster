"""Name-check helpers: the matching rules [R22] and the Chinese-character detector [R5]. Pure
functions over strings and string lists; they know nothing of cards. Each match function returns
the list items that matched, as given and in list order, so a caller can tell which name matched;
an empty list is no match."""

import re
import unicodedata
from collections.abc import Iterable

from opencc import OpenCC

_T2S = OpenCC("t2s")

# Chinese characters (SPEC.md Glossary): the CJK ideograph blocks, their extensions, and the
# compatibility ideographs, as whole blocks (Unicode 18 Blocks.txt).
_HAN_BLOCKS = (
    (0x3400, 0x4DBF),  # CJK Unified Ideographs Extension A
    (0x4E00, 0x9FFF),  # CJK Unified Ideographs
    (0xF900, 0xFAFF),  # CJK Compatibility Ideographs
    (0x20000, 0x2A6DF),  # Extension B
    (0x2A700, 0x2B73F),  # Extension C
    (0x2B740, 0x2B81F),  # Extension D
    (0x2B820, 0x2CEAF),  # Extension E
    (0x2CEB0, 0x2EBEF),  # Extension F
    (0x2EBF0, 0x2EE5F),  # Extension I
    (0x2F800, 0x2FA1F),  # CJK Compatibility Ideographs Supplement
    (0x30000, 0x3134F),  # Extension G
    (0x31350, 0x323AF),  # Extension H
    (0x323B0, 0x3347F),  # Extension J
)

_APOSTROPHES = {"'", "’"}


def normalize(text: str) -> str:
    """The [R22] normalization: NFKC, whitespace and category Z and P removed, lowercase, then
    Traditional to Simplified."""
    text = unicodedata.normalize("NFKC", text)
    text = "".join(ch for ch in text if not (ch.isspace() or unicodedata.category(ch)[0] in "ZP"))
    return str(_T2S.convert(text.lower()))


def chinese_contains(text: str, items: Iterable[str]) -> list[str]:
    """Items found in text as a substring after normalization [R22]."""
    normalized = normalize(text)
    return [item for item in items if normalize(item) in normalized]


def chinese_equals(text: str, items: Iterable[str]) -> list[str]:
    """Items equal to text after normalization [R22]."""
    normalized = normalize(text)
    return [item for item in items if normalize(item) == normalized]


def english_contains(text: str, items: Iterable[str]) -> list[str]:
    """Items found in text as a whole word or phrase, or as the item followed by s or es, after
    the English normalization [R22]."""
    normalized = _english_form(text)
    return [
        item
        for item in items
        if re.search(rf"(?<!\w){re.escape(_english_form(item))}(?:e?s)?(?!\w)", normalized)
    ]


def has_chinese_characters(text: str) -> bool:
    """Whether text has a code point in the Chinese-character blocks (SPEC.md Glossary) [R5]."""
    return any(low <= ord(ch) <= high for ch in text for low, high in _HAN_BLOCKS)


def _english_form(text: str) -> str:
    """NFKC, lowercase, apostrophes removed, every other category P character to a space, and
    runs of spaces collapsed to one [R22]."""
    text = unicodedata.normalize("NFKC", text).lower()
    text = "".join(
        "" if ch in _APOSTROPHES else " " if unicodedata.category(ch)[0] == "P" else ch
        for ch in text
    )
    return " ".join(text.split())

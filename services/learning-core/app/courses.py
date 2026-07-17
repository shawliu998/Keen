from __future__ import annotations

import re
import unicodedata

_WHITESPACE = re.compile(r"\s+")


def normalize_course_title_display(title: str) -> str:
    """Return the display-safe canonical spacing for a submitted course title."""

    return _WHITESPACE.sub(" ", unicodedata.normalize("NFKC", title)).strip()


def normalize_course_title_key(title: str) -> str:
    """Return the locale-independent uniqueness/idempotency identity for a title."""

    return normalize_course_title_display(title).casefold()

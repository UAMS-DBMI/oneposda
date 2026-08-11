"""The coercion dispatch table from ``Posda::DB::Modules::GetAttrs``.

Each coercion takes the value just read from the dataset plus the parameter
name (Posda passes the *key*, not the tag, as the ``$id`` used in error text)
and returns either a cleaned value or ``None``. Anything rejected is appended
to the caller's error list and ends up as a ``dicom_process_errors`` row.

These reproduce the Perl exactly, including its quirks -- notably that an
empty date string falls through to the "Bad date" branch, which is where the
``Bad date "" in dob`` rows that dominate ``dicom_process_errors`` come from.
"""

from __future__ import annotations

import re
from typing import Callable

_DATE_RE = re.compile(r"^(....)(..)(..)$")
_TIME_RE = re.compile(r"^(\d\d)(\d\d)(\d\d)$")
_TIME_FRAC_RE = re.compile(r"^(\d\d)(\d\d)(\d\d)\.(\d+)$")
_SPACE_DIGIT_RE = re.compile(r"^ (\d)$")
_INTEGERISH_RE = re.compile(r"^\s*[+-]?[0-9]+\s*$")
_LEADING_NUMBER_RE = re.compile(
    r"^\s*[+-]?(?:\d+\.?\d*(?:[eE][+-]?\d+)?|\.\d+(?:[eE][+-]?\d+)?)"
)

Coercion = Callable[[object, str, list[str]], object]


def _perl_numify(value: object) -> float:
    """Perl's implicit string-to-number conversion.

    Perl takes the leading numeric prefix and yields 0 when there isn't one,
    which is what makes ``$y > 0`` in the Date coercion behave the way it
    does for malformed years.
    """
    if isinstance(value, (int, float)):
        return float(value)
    match = _LEADING_NUMBER_RE.match(str(value))
    return float(match.group(0)) if match else 0.0


def date(value: object, name: str, errors: list[str]) -> str | None:
    """``Date`` -- reformat DICOM DA (``YYYYMMDD``) to ``YYYY/MM/DD``."""
    if value is None:
        return None
    if value == "<undef> ":
        return None
    # Perl's `$text &&` treats "" and "0" as false, sending them to the
    # error branch rather than the regex.
    match = _DATE_RE.match(_as_text(value)) if _perl_truthy(value) else None
    if match is None:
        errors.append(f'Bad date "{_as_text(value)}" in {name}')
        return None

    year, month, day = match.group(1), match.group(2), match.group(3)
    if year in ("    ", "????"):
        errors.append(f'Bad date "{_as_text(value)}" in {name}')
        return None
    month = _SPACE_DIGIT_RE.sub(r"0\1", month)
    day = _SPACE_DIGIT_RE.sub(r"0\1", day)

    y, m, d = _perl_numify(year), _perl_numify(month), _perl_numify(day)
    if not (y > 0 and 0 < m < 13 and 0 < d < 32):
        errors.append(f'Bad date "{_as_text(value)}" in {name}')
        return None
    return f"{int(y):04d}/{int(m):02d}/{int(d):02d}"


def timetag(value: object, name: str, errors: list[str]) -> str | None:
    """``Timetag`` -- reformat DICOM TM (``HHMMSS[.F]``) to ``HH:MM:SS[.F]``."""
    if value is None:
        return None
    if _perl_truthy(value):
        text = _as_text(value)
        match = _TIME_RE.match(text)
        if match:
            return f"{match.group(1)}:{match.group(2)}:{match.group(3)}"
        match = _TIME_FRAC_RE.match(text)
        if match:
            return (
                f"{match.group(1)}:{match.group(2)}:"
                f"{match.group(3)}.{match.group(4)}"
            )
    errors.append(f'Bad time "{_as_text(value)}" in {name}')
    return None


def multi_text(value: object, name: str, errors: list[str]) -> object:
    """``MultiText`` -- collapse a multi-valued element to a ``\\``-joined string."""
    if isinstance(value, list):
        return "\\".join("" if v is None else str(v) for v in value)
    return value


def undef_if_not_number(value: object, name: str, errors: list[str]) -> object:
    """``UndefIfNotNumber`` -- keep the original text, but only if integral.

    Posda returns the *unmodified* string on success, so surrounding
    whitespace that satisfied the regex is preserved and reaches the column.
    """
    if value is None:
        return None
    if not _INTEGERISH_RE.match(_as_text(value)):
        errors.append(f'Bad number "{_as_text(value)}" in {name}')
        return None
    return value


def integer(value: object, name: str, errors: list[str]) -> int | None:
    """``Integer`` -- truncate toward zero, complaining on any loss."""
    if value is None:
        return None
    number = _perl_numify(value)
    truncated = int(number)
    if truncated != number:
        errors.append(f"Error making {_as_text(value)} an integer\n")
    return truncated


def _perl_truthy(value: object) -> bool:
    if isinstance(value, str):
        return value not in ("", "0")
    if isinstance(value, list):
        return True
    return bool(value)


def _as_text(value: object) -> str:
    if isinstance(value, list):
        # A Perl array ref stringifies to ARRAY(0x...); the exact address is
        # meaningless, so use a stable stand-in in error text.
        return "ARRAY(0x0)"
    return str(value)


DISPATCH: dict[str, Coercion] = {
    "Date": date,
    "Timetag": timetag,
    "MultiText": multi_text,
    "UndefIfNotNumber": undef_if_not_number,
    "Integer": integer,
}


def get_attrs(
    values,
    params: dict[str, str],
    mod_list: dict[str, str],
    errors: list[str],
) -> dict[str, object]:
    """Reproduce ``Posda::DB::Modules::GetAttrs``.

    ``values`` is a :class:`posda.ingest.values.ParsedValues`. Every key in
    ``params`` is read; keys additionally named in ``mod_list`` are passed
    through the corresponding coercion.
    """
    result: dict[str, object] = {}
    for key, sig in params.items():
        value = values.get(sig)
        coercion_name = mod_list.get(key)
        if coercion_name is not None:
            coercion = DISPATCH.get(coercion_name)
            if coercion is not None:
                value = coercion(value, key, errors)
        result[key] = value
    return result

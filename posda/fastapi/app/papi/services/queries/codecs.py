"""Decode result cells the way DBD::Pg handed them to the Perl GUI.

DBD::Pg returned most non-integer columns as the server's text form
(``2026-08-26 21:48:29.123+00``, ``00:00:37.888997``, ``1.50``), and booleans
as ``1``/``0``. asyncpg would give datetimes, timedeltas and Decimals
instead, which render differently in the UI and in the CSV people have
scripts for, so those types are read as text.
"""

from typing import Any

TEXT_TYPES = (
    "numeric",
    "float4",
    "float8",
    "date",
    "time",
    "timetz",
    "timestamp",
    "timestamptz",
    "interval",
    "uuid",
    "json",
    "jsonb",
    "money",
)


def _identity(text: str) -> str:
    return text


def _bool_as_digit(text: str) -> str:
    return "1" if text == "t" else "0"


async def install_text_codecs(conn: Any) -> None:
    """Make ``conn`` (asyncpg) return the listed types as their text form."""
    for type_name in TEXT_TYPES:
        await conn.set_type_codec(
            type_name,
            schema="pg_catalog",
            encoder=_identity,
            decoder=_identity,
            format="text",
        )
    await conn.set_type_codec(
        "bool",
        schema="pg_catalog",
        encoder=_identity,
        decoder=_bool_as_digit,
        format="text",
    )

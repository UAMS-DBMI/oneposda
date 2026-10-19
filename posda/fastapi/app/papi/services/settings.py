"""Environment-derived settings for the ABC endpoints."""

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    cache_root: Path
    database_config: Path
    redis_host: str
    run_retention_days: int
    query_timeout_ms: int
    max_runs_per_user: int


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        cache_root=Path(os.environ.get("POSDA_CACHE_ROOT", "/home/posda/cache")),
        database_config=Path(
            os.environ.get(
                "POSDA_DATABASE_CONFIG",
                "/home/posda/posdatools/Config/databases.json",
            )
        ),
        redis_host=os.environ.get("POSDA_REDIS_HOST", "redis"),
        run_retention_days=_int_env("ABC_RUN_RETENTION_DAYS", 7),
        query_timeout_ms=_int_env("ABC_QUERY_TIMEOUT_MS", 0),
        max_runs_per_user=_int_env("ABC_MAX_RUNS_PER_USER", 5),
    )

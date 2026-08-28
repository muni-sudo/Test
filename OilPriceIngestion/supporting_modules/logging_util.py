"""Lightweight structured logging helper.

Snowpark stored-proc stdout is captured in the query log; we prefix messages so
they are greppable, and mirror important events to ETL_RUN_LOG / ALERT_LOG via
io_ops. This module has no Snowflake dependency so it is unit-testable.
"""
from __future__ import annotations

import sys
import traceback


def log(step: str, message: str, level: str = "INFO") -> None:
    """Emit a single structured line to stdout (captured by Snowflake)."""
    print(f"[ARG-LINEUP][{level}][{step}] {message}", file=sys.stdout, flush=True)


def log_exc(step: str, exc: BaseException) -> str:
    """Log an exception with traceback; return a one-line summary for the log tables."""
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    log(step, f"EXCEPTION: {exc}\n{tb}", level="ERROR")
    return f"{type(exc).__name__}: {exc}"

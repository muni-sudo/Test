"""Snowflake I/O helpers for the oil-price ingestion pipeline.

Audit logging (INGEST_FILE_LOG / ETL_RUN_LOG / ALERT_LOG), idempotency checks,
and stage uploads. All functions take a Snowpark ``session``.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import io
from typing import Optional

try:
    # Snowflake stored procedure environment (absolute imports)
    import constants as C
    from logging_util import log
except ImportError:
    # Local environment (relative imports)
    from . import constants as C
    from .logging_util import log


# --------------------------------------------------------------------------- #
# hashing
# --------------------------------------------------------------------------- #
def compute_file_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


# --------------------------------------------------------------------------- #
# reference reads
# --------------------------------------------------------------------------- #
def read_table(session, name: str, where: str = ""):
    q = f"SELECT * FROM {C.FQ}.{name}"
    if where:
        q += f" WHERE {where}"
    return session.sql(q).to_pandas()


# --------------------------------------------------------------------------- #
# audit + idempotency ledgers
# --------------------------------------------------------------------------- #
def _q(v) -> str:
    if v is None:
        return "NULL"
    return "'" + str(v).replace("'", "''") + "'"


def log_file(session, source: str, dataset: str, run_date: _dt.date, rows: int,
             status: str, message_id: str = None, file_name: str = None,
             file_hash: str = None, mode: str = "AUTO", detail: str = None) -> None:
    session.sql(f"""
        INSERT INTO {C.FQ}.INGEST_FILE_LOG
          (SOURCE, DATASET, RUN_DATE, FILE_NAME, FILE_HASH, MESSAGE_ID,
           ROW_COUNT, STATUS, LOAD_MODE, DETAIL)
        SELECT {_q(source)},{_q(dataset)},'{run_date}',{_q(file_name)},{_q(file_hash)},
               {_q(message_id)},{int(rows)},{_q(status)},{_q(mode)},{_q(detail)}
    """).collect()


def already_processed(session, message_id: str) -> bool:
    if not message_id:
        return False
    row = session.sql(f"SELECT COUNT(*) AS N FROM {C.FQ}.INGEST_FILE_LOG "
                      f"WHERE MESSAGE_ID = {_q(message_id)} AND STATUS IN ('LOADED','STAGED')").collect()
    return bool(row[0]["N"])


def file_hash_exists(session, file_hash: str, run_date: _dt.date) -> bool:
    if not file_hash:
        return False
    row = session.sql(f"SELECT COUNT(*) AS N FROM {C.FQ}.INGEST_FILE_LOG "
                      f"WHERE FILE_HASH={_q(file_hash)} AND RUN_DATE='{run_date}' "
                      f"AND STATUS IN ('LOADED','STAGED')").collect()
    return bool(row[0]["N"])


# --------------------------------------------------------------------------- #
# run log
# --------------------------------------------------------------------------- #
def start_step(session, run_date: _dt.date, step: str, mode: str = "AUTO") -> str:
    rid = session.sql("SELECT UUID_STRING() AS ID").collect()[0]["ID"]
    session.sql(f"""
        INSERT INTO {C.FQ}.ETL_RUN_LOG (RUN_ID, RUN_DATE, STEP, STATUS, RUN_MODE)
        SELECT {_q(rid)},'{run_date}',{_q(step)},'STARTED',{_q(mode)}
    """).collect()
    log(step, f"started (run_date={run_date}, mode={mode})")
    return rid


def end_step(session, run_id: str, status: str, rows_out: int = None,
             is_stale: bool = False, detail: str = None) -> None:
    sets = [f"STATUS={_q(status)}", "ENDED_AT=CURRENT_TIMESTAMP()",
            f"IS_STALE={'TRUE' if is_stale else 'FALSE'}"]
    if rows_out is not None:
        sets.append(f"ROWS_OUT={int(rows_out)}")
    if detail is not None:
        sets.append(f"DETAIL={_q(detail[:4000])}")
    session.sql(f"UPDATE {C.FQ}.ETL_RUN_LOG SET {', '.join(sets)} "
                f"WHERE RUN_ID={_q(run_id)}").collect()


# --------------------------------------------------------------------------- #
# alerts + stage IO
# --------------------------------------------------------------------------- #
def raise_alert(session, run_date: _dt.date, severity: str, step: str, message: str,
                email: bool = True) -> None:
    session.sql(f"""
        INSERT INTO {C.FQ}.ALERT_LOG (RUN_DATE, SEVERITY, STEP, MESSAGE)
        SELECT '{run_date}',{_q(severity)},{_q(step)},{_q(message)}
    """).collect()
    log(step, f"ALERT[{severity}] {message}", level=severity)
    if email:
        try:
            ops = read_table(session, "REF_EMAIL_RECIPIENTS", "RECIP_TYPE='OPS' AND ACTIVE=TRUE")
            to = ",".join(ops["EMAIL"].tolist()) if not ops.empty else ""
            if to:
                subj = f"[OIL-PRICE][{severity}] {step} {run_date}"
                body = message.replace("'", "''")
                session.sql(
                    f"CALL SYSTEM$SEND_EMAIL('ARG_EMAIL_INT','{to}','{subj}','{body}')"
                ).collect()
        except Exception as exc:  # never let alerting fail the pipeline
            log(step, f"alert email failed: {exc}", level="WARN")


def put_bytes(session, content: bytes, stage_path: str) -> None:
    """Upload raw bytes to an internal stage path (audit copy of a source file)."""
    session.file.put_stream(io.BytesIO(content), stage_path, auto_compress=False,
                            overwrite=True)

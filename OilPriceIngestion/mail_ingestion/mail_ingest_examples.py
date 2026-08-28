"""Example configurations and usage patterns for mail_ingestion library.

Shows how to configure and run different mail ingestion jobs.
"""
from __future__ import annotations

import datetime as _dt

from mail_ingestion import MailIngestConfig, ingest_attachments

try:
    # Snowflake stored procedure environment (files flat on the stage)
    import constants as C
except ImportError:
    # Local testing from the project root
    from supporting_modules import constants as C


# --- Example configs for common use cases -----------------------------------

def get_oils_config() -> MailIngestConfig:
    """Edible & Non Edible Oils - Excel price reports, any sender."""
    return MailIngestConfig(
        job_name=C.OILS_JOB_NAME,
        mailbox=C.SHARED_MAILBOX,
        sender_filter="",  # No sender filter - accept from any sender
        subject_filter=C.OILS_SUBJECT_MATCH,
        file_patterns=[".xlsx"],
        stage_path_template=C.STAGE_PATH_TEMPLATE,
        lookback_hours=36,
    )


def get_nabsa_config() -> MailIngestConfig:
    """NABSA Daily Circular - .xlsx files (Lineup + Sailed)."""
    return MailIngestConfig(
        job_name="NABSA",
        mailbox=C.SHARED_MAILBOX,
        sender_filter="navanithakrishnah.l@mindsprint.com",
        subject_filter="Daily Vessels Line Up",
        file_patterns=[".xlsx"],
        stage_path_template=C.STAGE_PATH_TEMPLATE,
        lookback_hours=36,
    )


def get_invoice_config() -> MailIngestConfig:
    """Invoices - accepts PDF, XLS, XLSX from Finance team."""
    return MailIngestConfig(
        job_name="INVOICES",
        mailbox=C.SHARED_MAILBOX,
        sender_filter="finance@company.com",
        subject_filter="Invoice",
        file_patterns=[".pdf", ".xls", ".xlsx"],
        stage_path_template=C.STAGE_PATH_TEMPLATE,
        lookback_hours=24,
    )


def get_manifest_config() -> MailIngestConfig:
    """Shipping Manifests - any file with 'manifest' in the name."""
    return MailIngestConfig(
        job_name="MANIFESTS",
        mailbox=C.SHARED_MAILBOX,
        sender_filter="shipping@logistics.com",
        subject_filter="Manifest",
        file_patterns=["manifest"],  # matches any file with 'manifest' in name
        stage_path_template=C.STAGE_PATH_TEMPLATE,
        lookback_hours=48,
    )


# --- Usage examples ---------------------------------------------------------

def run_oils_ingest(session, run_date: _dt.date = None, force: bool = False) -> dict:
    """Download and stage Edible & Non Edible Oils attachments.

    Can be called from a Snowflake stored procedure or directly from Python.

    Args:
        session: Snowpark session
        run_date: Date to process (default: today)
        force: If True, re-process even if already loaded

    Returns:
        dict with status, message, files_staged, messages_processed, run_id
    """
    if run_date is None:
        run_date = _dt.date.today()

    return ingest_attachments(session, get_oils_config(), run_date, force=force)


def run_nabsa_ingest(session, run_date: _dt.date = None, force: bool = False) -> dict:
    """Download and stage NABSA circular attachments."""
    if run_date is None:
        run_date = _dt.date.today()

    return ingest_attachments(session, get_nabsa_config(), run_date, force=force)


def run_custom_ingest(
    session,
    job_name: str,
    sender_filter: str,
    subject_filter: str,
    file_patterns: list[str],
    run_date: _dt.date = None,
    force: bool = False,
) -> dict:
    """
    Generic ingestion runner: configure on the fly via parameters.

    Use this when you need a quick one-off ingestion or want to parametrize
    from a Snowflake stored procedure.

    Args:
        session: Snowpark session
        job_name: Job identifier (e.g., "CUSTOM_JOB_001")
        sender_filter: Expected sender email (empty string accepts any sender)
        subject_filter: Subject line substring to match
        file_patterns: File patterns to accept (e.g., [".csv", "report"])
        run_date: Date to process (default: today)
        force: If True, re-process even if already loaded

    Returns:
        dict with status, message, files_staged, messages_processed, run_id
    """
    if run_date is None:
        run_date = _dt.date.today()

    config = MailIngestConfig(
        job_name=job_name,
        mailbox=C.SHARED_MAILBOX,
        sender_filter=sender_filter,
        subject_filter=subject_filter,
        file_patterns=file_patterns,
        stage_path_template=C.STAGE_PATH_TEMPLATE,
    )
    return ingest_attachments(session, config, run_date, force=force)


# --- Direct usage in stored procedure handler (copy-paste template) --------

def main(session, run_date: _dt.date, job_name: str, force: bool = False) -> str:
    """
    Stored procedure handler template.

    Can be used as entry point for: CALL SP_MAIL_INGEST(?, ?, ?)

    Parameters:
        session: Snowpark session (provided by Snowflake)
        run_date: Date to process
        job_name: Which ingestion config to use (e.g., "OILS", "NABSA", "INVOICES")
        force: Reprocess flag

    Returns:
        Status string
    """
    # Map job names to their configs
    configs = {
        "OILS": get_oils_config(),
        "NABSA": get_nabsa_config(),
        "INVOICES": get_invoice_config(),
        "MANIFESTS": get_manifest_config(),
    }

    if job_name not in configs:
        return f"FAILED: Unknown job_name '{job_name}'. Available: {list(configs.keys())}"

    result = ingest_attachments(session, configs[job_name], run_date, force=force)
    return f"{result['status']} :: {result['message']}"

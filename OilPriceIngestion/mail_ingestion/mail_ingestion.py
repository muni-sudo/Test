"""Dynamic mail attachment ingestion to Snowflake stage.

Reusable library for downloading attachments from shared mailboxes via Microsoft Graph,
filtering by configurable patterns, and staging to Snowflake. Idempotent via message ID
tracking: every matching message in the lookback window is processed once.
"""
from __future__ import annotations

import base64
import datetime as _dt

import requests

try:
    # When running as stored procedure in Snowflake, the imported files are
    # flat on the stage, so absolute imports work.
    from io_ops import (
        log_file, already_processed, put_bytes, compute_file_hash,
        start_step, end_step, raise_alert
    )
    from logging_util import log, log_exc
except ImportError:
    # Local testing from the project root.
    from supporting_modules.io_ops import (
        log_file, already_processed, put_bytes, compute_file_hash,
        start_step, end_step, raise_alert
    )
    from supporting_modules.logging_util import log, log_exc


class MailIngestConfig:
    """Configuration for a mail ingestion job."""

    def __init__(
        self,
        job_name: str,
        mailbox: str,
        sender_filter: str,
        subject_filter: str,
        file_patterns: list[str],  # e.g., [".xlsx", ".csv", "invoice"]
        stage_path_template: str,  # e.g., "@STAGE/ingestion/{job_name}/{date}"
        lookback_hours: int = 36,
        timeout: int = 120,
        match_type: str = "substring",  # or "regex", "exact"
    ):
        """
        Args:
            job_name: Identifier for this ingestion job (e.g., "NABSA", "OILS")
            mailbox: Shared mailbox email address
            sender_filter: Expected sender address (case-insensitive substring match;
                           empty string matches any sender)
            subject_filter: Expected subject substring (case-insensitive)
            file_patterns: List of file patterns to accept (extensions or name substrings)
            stage_path_template: Template for Snowflake stage path; {job_name} and {date}
                                 are replaced at runtime
            lookback_hours: Hours to look back for new messages
            timeout: HTTP request timeout in seconds
            match_type: How to match filters ("substring", "regex", "exact")
        """
        self.job_name = job_name
        self.mailbox = mailbox
        self.sender_filter = sender_filter
        self.subject_filter = subject_filter
        self.file_patterns = file_patterns
        self.stage_path_template = stage_path_template
        self.lookback_hours = lookback_hours
        self.timeout = timeout
        self.match_type = match_type

    def get_stage_path(self, run_date: _dt.date) -> str:
        """Render the stage path template with runtime values."""
        return self.stage_path_template.format(job_name=self.job_name, date=run_date)


# --- Microsoft Graph helpers ------------------------------------------------
GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"


def _get_graph_token() -> str:
    """Obtain a Graph API token from credentials module."""
    from credentials import TENANT_ID, CLIENT_ID, CLIENT_SECRET

    tid = TENANT_ID
    cid = CLIENT_ID
    csec = CLIENT_SECRET

    if not all([tid, cid, csec]) or "YOUR_" in str(tid):
        raise ValueError(
            "Credentials not configured. Please update credentials.py with your Azure values:\n"
            "TENANT_ID, CLIENT_ID, CLIENT_SECRET\n"
            "Then upload credentials.py to @DYNAMIC_FILE_INGESTION/IngestDataFromMail/"
        )

    r = requests.post(
        f"https://login.microsoftonline.com/{tid}/oauth2/v2.0/token",
        data={
            "grant_type": "client_credentials",
            "client_id": cid,
            "client_secret": csec,
            "scope": "https://graph.microsoft.com/.default",
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def _get_graph_headers(token: str) -> dict:
    """Build Graph API request headers."""
    return {"Authorization": f"Bearer {token}"}


# --- Message filtering ------------------------------------------------------
def _matches_filter(value: str, pattern: str, match_type: str) -> bool:
    """Check if a value matches a filter pattern. An empty pattern matches anything."""
    if not pattern:
        return True
    if not value:
        return False
    value_lower = value.lower()
    pattern_lower = pattern.lower()

    if match_type == "substring":
        return pattern_lower in value_lower
    elif match_type == "exact":
        return value_lower == pattern_lower
    elif match_type == "regex":
        import re

        return bool(re.search(pattern_lower, value_lower, re.IGNORECASE))
    return False


def _find_messages(
    requests_session: requests.Session,
    headers: dict,
    config: MailIngestConfig,
    run_date: _dt.date,
) -> list[dict]:
    """Query Graph API for messages matching the filter criteria.

    Returns a list of message objects, newest first.
    """
    since = (_dt.datetime.combine(run_date, _dt.time()) -
             _dt.timedelta(hours=config.lookback_hours)).strftime("%Y-%m-%dT%H:%M:%SZ")

    url = (
        f"{GRAPH_API_BASE}/users/{config.mailbox}/messages"
        f"?$filter=receivedDateTime ge {since}"
        f"&$orderby=receivedDateTime desc"
        f"&$select=id,subject,from,internetMessageId,hasAttachments&$top=50"
    )

    r = requests_session.get(url, headers=headers, timeout=config.timeout)
    body = r.json()

    if "value" not in body:
        # Graph returned an error object
        raise RuntimeError(f"Graph API error: status={r.status_code} body={body}")

    msgs = body.get("value", [])
    candidates = [
        m
        for m in msgs
        if _matches_filter(
            m.get("from", {}).get("emailAddress", {}).get("address", ""),
            config.sender_filter,
            config.match_type,
        )
        and _matches_filter(
            m.get("subject", ""),
            config.subject_filter,
            config.match_type,
        )
        and m.get("hasAttachments")
    ]

    return candidates


def _filter_attachments(
    attachments: list[dict],
    file_patterns: list[str]
) -> list[dict]:
    """Filter attachments by name patterns.

    Args:
        attachments: List of attachment objects from Graph API
        file_patterns: Patterns to match (case-insensitive substrings; e.g., [".xlsx", "invoice"])

    Returns:
        List of attachment objects that match any pattern.
    """
    if not file_patterns:
        return attachments

    matched = []
    for att in attachments:
        name = att.get("name", "").lower()
        if any(pattern.lower() in name for pattern in file_patterns):
            matched.append(att)
    return matched


def _stage_message_attachments(
    session,
    requests_session: requests.Session,
    headers: dict,
    config: MailIngestConfig,
    msg: dict,
    run_date: _dt.date,
) -> int:
    """Download one message's matching attachments and upload them to the stage.

    Returns the number of files staged (0 if nothing matched the file patterns).
    """
    msg_id = msg["internetMessageId"]

    att_url = f"{GRAPH_API_BASE}/users/{config.mailbox}/messages/{msg['id']}/attachments"
    r = requests_session.get(att_url, headers=headers, timeout=config.timeout)
    r.raise_for_status()
    attachments = r.json().get("value", [])

    valid_attachments = _filter_attachments(attachments, config.file_patterns)
    if not valid_attachments:
        log(
            config.job_name,
            f"message {msg_id}: no attachments matched patterns {config.file_patterns} "
            f"({len(attachments)} attachments total)",
            level="WARN",
        )
        return 0

    stage_path = config.get_stage_path(run_date)
    files_staged = 0
    for att in valid_attachments:
        name = att.get("name", "")
        if "contentBytes" not in att:
            log(config.job_name, f"skipping {name} (no contentBytes)", level="WARN")
            continue

        content = base64.b64decode(att["contentBytes"])
        file_stage_path = f"{stage_path}/{name}"

        put_bytes(session, content, file_stage_path)
        files_staged += 1

        log(
            config.job_name,
            f"staged {name} ({len(content)} bytes) to {file_stage_path}",
        )

        # Log to audit trail
        file_hash = compute_file_hash(content)
        log_file(
            session,
            source=config.job_name,
            dataset="ATTACHMENT",
            run_date=run_date,
            rows=len(content),
            status="STAGED",
            message_id=msg_id,
            file_name=name,
            file_hash=file_hash,
            detail=f"stage_path={file_stage_path}",
        )
    return files_staged


# --- Main ingestion function ------------------------------------------------
def ingest_attachments(
    session,
    config: MailIngestConfig,
    run_date: _dt.date,
    force: bool = False,
) -> dict:
    """Download and stage mail attachments matching the config.

    This is the main entry point for a mail ingestion job. Every matching
    message in the lookback window that has not been processed yet is handled,
    so multiple emails arriving between runs are not lost.

    Args:
        session: Snowpark session
        config: MailIngestConfig instance defining filters and target stage
        run_date: Date to process
        force: If True, re-process even if messages were already loaded

    Returns:
        dict with keys:
            - status: "OK", "NO_DATA", "ALREADY_LOADED", "FAILED"
            - message: Human-readable status message
            - files_staged: Number of files uploaded
            - messages_processed: Number of messages whose attachments were staged
            - run_id: ETL run ID (for audit tracking)
    """
    rid = start_step(session, run_date, f"{config.job_name}_MAIL_FETCH")

    try:
        token = _get_graph_token()
        headers = _get_graph_headers(token)
        requests_session = requests.Session()

        # Find candidate messages (newest first)
        candidates = _find_messages(requests_session, headers, config, run_date)

        if not candidates:
            detail = (
                f"No messages found matching: sender='{config.sender_filter}' "
                f"subject='{config.subject_filter}' with_attachments=True"
            )
            end_step(session, rid, "NO_DATA", detail=detail)
            return {
                "status": "NO_DATA",
                "message": detail,
                "files_staged": 0,
                "messages_processed": 0,
                "run_id": rid,
            }

        files_staged = 0
        messages_processed = 0
        skipped = 0
        for msg in candidates:
            msg_id = msg["internetMessageId"]
            if not force and already_processed(session, msg_id):
                skipped += 1
                continue
            staged = _stage_message_attachments(
                session, requests_session, headers, config, msg, run_date
            )
            if staged:
                messages_processed += 1
                files_staged += staged

        if files_staged == 0:
            if skipped == len(candidates):
                detail = f"All {skipped} matching message(s) already processed"
                end_step(session, rid, "SKIPPED", detail=detail)
                return {
                    "status": "ALREADY_LOADED",
                    "message": detail,
                    "files_staged": 0,
                    "messages_processed": 0,
                    "run_id": rid,
                }
            detail = (
                f"No attachments matched patterns {config.file_patterns} "
                f"across {len(candidates) - skipped} new message(s)"
            )
            end_step(session, rid, "NO_DATA", detail=detail)
            return {
                "status": "NO_DATA",
                "message": detail,
                "files_staged": 0,
                "messages_processed": 0,
                "run_id": rid,
            }

        stage_path = config.get_stage_path(run_date)
        end_step(session, rid, "OK", rows_out=files_staged)
        return {
            "status": "OK",
            "message": (
                f"Staged {files_staged} file(s) from {messages_processed} message(s) "
                f"to {stage_path}"
            ),
            "files_staged": files_staged,
            "messages_processed": messages_processed,
            "run_id": rid,
        }

    except Exception as exc:
        detail = log_exc(f"{config.job_name}_MAIL_FETCH", exc)
        end_step(session, rid, "FAILED", detail=detail)
        raise_alert(
            session,
            run_date,
            "ERROR",
            f"{config.job_name}_MAIL_FETCH",
            f"{config.job_name} mail fetch failed: {detail}",
        )
        return {
            "status": "FAILED",
            "message": detail,
            "files_staged": 0,
            "messages_processed": 0,
            "run_id": rid,
        }

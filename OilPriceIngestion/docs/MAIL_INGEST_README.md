# Dynamic Mail Attachment Ingestion

A reusable, parametrizable library for downloading email attachments to Snowflake stages.

## Overview

**What it does:**
1. ✅ Connects to a shared mailbox via Microsoft Graph API
2. ✅ Finds emails matching configurable filters (sender, subject)
3. ✅ Downloads attachments matching file patterns
4. ✅ Stages files to Snowflake (`@DYNAMIC_FILE_INGESTION/{job_name}/{date}/`)
5. ✅ Tracks processed messages for idempotency
6. ✅ Logs everything to audit tables

**Key features:**
- **Parametrizable**: Define filter rules once, reuse for similar jobs
- **Idempotent**: Won't re-process the same message (tracked by `internetMessageId`)
- **Audited**: Full logging to `INGEST_FILE_LOG` and `ETL_RUN_LOG`
- **Error-resilient**: Continues on missing attachments, logs warnings
- **Extensible**: Add new mail sources by defining a new `MailIngestConfig`

---

## Quick Start

### 1. Define Your Config

```python
from mail_ingestion import MailIngestConfig, ingest_attachments

config = MailIngestConfig(
    job_name="MY_JOB",                          # Identifier (e.g., "NABSA", "INVOICES")
    mailbox="shared@company.com",               # Shared mailbox to monitor
    sender_filter="sender@external.com",        # Email from...
    subject_filter="Daily Report",              # Subject contains...
    file_patterns=[".xlsx", ".csv"],            # Accept these file types
    stage_path_template='@"DB"."SCHEMA"."STAGE"/{job_name}/{date}',
    lookback_hours=24,                          # Look back 24 hours for new emails
)
```

### 2. Run the Ingestion

```python
import datetime as dt
result = ingest_attachments(
    session=session,              # Snowpark session
    config=config,                # Your config
    run_date=dt.date.today(),     # Which date to process
    force=False,                  # True = reprocess even if already loaded
)

print(result)
# Returns:
# {
#   "status": "OK",               # or "NO_DATA", "ALREADY_LOADED", "FAILED"
#   "message": "Staged 2 files",
#   "files_staged": 2,
#   "run_id": "uuid-string"
# }
```

---

## Configuration Reference

### MailIngestConfig Parameters

| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `job_name` | str | Unique job identifier | `"NABSA"` |
| `mailbox` | str | Shared mailbox email | `"shared@mindsprint.com"` |
| `sender_filter` | str | Expected sender (substring match, case-insensitive) | `"finance@company.com"` |
| `subject_filter` | str | Subject line substring to match | `"Invoice"` |
| `file_patterns` | list[str] | File patterns to accept (substrings, case-insensitive) | `[".xlsx", "manifest"]` |
| `stage_path_template` | str | Snowflake stage path; use `{job_name}` and `{date}` placeholders | `@STAGE/{job_name}/{date}` |
| `lookback_hours` | int | Hours back to search for new emails | `24` (default: `36`) |
| `timeout` | int | HTTP request timeout (seconds) | `120` (default) |
| `match_type` | str | Filter match mode: `"substring"`, `"exact"`, `"regex"` | `"substring"` (default) |

---

## Usage Patterns

### Pattern 1: Predefined Config (Recommended)

Define configs in `mail_ingest_examples.py`, reuse across jobs:

```python
from mail_ingest_examples import run_nabsa_ingest

result = run_nabsa_ingest(session, force=False)
```

### Pattern 2: Dynamic Config

Configure on-the-fly for one-off jobs:

```python
from mail_ingest_examples import run_custom_ingest

result = run_custom_ingest(
    session,
    job_name="QUARTERLY_REPORT",
    sender_filter="reports@partner.com",
    subject_filter="Q3 Report",
    file_patterns=[".pdf", ".xlsx"],
)
```

### Pattern 3: Stored Procedure Handler

For scheduled runs from Snowflake:

```sql
-- Create stored procedure wrapper
CREATE OR REPLACE PROCEDURE sp_mail_ingest(
    RUN_DATE DATE,
    JOB_NAME VARCHAR,
    FORCE BOOLEAN DEFAULT FALSE
)
RETURNS VARCHAR
LANGUAGE PYTHON
RUNTIME_VERSION = 3.10
PACKAGES = ('snowflake-snowpark-python', 'requests')
HANDLER = 'mail_ingest_examples.main'
;

-- Call it
CALL sp_mail_ingest(CURRENT_DATE(), 'NABSA', FALSE);
```

---

## File Organization

```
project/
├── mail_ingestion.py          # Core reusable library
├── mail_ingest_examples.py    # Predefined configs + examples
├── MAIL_INGEST_README.md      # This file
├── nabsa_mail_fetch.py        # Legacy NABSA handler (can be retired)
└── io_ops.py, constants.py    # Existing utilities (used by mail_ingestion)
```

---

## Adding New Mail Sources

When you get a new requirement (e.g., "ingest invoice attachments from Finance"):

### 1. Add a New Config Function in `mail_ingest_examples.py`

```python
def get_invoices_config() -> MailIngestConfig:
    """Invoices - PDF/XLS from Finance team."""
    return MailIngestConfig(
        job_name="INVOICES",
        mailbox="shared@mindsprint.com",
        sender_filter="finance@company.com",
        subject_filter="Invoice",
        file_patterns=[".pdf", ".xls", ".xlsx"],
        stage_path_template='@"DB_DW_DEV"."RPT_TRADERS_BM_SANDBOX"."DYNAMIC_FILE_INGESTION"/{job_name}/{date}',
        lookback_hours=24,
    )
```

### 2. Add a Runner Function

```python
def run_invoices_ingest(session, run_date=None, force=False) -> dict:
    if run_date is None:
        run_date = _dt.date.today()
    return ingest_attachments(session, get_invoices_config(), run_date, force)
```

### 3. Update the `main()` Function to Include It

```python
configs = {
    "NABSA": get_nabsa_config(),
    "INVOICES": get_invoices_config(),  # ← Add new job
}
```

### 4. Done! Now you can use it:

```python
result = run_invoices_ingest(session)
```

---

## How It Works (Technical Details)

### Authentication
- Uses **Snowflake secrets** (`tid`, `cid`, `csec`) to get a Graph API token
- Same as existing NABSA implementation
- No new credentials needed

### Message Finding
1. Query Graph API for messages received in the last `lookback_hours`
2. Filter by sender (case-insensitive substring match)
3. Filter by subject (case-insensitive substring match)
4. Keep only messages with attachments
5. Return the newest matching message

### Attachment Download
1. Fetch attachment list from the message
2. Filter by file patterns (e.g., only `.xlsx` files)
3. Decode `contentBytes` from Base64
4. Upload to Snowflake stage via `lib.put_bytes()`

### Idempotency
- Checks `INGEST_FILE_LOG` for the message's `internetMessageId`
- If already processed → returns `ALREADY_LOADED`, skips download
- Can override with `force=True` to re-process

### Audit Trail
- Logs to `ETL_RUN_LOG` (step start/end, status, row count)
- Logs to `INGEST_FILE_LOG` (per-file metadata, stage path, hash)
- Raises alerts on failure
- Compatible with existing `lib.log()` calls

---

## Error Handling

| Scenario | Status | What Happens |
|----------|--------|--------------|
| No emails match filters | `NO_DATA` | Logged as `NO_DATA` step |
| Message already processed | `ALREADY_LOADED` | Skipped (unless `force=True`) |
| No attachments match patterns | `NO_DATA` | Logged with detail about found vs. matched |
| Graph API error | `FAILED` | Full error logged, alert sent |
| File upload error | `FAILED` | Exception caught, alert sent |

All failures raise an alert to ops via `lib.raise_alert()`.

---

## Monitoring & Troubleshooting

### Check Processing History

```sql
SELECT * FROM DB_DW_DEV.RPT_TRADERS_BM_SANDBOX.INGEST_FILE_LOG
WHERE SOURCE = 'INVOICES'
ORDER BY RUN_DATE DESC
LIMIT 10;
```

### Check ETL Run Status

```sql
SELECT * FROM DB_DW_DEV.RPT_TRADERS_BM_SANDBOX.ETL_RUN_LOG
WHERE STEP = 'INVOICES_MAIL_FETCH'
ORDER BY RUN_DATE DESC
LIMIT 10;
```

### Manual Re-process

```python
from mail_ingest_examples import run_invoices_ingest
import datetime as dt

# Force re-process today's mail
result = run_invoices_ingest(session, run_date=dt.date.today(), force=True)
print(result)
```

---

## Migration from Legacy NABSA

The old `nabsa_mail_fetch.py` can now be replaced with:

```python
from mail_ingest_examples import run_nabsa_ingest

result = run_nabsa_ingest(session, run_date=run_date, force=force)
```

Or kept as-is (it's a working implementation; no need to change if stable).

---

## Next Steps

1. **Review** `mail_ingestion.py` and `mail_ingest_examples.py`
2. **Define** your specific mail sources by adding configs to `mail_ingest_examples.py`
3. **Test** with a sample email in the shared mailbox
4. **Schedule** ingestions via Snowflake stored procedures (Task Scheduler)
5. **Monitor** via `INGEST_FILE_LOG` and `ETL_RUN_LOG`

---

## FAQs

**Q: How do I match files with a complex pattern?**
A: Use `match_type="regex"` and pass a regex pattern, e.g., `file_patterns=[r"(invoice|bill)_\d{4}\.xlsx"]`

**Q: Can I accept all file types?**
A: Yes, use `file_patterns=[""]` (empty string matches everything)

**Q: What if the mailbox doesn't exist?**
A: Graph API returns a 404; it's logged as a `FAILED` step with error details.

**Q: Can I process multiple messages at once?**
A: Currently takes the newest matching message. To process all: call `ingest_attachments()` multiple times with different date ranges, or modify the library to loop over `candidates` list.

**Q: How do I change the stage location?**
A: Update `stage_path_template` in the config, e.g., `@CUSTOM_STAGE/{job_name}/{date}`

---

## Support

- For errors: Check `ETL_RUN_LOG` + `INGEST_FILE_LOG` for details
- For new mail sources: Add a config to `mail_ingest_examples.py` (see "Adding New Mail Sources" above)
- For modifications: Edit `mail_ingestion.py` core functions; keep the public API (`MailIngestConfig`, `ingest_attachments`) stable

# Mail Ingestion Implementation Checklist

## ✅ What's Been Created

- [x] **`mail_ingestion.py`** - Core reusable library with:
  - `MailIngestConfig` class for parametrizable configurations
  - `ingest_attachments()` main entry point
  - Microsoft Graph API helpers
  - Filter logic (sender, subject, file patterns)
  - Stage upload + audit logging
  - Idempotency tracking via message ID

- [x] **`mail_ingest_examples.py`** - Example configs + usage patterns:
  - `get_nabsa_config()` - NABSA circular example
  - `get_invoice_config()` - Invoice example
  - `get_manifest_config()` - Shipping manifest example
  - `run_nabsa_ingest()` - Callable runner
  - `run_custom_ingest()` - Dynamic config runner
  - `main()` - Stored procedure handler template

- [x] **`MAIL_INGEST_README.md`** - Full documentation:
  - Quick start guide
  - Configuration reference
  - Usage patterns
  - How to add new mail sources
  - Troubleshooting + monitoring queries

---

## 🚀 Next Steps

### Phase 1: Review & Validate (30 mins)

- [ ] Read `MAIL_INGEST_README.md` for overview
- [ ] Scan `mail_ingestion.py` to understand the flow
- [ ] Review `mail_ingest_examples.py` example configs
- [ ] Identify which mail sources you need to configure (e.g., NABSA, INVOICES, MANIFESTS, etc.)

### Phase 2: Configure Your Mail Sources (15-30 mins per source)

For each mail ingestion requirement:

1. **Gather the details:**
   - [ ] Sender email address (exact or substring to match)
   - [ ] Subject line substring to match
   - [ ] File types/patterns to accept (e.g., `.xlsx`, `.pdf`, `invoice`, `manifest`)
   - [ ] How far back to look for emails (hours; default 24-36)
   - [ ] Target stage path (default: `@"DB_DW_DEV"."RPT_TRADERS_BM_SANDBOX"."DYNAMIC_FILE_INGESTION"/{job_name}/{date}`)

2. **Add to `mail_ingest_examples.py`:**
   ```python
   def get_MY_JOB_config() -> MailIngestConfig:
       """Description of what this ingest does."""
       return MailIngestConfig(
           job_name="MY_JOB",
           mailbox="tradersdataITsupport@mindsprint.com",
           sender_filter="sender@external.com",
           subject_filter="Subject Substring",
           file_patterns=[".xlsx", ".csv"],
           stage_path_template='@"DB_DW_DEV"."RPT_TRADERS_BM_SANDBOX"."DYNAMIC_FILE_INGESTION"/{job_name}/{date}',
           lookback_hours=24,
       )
   ```

3. **Add a runner function:**
   ```python
   def run_MY_JOB_ingest(session, run_date=None, force=False) -> dict:
       if run_date is None:
           run_date = _dt.date.today()
       return ingest_attachments(session, get_MY_JOB_config(), run_date, force)
   ```

4. **Update `main()` to include it:**
   ```python
   configs = {
       "NABSA": get_nabsa_config(),
       "MY_JOB": get_MY_JOB_config(),  # ← Add here
   }
   ```

### Phase 3: Test Locally (15-20 mins per source)

For each new mail source:

1. **Validate the config:**
   ```python
   from mail_ingest_examples import run_MY_JOB_ingest
   import datetime as dt
   
   result = run_MY_JOB_ingest(session, run_date=dt.date.today(), force=False)
   print(result)
   ```

2. **Check the result:**
   - `"status": "OK"` → Files staged successfully ✅
   - `"status": "NO_DATA"` → No emails matched (review filters)
   - `"status": "ALREADY_LOADED"` → Message already processed (use `force=True` to retry)
   - `"status": "FAILED"` → Check logs + error message

3. **Verify in Snowflake:**
   ```sql
   -- Check staged files
   LS @"DB_DW_DEV"."RPT_TRADERS_BM_SANDBOX"."DYNAMIC_FILE_INGESTION"/MY_JOB/;
   
   -- Check audit log
   SELECT * FROM DB_DW_DEV.RPT_TRADERS_BM_SANDBOX.INGEST_FILE_LOG
   WHERE SOURCE = 'MY_JOB'
   ORDER BY RUN_DATE DESC LIMIT 5;
   ```

### Phase 4: Create Snowflake Stored Procedure (10 mins)

Once tested locally, create a stored procedure for scheduled runs:

```sql
CREATE OR REPLACE PROCEDURE sp_mail_ingest(
    RUN_DATE DATE,
    JOB_NAME VARCHAR,
    FORCE BOOLEAN DEFAULT FALSE
)
RETURNS VARCHAR
LANGUAGE PYTHON
RUNTIME_VERSION = 3.10
PACKAGES = ('snowflake-snowpark-python', 'requests')
IMPORTS = ('@CODE/mail_ingestion.py', '@CODE/mail_ingest_examples.py')
HANDLER = 'mail_ingest_examples.main'
;
```

### Phase 5: Schedule Tasks (optional, 10 mins per schedule)

Set up scheduled runs in Snowflake Task Scheduler:

```sql
-- Example: Run NABSA daily at 6 AM
CREATE OR REPLACE TASK task_nabsa_daily
WAREHOUSE = TRADER_ANALYSIS_WH
SCHEDULE = 'USING CRON 0 6 * * * UTC'
AS
CALL sp_mail_ingest(CURRENT_DATE(), 'NABSA', FALSE);

ALTER TASK task_nabsa_daily RESUME;
```

---

## 📋 Configuration Template

Use this to gather requirements for each new mail source:

```
Job Name: ___________________
Sender Email: ___________________
Subject Match: ___________________
File Patterns: ___________________
Lookback Hours: ___ (default: 24-36)
Target Stage: ___________________

Notes:
_________________________________
_________________________________
```

---

## 🧪 Testing Checklist

For each mail source configuration:

- [ ] Emails with matching sender + subject exist in the mailbox
- [ ] At least one attachment matches the file patterns
- [ ] Ran `run_MY_JOB_ingest()` and got `status: "OK"`
- [ ] Files appear in the stage directory
- [ ] Audit log shows the file metadata
- [ ] Re-running returns `status: "ALREADY_LOADED"` (idempotency works)
- [ ] Running with `force=True` re-processes successfully

---

## 🐛 Troubleshooting Quick Guide

| Issue | Solution |
|-------|----------|
| `"status": "NO_DATA"` | Check sender/subject filters against actual emails |
| `"status": "FAILED"` | Check run_id in `ETL_RUN_LOG` for error details |
| Files not appearing in stage | Check stage path in config (test with a known file first) |
| Emails skipped (ALREADY_LOADED) | Use `force=True` or wait for new emails from that sender |
| Graph API errors (401, 403) | Check Snowflake secrets: `tid`, `cid`, `csec` are correct |
| Attachment filtering not working | Verify file patterns match actual filenames (case-insensitive) |

---

## 📊 Monitoring

After deploying, monitor via these queries:

```sql
-- Daily status of all ingest jobs
SELECT 
    SOURCE,
    RUN_DATE,
    COUNT(*) as files,
    SUM(ROWS) as bytes,
    MAX(CASE WHEN STATUS='LOADED' THEN LOADED_AT END) as last_load
FROM DB_DW_DEV.RPT_TRADERS_BM_SANDBOX.INGEST_FILE_LOG
WHERE RUN_DATE >= CURRENT_DATE() - 7
GROUP BY SOURCE, RUN_DATE
ORDER BY RUN_DATE DESC;

-- Recent failures
SELECT 
    STEP,
    RUN_DATE,
    STATUS,
    DETAIL
FROM DB_DW_DEV.RPT_TRADERS_BM_SANDBOX.ETL_RUN_LOG
WHERE STATUS != 'OK'
    AND RUN_DATE >= CURRENT_DATE() - 1
ORDER BY RUN_DATE DESC;
```

---

## 🎯 Success Criteria

You'll know it's working when:

1. ✅ Mail configs are defined in `mail_ingest_examples.py`
2. ✅ Test runs return `"status": "OK"` with files staged
3. ✅ Audit logs show file metadata + stage paths
4. ✅ Stored procedure runs on schedule without errors
5. ✅ Files appear in `@DYNAMIC_FILE_INGESTION/{job_name}/{date}/`
6. ✅ Idempotency works (re-runs are skipped by default)

---

## ⏭️ Step 2: Parse & Ingest (Later)

Once Step 1 is stable, Phase 2 will:
- Read files from stage
- Parse them (using your working prototype)
- Validate data
- MERGE into target tables

You already have a working parsing prototype, so Step 2 should be straightforward once files are in the stage.

---

## Questions?

Refer to:
- **Overview & patterns:** `MAIL_INGEST_README.md`
- **API reference:** `mail_ingestion.py` docstrings
- **Examples:** `mail_ingest_examples.py`
- **Troubleshooting:** `MAIL_INGEST_README.md` → Monitoring & Troubleshooting section


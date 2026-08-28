# Quick Start: Oils Mail Ingestion Testing

## ✅ Status

- [x] Python files uploaded to `@DYNAMIC_FILE_INGESTION` stage
  - mail_ingestion.py (10.7KB)
  - mail_ingest_examples.py (5.7KB)
  - test_oils_ingestion.py (6.4KB)

---

## 🚀 Next Steps

### Step 1: Create the Stored Procedures

Run this SQL in your Snowflake worksheet:

```sql
USE WAREHOUSE TRADER_ANALYSIS_WH;
USE DATABASE DB_DW_DEV;
USE SCHEMA RPT_TRADERS_BM_SANDBOX;

-- Create main ingestion procedure
CREATE OR REPLACE PROCEDURE sp_mail_ingest(
    RUN_DATE DATE,
    JOB_NAME VARCHAR,
    FORCE BOOLEAN DEFAULT FALSE
)
RETURNS VARCHAR
LANGUAGE PYTHON
RUNTIME_VERSION = '3.10'
PACKAGES = ('snowflake-snowpark-python', 'requests')
IMPORTS = (
    '@OILPRICEINGESTION/mail_ingestion/mail_ingestion.py',
    '@OILPRICEINGESTION/mail_ingestion/mail_ingest_examples.py',
    '@OILPRICEINGESTION/mail_ingestion/credentials.py',
    '@OILPRICEINGESTION/supporting_modules/io_ops.py',
    '@OILPRICEINGESTION/supporting_modules/logging_util.py',
    '@OILPRICEINGESTION/supporting_modules/constants.py'
)
HANDLER = 'mail_ingest_examples.main'
EXECUTE AS OWNER
AS $$
from mail_ingest_examples import main
$$;

-- Create test procedure
CREATE OR REPLACE PROCEDURE test_oils_ingest()
RETURNS VARCHAR
LANGUAGE PYTHON
RUNTIME_VERSION = '3.10'
PACKAGES = ('snowflake-snowpark-python', 'requests')
IMPORTS = (
    '@OILPRICEINGESTION/mail_ingestion/mail_ingestion.py',
    '@OILPRICEINGESTION/mail_ingestion/mail_ingest_examples.py',
    '@OILPRICEINGESTION/mail_ingestion/test_oils_ingestion.py',
    '@OILPRICEINGESTION/mail_ingestion/credentials.py',
    '@OILPRICEINGESTION/supporting_modules/io_ops.py',
    '@OILPRICEINGESTION/supporting_modules/logging_util.py',
    '@OILPRICEINGESTION/supporting_modules/constants.py'
)
HANDLER = 'test_oils_ingestion.test_oils_ingestion'
EXECUTE AS OWNER
AS $$
from test_oils_ingestion import test_oils_ingestion
import datetime as dt
test_oils_ingestion(_session, run_date=dt.date.today(), force=True)
return "Test completed - check output above"
$$;
```

### Step 2: Send a Test Email

Send an email to: **`tradersdataITsupport@mindsprint.com`**

With:
- **Subject:** Must contain "Edible & Non Edible Oils"
- **Attachment:** Any file (.xlsx, .csv, .pdf)
- **From:** Any sender (no restriction)

### Step 3: Run the Test

In Snowflake, call this:

```sql
CALL test_oils_ingest();
```

Wait for the output...

---

## 📊 Expected Results

### ✅ Success (Status: OK)

```
✅ SUCCESS: Staged 1 file(s)
```

**What happened:**
- Found your test email ✓
- Downloaded the attachment ✓
- Uploaded to stage ✓
- Logged everything ✓

### ⚠️ No Data (Status: NO_DATA)

```
⚠️  NO DATA: No emails matching the criteria found.
```

**What to do:**
1. Send the test email (see Step 2 above)
2. Wait 1-2 minutes
3. Run the test again

### ⚠️ Already Loaded (Status: ALREADY_LOADED)

```
⚠️  ALREADY_LOADED: This message was already processed.
```

This is normal on 2nd run. To re-test:
- Send a NEW test email, OR
- Use `CALL sp_mail_ingest(CURRENT_DATE(), 'OILS', TRUE);` (force=TRUE)

### ❌ Failed (Status: FAILED)

Check the error message. Common issues:
- Graph API credentials missing (check Snowflake secrets: tid, cid, csec)
- Stage doesn't exist
- Audit tables missing

---

## 🔍 Verify Results in Snowflake

After successful test, run these queries:

```sql
-- 1. Check staged files
LS @DYNAMIC_FILE_INGESTION/OILS/;

-- 2. Check file audit log
SELECT FILE_NAME, STATUS, LOADED_AT
FROM INGEST_FILE_LOG
WHERE SOURCE = 'OILS'
ORDER BY LOADED_AT DESC LIMIT 5;

-- 3. Check ETL run log
SELECT STEP, STATUS, ROWS_OUT, DETAIL
FROM ETL_RUN_LOG
WHERE STEP = 'OILS_MAIL_FETCH'
ORDER BY ENDED_AT DESC LIMIT 5;
```

---

## 🎯 Next: Use for Other Jobs

Once testing works, use the same procedure for other mail sources:

```sql
-- NABSA (already configured)
CALL sp_mail_ingest(CURRENT_DATE(), 'NABSA', FALSE);

-- INVOICES (example config)
CALL sp_mail_ingest(CURRENT_DATE(), 'INVOICES', FALSE);

-- MANIFESTS (example config)
CALL sp_mail_ingest(CURRENT_DATE(), 'MANIFESTS', FALSE);
```

---

## ⏭️ Phase 2: Parsing & Ingestion

Once Step 1 is stable, Phase 2 will:
1. Read files from `@DYNAMIC_FILE_INGESTION/OILS/{date}/`
2. Parse them (using your working prototype)
3. Validate
4. MERGE into target tables

---

## 📞 Troubleshooting

| Issue | Solution |
|-------|----------|
| Procedure won't create | Check Python file paths are correct (`@DYNAMIC_FILE_INGESTION/...`) |
| "NO_DATA" status | Send test email, wait 1-2 min, retry |
| "File not found" error | Verify files exist in stage: `LS @DYNAMIC_FILE_INGESTION/;` |
| Graph API error (401/403) | Check Snowflake secrets exist: `SELECT SYSTEM$GET_GENERIC_SECRET_STRING('tid');` |
| Attachment not downloaded | Check file matches pattern (accepts all in OILS config) |

---

## 📋 Copy-Paste Commands

### Create Both Procedures (One Command)

```sql
USE WAREHOUSE TRADER_ANALYSIS_WH; USE DATABASE DB_DW_DEV; USE SCHEMA RPT_TRADERS_BM_SANDBOX; CREATE OR REPLACE PROCEDURE sp_mail_ingest(RUN_DATE DATE, JOB_NAME VARCHAR, FORCE BOOLEAN DEFAULT FALSE) RETURNS VARCHAR LANGUAGE PYTHON RUNTIME_VERSION = '3.10' PACKAGES = ('snowflake-snowpark-python', 'requests') IMPORTS = ('@DYNAMIC_FILE_INGESTION/mail_ingestion.py', '@DYNAMIC_FILE_INGESTION/mail_ingest_examples.py') HANDLER = 'mail_ingest_examples.main' EXECUTE AS OWNER AS $$ from mail_ingest_examples import main $$; CREATE OR REPLACE PROCEDURE test_oils_ingest() RETURNS VARCHAR LANGUAGE PYTHON RUNTIME_VERSION = '3.10' PACKAGES = ('snowflake-snowpark-python', 'requests') IMPORTS = ('@DYNAMIC_FILE_INGESTION/mail_ingestion.py', '@DYNAMIC_FILE_INGESTION/mail_ingest_examples.py', '@DYNAMIC_FILE_INGESTION/test_oils_ingestion.py') HANDLER = 'test_oils_ingestion.test_oils_ingestion' EXECUTE AS OWNER AS $$ from test_oils_ingestion import test_oils_ingestion; import datetime as dt; test_oils_ingestion(_session, run_date=dt.date.today(), force=True); return "Test completed" $$;
```

### Test Command

```sql
CALL test_oils_ingest();
```

### Verify Results

```sql
SELECT * FROM INGEST_FILE_LOG WHERE SOURCE = 'OILS' ORDER BY LOADED_AT DESC LIMIT 5;
SELECT * FROM ETL_RUN_LOG WHERE STEP = 'OILS_MAIL_FETCH' ORDER BY ENDED_AT DESC LIMIT 5;
```

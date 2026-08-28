# Deployment Guide

Step-by-step instructions to deploy the Oil Price Ingestion solution to Snowflake.

## ✅ Pre-Deployment Checklist

- [ ] Azure tenant ID, client ID, client secret obtained
- [ ] Snowflake account access (with ACCOUNTADMIN or sufficient role)
- [ ] `DYNAMIC_FILE_INGESTION` stage created
- [ ] `MSGRAPH_EAI` external access integration exists
- [ ] Database: `DB_DW_DEV`, Schema: `RPT_TRADERS_BM_SANDBOX`
- [ ] Warehouse: `TRADER_ANALYSIS_WH`

---

## Phase 1: Prepare Credentials (5 min)

### Step 1: Edit Credentials File

Open `mail_ingestion/credentials.py`:

```python
TENANT_ID = "YOUR_AZURE_TENANT_ID"      # e.g., 12345678-1234-1234-1234-123456789abc
CLIENT_ID = "YOUR_CLIENT_ID"             # e.g., 98765432-1234-5678-9012-345678901234
CLIENT_SECRET = "YOUR_CLIENT_SECRET"     # e.g., abc.def~ghi-jkl.mno.pqr
```

Save locally (don't commit to git with real values).

---

## Phase 2: Upload Files to Snowflake (10 min)

### Step 1: Create Directory Structure in Stage

In Snowflake, navigate to:
**Databases** → `DB_DW_DEV` → `RPT_TRADERS_BM_SANDBOX` → **Stages** → `DYNAMIC_FILE_INGESTION`

Create folder: `IngestDataFromMail/`

### Step 2: Upload Mail Ingestion Files

Upload to: `@DYNAMIC_FILE_INGESTION/IngestDataFromMail/`

Files:
- `mail_ingestion/mail_ingestion.py`
- `mail_ingestion/mail_ingest_examples.py`
- `mail_ingestion/test_oils_ingestion.py`
- `mail_ingestion/credentials.py` ← **With your actual values**

### Step 3: Upload Supporting Modules

Upload to same location:
- `supporting_modules/io_ops.py`
- `supporting_modules/logging_util.py`
- `supporting_modules/constants.py`

### Step 4: Upload Streamlit App Files

Upload to: `@DYNAMIC_FILE_INGESTION/IngestDataFromMail/` OR your Streamlit stage

- `streamlit_app/streamlit_app.py`
- `streamlit_app/excel_parser.py`

**Verify:** Run this in Snowflake to list uploaded files:
```sql
LS @DYNAMIC_FILE_INGESTION/IngestDataFromMail/;
```

---

## Phase 3: Create Snowflake Objects (10 min)

### Step 1: Verify External Access Integration

```sql
SHOW EXTERNAL ACCESS INTEGRATIONS;
```

If `MSGRAPH_EAI` doesn't exist, create it (requires ACCOUNTADMIN):

```sql
CREATE NETWORK RULE msgraph_network_rule
  MODE = EGRESS
  TYPE = HOST_PORT
  VALUE_LIST = ('login.microsoftonline.com', 'graph.microsoft.com');

CREATE EXTERNAL ACCESS INTEGRATION MSGRAPH_EAI
  ALLOWED_NETWORK_RULES = (msgraph_network_rule)
  ENABLED = TRUE;

GRANT USAGE ON INTEGRATION MSGRAPH_EAI TO YOUR_ROLE;
```

### Step 2: Create Mail Ingestion Stored Procedure

```sql
USE WAREHOUSE TRADER_ANALYSIS_WH;
USE DATABASE DB_DW_DEV;
USE SCHEMA RPT_TRADERS_BM_SANDBOX;

CREATE OR REPLACE PROCEDURE sp_mail_ingest(
    RUN_DATE DATE,
    JOB_NAME VARCHAR,
    FORCE BOOLEAN DEFAULT FALSE
)
RETURNS VARCHAR
LANGUAGE PYTHON
RUNTIME_VERSION = '3.10'
PACKAGES = ('snowflake-snowpark-python', 'requests')
EXTERNAL_ACCESS_INTEGRATIONS = (MSGRAPH_EAI)
IMPORTS = (
    '@DYNAMIC_FILE_INGESTION/IngestDataFromMail/mail_ingestion.py',
    '@DYNAMIC_FILE_INGESTION/IngestDataFromMail/mail_ingest_examples.py',
    '@DYNAMIC_FILE_INGESTION/IngestDataFromMail/io_ops.py',
    '@DYNAMIC_FILE_INGESTION/IngestDataFromMail/logging_util.py',
    '@DYNAMIC_FILE_INGESTION/IngestDataFromMail/constants.py',
    '@DYNAMIC_FILE_INGESTION/IngestDataFromMail/credentials.py'
)
HANDLER = 'mail_ingest_examples.main'
EXECUTE AS OWNER
AS
$$
from mail_ingest_examples import main
$$;
```

### Step 3: Create Test Procedure

```sql
CREATE OR REPLACE PROCEDURE test_oils_ingest()
RETURNS VARCHAR
LANGUAGE PYTHON
RUNTIME_VERSION = '3.10'
PACKAGES = ('snowflake-snowpark-python', 'requests')
EXTERNAL_ACCESS_INTEGRATIONS = (MSGRAPH_EAI)
IMPORTS = (
    '@DYNAMIC_FILE_INGESTION/IngestDataFromMail/mail_ingestion.py',
    '@DYNAMIC_FILE_INGESTION/IngestDataFromMail/mail_ingest_examples.py',
    '@DYNAMIC_FILE_INGESTION/IngestDataFromMail/test_oils_ingestion.py',
    '@DYNAMIC_FILE_INGESTION/IngestDataFromMail/io_ops.py',
    '@DYNAMIC_FILE_INGESTION/IngestDataFromMail/logging_util.py',
    '@DYNAMIC_FILE_INGESTION/IngestDataFromMail/constants.py',
    '@DYNAMIC_FILE_INGESTION/IngestDataFromMail/credentials.py'
)
HANDLER = 'handler_test'
EXECUTE AS OWNER
AS
$$
from test_oils_ingestion import test_oils_ingestion
import datetime as dt

def handler_test(session):
    test_oils_ingestion(session, run_date=dt.date.today(), force=True)
    return "Test completed"
$$;
```

---

## Phase 4: Test Mail Ingestion (10 min)

### Step 1: Send Test Email

Send email to: `tradersdataITsupport@mindsprint.com`
- **Subject:** "Edible & Non Edible Oils"
- **Attachment:** Any `.xlsx` file

### Step 2: Run Test

```sql
CALL test_oils_ingest();
```

### Step 3: Verify Results

Check staged files:
```sql
LS @DYNAMIC_FILE_INGESTION/OILS/;
```

Check audit logs:
```sql
SELECT FILE_NAME, STATUS, LOADED_AT
FROM INGEST_FILE_LOG
WHERE SOURCE = 'OILS'
ORDER BY LOADED_AT DESC LIMIT 5;
```

Expected:
- ✅ File staged to `@DYNAMIC_FILE_INGESTION/OILS/2026-08-XX/`
- ✅ Entry in `INGEST_FILE_LOG` with status `STAGED`
- ✅ No errors in procedure output

---

## Phase 5: Deploy Streamlit App (5 min)

### Step 1: Upload Streamlit Files to Streamlit Stage

If using Streamlit-in-Snowflake, upload to your Streamlit code stage:
- `streamlit_app/streamlit_app.py`
- `streamlit_app/excel_parser.py`

### Step 2: Create/Update Streamlit App

In Snowflake, create a new Streamlit app or update existing:
- Title: "Oil Price Report Uploader"
- Code location: Path to `streamlit_app.py`
- Warehouse: `TRADER_ANALYSIS_WH`

### Step 3: Open App & Test

1. Open Streamlit app
2. Go to **Edible Oils** tab
3. Click **"Fetch latest from mail"**
4. Verify it shows your test file
5. Review the parsed summary
6. Click **"Insert into Snowflake"** to test load

Expected:
- ✅ File appears in preview
- ✅ Sheet summary shows parsed data
- ✅ Data loads to `PRICE_EDIBLE_*` tables
- ✅ Entry in `OIL_PRICE_UPLOAD_LOG`

---

## Phase 6: Schedule (Optional, 5 min)

Create a scheduled task to run mail ingestion daily:

```sql
CREATE OR REPLACE TASK task_oils_daily
WAREHOUSE = TRADER_ANALYSIS_WH
SCHEDULE = 'USING CRON 0 6 * * * UTC'
COMMENT = 'Daily Oils mail ingestion'
AS
CALL sp_mail_ingest(CURRENT_DATE(), 'OILS', FALSE);

ALTER TASK task_oils_daily RESUME;

-- Check status
SELECT * FROM TABLE(INFORMATION_SCHEMA.TASK_HISTORY(TASK_NAME => 'TASK_OILS_DAILY'))
ORDER BY SCHEDULED_TIME DESC LIMIT 10;
```

---

## ✅ Post-Deployment Validation

Run these queries to confirm everything is working:

```sql
-- 1. Verify procedures exist
SHOW PROCEDURES LIKE '%INGEST%';
SHOW PROCEDURES LIKE 'TEST_OILS%';

-- 2. Check staged files
LS @DYNAMIC_FILE_INGESTION/OILS/;

-- 3. Verify audit logs
SELECT * FROM INGEST_FILE_LOG WHERE SOURCE = 'OILS' LIMIT 5;
SELECT * FROM ETL_RUN_LOG WHERE STEP LIKE 'OILS%' LIMIT 5;

-- 4. Check price tables created
SHOW TABLES LIKE 'PRICE_EDIBLE%';

-- 5. Verify upload log
SELECT * FROM OIL_PRICE_UPLOAD_LOG LIMIT 5;
```

---

## 🔄 Daily Operations

### To Fetch & Load a New File

1. **Send email** to `tradersdataITsupport@mindsprint.com`
   - Subject: "Edible & Non Edible Oils"
   - Attach: price report `.xlsx`

2. **Open Streamlit app**
   - Go to **Edible Oils** tab
   - Click **"Fetch latest from mail"**
   - Review & confirm load

3. **Verify load**
   ```sql
   SELECT * FROM OIL_PRICE_UPLOAD_LOG ORDER BY UPLOAD_TIMESTAMP DESC LIMIT 1;
   ```

---

## 🚨 Troubleshooting

| Problem | Solution |
|---------|----------|
| Procedure fails with "Unknown function" | Check `credentials.py` has valid values |
| "Max retries exceeded" | Verify `MSGRAPH_EAI` integration exists and is ENABLED |
| "File not found in stage" | Send test email with subject "Edible & Non Edible Oils" |
| Streamlit won't load | Check files uploaded to correct stage path |
| Parser error | Verify Excel file format matches expected structure |

---

## 📞 Support

- **Mail issues:** See `docs/MAIL_INGEST_README.md`
- **Streamlit issues:** Check `docs/QUICK_START.md`
- **Testing:** Run `CALL test_oils_ingest();` and review output
- **Logs:** Query `INGEST_FILE_LOG`, `ETL_RUN_LOG`, `OIL_PRICE_UPLOAD_LOG`


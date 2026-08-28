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
    '@OILPRICEINGESTION/mail_ingestion/mail_ingestion.py',
    '@OILPRICEINGESTION/mail_ingestion/mail_ingest_examples.py',
    '@OILPRICEINGESTION/mail_ingestion/credentials.py',
    '@OILPRICEINGESTION/supporting_modules/io_ops.py',
    '@OILPRICEINGESTION/supporting_modules/logging_util.py',
    '@OILPRICEINGESTION/supporting_modules/constants.py'
)
HANDLER = 'mail_ingest_examples.main'
EXECUTE AS OWNER
AS
$$
from mail_ingest_examples import main
$$;
```

**The `IMPORTS` paths must match where the files actually sit on the stage.**
The paths above assume the project folders were uploaded as-is (the layout of
the delivered zip):

```
@OILPRICEINGESTION/
├── mail_ingestion/       mail_ingestion.py, mail_ingest_examples.py,
│                         credentials.py, test_oils_ingestion.py
├── supporting_modules/   io_ops.py, logging_util.py, constants.py
└── streamlit_app/        streamlit_app.py, excel_parser.py, environment.yml
```

Confirm with `LIST @OILPRICEINGESTION;` before creating the procedure — a
wrong path fails at CREATE time with "Remote file ... was not found".

Subfolders matter only for locating the file: Snowflake copies each import
into one flat directory on the Python path, so `supporting_modules/io_ops.py`
is imported in code as `import io_ops`, not `import supporting_modules.io_ops`.

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

Upload **all three** files to the same folder on your Streamlit code stage:
- `streamlit_app/streamlit_app.py` — the main file
- `streamlit_app/excel_parser.py` — imported by the app
- `streamlit_app/environment.yml` — **required**; pins the Streamlit version
  and pulls in `openpyxl`, which is not in the default environment

Omitting `environment.yml` is the most common deployment failure: the app
starts on Streamlit 1.22.0, where `st.file_uploader` is unsupported, and
`import openpyxl` fails.

The stage must be an internal stage with Snowflake server-side encryption:

```sql
CREATE STAGE IF NOT EXISTS DB_DW_DEV.RPT_TRADERS_BM_SANDBOX.OILPRICEINGESTION
  DIRECTORY = (ENABLE = TRUE)
  ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE');
```

### Step 2: Create/Update Streamlit App

```sql
CREATE OR REPLACE STREAMLIT DB_DW_DEV.RPT_TRADERS_BM_SANDBOX.OIL_PRICE_UPLOADER
ROOT_LOCATION = '@DB_DW_DEV.RPT_TRADERS_BM_SANDBOX.OILPRICEINGESTION/streamlit_app'
MAIN_FILE = '/streamlit_app.py'
QUERY_WAREHOUSE = 'TRADER_ANALYSIS_WH'
TITLE = 'Oil Price Report Uploader'
COMMENT = 'Oil Price Report Uploader - Upload or fetch from mail, parse, and load to Snowflake';
```

Note: `CREATE OR REPLACE` gives the app a new URL and drops existing grants.
If the app already exists and only the code changed, just re-upload the files
to the stage and refresh the app — no DDL needed.

The app runs with **owner's rights**. Grant the owning role `READ` on the
`DYNAMIC_FILE_INGESTION` stage (for "Read from mail"), plus `CREATE TABLE`,
`SELECT` and `INSERT` on `RPT_TRADERS_BM_SANDBOX`.

The **Fetch new mail now** button calls `SP_MAIL_INGEST` (created in Phase 3),
so that procedure must exist before the button works, and the app's role needs:

```sql
GRANT USAGE ON PROCEDURE DB_DW_DEV.RPT_TRADERS_BM_SANDBOX.SP_MAIL_INGEST(DATE, VARCHAR, BOOLEAN)
  TO ROLE <app_owner_role>;
```

The procedure keeps its own `EXTERNAL_ACCESS_INTEGRATIONS = (MSGRAPH_EAI)` and
runs `EXECUTE AS OWNER`, so the Streamlit app itself needs no external access.

### Step 3: Open App & Test

1. Open Streamlit app
2. Go to either tab — **Non-Edible Oils** or **Edible Oils**
3. Choose **"Read from mail"**, pick your test file, click **"Use this file"**
   (or choose **"Upload file"** and upload one manually)
4. Verify the sheet-level summary and preview look right
5. Tick the confirmation checkbox
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


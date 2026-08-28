# Testing the Oils Mail Ingestion

## Prerequisites

1. **Snowflake credentials** - Must be able to connect to Snowflake
2. **Test email** - Send a test email to `tradersdataITsupport@mindsprint.com` with:
   - Subject: Must contain "Edible & Non Edible Oils"
   - Attachment: Any file (.xlsx, .csv, .pdf, etc.)
   - From: Any sender (no sender filter)

3. **Python environment** - Same environment where you have access to Snowpark

---

## Option 1: Run in Jupyter Notebook (Recommended)

```python
# In a Jupyter notebook cell
from snowflake.snowpark import Session
from test_oils_ingestion import test_oils_ingestion
import datetime as dt

# Create Snowflake session (adjust connection params as needed)
connection_params = {
    "account": "YOUR_ACCOUNT",
    "user": "YOUR_USER",
    "password": "YOUR_PASSWORD",
    "warehouse": "TRADER_ANALYSIS_WH",
    "database": "DB_DW_DEV",
    "schema": "RPT_TRADERS_BM_SANDBOX"
}

session = Session.builder.configs(connection_params).create()

# Run the test
test_oils_ingestion(session, run_date=dt.date.today(), force=True)

session.close()
```

---

## Option 2: Run in VSCode Python Environment

Create a test file `run_test.py`:

```python
from snowflake.snowpark import Session
from test_oils_ingestion import test_oils_ingestion
import datetime as dt

# Connection params
connection_params = {
    "account": "YOUR_ACCOUNT",
    "user": "YOUR_USER",
    "password": "YOUR_PASSWORD",
    "warehouse": "TRADER_ANALYSIS_WH",
    "database": "DB_DW_DEV",
    "schema": "RPT_TRADERS_BM_SANDBOX"
}

session = Session.builder.configs(connection_params).create()
test_oils_ingestion(session, force=True)
session.close()
```

Then run:
```bash
python run_test.py
```

---

## Option 3: Run in Snowflake via Stored Procedure

Create the stored procedure:

```sql
CREATE OR REPLACE PROCEDURE test_oils_ingest()
RETURNS VARCHAR
LANGUAGE PYTHON
RUNTIME_VERSION = 3.10
PACKAGES = ('snowflake-snowpark-python', 'requests')
IMPORTS = ('@CODE/mail_ingestion.py', '@CODE/mail_ingest_examples.py', '@CODE/test_oils_ingestion.py')
AS
$$
from test_oils_ingestion import test_oils_ingestion
import datetime as dt

test_oils_ingestion(_session, run_date=dt.date.today(), force=True)
return "Test completed - check output above"
$$;
```

Then call it:
```sql
CALL test_oils_ingest();
```

---

## Expected Output

The test script will:

1. **[STEP 1]** Show your configuration (job name, mailbox, filters, etc.)
2. **[STEP 2]** Connect to Graph API and search for matching emails
3. **[STEP 3]** Show the result:
   - Status: `OK`, `NO_DATA`, `ALREADY_LOADED`, or `FAILED`
   - Files staged count
   - Run ID for audit trail
4. **[STEP 4]** List the files that were uploaded to the stage
5. **[STEP 5]** Show audit log entries from `INGEST_FILE_LOG`
6. **[STEP 6]** Show ETL run details from `ETL_RUN_LOG`
7. **Summary** - Overall success/failure with tips

---

## Interpreting Results

### ✅ Success (`status: "OK"`)

```
✅ SUCCESS: Staged 1 file(s)
```

This means:
- Found the email ✅
- Downloaded the attachment ✅
- Uploaded to Snowflake stage ✅
- Logged everything ✅

**Next step:** Check the files are in the stage directory.

---

### ⚠️ No Data (`status: "NO_DATA"`)

```
⚠️  NO DATA: No emails matching the criteria found.
   Tip: Verify a test email exists in the mailbox with:
   - Subject containing: 'Edible & Non Edible Oils'
   - At least one attachment
```

**What to do:**
1. Send a test email to `tradersdataITsupport@mindsprint.com`
2. Subject: Must contain "Edible & Non Edible Oils"
3. Add an attachment (any file type)
4. Run the test again

---

### ⚠️ Already Loaded (`status: "ALREADY_LOADED"`)

```
⚠️  ALREADY_LOADED: This message was already processed.
   Tip: Use force=True to reprocess, or send a new test email
```

This is normal on the 2nd run with the same email. The script prevents duplicate processing.

**To reprocess:** Use `force=True` in the test call.

---

### ❌ Failed (`status: "FAILED"`)

```
❌ FAILED: [error message]
```

**Check these things:**

1. **Graph API credentials** - Verify Snowflake secrets exist:
   ```sql
   SELECT SYSTEM$GET_GENERIC_SECRET_STRING('tid');
   -- Should return a non-empty string
   ```

2. **Mailbox access** - Verify the mailbox exists and you have access

3. **Snowflake stage** - Verify the target stage exists:
   ```sql
   LS @"DB_DW_DEV"."RPT_TRADERS_BM_SANDBOX"."DYNAMIC_FILE_INGESTION"/;
   ```

4. **Audit tables** - Verify the audit tables exist:
   ```sql
   SHOW TABLES IN DB_DW_DEV.RPT_TRADERS_BM_SANDBOX LIKE 'INGEST_FILE_LOG';
   SHOW TABLES IN DB_DW_DEV.RPT_TRADERS_BM_SANDBOX LIKE 'ETL_RUN_LOG';
   ```

---

## Verification Queries

After a successful test run, you can verify in Snowflake:

```sql
-- Check staged files
LS @"DB_DW_DEV"."RPT_TRADERS_BM_SANDBOX"."DYNAMIC_FILE_INGESTION"/OILS/2026-08-26/;

-- Check audit log
SELECT *
FROM DB_DW_DEV.RPT_TRADERS_BM_SANDBOX.INGEST_FILE_LOG
WHERE SOURCE = 'OILS'
ORDER BY RUN_DATE DESC, LOADED_AT DESC
LIMIT 10;

-- Check ETL run log
SELECT *
FROM DB_DW_DEV.RPT_TRADERS_BM_SANDBOX.ETL_RUN_LOG
WHERE STEP = 'OILS_MAIL_FETCH'
ORDER BY RUN_DATE DESC
LIMIT 10;
```

---

## Debugging Tips

If the test fails:

1. **Check the run_id** from the output
2. **Query the run log** for details:
   ```sql
   SELECT DETAIL FROM DB_DW_DEV.RPT_TRADERS_BM_SANDBOX.ETL_RUN_LOG
   WHERE RUN_ID = 'YOUR_RUN_ID_HERE';
   ```

3. **Check for alerts:**
   ```sql
   SELECT * FROM DB_DW_DEV.RPT_TRADERS_BM_SANDBOX.ALERT_LOG
   WHERE RUN_DATE >= CURRENT_DATE() - 1
   ORDER BY CREATED_AT DESC;
   ```

4. **Look for warnings in logs:**
   ```python
   # The test will print any warnings or errors to console
   # Review the full output above the summary
   ```

---

## Next Steps After Successful Test

1. ✅ Verify files are in the stage
2. ✅ Check audit/ETL logs show correct entries
3. ✅ Run test 2-3 times to confirm idempotency (same message returns ALREADY_LOADED)
4. ✅ Then proceed to Phase 2: Parsing & Ingestion

---

## Questions?

- **Config not matching?** Review the config in `mail_ingest_examples.py`
- **Can't connect to Snowflake?** Check your credentials and warehouse access
- **Files not staging?** Verify the stage path exists and is writable
- **Unexpected results?** Check the ETL_RUN_LOG DETAIL column for full error messages

# Oil Price Ingestion - End-to-End Solution

Complete solution for fetching Oil Price reports from email and ingesting them into Snowflake via Streamlit.

## 📁 Folder Structure

```
OilPriceIngestion/
├── mail_ingestion/              # Email & Stage Management
│   ├── mail_ingestion.py        # Core mail fetching library
│   ├── mail_ingest_examples.py  # Configuration templates (OILS, NABSA, etc.)
│   ├── test_oils_ingestion.py   # End-to-end test script
│   └── credentials.py           # Azure Graph API credentials (EDIT WITH YOUR VALUES)
│
├── streamlit_app/               # User Interface
│   ├── streamlit_app.py         # Main Streamlit app (upload + fetch from mail)
│   └── excel_parser.py          # Excel parsing & data transformation
│
├── supporting_modules/          # Snowflake Integration
│   ├── io_ops.py               # I/O helpers (audit logging, MERGE operations)
│   ├── logging_util.py         # Structured logging
│   └── constants.py            # Shared configuration
│
└── docs/                        # Documentation
    ├── MAIL_INGEST_README.md   # Mail ingestion detailed guide
    ├── QUICK_START.md          # Getting started (5 min setup)
    ├── TEST_GUIDE.md           # Testing mail integration
    └── IMPLEMENTATION_CHECKLIST.md
```

## 🚀 Quick Start (5 minutes)

### 1. Configure Credentials
Edit `mail_ingestion/credentials.py`:
```python
TENANT_ID = "your-azure-tenant-id"
CLIENT_ID = "your-client-id"
CLIENT_SECRET = "your-client-secret"
```

### 2. Upload Files to Snowflake
All files go to: `@DYNAMIC_FILE_INGESTION/IngestDataFromMail/`

```
mail_ingestion/
├── mail_ingestion.py
├── mail_ingest_examples.py
├── test_oils_ingestion.py
└── credentials.py

streamlit_app/
├── streamlit_app.py
└── excel_parser.py

supporting_modules/
├── io_ops.py
├── logging_util.py
└── constants.py
```

### 3. Create Stored Procedure
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

CALL test_oils_ingest();
```

### 4. Deploy Streamlit App
Upload to Snowflake Streamlit stage:
- `streamlit_app/streamlit_app.py`
- `streamlit_app/excel_parser.py`

---

## 📊 How It Works

### Phase 1: Mail Ingestion
1. Scheduled job calls mail ingestion procedure
2. Fetches emails from shared mailbox (subject: "Edible & Non Edible Oils")
3. Downloads `.xlsx` attachments
4. Stages files to `@DYNAMIC_FILE_INGESTION/OILS/{date}/`
5. Logs metadata to `INGEST_FILE_LOG`

### Phase 2: Streamlit Workflow
1. User opens either tab — "Non-Edible Oils" or "Edible Oils"
2. Two input options on **both** tabs:
   - **Upload file** → Manual upload
   - **Read from mail** → Pick from the files staged by mail ingestion
     (newest first, with date and size shown). **Fetch new mail now** runs
     the ingestion job on demand — no need to wait for the scheduled task —
     and refreshes the list.
3. Parse workbook with `excel_parser.py`
4. Review sheet summary & data preview
5. Confirm & load to `PRICE_NONEDIBLE_*` / `PRICE_EDIBLE_*` tables
6. Log to `OIL_PRICE_UPLOAD_LOG` (including whether the file came from
   UPLOAD or MAIL)

---

## 🔐 Prerequisites

- **Snowflake**: Account, warehouse, database, schema
- **Azure AD**: Tenant ID, Client ID, Client Secret (for Graph API)
- **Snowflake Integrations**: 
  - `MSGRAPH_EAI` (External Access Integration for HTTPS outbound)
  - `DYNAMIC_FILE_INGESTION` stage exists

---

## 📝 Configuration

### Snowflake Objects Required
```sql
-- Database & Schema (should exist)
USE DATABASE DB_DW_DEV;
USE SCHEMA RPT_TRADERS_BM_SANDBOX;

-- External Access Integration (if not exists)
CREATE NETWORK RULE msgraph_network_rule
  MODE = EGRESS
  TYPE = HOST_PORT
  VALUE_LIST = ('login.microsoftonline.com', 'graph.microsoft.com');

CREATE EXTERNAL ACCESS INTEGRATION MSGRAPH_EAI
  ALLOWED_NETWORK_RULES = (msgraph_network_rule)
  ENABLED = TRUE;

-- Stage (should exist)
CREATE STAGE DYNAMIC_FILE_INGESTION
  COMMENT = 'Mail ingestion & processing stage';

-- Upload log table (auto-created by Streamlit app)
-- Price tables auto-created as data arrives
```

### Azure Setup
1. Go to Azure Portal → Azure AD → App registrations
2. Create app (or use existing)
3. Copy:
   - **Directory (tenant) ID** → `TENANT_ID`
   - **Client ID** → `CLIENT_ID`
   - Go to "Certificates & secrets" → New secret → Copy value → `CLIENT_SECRET`
4. Grant permissions to Microsoft Graph (Mail.Read, User.Read.All)

---

## 🧪 Testing

### Test Mail Ingestion
```sql
CALL test_oils_ingest();
```

Expected results:
- Files staged to `@DYNAMIC_FILE_INGESTION/OILS/2026-08-XX/`
- Entries in `INGEST_FILE_LOG` with status `STAGED`
- Entries in `ETL_RUN_LOG` with step `OILS_MAIL_FETCH`

### Test Streamlit App
1. Open Streamlit app → either tab (Non-Edible or Edible Oils)
2. Choose "Read from mail", pick a staged file, click "Use this file"
3. Should show parsed summary
4. Confirm & load to Snowflake

---

## 📚 Documentation

| Document | Purpose |
|----------|---------|
| `MAIL_INGEST_README.md` | Detailed mail ingestion reference |
| `QUICK_START.md` | 5-minute setup guide |
| `TEST_GUIDE.md` | Testing procedures |
| `IMPLEMENTATION_CHECKLIST.md` | Full implementation roadmap |

---

## 🔄 Typical Workflow

### Day 1: Setup
- [ ] Configure `credentials.py` with Azure values
- [ ] Upload all files to Snowflake stage
- [ ] Create stored procedures
- [ ] Test with `CALL test_oils_ingest();`
- [ ] Deploy Streamlit app

### Day 2+: Operations
- [ ] Send email with subject "Edible & Non Edible Oils" + xlsx attachment
- [ ] Mail ingestion runs (scheduled) or manual trigger
- [ ] Open Streamlit app → the relevant tab (Non-Edible or Edible)
- [ ] Choose "Read from mail" and pick the staged file (or upload manually)
- [ ] Review & confirm load
- [ ] Data in `PRICE_NONEDIBLE_*` / `PRICE_EDIBLE_*` tables

---

## ⚠️ Important Notes

1. **Credentials**: Never commit `credentials.py` with real values to version control
2. **External Access**: Required for Graph API outbound access (HTTPS to login.microsoftonline.com)
3. **Idempotency**: Re-running mail ingestion with same email skips duplicate processing
4. **Merge Behavior**: Re-loading a file overwrites matching dates (not duplicates)
5. **File Format**: Expected `.xlsx` with price sheets (FATY, LAURICS, etc.)

---

## 🛠️ Troubleshooting

| Issue | Solution |
|-------|----------|
| "Unknown function SYSTEM$GET_GENERIC_SECRET_STRING" | Credentials not found; edit `credentials.py` |
| "Max retries exceeded with url login.microsoftonline.com" | Missing `EXTERNAL_ACCESS_INTEGRATIONS = (MSGRAPH_EAI)` |
| "File not found in stage" | Mail ingestion hasn't run; send test email & trigger |
| "Parse error" | Check Excel format matches expected structure |

---

## 📞 Support

Refer to:
- `docs/MAIL_INGEST_README.md` — Mail fetching details
- `docs/QUICK_START.md` — Setup steps
- `docs/TEST_GUIDE.md` — Testing procedures
- Snowflake logs: `INGEST_FILE_LOG`, `ETL_RUN_LOG`, `OIL_PRICE_UPLOAD_LOG`


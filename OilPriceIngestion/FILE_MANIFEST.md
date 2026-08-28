# File Manifest & Deployment Checklist

Complete list of all files and where they go in Snowflake.

---

## 📋 Files by Component

### 1️⃣ Mail Ingestion Component

**Location in OilPriceIngestion:** `mail_ingestion/`

| File | Purpose | Snowflake Stage Path |
|------|---------|----------------------|
| `mail_ingestion.py` | Core library for Graph API integration & file staging | `@DYNAMIC_FILE_INGESTION/IngestDataFromMail/` |
| `mail_ingest_examples.py` | Configuration templates (OILS, NABSA, INVOICES, etc.) | `@DYNAMIC_FILE_INGESTION/IngestDataFromMail/` |
| `test_oils_ingestion.py` | End-to-end test script | `@DYNAMIC_FILE_INGESTION/IngestDataFromMail/` |
| `credentials.py` | **Azure Graph API credentials (EDIT WITH YOUR VALUES)** | `@DYNAMIC_FILE_INGESTION/IngestDataFromMail/` |

**Key Note:** `credentials.py` must be edited with your actual Azure credentials before uploading.

---

### 2️⃣ Streamlit Application

**Location in OilPriceIngestion:** `streamlit_app/`

| File | Purpose | Snowflake Stage Path |
|------|---------|----------------------|
| `streamlit_app.py` | Main UI (Upload + Fetch from Mail + Parse + Load) | Streamlit code stage |
| `excel_parser.py` | Excel parsing & data transformation logic | Streamlit code stage |

**Key Note:** If Streamlit-in-Snowflake is enabled, upload to your designated Streamlit stage.

---

### 3️⃣ Supporting Modules

**Location in OilPriceIngestion:** `supporting_modules/`

| File | Purpose | Snowflake Stage Path |
|------|---------|----------------------|
| `io_ops.py` | Snowflake I/O helpers (audit logging, MERGE, snapshots) | `@DYNAMIC_FILE_INGESTION/IngestDataFromMail/` |
| `logging_util.py` | Structured logging for stored procedures | `@DYNAMIC_FILE_INGESTION/IngestDataFromMail/` |
| `constants.py` | Shared configuration (DB, schema, tables, etc.) | `@DYNAMIC_FILE_INGESTION/IngestDataFromMail/` |

---

### 4️⃣ Documentation

**Location in OilPriceIngestion:** `docs/`

| File | Use Case |
|------|----------|
| `MAIL_INGEST_README.md` | Detailed mail ingestion reference & API docs |
| `QUICK_START.md` | 5-minute getting-started guide |
| `TEST_GUIDE.md` | How to test mail integration |
| `IMPLEMENTATION_CHECKLIST.md` | Full implementation roadmap |

---

### 5️⃣ Setup & Configuration Files (Root)

| File | Purpose |
|------|---------|
| `README.md` | Overview, folder structure, quick start |
| `DEPLOYMENT_GUIDE.md` | Step-by-step deployment instructions |
| `FILE_MANIFEST.md` | This file — file locations & purposes |

---

## 🎯 Deployment Checklist

### Pre-Deployment (Before uploading to Snowflake)

- [ ] **Edit credentials** — Open `mail_ingestion/credentials.py` and add your Azure values
- [ ] **Verify file count** — All 13 files present:
  ```
  mail_ingestion/: 4 files
  streamlit_app/: 2 files
  supporting_modules/: 3 files
  docs/: 4 files
  Root: 3 files
  Total: 16 files
  ```

### Snowflake Preparation (Before upload)

- [ ] Database `DB_DW_DEV` exists
- [ ] Schema `RPT_TRADERS_BM_SANDBOX` exists
- [ ] Warehouse `TRADER_ANALYSIS_WH` exists
- [ ] Stage `@DYNAMIC_FILE_INGESTION` exists
- [ ] Integration `MSGRAPH_EAI` exists (or create it)

### Upload Phase

- [ ] Create folder: `@DYNAMIC_FILE_INGESTION/IngestDataFromMail/`
- [ ] Upload **7 files** to `@DYNAMIC_FILE_INGESTION/IngestDataFromMail/`:
  - [ ] `mail_ingestion.py`
  - [ ] `mail_ingest_examples.py`
  - [ ] `test_oils_ingestion.py`
  - [ ] `credentials.py` ← **With your actual values**
  - [ ] `io_ops.py`
  - [ ] `logging_util.py`
  - [ ] `constants.py`
- [ ] Upload **2 files** to Streamlit stage (if using Streamlit-in-Snowflake):
  - [ ] `streamlit_app.py`
  - [ ] `excel_parser.py`

### Procedure Creation

- [ ] Create `sp_mail_ingest()` stored procedure
- [ ] Create `test_oils_ingest()` test procedure
- [ ] Verify procedures exist: `SHOW PROCEDURES LIKE '%INGEST%';`

### Testing

- [ ] Send test email (subject: "Edible & Non Edible Oils", with `.xlsx` attachment)
- [ ] Run: `CALL test_oils_ingest();`
- [ ] Verify files staged: `LS @DYNAMIC_FILE_INGESTION/OILS/;`
- [ ] Verify logs: Query `INGEST_FILE_LOG` for `OILS` entries
- [ ] Test Streamlit: Fetch from mail and confirm load

### Operations

- [ ] Set up scheduled task (optional): `CREATE TASK task_oils_daily ...`
- [ ] Document any site-specific configurations
- [ ] Train users on using the Streamlit app

---

## 📦 Package Contents Summary

```
OilPriceIngestion/
│
├── README.md (1.5 KB)
├── DEPLOYMENT_GUIDE.md (5 KB)
├── FILE_MANIFEST.md (THIS FILE)
│
├── mail_ingestion/ (4 files, ~35 KB)
│   ├── mail_ingestion.py           # Core library
│   ├── mail_ingest_examples.py     # Configs
│   ├── test_oils_ingestion.py      # Tests
│   └── credentials.py              # Azure credentials (EDIT ME!)
│
├── streamlit_app/ (2 files, ~20 KB)
│   ├── streamlit_app.py            # Main UI
│   └── excel_parser.py             # Excel parsing
│
├── supporting_modules/ (3 files, ~30 KB)
│   ├── io_ops.py                   # Snowflake I/O
│   ├── logging_util.py             # Logging
│   └── constants.py                # Configuration
│
└── docs/ (4 files, ~30 KB)
    ├── MAIL_INGEST_README.md       # Detailed guide
    ├── QUICK_START.md              # 5-min setup
    ├── TEST_GUIDE.md               # Testing
    └── IMPLEMENTATION_CHECKLIST.md # Roadmap

Total: ~120 KB (all text, easily compressible)
```

---

## 🔑 Critical Files to Edit

**Before deployment, you MUST edit:**

1. **`mail_ingestion/credentials.py`** — Add your Azure credentials:
   ```python
   TENANT_ID = "your-tenant-id"
   CLIENT_ID = "your-client-id"
   CLIENT_SECRET = "your-secret"
   ```

---

## 📍 Where Each File Goes in Snowflake

### Mail Ingestion & Supporting Files (Same Location)

**Upload to:** `@DB_DW_DEV.RPT_TRADERS_BM_SANDBOX.DYNAMIC_FILE_INGESTION/IngestDataFromMail/`

```
IngestDataFromMail/
├── mail_ingestion.py
├── mail_ingest_examples.py
├── test_oils_ingestion.py
├── credentials.py
├── io_ops.py
├── logging_util.py
└── constants.py
```

### Streamlit App Files

**Upload to:** Your designated Streamlit code stage (project-specific)

```
streamlit_code/
├── streamlit_app.py
└── excel_parser.py
```

---

## 🔍 Verification Queries

After upload, verify files are in place:

```sql
-- Verify mail ingestion files
LS @DYNAMIC_FILE_INGESTION/IngestDataFromMail/;

-- Should list 7 files:
-- - mail_ingestion.py
-- - mail_ingest_examples.py
-- - test_oils_ingestion.py
-- - credentials.py
-- - io_ops.py
-- - logging_util.py
-- - constants.py
```

---

## 🚀 Next Steps

1. **Read** `README.md` — Overview
2. **Follow** `DEPLOYMENT_GUIDE.md` — Step-by-step deployment
3. **Test** Using `docs/TEST_GUIDE.md` — Validate setup
4. **Reference** `docs/MAIL_INGEST_README.md` — For detailed info

---

## 📞 Quick Reference

| Need | File |
|------|------|
| Overview | `README.md` |
| Deploy instructions | `DEPLOYMENT_GUIDE.md` |
| File locations | `FILE_MANIFEST.md` (this file) |
| Technical details | `docs/MAIL_INGEST_README.md` |
| Quick setup (5 min) | `docs/QUICK_START.md` |
| Testing | `docs/TEST_GUIDE.md` |
| Full roadmap | `docs/IMPLEMENTATION_CHECKLIST.md` |


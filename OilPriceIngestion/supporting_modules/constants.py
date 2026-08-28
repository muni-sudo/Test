"""Central constants for the oil-price ingestion pipeline.

Single source of truth for Snowflake object names and the mail-ingestion
defaults. Changing an object name here means changing it in the SQL scripts
(and in streamlit_app.py, which cannot import this module when deployed to
its own stage) too.
"""
from __future__ import annotations

# --- Snowflake objects ------------------------------------------------------
DATABASE = "DB_DW_DEV"
SCHEMA = "RPT_TRADERS_BM_SANDBOX"
FQ = f"{DATABASE}.{SCHEMA}"
WAREHOUSE = "TRADER_ANALYSIS_WH"

# Stage the mail-ingestion job writes attachments to; the Streamlit app reads
# the OILS/ subfolder of the same stage.
MAIL_STAGE_NAME = "DYNAMIC_FILE_INGESTION"
STAGE_PATH_TEMPLATE = (
    f'@"{DATABASE}"."{SCHEMA}"."{MAIL_STAGE_NAME}"' + "/{job_name}/{date}"
)

# --- Mail ingestion defaults ------------------------------------------------
SHARED_MAILBOX = "tradersdataITsupport@mindsprint.com"

# Edible & Non Edible Oils job
OILS_JOB_NAME = "OILS"
OILS_SUBJECT_MATCH = "Edible & Non Edible Oils"  # substring match (robust to prefixes)

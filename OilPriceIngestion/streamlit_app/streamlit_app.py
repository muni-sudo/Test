"""
Oil Price Report Uploader (Streamlit in Snowflake)

One app, two categories (Non-Edible / Edible oils), two input modes each:

  1. Upload file    -- the user picks the monthly price-report .xlsx manually.
  2. Read from mail -- the user picks a file that the mail-ingestion job has
                       already staged from the shared mailbox
                       ("Edible & Non Edible Oils" emails) to
                       @DYNAMIC_FILE_INGESTION/OILS/{date}/.

Whichever the source, the flow is identical: parse the workbook, show a
sheet-level summary plus an Excel-shaped preview, and write to Snowflake only
after the user explicitly confirms.

Data model: one wide table per product sheet per category
(PRICE_NONEDIBLE_FATY, PRICE_NONEDIBLE_LAURICS, ..., and PRICE_EDIBLE_SOYMEAL,
PRICE_EDIBLE_CASTOR, ...), shaped like the source Excel tab -- one row per
PRICE_DATE and, per price series, a <SERIES>_LOW / <SERIES>_HIGH FLOAT pair.
Both hold the same number for a single quote and the two ends for a range
quote ("6600-6800"), so the mid is always (LOW + HIGH) / 2. A futures MONTH
column is carried as a single VARCHAR instead.

Re-uploading a file overwrites matching dates (MERGE) rather than duplicating
them. A new price series is a new column, added automatically the first time
it's seen.
"""
import datetime
import io
import re

import pandas as pd
import streamlit as st
from snowflake.snowpark.context import get_active_session
from snowflake.snowpark.functions import when_matched, when_not_matched
from snowflake.snowpark.types import (
    DateType, DoubleType, StringType, StructField, StructType, TimestampType,
)

from excel_parser import parse_workbook, sanitize_identifier

# --- Placeholders: confirm/rename before go-live -----------------------
DATABASE_NAME = "DB_DW_DEV"
SCHEMA_NAME = "RPT_TRADERS_BM_SANDBOX"
UPLOAD_LOG_TABLE = "OIL_PRICE_UPLOAD_LOG"
WAREHOUSE_NAME = "TRADER_ANALYSIS_WH"
MAIL_STAGE_NAME = "DYNAMIC_FILE_INGESTION"
MAIL_STAGE_FOLDER = "OILS"  # mail ingestion stages to {stage}/OILS/{date}/
MAIL_INGEST_PROCEDURE = "SP_MAIL_INGEST"
MAIL_INGEST_JOB_NAME = "OILS"
MAX_MAIL_FILES_LISTED = 20
# -------------------------------------------------------------------------

FQ_UPLOAD_LOG_TABLE = f"{DATABASE_NAME}.{SCHEMA_NAME}.{UPLOAD_LOG_TABLE}"
FQ_MAIL_INGEST_PROCEDURE = f"{DATABASE_NAME}.{SCHEMA_NAME}.{MAIL_INGEST_PROCEDURE}"
MAIL_STAGE_PATH = f"@{DATABASE_NAME}.{SCHEMA_NAME}.{MAIL_STAGE_NAME}/{MAIL_STAGE_FOLDER}"
BASE_COLUMNS = ["REPORT_MONTH", "SHEET_NAME", "PRICE_DATE", "DAY_TYPE", "LOAD_TIMESTAMP"]
BASE_COLUMN_TYPES = {
    "REPORT_MONTH": "VARCHAR(50)",
    "SHEET_NAME": "VARCHAR(100)",
    "PRICE_DATE": "DATE",
    "DAY_TYPE": "VARCHAR(50)",
    "LOAD_TIMESTAMP": "TIMESTAMP_NTZ",
}

INPUT_MODE_UPLOAD = "Upload file"
INPUT_MODE_MAIL = "Read from mail"

CATEGORIES = {
    "NONEDIBLE": {
        "key": "non_edible",
        "tab_label": "Non-Edible Oils",
        "table_example": "PRICE_NONEDIBLE_FATY",
        "description": (
            "Provide the monthly `*_NON_EDIBLE_*.xlsx` report. Every product sheet "
            "(FATY, LAURICS, SPENT, STERIN, ACIDS, LINSEED, MISC 1, CASTOR) is parsed "
            "into a preview shaped like the original Excel tab below — nothing is "
            "written to Snowflake until you confirm."
        ),
    },
    "EDIBLE": {
        "key": "edible",
        "tab_label": "Edible Oils",
        "table_example": "PRICE_EDIBLE_*",
        "description": (
            "Provide the monthly `*_EDIBLE_OIL_RATE_LIST_*.xlsx` report. All 24 "
            "product sheets (SOYMEAL, SOYBEAN, MUSTARD, PALM OIL, CASTOR, CHINA, "
            "WHEAT, ...) are parsed into a preview shaped like the original Excel "
            "tab below — nothing is written to Snowflake until you confirm. "
            "Range quotes like `6600-6800` are kept as a LOW/HIGH pair."
        ),
    },
}

st.set_page_config(page_title="Oil Price Report Uploader", layout="wide")
session = get_active_session()
try:
    session.sql(f"USE WAREHOUSE {WAREHOUSE_NAME}").collect()
except Exception:
    pass


# --- Snowflake helpers ---------------------------------------------------
def rerun():
    """st.rerun() landed in Streamlit 1.27; older runtimes only have the
    experimental alias."""
    (getattr(st, "rerun", None) or st.experimental_rerun)()


def table_name_for_sheet(category: str, sheet_name: str) -> str:
    return f"{DATABASE_NAME}.{SCHEMA_NAME}.PRICE_{category}_{sanitize_identifier(sheet_name)}"


_MONTH_NAMES = (
    "JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE",
    "JULY", "AUGUST", "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER",
)


def guess_report_month(file_name: str) -> str:
    """Guess REPORT_MONTH from the file name.

    Matches "JULY_NON_EDIBLE_2026.xlsx", "JULY NON EDIBLE 2026.xlsx" and
    "JULY_EDIBLE_2026.xlsx" alike; falls back to any month name + 4-digit
    year found anywhere in the name (so edible reports without the literal
    "EDIBLE" token still get a guess).
    """
    match = re.search(r"([A-Za-z]+)[\s_]+(?:NON[\s_]+)?EDIBLE[\s_]+(\d{4})", file_name, re.IGNORECASE)
    if match:
        return f"{match.group(1).upper()}_{match.group(2)}"
    upper = file_name.upper()
    month = next((m for m in _MONTH_NAMES if m in upper), None)
    year = re.search(r"(20\d{2})", file_name)
    if month and year:
        return f"{month}_{year.group(1)}"
    return ""


def get_current_user() -> str:
    return session.sql("SELECT CURRENT_USER()").collect()[0][0]


def ensure_upload_log_table():
    session.sql(f"""
        CREATE TABLE IF NOT EXISTS {FQ_UPLOAD_LOG_TABLE} (
            CATEGORY VARCHAR(50),
            FILE_NAME VARCHAR(500),
            REPORT_MONTH VARCHAR(50),
            UPLOADED_BY VARCHAR(200),
            UPLOAD_TIMESTAMP TIMESTAMP_NTZ,
            ROWS_INSERTED NUMBER,
            SHEETS_PARSED NUMBER,
            STATUS VARCHAR(20),
            INPUT_SOURCE VARCHAR(20)
        )
    """).collect()
    # Older deployments may predate INPUT_SOURCE.
    try:
        session.sql(
            f"ALTER TABLE {FQ_UPLOAD_LOG_TABLE} ADD COLUMN IF NOT EXISTS INPUT_SOURCE VARCHAR(20)"
        ).collect()
    except Exception:
        pass


def already_uploaded(category: str, file_name: str) -> int:
    try:
        rows = session.sql(
            f"SELECT COUNT(*) FROM {FQ_UPLOAD_LOG_TABLE} WHERE CATEGORY = ? AND FILE_NAME = ?",
            params=[category, file_name],
        ).collect()
        return rows[0][0]
    except Exception:
        # Log table may not exist yet in a fresh environment.
        return 0


def ensure_table(table_fqn: str, series_columns: list, column_types: dict):
    """Create the sheet's table if absent, then add any series column it lacks.

    A price series is two FLOAT columns (<SERIES>_LOW / <SERIES>_HIGH); a
    futures MONTH label is a single VARCHAR. The parser decides which, so the
    column type comes from its wide_column_types map.
    """
    session.sql(f"""
        CREATE TABLE IF NOT EXISTS {table_fqn} (
            REPORT_MONTH VARCHAR(50),
            SHEET_NAME VARCHAR(100),
            PRICE_DATE DATE,
            DAY_TYPE VARCHAR(50),
            LOAD_TIMESTAMP TIMESTAMP_NTZ
        )
    """).collect()
    existing = set(session.table(table_fqn).schema.names)
    for col in series_columns:
        if col not in existing:
            sql_type = "VARCHAR" if column_types.get(col) == "VARCHAR" else "FLOAT"
            session.sql(f'ALTER TABLE {table_fqn} ADD COLUMN "{col}" {sql_type}').collect()


def _snowpark_schema(ordered_cols: list, column_types: dict) -> StructType:
    """Explicit schema for the staged frame.

    Snowpark infers a column's type from pandas dtypes, which silently gets it
    wrong for a column that is entirely null on a given month -- common here,
    since a series can be NA for every day of a month. Naming the types keeps
    the MERGE stable regardless of what a particular file contains.
    """
    fields = []
    for col in ordered_cols:
        declared = BASE_COLUMN_TYPES.get(col) or column_types.get(col, "FLOAT")
        if declared.startswith("TIMESTAMP"):
            dtype = TimestampType()
        elif declared.startswith("DATE"):
            dtype = DateType()
        elif declared.startswith("VARCHAR"):
            dtype = StringType()
        else:
            dtype = DoubleType()
        fields.append(StructField(col, dtype))
    return StructType(fields)


def _frame_to_rows(out: pd.DataFrame) -> list:
    """pandas frame -> plain Python rows, with every NaN/NaT flattened to None."""
    clean = out.astype(object).where(pd.notna(out), None)
    rows = []
    for record in clean.values.tolist():
        row = []
        for value in record:
            if isinstance(value, pd.Timestamp):
                value = value.to_pydatetime()
            row.append(value)
        rows.append(row)
    return rows


def upsert_sheet(category: str, sheet_name: str, wide_df: pd.DataFrame, report_month: str,
                 load_ts, column_types: dict) -> int:
    series_columns = [c for c in wide_df.columns if c not in ("PRICE_DATE", "DAY_TYPE")]
    table_fqn = table_name_for_sheet(category, sheet_name)
    ensure_table(table_fqn, series_columns, column_types)

    out = wide_df.copy()
    out["PRICE_DATE"] = pd.to_datetime(out["PRICE_DATE"]).dt.date
    out["REPORT_MONTH"] = report_month
    out["SHEET_NAME"] = sheet_name
    out["LOAD_TIMESTAMP"] = load_ts

    ordered_cols = BASE_COLUMNS + series_columns
    out = out[ordered_cols]

    source = session.create_dataframe(
        _frame_to_rows(out), schema=_snowpark_schema(ordered_cols, column_types)
    )
    target = session.table(table_fqn)

    update_cols = ["REPORT_MONTH", "DAY_TYPE", "LOAD_TIMESTAMP"] + series_columns
    target.merge(
        source,
        target["PRICE_DATE"] == source["PRICE_DATE"],
        [
            when_matched().update({c: source[c] for c in update_cols}),
            when_not_matched().insert({c: source[c] for c in ordered_cols}),
        ],
    )
    return len(out)


def load_workbook(category: str, wide_frames: dict, file_name: str, report_month: str,
                  input_source: str, column_types_by_sheet: dict):
    load_ts = datetime.datetime.utcnow()
    total_rows = 0
    for sheet_name, wide_df in wide_frames.items():
        if wide_df.empty:
            continue
        total_rows += upsert_sheet(
            category, sheet_name, wide_df, report_month, load_ts,
            column_types_by_sheet.get(sheet_name, {}),
        )

    ensure_upload_log_table()
    session.sql(
        f"""INSERT INTO {FQ_UPLOAD_LOG_TABLE}
            (CATEGORY, FILE_NAME, REPORT_MONTH, UPLOADED_BY, UPLOAD_TIMESTAMP,
             ROWS_INSERTED, SHEETS_PARSED, STATUS, INPUT_SOURCE)
            SELECT ?, ?, ?, ?, ?, ?, ?, 'SUCCESS', ?""",
        params=[category, file_name, report_month, get_current_user(), load_ts,
                total_rows, len(wide_frames), input_source],
    ).collect()
    return total_rows


# --- Mail-stage helpers --------------------------------------------------
def list_mail_stage_files() -> list:
    """List .xlsx files the mail-ingestion job staged, newest first.

    LIST does not support ORDER BY / LIMIT, so sorting happens here.
    Returns dicts with: file_name, stage_path (fully qualified, usable by
    session.file.get_stream), size_kb, last_modified.
    """
    # Doubled backslash: Snowflake drops a lone backslash from string literals.
    rows = session.sql(rf"LIST {MAIL_STAGE_PATH} PATTERN='.*\\.xlsx'").collect()
    files = []
    for row in rows:
        d = row.as_dict() if hasattr(row, "as_dict") else row.asDict()
        name = d.get("name") or d.get("NAME") or ""
        # LIST returns paths relative to the stage, prefixed with the stage
        # name itself (e.g. "dynamic_file_ingestion/OILS/2026-08-01/x.xlsx");
        # strip that first segment and re-qualify for get_stream().
        relative = name.split("/", 1)[1] if "/" in name else name
        size = d.get("size") or d.get("SIZE") or 0
        last_modified = d.get("last_modified") or d.get("LAST_MODIFIED")
        files.append({
            "file_name": name.rsplit("/", 1)[-1],
            "stage_path": f"@{DATABASE_NAME}.{SCHEMA_NAME}.{MAIL_STAGE_NAME}/{relative}",
            "size_kb": round(int(size) / 1024, 1),
            "last_modified": pd.to_datetime(last_modified, errors="coerce"),
        })
    files.sort(key=lambda f: (f["last_modified"] is not pd.NaT, f["last_modified"]), reverse=True)
    return files[:MAX_MAIL_FILES_LISTED]


def read_stage_file(stage_path: str) -> io.BytesIO:
    with session.file.get_stream(stage_path, decompress=False) as stream:
        return io.BytesIO(stream.read())


def fetch_new_mail() -> str:
    """Run the mail-ingestion job now and return its '<STATUS> :: <message>' result.

    Both arguments are module constants, so they are inlined rather than bound.
    """
    rows = session.sql(
        f"CALL {FQ_MAIL_INGEST_PROCEDURE}"
        f"(CURRENT_DATE(), '{MAIL_INGEST_JOB_NAME}', FALSE)"
    ).collect()
    return str(rows[0][0]) if rows else ""


def show_ingest_status(status: str):
    """Render what the ingestion procedure returned, keyed off its status prefix."""
    head = status.split("::", 1)[0].strip().upper()
    if head == "OK":
        st.success(status)
    elif head == "FAILED":
        st.error(status)
    else:  # NO_DATA / ALREADY_LOADED — normal outcomes, not errors
        st.info(status)


def render_mail_input(key: str):
    """'Read from mail' input mode. Returns (file_name, BytesIO) or (None, None).

    The chosen file is kept in st.session_state so it survives Streamlit's
    rerun on every widget interaction (editing the report month, ticking the
    confirm checkbox, ...).
    """
    files_key = "mail_stage_files"  # shared across tabs: one LIST serves both
    loaded_key = f"{key}_mail_loaded"

    st.markdown(
        f"Pick a file that was ingested from the shared mailbox "
        f"(**'Edible & Non Edible Oils'** emails, staged to `{MAIL_STAGE_PATH}`). "
        "If a report has just arrived, **Fetch new mail now** checks the mailbox "
        "and stages any new attachments straight away."
    )

    col_fetch, col_refresh, _ = st.columns([1, 1, 3])
    fetch_clicked = col_fetch.button("Fetch new mail now", key=f"{key}_mail_fetch")
    refresh_clicked = col_refresh.button("Refresh file list", key=f"{key}_mail_refresh")

    if fetch_clicked:
        try:
            with st.spinner("Checking the mailbox for new attachments..."):
                show_ingest_status(fetch_new_mail())
        except Exception as exc:
            st.error(
                f"Could not run the mail-ingestion job: {exc}\n\n"
                f"Check that `{FQ_MAIL_INGEST_PROCEDURE}` exists and that this "
                "app's role has USAGE on it."
            )

    if fetch_clicked or refresh_clicked or files_key not in st.session_state:
        try:
            with st.spinner("Listing mail-ingested files..."):
                st.session_state[files_key] = list_mail_stage_files()
        except Exception as exc:
            st.error(f"Could not list files in the mail stage: {exc}")
            st.session_state[files_key] = []

    files = st.session_state.get(files_key, [])
    if not files:
        st.warning(
            "No files found in the mail stage. Click **Fetch new mail now** to "
            "check the mailbox, or confirm a matching email has actually arrived."
        )
        return None, None

    def _label(f):
        modified = (
            f["last_modified"].strftime("%Y-%m-%d %H:%M")
            if f["last_modified"] is not pd.NaT else "unknown date"
        )
        return f"{f['file_name']}  ({modified}, {f['size_kb']} KB)"

    selected = st.selectbox(
        f"Files found (newest first, showing up to {MAX_MAIL_FILES_LISTED})",
        options=files,
        format_func=_label,
        key=f"{key}_mail_select",
    )

    if st.button("Use this file", key=f"{key}_mail_use", type="secondary"):
        try:
            with st.spinner(f"Reading {selected['file_name']} from stage..."):
                st.session_state[loaded_key] = {
                    "file_name": selected["file_name"],
                    "content": read_stage_file(selected["stage_path"]).getvalue(),
                }
        except Exception as exc:
            st.error(f"Could not read {selected['file_name']} from the stage: {exc}")

    loaded = st.session_state.get(loaded_key)
    if not loaded:
        st.info("Select a file and click **Use this file** to begin.")
        return None, None

    col_status, col_clear = st.columns([4, 1])
    col_status.success(f"Loaded from mail: **{loaded['file_name']}**")
    if col_clear.button("Clear", key=f"{key}_mail_clear"):
        del st.session_state[loaded_key]
        rerun()

    return loaded["file_name"], io.BytesIO(loaded["content"])


# --- Shared review-and-load flow -----------------------------------------
def render_category_tab(category: str):
    cfg = CATEGORIES[category]
    key = cfg["key"]

    st.caption(
        f"Target: one table per product sheet (`{cfg['table_example']}`, ...) "
        f"in `{DATABASE_NAME}.{SCHEMA_NAME}`."
    )
    st.markdown(cfg["description"])

    input_mode = st.radio(
        "How do you want to provide the file?",
        options=[INPUT_MODE_UPLOAD, INPUT_MODE_MAIL],
        key=f"{key}_input_mode",
        horizontal=True,
    )

    file_name = None
    file_bytes = None
    if input_mode == INPUT_MODE_UPLOAD:
        uploaded_file = st.file_uploader("Choose the Excel file", type=["xlsx"], key=f"{key}_uploader")
        if uploaded_file is not None:
            file_name = uploaded_file.name
            file_bytes = io.BytesIO(uploaded_file.getvalue())
        else:
            st.info("Upload a file to begin.")
    else:
        file_name, file_bytes = render_mail_input(key)

    if file_bytes is None or file_name is None:
        return

    with st.spinner("Parsing workbook..."):
        try:
            result = parse_workbook(file_bytes, file_name)
        except Exception as exc:
            st.error(f"Could not parse this file: {exc}")
            st.stop()

    if result.total_rows == 0:
        st.warning("No data rows were found in this file. Please check the file and try again.")
        st.stop()

    default_month = guess_report_month(file_name)
    report_month = st.text_input(
        "Report month (used to tag this load — edit if it was guessed wrong)",
        value=default_month,
        key=f"{key}_report_month",
    )

    prior_count = already_uploaded(category, file_name)
    if prior_count > 0:
        st.warning(
            f"A file named **{file_name}** was already loaded {prior_count} time(s) before. "
            "Re-loading will overwrite matching dates in the target tables, not duplicate them."
        )

    st.subheader("1. Sheet-level summary — confirm this matches what you expect")
    summary_rows = []
    for sheet in result.sheets:
        summary_rows.append({
            "Sheet": sheet.sheet_name,
            "Target table": table_name_for_sheet(category, sheet.sheet_name).split(".")[-1],
            "Price series found": len(sheet.series),
            "Data rows": len(sheet.rows),
            "Date range": f"{sheet.date_range[0]} to {sheet.date_range[1]}" if sheet.date_range else "—",
            "Warnings": "; ".join(sheet.warnings) if sheet.warnings else "",
        })
    summary_df = pd.DataFrame(summary_rows)
    st.dataframe(summary_df, use_container_width=True, hide_index=True)

    any_warnings = summary_df["Warnings"].str.len().gt(0).any()
    if any_warnings:
        st.warning("Some sheets raised warnings during parsing — review them before proceeding.")

    wide_frames = result.to_wide_frames()
    # to_wide_frames() fills in each sheet's wide_column_types, so read it after.
    column_types_by_sheet = {s.sheet_name: s.wide_column_types for s in result.sheets}
    total_rows = sum(len(df) for df in wide_frames.values())

    st.subheader("2. Preview — shaped like the source Excel tab, one sheet per tab below")
    sheet_names_with_data = [s.sheet_name for s in result.sheets if not wide_frames[s.sheet_name].empty]
    if sheet_names_with_data:
        sheet_tabs = st.tabs(sheet_names_with_data)
        for sheet_tab, sheet_name in zip(sheet_tabs, sheet_names_with_data):
            with sheet_tab:
                st.dataframe(wide_frames[sheet_name], use_container_width=True, height=400)

    st.subheader("3. Confirm and load")
    st.write(
        f"This will write **{total_rows:,} rows** across **{len(sheet_names_with_data)} sheets** "
        f"(one table per sheet, e.g. `{cfg['table_example']}`), tagged as report month "
        f"**{report_month or '(not set)'}**. Matching dates already in a table are overwritten; "
        "new dates are inserted."
    )
    confirmed = st.checkbox("I have reviewed the data above and it looks correct.", key=f"{key}_confirm")
    load_clicked = st.button(
        "Insert into Snowflake", type="primary", disabled=not confirmed, key=f"{key}_insert"
    )

    if load_clicked:
        if not report_month:
            st.error("Please set a report month before loading.")
            st.stop()
        input_source = "MAIL" if input_mode == INPUT_MODE_MAIL else "UPLOAD"
        try:
            with st.spinner("Writing to Snowflake..."):
                rows_written = load_workbook(
                    category, wide_frames, file_name, report_month, input_source,
                    column_types_by_sheet,
                )
            st.success(f"Loaded {rows_written:,} rows from {file_name}.")
        except Exception as exc:
            st.error(f"Insert failed: {exc}")


st.title("Oil Price Report Uploader")

tabs = st.tabs([CATEGORIES[c]["tab_label"] for c in CATEGORIES])
for tab, category in zip(tabs, CATEGORIES):
    with tab:
        render_category_tab(category)

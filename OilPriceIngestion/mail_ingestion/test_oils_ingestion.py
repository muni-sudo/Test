"""Test script for Edible & Non Edible Oils mail ingestion.

Run this locally after connecting to Snowflake to validate the entire pipeline.
"""
from __future__ import annotations

import datetime as _dt
import sys

from mail_ingestion import ingest_attachments
from mail_ingest_examples import get_oils_config


def test_oils_ingestion(session, run_date: _dt.date = None, force: bool = False) -> None:
    """
    End-to-end test of Oils mail ingestion.

    Args:
        session: Snowpark session (must be connected to Snowflake)
        run_date: Date to process (default: today)
        force: If True, reprocess even if already loaded
    """
    if run_date is None:
        run_date = _dt.date.today()

    print("\n" + "=" * 80)
    print("OILS MAIL INGESTION TEST")
    print("=" * 80)

    # --- Step 1: Display Config ---
    print("\n[STEP 1] Configuration")
    print("-" * 80)
    config = get_oils_config()
    print(f"  Job Name:           {config.job_name}")
    print(f"  Mailbox:            {config.mailbox}")
    print(f"  Sender Filter:      {config.sender_filter or '(no filter - accept any sender)'}")
    print(f"  Subject Filter:     {config.subject_filter}")
    print(f"  File Patterns:      {config.file_patterns}")
    print(f"  Lookback Hours:     {config.lookback_hours}")
    print(f"  Target Stage:       {config.get_stage_path(run_date)}")
    print(f"  Run Date:           {run_date}")
    print(f"  Force Reprocess:    {force}")

    # --- Step 2: Run Ingestion ---
    print("\n[STEP 2] Running Ingestion")
    print("-" * 80)
    try:
        result = ingest_attachments(session, config, run_date, force=force)
    except Exception as e:
        print(f"  ❌ FAILED: {e}")
        import traceback
        traceback.print_exc()
        return

    # --- Step 3: Display Result ---
    print("\n[STEP 3] Result")
    print("-" * 80)
    print(f"  Status:         {result['status']}")
    print(f"  Message:        {result['message']}")
    print(f"  Files Staged:   {result['files_staged']}")
    print(f"  Run ID:         {result['run_id']}")

    if result["status"] == "FAILED":
        print("\n  ⚠️  Ingestion failed. Check logs for details.")
        return

    # --- Step 4: Verify Stage Files ---
    if result["files_staged"] > 0:
        print("\n[STEP 4] Verifying Staged Files")
        print("-" * 80)
        try:
            stage_path = config.get_stage_path(run_date)
            files = session.sql(f"LS {stage_path}").collect()
            print(f"  Files in {stage_path}:")
            for f in files:
                print(f"    - {f}")
        except Exception as e:
            print(f"  ⚠️  Could not list stage files: {e}")

    # --- Step 5: Check Audit Log ---
    print("\n[STEP 5] Checking Audit Log (INGEST_FILE_LOG)")
    print("-" * 80)
    try:
        q = f"""
            SELECT
                SOURCE, DATASET, RUN_DATE, FILE_NAME, MESSAGE_ID,
                ROW_COUNT, STATUS, LOADED_AT
            FROM DB_DW_DEV.RPT_TRADERS_BM_SANDBOX.INGEST_FILE_LOG
            WHERE SOURCE = '{config.job_name}'
                AND RUN_DATE = '{run_date}'
            ORDER BY LOADED_AT DESC
            LIMIT 10
        """
        logs = session.sql(q).to_pandas()
        if logs.empty:
            print(f"  No audit records found for {config.job_name} on {run_date}")
        else:
            print(f"  Found {len(logs)} record(s):")
            for idx, row in logs.iterrows():
                print(f"\n    Record {idx + 1}:")
                print(f"      File:       {row['FILE_NAME']}")
                print(f"      Status:     {row['STATUS']}")
                print(f"      Message ID: {row['MESSAGE_ID']}")
                print(f"      Bytes:      {row['ROW_COUNT']}")
                print(f"      Loaded At:  {row['LOADED_AT']}")
    except Exception as e:
        print(f"  ⚠️  Could not query audit log: {e}")

    # --- Step 6: Check ETL Run Log ---
    print("\n[STEP 6] Checking ETL Run Log")
    print("-" * 80)
    try:
        q = f"""
            SELECT
                RUN_ID, STEP, STATUS, ROWS_OUT, DETAIL, ENDED_AT
            FROM DB_DW_DEV.RPT_TRADERS_BM_SANDBOX.ETL_RUN_LOG
            WHERE RUN_ID = '{result["run_id"]}'
        """
        etl_log = session.sql(q).collect()
        if etl_log:
            row = etl_log[0]
            print(f"  Run ID:     {row['RUN_ID']}")
            print(f"  Step:       {row['STEP']}")
            print(f"  Status:     {row['STATUS']}")
            print(f"  Rows Out:   {row['ROWS_OUT']}")
            print(f"  Ended At:   {row['ENDED_AT']}")
            if row['DETAIL']:
                print(f"  Detail:     {row['DETAIL']}")
    except Exception as e:
        print(f"  ⚠️  Could not query ETL log: {e}")

    # --- Summary ---
    print("\n" + "=" * 80)
    if result["status"] == "OK":
        print(f"✅ SUCCESS: Staged {result['files_staged']} file(s)")
    elif result["status"] == "NO_DATA":
        print("⚠️  NO DATA: No emails matching the criteria found.")
        print("   Tip: Verify a test email exists in the mailbox with:")
        print("   - Subject containing: 'Edible & Non Edible Oils'")
        print("   - At least one attachment")
    elif result["status"] == "ALREADY_LOADED":
        print("⚠️  ALREADY_LOADED: This message was already processed.")
        print(f"   Tip: Use force=True to reprocess, or send a new test email")
    else:
        print(f"❌ FAILED: {result['message']}")

    print("=" * 80 + "\n")


if __name__ == "__main__":
    # For testing, you would need to provide a Snowpark session.
    # Example (uncomment and adjust as needed):
    #
    # from snowflake.snowpark import Session
    # import os
    #
    # connection_params = {
    #     "account": "YOUR_ACCOUNT",
    #     "user": "YOUR_USER",
    #     "password": "YOUR_PASSWORD",
    #     "warehouse": "TRADER_ANALYSIS_WH",
    #     "database": "DB_DW_DEV",
    #     "schema": "RPT_TRADERS_BM_SANDBOX"
    # }
    # session = Session.builder.configs(connection_params).create()
    # test_oils_ingestion(session, force=True)
    # session.close()

    print("Test script created. To run this test:")
    print("1. Set up a Snowflake session with your credentials")
    print("2. Call test_oils_ingestion(session, force=True)")
    print("3. Review the output for details on what happened")
    print("\nExample usage in a notebook or script:")
    print("  from test_oils_ingestion import test_oils_ingestion")
    print("  test_oils_ingestion(session, force=True)")

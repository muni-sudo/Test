"""
Generic parser for the "NON_EDIBLE" monthly price-report workbooks.

Each workbook has one INDEX sheet (skipped) plus a fixed set of product
sheets (FATY, LAURICS, SPENT, STERIN, ACIDS, LINSEED, MISC 1, CASTOR).
Each product sheet is a daily price grid: column A = date, every other
column is a distinct price series spread across 2-3 stacked/merged
header rows. This module flattens each sheet into a long/tall list of
(series_name, price_date, raw_value, price_value, status_flag) rows.
"""
from __future__ import annotations

import datetime
import re
from dataclasses import dataclass, field

import openpyxl

SKIP_SHEETS = {"INDEX"}
STATUS_TOKENS = {"NA", "SUNDAY", "MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY",
                  "FRIDAY", "SATURDAY", "CLOSE", "CLOSED", "HOLIDAY"}


@dataclass
class ParsedRow:
    sheet_name: str
    series_name: str
    column_index: int
    price_date: datetime.date
    raw_value: str
    price_value: float | None
    status_flag: str | None


@dataclass
class SheetParseResult:
    sheet_name: str
    series: list[str] = field(default_factory=list)
    rows: list[ParsedRow] = field(default_factory=list)
    date_range: tuple[datetime.date, datetime.date] | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class WorkbookParseResult:
    file_name: str
    sheets: list[SheetParseResult] = field(default_factory=list)

    @property
    def total_rows(self) -> int:
        return sum(len(s.rows) for s in self.sheets)

    @property
    def all_series(self) -> list[tuple[str, str]]:
        return [(s.sheet_name, series) for s in self.sheets for series in s.series]

    def to_dataframe(self):
        import pandas as pd
        records = []
        for sheet in self.sheets:
            for r in sheet.rows:
                records.append({
                    "SHEET_NAME": r.sheet_name,
                    "SERIES_NAME": r.series_name,
                    "COLUMN_INDEX": r.column_index,
                    "PRICE_DATE": r.price_date,
                    "RAW_VALUE": r.raw_value,
                    "PRICE_VALUE": r.price_value,
                    "STATUS_FLAG": r.status_flag,
                })
        return pd.DataFrame.from_records(records)

    def to_wide_frames(self):
        """One wide, Excel-shaped DataFrame per sheet: PRICE_DATE, DAY_TYPE,
        then one column per price series. See pivot_sheet_wide()."""
        return {sheet.sheet_name: pivot_sheet_wide(sheet) for sheet in self.sheets}


def _build_merge_map(ws):
    """Map every cell coordinate covered by a merge to the anchor cell's value."""
    merge_map = {}
    for merged_range in ws.merged_cells.ranges:
        anchor_value = ws.cell(row=merged_range.min_row, column=merged_range.min_col).value
        for row in range(merged_range.min_row, merged_range.max_row + 1):
            for col in range(merged_range.min_col, merged_range.max_col + 1):
                merge_map[(row, col)] = anchor_value
    return merge_map


def _cell_value(ws, merge_map, row, col):
    if (row, col) in merge_map:
        return merge_map[(row, col)]
    return ws.cell(row=row, column=col).value


def _clean(v) -> str:
    if v is None:
        return ""
    return re.sub(r"\s+", " ", str(v)).strip()


def _is_letterhead_noise(text: str) -> bool:
    """Company letterhead/address blocks sometimes live in a merged cell that
    spans real data columns; they must not pollute the series name."""
    if "@" in text or "FAX" in text.upper():
        return True
    if len(text) > 60:
        return True
    return False


def _find_date_label_row(ws, merge_map, max_row_scan=15) -> int | None:
    for row in range(1, max_row_scan + 1):
        v = _clean(_cell_value(ws, merge_map, row, 1))
        if "DATE" in v.upper():
            return row
    return None


def _find_used_columns(ws, max_col_scan=60) -> int:
    """SPENT-style sheets report a bogus huge max_column; find the real
    rightmost column by scanning the header band instead."""
    max_col = 1
    for row in range(1, 6):
        for col in range(1, max_col_scan + 1):
            if ws.cell(row=row, column=col).value not in (None, ""):
                max_col = max(max_col, col)
    return max_col


def parse_sheet(ws) -> SheetParseResult:
    result = SheetParseResult(sheet_name=ws.title)
    merge_map = _build_merge_map(ws)

    date_row = _find_date_label_row(ws, merge_map)
    if date_row is None:
        result.warnings.append("Could not locate a 'DATE' header row; sheet skipped.")
        return result

    used_max_col = _find_used_columns(ws)

    # Build a series name per column by concatenating header rows 1..date_row
    series_by_col: dict[int, str] = {}
    for col in range(2, used_max_col + 1):
        parts = []
        for row in range(1, date_row + 1):
            v = _clean(_cell_value(ws, merge_map, row, col))
            if v and v not in parts and not _is_letterhead_noise(v):
                parts.append(v)
        name = " | ".join(parts)
        if name:
            series_by_col[col] = name

    result.series = list(series_by_col.values())

    # Data starts right after the date-label row; skip blank spacer rows.
    data_row = date_row + 1
    real_max_row = ws.max_row
    if ws.title == "SPENT" or real_max_row > 5000:
        # openpyxl over-reports dimensions on some sheets (phantom formatted
        # rows); cap the scan to a sane window past the last real date.
        real_max_row = date_row + 400

    min_d, max_d = None, None
    consecutive_blank = 0
    row = data_row
    while row <= real_max_row:
        raw_date = ws.cell(row=row, column=1).value
        price_date = None
        if isinstance(raw_date, datetime.datetime):
            price_date = raw_date.date()
        elif isinstance(raw_date, datetime.date):
            price_date = raw_date

        if price_date is None:
            row_has_any_value = any(
                ws.cell(row=row, column=c).value not in (None, "")
                for c in range(1, used_max_col + 1)
            )
            consecutive_blank = 0 if row_has_any_value else consecutive_blank + 1
            if consecutive_blank >= 5:
                break
            row += 1
            continue

        consecutive_blank = 0
        min_d = price_date if min_d is None else min(min_d, price_date)
        max_d = price_date if max_d is None else max(max_d, price_date)

        for col, series_name in series_by_col.items():
            value = ws.cell(row=row, column=col).value
            if value is None or value == "":
                continue
            raw_str = _clean(value)
            price_value = None
            status_flag = None
            if isinstance(value, (int, float)):
                price_value = float(value)
            else:
                token = raw_str.upper()
                if token in STATUS_TOKENS:
                    status_flag = token
                else:
                    try:
                        price_value = float(raw_str)
                    except ValueError:
                        status_flag = token or None
            result.rows.append(ParsedRow(
                sheet_name=ws.title,
                series_name=series_name,
                column_index=col,
                price_date=price_date,
                raw_value=raw_str,
                price_value=price_value,
                status_flag=status_flag,
            ))
        row += 1

    if min_d and max_d:
        result.date_range = (min_d, max_d)
    return result


def sanitize_identifier(name: str) -> str:
    """Turn a header string (or sheet name) into a valid unquoted Snowflake
    identifier, e.g. "PALM OIL | CRUDE" -> "PALM_OIL_CRUDE", "MISC 1" ->
    "MISC_1"."""
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").upper()
    if not cleaned:
        cleaned = "COLUMN"
    if cleaned[0].isdigit():
        cleaned = f"C_{cleaned}"
    return cleaned


def pivot_sheet_wide(sheet: SheetParseResult):
    """Reshape a sheet's long rows into one row per PRICE_DATE, one column
    per price series (matching the source Excel tab), plus a DAY_TYPE
    column set only when EVERY series on that date shares the same
    non-numeric status token (e.g. the whole sheet says SUNDAY) -- a single
    series being NA for one date does not count as a sheet-wide day type.

    Columns are keyed by COLUMN_INDEX, not by the raw series-name text,
    since two columns can end up with the same reconstructed header text
    (see README "Known limitation") -- COLUMN_INDEX is always unique.
    """
    import pandas as pd

    col_order: list[int] = []
    name_by_index: dict[int, str] = {}
    for row in sheet.rows:
        if row.column_index not in name_by_index:
            name_by_index[row.column_index] = row.series_name
            col_order.append(row.column_index)

    seen: dict[str, int] = {}
    sanitized_by_index: dict[int, str] = {}
    for idx in col_order:
        base = sanitize_identifier(name_by_index[idx])
        n = seen.get(base, 0)
        sanitized_by_index[idx] = base if n == 0 else f"{base}_{n + 1}"
        seen[base] = n + 1

    by_date: dict[datetime.date, dict[int, ParsedRow]] = {}
    for row in sheet.rows:
        by_date.setdefault(row.price_date, {})[row.column_index] = row

    records = []
    for price_date in sorted(by_date):
        cells = by_date[price_date]
        record = {"PRICE_DATE": price_date}
        statuses = []
        any_present = False
        any_numeric = False
        for idx in col_order:
            col = sanitized_by_index[idx]
            cell = cells.get(idx)
            if cell is None:
                record[col] = None
                continue
            any_present = True
            if cell.price_value is not None:
                record[col] = cell.price_value
                any_numeric = True
            else:
                record[col] = None
                if cell.status_flag:
                    statuses.append(cell.status_flag)
        record["DAY_TYPE"] = (
            statuses[0]
            if any_present and not any_numeric and statuses and len(set(statuses)) == 1
            else None
        )
        records.append(record)

    columns = ["PRICE_DATE", "DAY_TYPE"] + [sanitized_by_index[idx] for idx in col_order]
    return pd.DataFrame.from_records(records, columns=columns)


def parse_workbook(file_path_or_bytes, file_name: str) -> WorkbookParseResult:
    wb = openpyxl.load_workbook(file_path_or_bytes, data_only=True, read_only=False)
    result = WorkbookParseResult(file_name=file_name)
    for sheet_name in wb.sheetnames:
        if sheet_name.upper() in SKIP_SHEETS:
            continue
        ws = wb[sheet_name]
        result.sheets.append(parse_sheet(ws))
    return result


if __name__ == "__main__":
    import sys
    for path in sys.argv[1:]:
        wb_result = parse_workbook(path, path.split("/")[-1])
        print("=" * 100)
        print(wb_result.file_name, "-> total rows:", wb_result.total_rows)
        for s in wb_result.sheets:
            print(f"  {s.sheet_name:10s} series={len(s.series):3d} rows={len(s.rows):5d} "
                  f"date_range={s.date_range} warnings={s.warnings}")

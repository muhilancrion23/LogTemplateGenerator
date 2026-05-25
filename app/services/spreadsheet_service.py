"""
SpreadsheetService — converts Excel (.xlsx, .xls) and CSV files to
a clean, multi-page PDF so Gemini can analyse them via its File API.

Why PDF instead of passing the raw file?
  Gemini's File API does not support Excel or CSV natively (May 2026).
  Converting to PDF keeps the existing VLMService contract intact and
  gives Gemini full cross-sheet/cross-page context in one API call.

Conversion approach
-------------------
  1.  Read every sheet (Excel) or the single table (CSV) with pandas.
  2.  Render each sheet as a ReportLab table, one sheet per page group.
  3.  Write the result to Config.TEMP_FOLDER and return the path.

The caller is responsible for deleting the generated PDF after use.

Dependencies: pandas, openpyxl (xlsx), xlrd (xls), reportlab
"""

import logging
import os
import uuid
from typing import Optional

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.config import Config

logger = logging.getLogger(__name__)

# Maximum rows rendered per sheet — keeps PDF size sane for huge files.
_MAX_ROWS_PER_SHEET: int = 500
# Maximum columns before we switch to landscape orientation.
_LANDSCAPE_THRESHOLD_COLS: int = 8


# ── Internal helpers ──────────────────────────────────────────────────────────

def _read_excel(file_path: str) -> dict[str, pd.DataFrame]:
    """
    Read all sheets from an Excel file.
    Returns {sheet_name: DataFrame}.
    Handles both .xlsx (openpyxl) and .xls (xlrd) transparently.
    """
    ext = os.path.splitext(file_path)[1].lower()
    engine: Optional[str] = "xlrd" if ext == ".xls" else None  # openpyxl is default

    try:
        sheets: dict[str, pd.DataFrame] = pd.read_excel(
            file_path,
            sheet_name=None,        # all sheets
            engine=engine,
            nrows=_MAX_ROWS_PER_SHEET,
            dtype=str,              # keep everything as text; avoids float noise
        )
        return sheets
    except Exception as err:
        raise RuntimeError(f"Cannot read Excel file: {err}") from err


def _read_csv(file_path: str) -> dict[str, pd.DataFrame]:
    """
    Read a CSV file.  Returns a single-entry dict so the caller can
    treat CSV and Excel identically.
    """
    try:
        df = pd.read_csv(
            file_path,
            nrows=_MAX_ROWS_PER_SHEET,
            dtype=str,
            encoding="utf-8",
            encoding_errors="replace",
        )
        sheet_name = os.path.basename(file_path)
        return {sheet_name: df}
    except Exception as err:
        raise RuntimeError(f"Cannot read CSV file: {err}") from err


def _df_to_table_data(df: pd.DataFrame) -> list[list[str]]:
    """
    Convert a DataFrame to a list-of-lists (header + rows) with safe
    string coercion so ReportLab never chokes on NaN or None.
    """
    df = df.fillna("")
    header = [str(col) for col in df.columns]
    rows = [[str(cell) for cell in row] for row in df.itertuples(index=False)]
    return [header] + rows


def _build_reportlab_table(
    table_data: list[list[str]],
    col_count: int,
    page_width: float,
) -> Table:
    """
    Build a styled ReportLab Table from raw string data.
    Column widths are distributed evenly across the page.
    """
    usable_width = page_width - 2 * cm
    col_width = usable_width / max(col_count, 1)
    col_widths = [col_width] * col_count

    tbl = Table(table_data, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(
        TableStyle(
            [
                # Header row
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a6b8a")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 7),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 4),
                ("TOPPADDING", (0, 0), (-1, 0), 4),
                # Data rows — alternating shading
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 1), (-1, -1), 6.5),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f8fb")]),
                ("TOPPADDING", (0, 1), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 3),
                # Grid
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#c0c0c0")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("WORDWRAP", (0, 0), (-1, -1), True),
            ]
        )
    )
    return tbl


# ── Public API ────────────────────────────────────────────────────────────────

class SpreadsheetService:
    """
    Converts a spreadsheet file to a PDF suitable for Gemini analysis.

    Usage::

        pdf_path = SpreadsheetService.to_pdf("/tmp/data.xlsx")
        # ... pass pdf_path to VLMService.extract_parameters_from_pdf()
        FileService.delete_file(pdf_path)   # caller's responsibility
    """

    @staticmethod
    def to_pdf(spreadsheet_path: str) -> str:
        """
        Convert *spreadsheet_path* (Excel or CSV) to a PDF file stored
        in Config.TEMP_FOLDER.

        Returns the absolute path to the generated PDF.
        Raises RuntimeError on any failure.
        """
        if not os.path.isfile(spreadsheet_path):
            raise FileNotFoundError(
                f"Spreadsheet not found: {spreadsheet_path}"
            )

        ext = os.path.splitext(spreadsheet_path)[1].lower()

        # ── 1. Read into DataFrames ───────────────────────────────────
        if ext == ".csv":
            sheets = _read_csv(spreadsheet_path)
        elif ext in {".xlsx", ".xls"}:
            sheets = _read_excel(spreadsheet_path)
        else:
            raise ValueError(
                f"Unsupported spreadsheet format: {ext!r}. "
                "Expected .csv, .xlsx, or .xls"
            )

        if not sheets:
            raise RuntimeError("Spreadsheet contains no readable sheets.")

        logger.info(
            "SpreadsheetService: read %d sheet(s) from %s",
            len(sheets),
            spreadsheet_path,
        )

        # ── 2. Determine page orientation from widest sheet ───────────
        max_cols = max(df.shape[1] for df in sheets.values() if not df.empty)
        if max_cols >= _LANDSCAPE_THRESHOLD_COLS:
            page_size = landscape(A4)
        else:
            page_size = A4
        page_width, _ = page_size

        # ── 3. Build PDF story ────────────────────────────────────────
        styles = getSampleStyleSheet()
        heading_style = styles["Heading2"]
        story = []

        for sheet_name, df in sheets.items():
            if df.empty:
                logger.debug("Skipping empty sheet: %s", sheet_name)
                continue

            # Sheet heading
            story.append(Paragraph(f"Sheet: {sheet_name}", heading_style))
            story.append(Spacer(1, 0.3 * cm))

            # Truncation notice
            if len(df) == _MAX_ROWS_PER_SHEET:
                notice = Paragraph(
                    f"<i>Note: Displaying first {_MAX_ROWS_PER_SHEET} rows only.</i>",
                    styles["Italic"],
                )
                story.append(notice)
                story.append(Spacer(1, 0.2 * cm))

            table_data = _df_to_table_data(df)
            tbl = _build_reportlab_table(
                table_data, col_count=df.shape[1], page_width=page_width
            )
            story.append(tbl)
            story.append(Spacer(1, 0.5 * cm))

        if not story:
            raise RuntimeError(
                "All sheets in the spreadsheet were empty."
            )

        # ── 4. Write PDF ──────────────────────────────────────────────
        out_filename = f"{uuid.uuid4()}_converted.pdf"
        out_path = os.path.join(Config.TEMP_FOLDER, out_filename)

        doc = SimpleDocTemplate(
            out_path,
            pagesize=page_size,
            leftMargin=1 * cm,
            rightMargin=1 * cm,
            topMargin=1.5 * cm,
            bottomMargin=1.5 * cm,
        )
        doc.build(story)

        logger.info(
            "SpreadsheetService: PDF written → %s (%d bytes)",
            out_path,
            os.path.getsize(out_path),
        )
        return out_path
from datetime import datetime

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

from .config import ODOO_SKU_COLUMN, ODOO_IMG_COLUMN, ODOO_EXT_COLUMN, ODOO_VAR_COLUMN
from .logger import log


def export_odoo_excel(df, sku_files, output_path):
    out = df.copy()
    if ODOO_IMG_COLUMN not in out.columns:
        out[ODOO_IMG_COLUMN] = ""

    out[ODOO_IMG_COLUMN] = out[ODOO_SKU_COLUMN].apply(
        lambda sku: (sku_files.get(str(sku).strip()) or [""])[0]
    )

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "product.product"

    headers = list(out.columns)
    hdr_fill = PatternFill("solid", start_color="1D3557")
    hdr_font = Font(bold=True, color="FFFFFF", name="Arial", size=10)
    hdr_align = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for ci, col in enumerate(headers, 1):
        c = ws.cell(row=1, column=ci, value=col)
        c.fill = hdr_fill
        c.font = hdr_font
        c.alignment = hdr_align

    alt_fill = PatternFill("solid", start_color="F0F4F8")
    ok_fill = PatternFill("solid", start_color="D4EDDA")
    miss_fill = PatternFill("solid", start_color="FFF3CD")
    norm_font = Font(name="Arial", size=9)
    img_ci = headers.index(ODOO_IMG_COLUMN) + 1

    for ri, row in enumerate(out.itertuples(index=False), 2):
        for ci, value in enumerate(row, 1):
            val = "" if str(value) in ("nan", "None") else str(value)
            c = ws.cell(row=ri, column=ci, value=val)
            c.font = norm_font
            c.alignment = Alignment(vertical="center")
            if ci == img_ci:
                c.fill = ok_fill if val else miss_fill
            elif ri % 2 == 0:
                c.fill = alt_fill

    col_widths = {
        ODOO_EXT_COLUMN: 45,
        ODOO_SKU_COLUMN: 20,
        ODOO_VAR_COLUMN: 18,
        ODOO_IMG_COLUMN: 30,
    }
    for ci, col in enumerate(headers, 1):
        ws.column_dimensions[get_column_letter(ci)].width = col_widths.get(col, 20)

    ws.row_dimensions[1].height = 28
    ws.freeze_panes = "A2"

    img_col_letter = get_column_letter(img_ci)
    n_rows = len(out) + 1
    ws2 = wb.create_sheet("Resume")
    ws2["A1"] = "Rapport de Scraping"
    ws2["A1"].font = Font(bold=True, size=14, name="Arial")
    ws2["A3"] = "Date de generation"
    ws2["B3"] = datetime.now().strftime("%d/%m/%Y %H:%M")
    ws2["A4"] = "Total SKUs"
    ws2["B4"] = len(sku_files)
    ws2["A5"] = "Images trouvees"
    ws2["B5"] = sum(1 for v in sku_files.values() if v)
    ws2["A6"] = "Images manquantes"
    ws2["B6"] = "=B4-B5"
    ws2["A7"] = "Total Variantes OK"
    ws2["B7"] = (
        f"=COUNTIF('product.product'!{img_col_letter}2:{img_col_letter}{n_rows},\"*.jpg\")"
        f"+COUNTIF('product.product'!{img_col_letter}2:{img_col_letter}{n_rows},\"*.png\")"
        f"+COUNTIF('product.product'!{img_col_letter}2:{img_col_letter}{n_rows},\"*.webp\")"
    )
    for cell in ["A3", "A4", "A5", "A6", "A7"]:
        ws2[cell].font = Font(bold=True, name="Arial", size=10)
    ws2.column_dimensions["A"].width = 22
    ws2.column_dimensions["B"].width = 28

    wb.save(str(output_path))
    log(f"Fichier Odoo sauvegarde : {output_path.resolve()}", "OK")

import openpyxl
import os
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from datetime import datetime
from models import ReceiptData, ExtractionResult
from typing import List

def generate_petty_cash_log(results: List[ExtractionResult], output_path: str):
    template_path = os.path.join(os.path.dirname(__file__), "petty_cash_template.xlsx")
    if os.path.exists(template_path):
        wb = openpyxl.load_workbook(template_path)
        ws = wb.active
    else:
        # Fallback if template is missing but user is supposed to have uploaded it
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Petty Cash Log"

    bhd_format = '"BHD" #,##0.000'

    # --- Date Sorting Logic ---
    def parse_date(date_str):
        if not date_str: return datetime.max
        try:
            return datetime.strptime(date_str, "%d/%m/%Y")
        except:
            try:
                return datetime.strptime(date_str, "%Y-%m-%d")
            except:
                return datetime.max

    # Filter and Sort results by date
    results_to_process = [r for r in results if r.data]
    results_to_process.sort(key=lambda x: (
        parse_date(x.data.date),
        0 if x.data.description and "Opening balance" in str(x.data.description) else 1
    ))

    # --- Determine the year and date range from the receipt dates ---
    all_parsed_dates = []
    for r in results_to_process:
        if r.data and r.data.date:
            parsed = parse_date(r.data.date)
            if parsed != datetime.max:
                all_parsed_dates.append(parsed)

    if all_parsed_dates:
        min_date = min(all_parsed_dates)
        max_date = max(all_parsed_dates)
        receipt_year = min_date.year
    else:
        min_date = None
        max_date = None
        receipt_year = datetime.now().year  # Fallback if no valid dates

    # 1. Update Headers
    try:
        ws['F1'] = receipt_year
        if min_date and max_date:
            ws['A3'] = f"For {min_date.strftime('%d/%m/%Y')} through {max_date.strftime('%d/%m/%Y')}"
        else:
            ws['A3'] = f"For 01/01/{receipt_year} through 31/12/{receipt_year}"
    except: pass

    # 2. Total Balance (D3)
    current_balance = 0
    for r in results_to_process:
        current_balance += safe_float(r.data.deposit_amount)
        current_balance -= safe_float(r.data.amount)
            
    try:
        ws['D3'] = current_balance
    except: pass

    # 3. Data Rows (Starts at Row 5)
    row_idx = 5
    running_balance = 0
    
    for result in results_to_process:
        if not result.data: continue
        d = result.data
        
        # Add to balance
        dep = safe_float(d.deposit_amount)
        exp = safe_float(d.amount)
        running_balance = running_balance + dep - exp
        
        # VALUES ONLY — Let the template handle alignment/styling
        if d.date: ws.cell(row=row_idx, column=1, value=d.date)
        if d.description: ws.cell(row=row_idx, column=2, value=d.description)
        if dep != 0: ws.cell(row=row_idx, column=3, value=dep)
        if exp != 0: ws.cell(row=row_idx, column=4, value=exp)
        if d.received_by: ws.cell(row=row_idx, column=5, value=d.received_by)
        
        ws.cell(row=row_idx, column=6, value=running_balance)
        ws.cell(row=row_idx, column=7, value=d.remarks or "ok")
        
        row_idx += 1

    # NOTE: No "Total" row added here — the template already has built-in total formulas

    wb.save(output_path)

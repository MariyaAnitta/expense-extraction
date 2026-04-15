import openpyxl
import os
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from datetime import datetime
from models import ReceiptData, ExtractionResult
from typing import List

def generate_petty_cash_log(results: List[ExtractionResult], output_path: str, currency: str = "BHD"):
    template_path = os.path.join(os.path.dirname(__file__), "petty_cash_template.xlsx")
    if os.path.exists(template_path):
        wb = openpyxl.load_workbook(template_path)
        ws = wb.active
        
        # V2 Step D: Programmatic Find & Replace BHD with target currency
        if currency.strip().upper() != "BHD":
            target_curr = currency.strip().upper()
            for row in ws.iter_rows():
                for cell in row:
                    # 1. Surgical string replacement in cell values (headers/titles)
                    if cell.value and isinstance(cell.value, str) and "BHD" in cell.value:
                        cell.value = cell.value.replace("BHD", target_curr)
                    
                    # 2. Surgical number_format replacement (Corruption fix)
                    # We wrap the currency in quotes to ensure Excel treats it as literal text
                    if cell.number_format and "BHD" in cell.number_format:
                        # Find out if BHD was already quoted in the format
                        if f'"{target_curr}"' not in cell.number_format:
                            cell.number_format = cell.number_format.replace("BHD", f'"{target_curr}"')
                        else:
                            cell.number_format = cell.number_format.replace("BHD", target_curr)
    else:
        # Fallback if template is missing
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Petty Cash Log"

    currency_format = f'{currency} #,##0.000'

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

    def safe_float(val):
        if val is None or val == "" or val == "null": return 0.0
        try:
            # Handle cases where currency strings might have commas or extra labels
            s = str(val).replace(currency, '').replace('BHD', '').replace(',', '').strip()
            return float(s)
        except: return 0.0

    # 2. Total Balance (D3)
    current_balance = 0
    for r in results_to_process:
        if not r.data: continue
        current_balance += safe_float(r.data.deposit_amount)
        current_balance -= safe_float(r.data.amount)
            
    try:
        ws['D3'] = current_balance
    except Exception as e:
        print(f"ERROR: Failed to update D3 balance: {e}")

    # 3. Data Rows (Starts at Row 5)
    row_idx = 5
    running_balance = 0
    
    for result in results_to_process:
        try:
            if not result.data: continue
            d = result.data
            
            # Add to balance
            dep = safe_float(d.deposit_amount)
            exp = safe_float(d.amount)
            running_balance = running_balance + dep - exp
            
            # VALUES ONLY — Let the template handle alignment/styling
            # DATE: Use native datetime for Excel to recognize it as a date
            if d.date:
                try:
                    dt = parse_date(d.date)
                    if dt != datetime.max:
                        c_date = ws.cell(row=row_idx, column=1, value=dt)
                        c_date.number_format = 'yyyy-mm-dd' # Match user's prefered display in image
                    else:
                        ws.cell(row=row_idx, column=1, value=str(d.date))
                except:
                    ws.cell(row=row_idx, column=1, value=str(d.date))
            
            desc = d.description or d.category or "Expense"
            ws.cell(row=row_idx, column=2, value=str(desc))
            
            if dep != 0: 
                c = ws.cell(row=row_idx, column=3, value=dep)
                # Apply format only if not already set or specifically needed
                if "0.000" not in (c.number_format or ""):
                    c.number_format = f'"{currency}" #,##0.000'
            if exp != 0: 
                c = ws.cell(row=row_idx, column=4, value=exp)
                if "0.000" not in (c.number_format or ""):
                    c.number_format = f'"{currency}" #,##0.000'
            
            rb = d.received_by or ""
            ws.cell(row=row_idx, column=5, value=str(rb))
            
            c_bal = ws.cell(row=row_idx, column=6, value=running_balance)
            if "0.000" not in (c_bal.number_format or ""):
                c_bal.number_format = f'"{currency}" #,##0.000'
            ws.cell(row=row_idx, column=7, value=str(d.remarks or "ok"))
            
            row_idx += 1
        except Exception as e:
            print(f"ERROR: Failed to process row {row_idx}: {e}")
            continue

    # NOTE: No "Total" row added here — the template already has built-in total formulas

    wb.save(output_path)

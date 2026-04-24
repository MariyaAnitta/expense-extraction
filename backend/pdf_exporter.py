from fpdf import FPDF
from datetime import datetime
from typing import List
from models import ExtractionResult

class PettyCashPDF(FPDF):
    def header(self):
        # Title
        self.set_font('helvetica', 'B', 16)
        self.set_text_color(220, 50, 50) # Red
        self.cell(0, 10, 'Exponential Digital Solutions W.L.L - Petty Cash Log', ln=True, align='L')
        self.ln(2)
        
        # Subheaders will be handled in the main generate function
        
    def footer(self):
        self.set_y(-15)
        self.set_font('helvetica', 'I', 8)
        self.set_text_color(128)
        self.cell(0, 10, f'Page {self.page_no()}/{{nb}}', align='C')

def generate_pdf_log(results: List[ExtractionResult], output_path: str, currency: str = "BHD"):
    pdf = PettyCashPDF(orientation='L', unit='mm', format='A3') # Landscape, A3 for wide table
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    # Process results (Sort by date)
    def parse_date(date_str):
        if not date_str: return datetime.max
        try: return datetime.strptime(date_str, "%d/%m/%Y")
        except:
            try: return datetime.strptime(date_str, "%Y-%m-%d")
            except: return datetime.max

    results_to_process = [r for r in results if r.data]
    results_to_process.sort(key=lambda x: (
        parse_date(x.data.date),
        0 if x.data.description and "Opening balance" in str(x.data.description) else 1
    ))

    # Date Range for header
    all_dates = [parse_date(r.data.date) for r in results_to_process if r.data.date]
    date_range = ""
    if all_dates:
        min_date = min(d for d in all_dates if d != datetime.max)
        max_date = max(d for d in all_dates if d != datetime.max)
        date_range = f"For {min_date.strftime('%d/%m/%Y')} through {max_date.strftime('%d/%m/%Y')}"
        year = min_date.year
    else:
        date_range = "Petty Cash Log"
        year = datetime.now().year

    # Header section
    pdf.set_font('helvetica', '', 10)
    pdf.set_text_color(0)
    pdf.cell(100, 10, date_range, ln=0)
    pdf.set_x(-50)
    pdf.set_fill_color(80, 40, 120) # Purple
    pdf.set_text_color(255)
    pdf.cell(40, 10, f'  {year}', ln=True, fill=True, align='C')
    pdf.ln(5)

    # Table Header
    # Columns: Date, Desc, Cat (Dep/Exp), Orig Amt, Audited, Final, Recv, Balance
    pdf.set_font('helvetica', 'B', 8)
    pdf.set_fill_color(240, 240, 240)
    pdf.set_text_color(0)
    
    # Widths (Total ~400mm for A3 Landscape)
    w = {
        'date': 25,
        'desc': 60,
        'cat': 40,
        'orig': 45,
        'audit': 45,
        'final': 45,
        'rate': 20,
        'recv': 40,
        'bal': 35,
        'rem': 45
    }

    headers = [
        ('Date', w['date']), ('Description', w['desc']), ('Category', w['cat']), 
        ('Original Amt', w['orig']), ('Audited', w['audit']), ('Audit Rate', w['rate']),
        ('Final (Entity)', w['final']), ('Final Rate', w['rate']), ('Recv. By', w['recv']),
        ('Balance', w['bal'])
    ]

    for h, width in headers:
        pdf.cell(width, 10, h, border=1, align='C', fill=True)
    pdf.ln()

    # Data Rows
    pdf.set_font('helvetica', '', 8)
    running_balance = 0
    
    for r in results_to_process:
        d = r.data
        if not d: continue
        
        # Dual-track amounts
        f_amt = float(d.functional_amount if d.functional_amount is not None else d.base_amount or 0)
        is_dep = (d.category == "Deposit")
        running_balance += (f_amt if is_dep else -f_amt)
        
        orig_amt = float(d.deposit_amount if is_dep else d.amount or 0)
        orig_curr = str(d.currency or currency).upper()
        orig_disp = f"{orig_amt:,.3f} {orig_curr}"
        
        target_amt = float(d.base_amount or 0)
        target_curr = str(d.target_currency or currency).upper()
        
        func_curr = str(d.functional_currency or currency).upper()

        # Row Data
        pdf.cell(w['date'], 10, str(d.date or ''), border=1)
        pdf.cell(w['desc'], 10, str(d.description or '')[:35], border=1)
        pdf.cell(w['cat'], 10, str(d.sub_type or d.category or '')[:25], border=1)
        
        # Original (Highlight Deposit vs Expense)
        if is_dep: pdf.set_text_color(0, 150, 0) # Green
        else: pdf.set_text_color(200, 0, 0) # Red
        pdf.cell(w['orig'], 10, orig_disp, border=1, align='R')
        pdf.set_text_color(0)
        
        # Audited
        audit_disp = f"{target_amt:,.3f} {target_curr}" if (orig_curr != target_curr) else ""
        pdf.cell(w['audit'], 10, audit_disp, border=1, align='R')
        pdf.cell(w['rate'], 10, f"{float(d.exchange_rate or 1):.4f}" if audit_disp else "", border=1, align='C')
        
        # Final
        pdf.set_font('helvetica', 'B', 8)
        pdf.cell(w['final'], 10, f"{f_amt:,.3f} {func_curr}", border=1, align='R')
        pdf.set_font('helvetica', '', 8)
        pdf.cell(w['rate'], 10, f"{float(d.functional_rate or 1):.4f}", border=1, align='C')
        
        pdf.cell(w['recv'], 10, str(d.received_by or '')[:20], border=1)
        
        # Balance
        pdf.set_font('helvetica', 'B', 8)
        pdf.cell(w['bal'], 10, f"{running_balance:,.3f}", border=1, align='R')
        pdf.set_font('helvetica', '', 8)
        pdf.ln()

    pdf.output(output_path)

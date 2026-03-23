import os
import sys
import tempfile
import traceback

# Add backend to path so imports work directly
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from firebase_config import db
from models import ExtractionResult, ReceiptData
from excel_exporter import generate_petty_cash_log

try:
    print("Fetching extractions...")
    docs_ref = db.collection('extractions').where('status', '==', 'COMPLETED').stream()
    results = []
    for doc in docs_ref:
        data = doc.to_dict()
        data_payload = data.get('data')
        
        # Need to parse it as ReceiptData
        receipt_data = ReceiptData(**data_payload) if data_payload else None

        res = ExtractionResult(
            file_id=doc.id,
            file_name=data.get('name', ''),
            status=data.get('status', 'COMPLETED'),
            data=receipt_data
        )
        results.append(res)
    print(f"Found {len(results)} results")
    
    temp_excel = tempfile.mktemp(suffix='.xlsx')
    print(f"Writing to {temp_excel}")
    generate_petty_cash_log(results, temp_excel)
    print("SUCCESS")
except Exception as e:
    print("ERROR CAUGHT:")
    traceback.print_exc()

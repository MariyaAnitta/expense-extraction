import os
import time
import tempfile
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from .firebase_config import db, bucket
from .processor import ReceiptProcessor
from .excel_exporter import generate_petty_cash_log
from .models import ExtractionResult, ReceiptData
from dotenv import load_dotenv

# Load from specific backend folder
current_dir = os.path.dirname(os.path.abspath(__file__))
dotenv_path = os.path.join(current_dir, '.env')

if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)
else:
    print(f"ERROR: .env file not found at {dotenv_path}")

app = FastAPI(title="Expense Extraction API")
processor = ReceiptProcessor()

# Setup CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "Expense Extraction Portal API is running"}

import asyncio

async def run_batch_processor():
    """Background task to process all queued/stuck files (Locally stored)"""
    print("Background processor started...")
    # Also fetch stuck 'PROCESSING' items which might be orphaned from previous runs
    docs_ref = db.collection("extractions").where("status", "in", ["QUEUED", "PROCESSING"]).stream()
    
    count = 0
    for doc in docs_ref:
        doc_id = doc.id
        data = doc.to_dict()
        file_name = data.get("name")
        local_path = data.get("local_path")
        
        if not local_path or not os.path.exists(local_path):
            print(f"File not found on disk: {local_path}. Marking as FAILED.")
            db.collection("extractions").document(doc_id).update({
                "status": "FAILED", 
                "error": "Local file not found. Please upload again."
            })
            continue
        
        print(f"Processing {file_name} from disk...")
        db.collection("extractions").document(doc_id).update({"status": "PROCESSING"})
        
        try:
            # 3. Process directly from disk
            result = processor.process_file(local_path)
            
            # 4. Update Firestore
            update_data = {
                "status": result.status,
                "confidence": result.data.confidence if result.data else 0,
                "data": result.data.model_dump() if result.data else None,
                "error": result.error
            }
            db.collection("extractions").document(doc_id).update(update_data)
        except Exception as e:
            print(f"Error processing {file_name}: {e}")
            db.collection("extractions").document(doc_id).update({"status": "FAILED", "error": str(e)})
        
        count += 1
        await asyncio.sleep(5)
    
    print(f"Batch processing completed. Total files: {count}")

@app.post("/upload-batch")
async def upload_batch(files: List[UploadFile] = File(...)):
    """Save multiple files to LOCAL storage and create queue records"""
    uploaded_ids = []
    print(f"Received local batch upload: {len(files)} files")
    
    # Ensure uploads dir exists
    uploads_dir = os.path.join(os.path.dirname(__file__), "uploads")
    os.makedirs(uploads_dir, exist_ok=True)
    
    try:
        for file in files:
            # 1. Create a Firestore record (Metadata only)
            doc_ref = db.collection("extractions").add({
                "name": file.filename,
                "status": "QUEUED",
                "upload_time": time.time(),
                "data": None
            })
            doc_id = doc_ref[1].id
            
            # 2. Save locally
            safe_filename = os.path.basename(file.filename)
            file_dir = os.path.join(uploads_dir, doc_id)
            os.makedirs(file_dir, exist_ok=True)
            local_path = os.path.join(file_dir, safe_filename)
            
            with open(local_path, "wb") as f:
                content = await file.read()
                f.write(content)
            
            # 3. Update Firestore with local path
            db.collection("extractions").document(doc_id).update({
                "local_path": local_path
            })
            uploaded_ids.append(doc_id)
            
        print(f"Local batch upload success: {len(uploaded_ids)} files")
        return {"status": "success", "count": len(uploaded_ids), "ids": uploaded_ids}
    except Exception as e:
        print(f"Upload error: {e}")
        return {"status": "error", "message": str(e)}

@app.post("/clear-queue")
async def clear_queue():
    """Clear all records from the extractions collection"""
    try:
        docs = db.collection("extractions").stream()
        deleted_count = 0
        for doc in docs:
            # Delete record
            db.collection("extractions").document(doc.id).delete()
            # Note: For full production, you'd also delete the file in Storage here
            deleted_count += 1
        return {"status": "success", "deleted_count": deleted_count}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.delete("/delete-extraction/{doc_id}")
async def delete_extraction(doc_id: str):
    """Delete a specific record from the extractions collection"""
    try:
        # Note: You can add logic here to remove the file from storage if needed
        db.collection("extractions").document(doc_id).delete()
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/files/{doc_id}")
async def get_file(doc_id: str):
    """Serve the local file for the frontend preview"""
    doc = db.collection("extractions").document(doc_id).get()
    if not doc.exists:
        return {"error": "Document not found"}
    
    data = doc.to_dict()
    local_path = data.get("local_path")
    
    if not local_path or not os.path.exists(local_path):
        return {"error": "File not found on disk"}
    
    # Correct media type based on extension
    ext = os.path.splitext(local_path)[1].lower()
    media_types = {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".msg": "application/vnd.ms-outlook"
    }
    
    return FileResponse(local_path, media_type=media_types.get(ext, "application/octet-stream"))

@app.post("/update-extraction/{doc_id}")
async def update_extraction(doc_id: str, data: ReceiptData):
    """Manually update extraction data (Confirm Details)"""
    try:
        db.collection("extractions").document(doc_id).update({
            "data": data.model_dump(),
            "status": "COMPLETED",
            "is_verified": True
        })
        print(f"Extraction {doc_id} manually verified and completed.")
        return {"status": "success"}
    except Exception as e:
        print(f"Error updating extraction {doc_id}: {e}")
        return {"status": "error", "message": str(e)}

@app.post("/add-manual")
async def add_manual(data: Optional[ReceiptData] = None):
    """Create a manual entry for accounting, either from default or from frontend draft."""
    try:
        if data:
            data_dict = data.dict()
        else:
            data_dict = {
                "date": datetime.now().strftime("%Y-%m-%d"),
                "description": "Opening balance B/F",
                "amount": None,
                "deposit_amount": None,
                "currency": "BHD",
                "received_by": "",
                "transaction_no": "MANUAL",
                "category": "Deposit",
                "remarks": "ok",
                "confidence": 100.0
            }
            
        doc_ref = db.collection("extractions").add({
            "name": "Manual Entry",
            "status": "COMPLETED",
            "data": data_dict,
            "upload_time": time.time(),
            "local_path": None, # No file for manual entries
            "is_verified": True
        })
        return {"status": "success", "id": doc_ref[1].id}
    except Exception as e:
        print(f"Error adding manual entry: {e}")
        return {"status": "error", "message": str(e)}

@app.post("/process-batch")
async def process_batch(background_tasks: BackgroundTasks):
    background_tasks.add_task(run_batch_processor)
    return {"status": "batch_processing_triggered"}

@app.get("/export-excel")
async def export_excel():
    try:
        # Fetch COMPLETED results
        docs_ref = db.collection("extractions").where("status", "==", "COMPLETED").stream()
        results = []
        for doc in docs_ref:
            data = doc.to_dict()
            # Create an ExtractionResult object for the exporter
            res = ExtractionResult(
                file_id=doc.id,
                file_name=data.get("name", "Unknown File"),
                status=data.get("status", "COMPLETED"),
                data=data.get("data")
            )
            results.append(res)
        
        if not results:
            return {"error": "No completed extractions to export"}
            
        temp_excel = tempfile.mktemp(suffix=".xlsx")
        generate_petty_cash_log(results, temp_excel)
        
        return FileResponse(
            temp_excel,
            media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            filename=f"Petty_Cash_Log_{time.strftime('%Y%m%d_%H%M%S')}.xlsx"
        )
    except Exception as e:
        import traceback
        error_msg = traceback.format_exc()
        print("INTERNAL ERROR EXPORTING EXCEL:")
        print(error_msg)
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=500, content={"error": str(e), "traceback": error_msg})

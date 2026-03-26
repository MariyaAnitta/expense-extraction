import os
from datetime import datetime
import time
import tempfile
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from firebase_config import db, bucket
from processor import ReceiptProcessor
from excel_exporter import generate_petty_cash_log
from models import ExtractionResult, ReceiptData
from dotenv import load_dotenv
from supabase import create_client, Client

# Load from specific backend folder
current_dir = os.path.dirname(os.path.abspath(__file__))
dotenv_path = os.path.join(current_dir, '.env')

if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)
else:
    print(f"ERROR: .env file not found at {dotenv_path}")

# Initialize Supabase
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")
supabase: Optional[Client] = None

if supabase_url and supabase_key:
    try:
        supabase = create_client(supabase_url, supabase_key)
        print("Supabase connected successfully")
    except Exception as e:
        print(f"Supabase Connection Failed: {e}")
else:
    print("WARNING: SUPABASE_URL or SUPABASE_KEY missing in .env")

app = FastAPI(title="Expense Extraction API")
processor = ReceiptProcessor()

# Setup CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi import Request
from fastapi.responses import JSONResponse

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    print(f"GLOBAL ERROR: {exc}")
    # Always return CORS headers manually if needed, 
    # but FastAPI's CORSMiddleware should handle this if we return a JSONResponse
    return JSONResponse(
        status_code=500,
        content={"status": "error", "message": str(exc)},
    )

@app.get("/")
async def root():
    return {"message": "Expense Extraction Portal API is running"}

@app.get("/debug-supabase")
async def debug_supabase():
    if not supabase:
        return {"status": "error", "message": "Supabase client not initialized. Check ENV vars."}
    try:
        # Test connection by listing buckets
        buckets = supabase.storage.list_buckets()
        bucket_exists = any(b.name == "receipts" for b in buckets)
        return {
            "status": "connected",
            "bucket_found": bucket_exists,
            "buckets": [b.name for b in buckets],
            "supabase_url": supabase_url[:15] + "..." # Partial for security
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

import asyncio

async def run_batch_processor():
    """Background task to process queued files (Local Disk -> Extract -> Delete)"""
    print("Zero-Bucket Background processor started...")
    docs_ref = db.collection("extractions").where("status", "in", ["QUEUED", "PROCESSING", "FAILED"]).stream()
    
    count = 0
    for doc in docs_ref:
        doc_id = doc.id
        data = doc.to_dict()
        file_name = data.get("name")
        temp_path = data.get("temp_local_path")
        
        if not temp_path or not os.path.exists(temp_path):
            print(f"No file found for processing {file_name}. Skipping.")
            db.collection("extractions").document(doc_id).update({"status": "FAILED", "error": "File already cleared from temporary memory."})
            continue

        try:
            print(f"Processing {file_name}...")
            db.collection("extractions").document(doc_id).update({"status": "PROCESSING"})
            
            # 1. Process the AI Extraction
            result = processor.process_file(temp_path)
            
            # 2. Upload to Supabase for permanent viewing (if successful)
            image_url = None
            if result.status in ["COMPLETED", "AMBER"] and supabase:
                try:
                    import mimetypes
                    mime_type, _ = mimetypes.guess_type(file_name)
                    if not mime_type:
                        mime_type = "application/octet-stream"
                    
                    # Fix: Directly use filename (no redundant receipts/ prefix)
                    target_path = f"{int(time.time())}_{file_name}"
                    with open(temp_path, "rb") as f:
                        upload_res = supabase.storage.from_("receipts").upload(
                            target_path, 
                            f.read(),
                            file_options={"content-type": mime_type}
                        )
                        print(f"Supabase Response: {upload_res}")
                    
                    # Get public URL
                    res = supabase.storage.from_("receipts").get_public_url(target_path)
                    image_url = str(res) # Ensure it's a string
                    print(f"Supabase Upload Success: {image_url}")
                except Exception as upload_err:
                    print(f"Supabase Upload Failed for {file_name}: {upload_err}")
            
            # 3. Update Firestore with all data + the new image_url
            update_data = {
                "status": result.status,
                "confidence": result.data.confidence if result.data else 0,
                "data": result.data.model_dump() if result.data else None,
                "error": result.error,
                "image_url": image_url,
                "temp_local_path": None # Clear from DB
            }
            db.collection("extractions").document(doc_id).update(update_data)
            
            # 4. Cleanup: DELETE the local file from Render disk (Only if not FAILED)
            if result.status != "FAILED" and os.path.exists(temp_path):
                os.remove(temp_path)
                print(f"SUCCESS: Result saved and temp file deleted for {file_name}")
            elif result.status == "FAILED":
                print(f"WARNING: Extraction FAILED for {file_name}. Preserving local file for retry.")
                
        except Exception as e:
            print(f"Error processing {file_name}: {e}")
            db.collection("extractions").document(doc_id).update({"status": "FAILED", "error": str(e)})
        
        count += 1
        await asyncio.sleep(5)
    
    print(f"Zero-Bucket batch task finished. Total: {count}")

@app.post("/upload-batch")
async def upload_batch(files: List[UploadFile] = File(...)):
    """Save multiple files to TEMPORARY local storage for processing"""
    uploaded_ids = []
    print(f"DEBUG: Processing batch upload in Zero-Bucket mode: {len(files)} files")
    
    # Use a temporary folder on the local disk (ephemeral on Render)
    uploads_dir = os.path.join(tempfile.gettempdir(), "receipt_uploads")
    os.makedirs(uploads_dir, exist_ok=True)
    
    try:
        for file in files:
            # 1. Create a Firestore record
            doc_ref = db.collection("extractions").add({
                "name": os.path.basename(file.filename),
                "status": "QUEUED",
                "upload_time": time.time(),
                "data": None
            })
            doc_id = doc_ref[1].id
            
            # 2. Save locally (Temporary)
            content = await file.read()
            # Ensure safe filename (remove subdirectories)
            safe_filename = os.path.basename(file.filename)
            local_path = os.path.join(uploads_dir, f"{doc_id}_{safe_filename}")
            
            with open(local_path, "wb") as f:
                f.write(content)
                
            # 3. Update Firestore (NO STORAGE PATH)
            db.collection("extractions").document(doc_id).update({
                "temp_local_path": local_path
            })
            uploaded_ids.append(doc_id)
            
        return {"status": "success", "count": len(uploaded_ids), "ids": uploaded_ids}
    except Exception as e:
        print(f"DEBUG ERROR during upload: {e}")
        return {"status": "error", "message": str(e)}

from fastapi import Header
import base64
import mimetypes

@app.post("/upload-automation")
async def upload_automation(request: Request, background_tasks: BackgroundTasks, x_filename: str = Header(None)):
    """Special endpoint for Power Automate to send raw binary OR Base64 JSON."""
    try:
        content_type = request.headers.get("Content-Type", "")
        
        if "application/json" in content_type:
            # Case 1: JSON with Base64 Content
            data = await request.json()
            filename = data.get("filename") or x_filename or f"Teams_Upload_{int(time.time())}"
            base64_file = data.get("file")
            if not base64_file:
                return {"status": "error", "message": "JSON body must have 'file' key with base64 string"}
            content = base64.b64decode(base64_file)
            print(f"DEBUG: Processing base64 automation upload: {filename}")
        else:
            # Case 2: Raw Binary
            filename = x_filename or f"Teams_Upload_{int(time.time())}"
            content = await request.body()
            print(f"DEBUG: Processing raw binary automation upload: {filename}")
            
        if not content:
            return {"status": "error", "message": "File content is empty"}

        # --- SMART EXTENSION FIX: Inspect magic bytes ---
        if "." not in filename:
            # Default to .jpg
            real_ext = ".jpg"
            if content.startswith(b"%PDF-"):
                real_ext = ".pdf"
            elif content.startswith(b"\x89PNG\r\n\x1a\n"):
                real_ext = ".png"
            elif content.startswith(b"\xff\xd8\xff"):
                real_ext = ".jpg"
            elif content.startswith(b"PK\x03\x04"): # Office files (DOCX/XLSX)
                real_ext = ".docx" # Simple default for zip-based office files
            
            filename += real_ext
            print(f"Inferred real extension from bytes: {filename}")

        # 2. Create a Firestore record
        doc_ref = db.collection("extractions").add({
            "name": filename,
            "status": "QUEUED",
            "upload_time": time.time(),
            "data": None
        })
        doc_id = doc_ref[1].id
        
        # 3. Save locally (Temporary)
        uploads_dir = os.path.join(tempfile.gettempdir(), "receipt_uploads")
        os.makedirs(uploads_dir, exist_ok=True)
        local_path = os.path.join(uploads_dir, f"{doc_id}_{filename}")
        
        with open(local_path, "wb") as f:
            f.write(content)
            
        # 4. Update Firestore
        db.collection("extractions").document(doc_id).update({
            "temp_local_path": local_path
        })

        # 5. AUTO-TRIGGER the AI processor
        background_tasks.add_task(run_batch_processor)
            
        return {
            "status": "success", 
            "id": doc_id, 
            "message": "File received and AI processing started automatically."
        }
    except Exception as e:
        print(f"DEBUG ERROR during automation upload: {e}")
        return {"status": "error", "message": str(e)}

@app.post("/clear-queue")
async def clear_queue():
    """Clear all records and files from storage"""
    try:
        docs = db.collection("extractions").stream()
        deleted_count = 0
        for doc in docs:
            data = doc.to_dict()
            # Delete from Storage
            storage_path = data.get("storage_path")
            if storage_path:
                try:
                    bucket.blob(storage_path).delete()
                except:
                    pass
            # Delete record
            db.collection("extractions").document(doc.id).delete()
            deleted_count += 1
        return {"status": "success", "deleted_count": deleted_count}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.delete("/delete-extraction/{doc_id}")
async def delete_extraction(doc_id: str):
    """Delete a specific record and its file from storage"""
    try:
        doc = db.collection("extractions").document(doc_id).get()
        if doc.exists:
            data = doc.to_dict()
            storage_path = data.get("storage_path")
            if storage_path:
                try:
                    bucket.blob(storage_path).delete()
                except:
                    pass
            db.collection("extractions").document(doc_id).delete()
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/files/{doc_id}")
async def get_file(doc_id: str):
    """Placeholder for file preview in Zero-Bucket mode"""
    return {"message": "Preview disabled in Zero-Bucket Free Mode to avoid storage costs. All extracted data is shown on the right."}

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
        # Fetch ONLY COMPLETED and VERIFIED results
        docs_ref = db.collection("extractions")\
            .where("status", "in", ["COMPLETED", "AMBER"])\
            .where("is_verified", "==", True)\
            .stream()
        
        results = []
        for doc in docs_ref:
            data = doc.to_dict()
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

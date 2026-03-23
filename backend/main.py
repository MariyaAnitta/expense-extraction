import os
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
    """Background task to process all queued files using Firebase Storage"""
    print("Background processor started...")
    docs_ref = db.collection("extractions").where("status", "in", ["QUEUED", "PROCESSING"]).stream()
    
    count = 0
    for doc in docs_ref:
        doc_id = doc.id
        data = doc.to_dict()
        file_name = data.get("name")
        storage_path = data.get("storage_path")
        local_path = None
        
        try:
            if not storage_path:
                # Fallback for old records if any
                fallback_path = data.get("local_path")
                if not fallback_path or not os.path.exists(fallback_path):
                    print(f"No valid file found for {file_name}. Marking as FAILED.")
                    db.collection("extractions").document(doc_id).update({"status": "FAILED", "error": "File not found."})
                    continue
                local_path = fallback_path
            else:
                # Download from Firebase Storage to a temp file
                suffix = os.path.splitext(file_name)[1]
                fd, local_path = tempfile.mkstemp(suffix=suffix)
                os.close(fd)
                blob = bucket.blob(storage_path)
                blob.download_to_filename(local_path)
                print(f"Downloaded {file_name} from Storage to {local_path}")

            print(f"Processing {file_name}...")
            db.collection("extractions").document(doc_id).update({"status": "PROCESSING"})
            
            # Process the file (temp local path)
            result = processor.process_file(local_path)
            
            # Update Firestore
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
        finally:
            # Clean up temp file if we created one
            if storage_path and local_path and os.path.exists(local_path):
                try:
                    os.remove(local_path)
                    print(f"Cleaned up temp file: {local_path}")
                except Exception as ex:
                    print(f"Failed to delete temp file {local_path}: {ex}")
        
        count += 1
        await asyncio.sleep(5)
    
    print(f"Batch processing completed. Total files: {count}")

@app.post("/upload-batch")
async def upload_batch(files: List[UploadFile] = File(...)):
    """Save multiple files to FIREBASE storage and create queue records"""
    uploaded_ids = []
    print(f"DEBUG: Received batch upload to Firebase: {len(files)} files")
    
    try:
        for file in files:
            # 1. Create a Firestore record
            doc_ref = db.collection("extractions").add({
                "name": file.filename,
                "status": "QUEUED",
                "upload_time": time.time(),
                "data": None
            })
            doc_id = doc_ref[1].id
            print(f"DEBUG: Created Firestore record doc_id={doc_id} for {file.filename}")
            
            # 2. Save to Firebase Storage
            content = await file.read()
            blob_path = f"uploads/{doc_id}/{file.filename}"
            print(f"DEBUG: Uploading to Firebase Storage blob_path={blob_path}")
            blob = bucket.blob(blob_path)
            blob.upload_from_string(content, content_type=file.content_type)
            print(f"DEBUG: Firebase Storage Upload SUCCESS for {blob_path}")
            
            # 3. Update Firestore with storage path
            db.collection("extractions").document(doc_id).update({
                "storage_path": blob_path,
                "content_type": file.content_type
            })
            print(f"DEBUG: Firestore updated with storage_path={blob_path}")
            uploaded_ids.append(doc_id)
            
        print(f"DEBUG: Final uploaded_ids={uploaded_ids}")
        return {"status": "success", "count": len(uploaded_ids), "ids": uploaded_ids}
    except Exception as e:
        print(f"DEBUG ERROR during upload_batch: {e}")
        import traceback
        traceback.print_exc()
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
    """Serve the file from Firebase Storage for the frontend preview"""
    import io
    from fastapi.responses import StreamingResponse
    
    doc = db.collection("extractions").document(doc_id).get()
    if not doc.exists:
        return {"error": "Document not found"}
    
    data = doc.to_dict()
    storage_path = data.get("storage_path")
    content_type = data.get("content_type", "application/octet-stream")
    
    if not storage_path:
        return {"error": "File path not found in database"}
    
    try:
        blob = bucket.blob(storage_path)
        # Download content to memory
        content = blob.download_as_bytes()
        return StreamingResponse(io.BytesIO(content), media_type=content_type)
    except Exception as e:
        print(f"Error fetching from static storage: {e}")
        return {"error": f"Failed to fetch file: {str(e)}"}

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

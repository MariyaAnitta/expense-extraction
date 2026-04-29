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
from pdf_exporter import generate_pdf_log
from models import ExtractionResult, ReceiptData, ZohoConfig
from zoho_client import ZohoClient
from dotenv import load_dotenv
from supabase import create_client, Client
import httpx

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

from fastapi import Request, Form
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

from fastapi.responses import HTMLResponse

@app.get("/", response_class=HTMLResponse)
async def root():
    return """
    <!DOCTYPE html>
    <html>
        <head>
            <meta name="google-site-verification" content="ruy31GLsjKSOAbHT2rqLVYNvKJZi6O60MhOjAKjZdLI" />
            <title>Expense Extraction API</title>
        </head>
        <body>
            <h1>Expense Extraction Portal API is running</h1>
            <p>Google Drive Webhook Integration Active</p>
        </body>
    </html>
    """

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

def get_entity_data(entity_id: str) -> dict:
    """Fetch entity configuration including base and active currency portfolio"""
    defaults = {"base": "BHD", "active": ["BHD", "USD", "SAR", "INR"]}
    if not entity_id or entity_id == "default":
        return defaults
    try:
        doc = db.collection("entities").document(entity_id).get()
        if doc.exists:
            d = doc.to_dict()
            return {
                "base": d.get("currency", "BHD"),
                "active": d.get("active_currencies") or [d.get("currency", "BHD"), "USD", "SAR", "INR"]
            }
    except Exception as e:
        print(f"Error fetching entity data: {e}")
    return defaults

def get_entity_currency(entity_id: str) -> str:
    """Legacy helper for backward compatibility - returns base currency"""
    return get_entity_data(entity_id)["base"]

@app.post("/update-entity-portfolio")
async def update_entity_portfolio(entity_id: str, active_currencies: List[str]):
    try:
        active_currencies = [c.upper() for c in active_currencies if c]
        db.collection("entities").document(entity_id).update({
            "active_currencies": active_currencies
        })
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/update-user-portfolio")
async def update_user_portfolio(user_id: str, active_currencies: List[str]):
    try:
        active_currencies = [c.upper() for c in active_currencies if c]
        db.collection("users").document(user_id).update({
            "personal_currencies": active_currencies
        })
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

async def get_exchange_rate(from_curr: str, to_curr: str) -> float:
    """Fetch live exchange rate from API"""
    if not from_curr or not to_curr or from_curr.upper() == to_curr.upper():
        return 1.0
    try:
        url = f"https://api.exchangerate-api.com/v4/latest/{from_curr.upper()}"
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=5)
            if response.status_code == 200:
                rates = response.json().get("rates", {})
                return float(rates.get(to_curr.upper(), 1.0))
    except Exception as e:
        print(f"FX API Error ({from_curr}->{to_curr}): {e}")
    return 1.0

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
            # 0. V2: Fetch entity currency for AI Hint
            hint_currency = "BHD"
            uid = data.get("user_id")
            team_id = data.get("team_id", "General")
            
            # Logic: If user exists, use their entity. 
            # If it's automation, use the team leader's entity.
            target_ent_id = None
            if uid and uid != "automation":
                user_doc = db.collection("users").document(uid).get()
                if user_doc.exists:
                    target_ent_id = user_doc.to_dict().get("entity_id")
            
            if not target_ent_id or target_ent_id == "default":
                # Automation or user without entity: try to find a leader for this team
                leaders = db.collection("users").where("team_id", "==", team_id.lower()).where("role", "==", "leader").limit(1).stream()
                for l in leaders:
                    target_ent_id = l.to_dict().get("entity_id")
                    break
            
            if target_ent_id and target_ent_id != "default":
                ent_doc = db.collection("entities").document(target_ent_id).get()
                if ent_doc.exists:
                    hint_currency = ent_doc.to_dict().get("currency", "BHD")

            # 0.5 V3: Fetch Dynamic Categories for AI Taxonomy (Scoping by Team)
            dynamic_cats = []
            try:
                team_id = data.get("team_id", "General")
                # Query global OR specific team categories
                cat_docs = db.collection("categories").where("team_id", "in", ["global", team_id]).stream()
                dynamic_cats = [c.to_dict().get("name") for c in cat_docs if c.to_dict().get("name")]
            except Exception as cat_err:
                print(f"Warning: Failed to fetch dynamic categories: {cat_err}")

            # 1. Process the AI Extraction
            result = processor.process_file(temp_path, currency=hint_currency, dynamic_categories=dynamic_cats)
            
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
            
            # 3. FX Calculation: Convert extracted currency to Entity Base Currency
            # Ensure we use the correct entity_id resolved earlier OR fallback to document's entity_id
            final_ent_id = target_ent_id or data.get("entity_id") or "default"
            target_currency = get_entity_currency(final_ent_id)
            rate = 1.0
            base_amount = 0.0
            
            if result.data:
                orig_currency = result.data.currency or target_currency
                rate = await get_exchange_rate(orig_currency, target_currency)
                
                # Calculate base amount (Target Audit)
                orig_amount = 0.0
                try:
                    if result.data.category == "Deposit":
                        orig_amount = float(result.data.deposit_amount or 0)
                    else:
                        orig_amount = float(result.data.amount or 0)
                except:
                    pass
                
                # Dual-Track FX: 
                # 1. Target (User Audit Choice)
                result.data.exchange_rate = rate
                result.data.base_amount = orig_amount * rate
                result.data.target_currency = target_currency
                
                # 2. Functional (Entity Standard - e.g. INR)
                # For initial AI extraction, functional usually matches target unless target is manually overridden later
                result.data.functional_currency = target_currency 
                result.data.functional_rate = rate
                result.data.functional_amount = orig_amount * rate
            
            # 4. Update Firestore with all data + image_url + FX data
            update_data = {
                "status": result.status,
                "confidence": result.data.confidence if result.data else 0,
                "data": result.data.model_dump() if result.data else None,
                "error": result.error,
                "image_url": image_url,
                "temp_local_path": None 
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
        await asyncio.sleep(1)
    
    print(f"Zero-Bucket batch task finished. Total: {count}")

@app.post("/upload-batch")
async def upload_batch(
    background_tasks: BackgroundTasks, 
    files: List[UploadFile] = File(...),
    user_id: str = Form("unknown"),
    team_id: str = Form("General"),
    entity_id: str = Form("default")
):
    """Save multiple files to TEMPORARY local storage for processing"""
    uploaded_ids = []
    print(f"DEBUG: Processing batch upload for user {user_id} in team {team_id}")
    
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
                "user_id": user_id,
                "team_id": team_id,
                "entity_id": entity_id,
                "is_verified": False,
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
            
        # --- AUTO-TRIGGER DISABLED FOR WEB UPLOADS PER USER REQUEST ---
        # background_tasks.add_task(run_batch_processor)
            
        return {"status": "success", "count": len(uploaded_ids), "ids": uploaded_ids}
    except Exception as e:
        print(f"DEBUG ERROR during upload: {e}")
        return {"status": "error", "message": str(e)}

from fastapi import Header
import base64
import mimetypes

@app.post("/upload-automation")
async def upload_automation(
    request: Request, 
    background_tasks: BackgroundTasks, 
    x_filename: str = Header(None),
    x_team_id: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None),
    x_entity_id: Optional[str] = Header(None)
):
    """Special endpoint for Power Automate to send raw binary OR Base64 JSON."""
    try:
        content_type = request.headers.get("Content-Type", "")
        
        # Use headers if provided, otherwise default to generic automation
        team_id = x_team_id or "Global"
        user_id = x_user_id or "automation"
        entity_id = x_entity_id or "default"
        
        if "application/json" in content_type:
            # Case 1: JSON with Base64 Content
            data = await request.json()
            filename = data.get("filename") or x_filename or f"Teams_Upload_{int(time.time())}"
            base64_file = data.get("file")
            
            # Allow JSON body to override headers if needed
            team_id = data.get("team_id") or team_id
            user_id = data.get("user_id") or user_id
            entity_id = data.get("entity_id") or entity_id
            
            if not base64_file:
                return {"status": "error", "message": "JSON body must have 'file' key with base64 string"}
            content = base64.b64decode(base64_file)
            print(f"DEBUG: Processing base64 automation upload: {filename} for team: {team_id}")
        else:
            # Case 2: Raw Binary
            filename = x_filename or f"Teams_Upload_{int(time.time())}"
            content = await request.body()
            print(f"DEBUG: Processing raw binary automation upload: {filename} for team: {team_id}")
            
        if not content:
            return {"status": "error", "message": "File content is empty"}

        # --- SMART EXTENSION FIX: Inspect magic bytes ---
        # Fixed: Check for actual file extension at the end (dots in mid-filename shouldn't fool us)
        supported_extensions = ('.pdf', '.jpg', '.jpeg', '.png', '.docx', '.xlsx', '.msg')
        if not filename.lower().endswith(supported_extensions):
            # Default to .jpg
            real_ext = ".jpg"
            if content.startswith(b"%PDF-"):
                real_ext = ".pdf"
            elif content.startswith(b"\x89PNG\r\n\x1a\n"):
                real_ext = ".png"
            elif content.startswith(b"\xff\xd8\xff"):
                real_ext = ".jpg"
            elif content.startswith(b"PK\x03\x04"): # Office files (DOCX/XLSX)
                real_ext = ".docx" 
            
            filename += real_ext
            print(f"Inferred real extension from bytes: {filename}")

        # 2. Create a Firestore record
        doc_ref = db.collection("extractions").add({
            "name": filename,
            "status": "QUEUED",
            "upload_time": time.time(),
            "user_id": user_id,
            "team_id": team_id,
            "entity_id": entity_id,
            "is_verified": False,
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
async def clear_queue(team_id: Optional[str] = None, user_id: Optional[str] = None):
    """
    Carefully scoped clearing:
    - If user_id is provided, only clear that user's data.
    - If only team_id is provided, clear all team data (use with caution).
    """
    try:
        query = db.collection("extractions")
        if user_id:
            docs = query.where("user_id", "==", user_id).stream()
        elif team_id:
            docs = query.where("team_id", "==", team_id.lower()).stream()
        else:
            return {"status": "error", "message": "No scope (team_id or user_id) provided"}

        deleted_count = 0
        for doc in docs:
            data = doc.to_dict()
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
async def update_extraction(doc_id: str, data: ReceiptData, role: str = "user"):
    """Manually update extraction data (Confirm Details)"""
    try:
        update_dict = {
            "data": data.model_dump(),
            "status": "COMPLETED"
        }
        
        # Two-step Verification Logic:
        # is_verified is the GLOBAL gate for Excel exports.
        # Only leaders and admins can set it to True.
        
        if role in ["leader", "admin"]:
            update_dict["is_verified"] = True
            update_dict["leader_verified"] = True
            update_dict["user_verified"] = True
        else:
            # General User or Admin confirm-only
            update_dict["user_verified"] = True
            update_dict["is_verified"] = False # explicitly keep it false until Leader checks
            
        db.collection("extractions").document(doc_id).update(update_dict)
        print(f"Extraction {doc_id} manually verified and completed.")
        return {"status": "success"}
    except Exception as e:
        print(f"Error updating extraction {doc_id}: {e}")
        return {"status": "error", "message": str(e)}

@app.post("/add-manual")
async def add_manual(data: Optional[ReceiptData] = None, user_id: Optional[str] = None, team_id: Optional[str] = None, role: str = "user"):
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
                "currency": "BHD", # Will be updated below
                "received_by": "",
                "transaction_no": "MANUAL",
                "category": "Deposit",
                "remarks": "ok",
                "confidence": 100.0
            }
            
        # V2/V4 Fix: Inherit currency and entity from the office if it's a manual entry
        uid_for_ent = user_id or "unknown"
        inherited_entity_id = "default"
        target_currency = "BHD"
        
        if uid_for_ent != "unknown":
            u_doc = db.collection("users").document(uid_for_ent).get()
            if u_doc.exists:
                e_id = u_doc.to_dict().get("entity_id")
                if e_id and e_id != "default":
                    inherited_entity_id = e_id
                    target_currency = get_entity_currency(e_id)
                    if not data: # Only set default currency if it's a blank manual entry
                        data_dict["currency"] = target_currency

        # V4: Fill FX data for manual entries
        orig_currency = data_dict.get("currency", target_currency)
        data_dict["target_currency"] = target_currency
        data_dict["functional_currency"] = target_currency # Default entity functional to target initially
        
        # If the user didn't provide a rate, fetch it
        if not data_dict.get("exchange_rate") or data_dict.get("exchange_rate") == 1.0:
            data_dict["exchange_rate"] = await get_exchange_rate(orig_currency, target_currency)
        
        # Dual-Track: Functional rate (usually same as target rate for manual entry unless overridden)
        data_dict["functional_rate"] = data_dict.get("functional_rate") or data_dict["exchange_rate"]
        
        # Calculate amounts
        try:
            orig_amt = float(data_dict.get("deposit_amount") or data_dict.get("amount") or 0)
            data_dict["base_amount"] = orig_amt * data_dict["exchange_rate"]
            data_dict["functional_amount"] = orig_amt * data_dict["functional_rate"]
        except:
            data_dict["base_amount"] = 0.0
            data_dict["functional_amount"] = 0.0

        doc_ref = db.collection("extractions").add({
            "name": data_dict.get("description", "Manual Entry") if data else "Manual Entry",
            "status": "COMPLETED",
            "data": data_dict,
            "upload_time": time.time(),
            "local_path": None, # No file for manual entries
            "is_verified": True if role == "leader" else False,
            "user_verified": True,
            "leader_verified": True if role == "leader" else False,
            "admin_verified": True if role == "admin" else False,
                "user_id": user_id,
                "team_id": team_id,
                "entity_id": inherited_entity_id
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
async def export_excel(team_id: Optional[str] = None, user_id: Optional[str] = None, currency: Optional[str] = None):
    try:
        # Build query for COMPLETED and VERIFIED results
        docs_ref_query = db.collection("extractions")\
            .where("status", "in", ["COMPLETED", "AMBER"])\
            .where("is_verified", "==", True)
            
        # Apply role-based filters if provided
        if user_id and team_id:
            # Personal + Automation: fetch by team, then JS-filter for user + automation
            docs_ref_query = docs_ref_query.where("team_id", "==", team_id)
            docs_ref = docs_ref_query.stream()
            results = []
            for doc in docs_ref:
                data = doc.to_dict()
                if data.get("user_id") == user_id or data.get("user_id") == "automation":
                    res = ExtractionResult(
                        file_id=doc.id,
                        file_name=data.get("name", "Unknown File"),
                        status=data.get("status", "COMPLETED"),
                        data=data.get("data")
                    )
                    results.append(res)
        elif team_id:
            docs_ref_query = docs_ref_query.where("team_id", "==", team_id)
            docs_ref = docs_ref_query.stream()
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
        elif user_id:
            docs_ref_query = docs_ref_query.where("user_id", "==", user_id)
            docs_ref = docs_ref_query.stream()
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
        else:
            docs_ref = docs_ref_query.stream()
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
            
        # V2/V4: Strategic Currency Resolution
        # 1. Start with provided currency if valid
        target_currency = currency.strip().upper() if (currency and currency.strip()) else None
        
        # 2. If no currency provided, resolve from the entity of the first result
        if not target_currency and results:
            for r in results[:10]: # Check first few to find an entity_id
                # Note: r is an ExtractionResult object
                ex_doc = db.collection("extractions").document(r.file_id).get()
                if ex_doc.exists:
                    e_id = ex_doc.to_dict().get("entity_id")
                    if e_id and e_id != "default":
                        target_currency = get_entity_currency(e_id)
                        break
        
        # 3. Fallback to lookup based on user or team
        if not target_currency:
            lookup_uid = user_id
            if not lookup_uid and team_id:
                leaders = db.collection("users").where("team_id", "==", team_id.lower()).where("role", "==", "leader").limit(1).stream()
                for l in leaders:
                    lookup_uid = l.id
                    break
            
            if lookup_uid:
                u_doc = db.collection("users").document(lookup_uid).get()
                if u_doc.exists:
                    e_id = u_doc.to_dict().get("entity_id")
                    target_currency = get_entity_currency(e_id)

        # 4. Final safety default
        if not target_currency:
            target_currency = "BHD"

        print(f"DEBUG: Final Resolved Currency for Export: {target_currency}")

        temp_excel = tempfile.mktemp(suffix=".xlsx")
        generate_petty_cash_log(results, temp_excel, currency=target_currency)
        
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

@app.get("/export-pdf")
async def export_pdf(team_id: Optional[str] = None, user_id: Optional[str] = None, currency: Optional[str] = None):
    try:
        # 1. Fetch exactly the same data as Excel
        docs_ref_query = db.collection("extractions")\
            .where("status", "in", ["COMPLETED", "AMBER"])\
            .where("is_verified", "==", True)
            
        # Re-use the filtering logic from export_excel
        if user_id and team_id:
            docs_ref_query = docs_ref_query.where("team_id", "==", team_id)
            docs_ref = docs_ref_query.stream()
            results = []
            for doc in docs_ref:
                data = doc.to_dict()
                if data.get("user_id") == user_id or data.get("user_id") == "automation":
                    results.append(ExtractionResult(file_id=doc.id, file_name=data.get("name"), status="COMPLETED", data=data.get("data")))
        elif team_id:
            docs_ref_query = docs_ref_query.where("team_id", "==", team_id)
            docs_ref = docs_ref_query.stream()
            results = [ExtractionResult(file_id=doc.id, file_name=doc.to_dict().get("name"), status="COMPLETED", data=doc.to_dict().get("data")) for doc in docs_ref]
        elif user_id:
            docs_ref_query = docs_ref_query.where("user_id", "==", user_id)
            docs_ref = docs_ref_query.stream()
            results = [ExtractionResult(file_id=doc.id, file_name=doc.to_dict().get("name"), status="COMPLETED", data=doc.to_dict().get("data")) for doc in docs_ref]
        else:
            docs_ref = docs_ref_query.stream()
            results = [ExtractionResult(file_id=doc.id, file_name=doc.to_dict().get("name"), status="COMPLETED", data=doc.to_dict().get("data")) for doc in docs_ref]

        if not results:
            return {"error": "No completed extractions to export"}

        # 2. Resolve Currency
        target_currency = currency.strip().upper() if (currency and currency.strip()) else "INR"
        
        # 3. Generate PDF
        temp_pdf = tempfile.mktemp(suffix=".pdf")
        generate_pdf_log(results, temp_pdf, currency=target_currency)
        
        return FileResponse(
            temp_pdf,
            media_type='application/pdf',
            filename=f"Petty_Cash_Log_{time.strftime('%Y%m%d_%H%M%S')}.pdf"
        )
    except Exception as e:
        import traceback
        print(f"INTERNAL ERROR EXPORTING PDF: {traceback.format_exc()}")
        return JSONResponse(status_code=500, content={"error": str(e)})

from pydantic import BaseModel

class UserCreate(BaseModel):
    email: str
    password: str
    role: str
    team_id: Optional[str] = "general"
    entity_id: Optional[str] = "default"

class EntityCreate(BaseModel):
    name: str
    currency: str
    symbol: Optional[str] = ""
    active_currencies: Optional[List[str]] = []

# --- ENTITY MANAGEMENT (V2) ---
@app.get("/entities")
async def get_entities():
    try:
        docs = db.collection("entities").stream()
        entities = [{"id": d.id, **d.to_dict()} for d in docs]
        return {"status": "success", "entities": entities}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/create-entity")
async def create_entity(req: EntityCreate):
    try:
        # Check if entity already exists by name (case-insensitive)
        entities = db.collection("entities").where("name", "==", req.name.strip()).stream()
        if any(entities):
            return JSONResponse(status_code=400, content={"error": "An entity with this name already exists"})

        doc_ref = db.collection("entities").document()
        doc_ref.set({
            "name": req.name.strip(),
            "currency": req.currency.strip().upper(),
            "symbol": req.symbol.strip() if req.symbol else "",
            "active_currencies": [c.upper() for c in req.active_currencies] if req.active_currencies else [req.currency.strip().upper(), "USD", "SAR", "INR"],
            "created_at": time.time()
        })
        return {"status": "success", "id": doc_ref.id, "message": "Entity created successfully"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.patch("/update-entity/{entity_id}")
async def update_entity(entity_id: str, req: EntityCreate):
    try:
        db.collection("entities").document(entity_id).update({
            "name": req.name.strip(),
            "currency": req.currency.strip().upper(),
            "symbol": req.symbol.strip() if req.symbol else "",
            "active_currencies": [c.upper() for c in req.active_currencies] if req.active_currencies else [req.currency.strip().upper(), "USD", "SAR", "INR"]
        })
        return {"status": "success"}
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": str(e)})

@app.delete("/delete-entity/{entity_id}")
async def delete_entity(entity_id: str):
    try:
        db.collection("entities").document(entity_id).delete()
        return {"status": "success"}
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": str(e)})



# --- ZOHO INTEGRATION (V5) ---
def get_zoho_config(entity_id: str) -> Optional[ZohoConfig]:
    """Fetch Zoho configuration for an entity from Firestore"""
    if not entity_id or entity_id == "default":
        return None
    try:
        doc = db.collection("entities").document(entity_id).get()
        if doc.exists:
            d = doc.to_dict()
            zoho_data = d.get("zoho_config")
            if zoho_data:
                return ZohoConfig(**zoho_data)
    except Exception as e:
        print(f"Error fetching Zoho config for entity {entity_id}: {e}")
    return None

@app.post("/entities/{entity_id}/zoho-config")
async def save_zoho_config(entity_id: str, config: ZohoConfig):
    try:
        db.collection("entities").document(entity_id).update({
            "zoho_config": config.model_dump()
        })
        return {"status": "success", "message": "Zoho configuration saved successfully"}
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": str(e)})

@app.post("/extractions/{doc_id}/sync-zoho")
async def sync_to_zoho(doc_id: str, role: str = "user"):
    # RBAC: Only Admin and Leader can sync
    if role not in ["admin", "leader"]:
        return JSONResponse(status_code=403, content={"error": "Permission denied: Only Admins and Leaders can sync to Zoho"})

    try:
        # 1. Fetch extraction record
        doc_ref = db.collection("extractions").document(doc_id)
        doc = doc_ref.get()
        if not doc.exists:
            return JSONResponse(status_code=404, content={"error": "Extraction record not found"})
        
        data = doc.to_dict()
        if not data.get("is_verified"):
             return JSONResponse(status_code=400, content={"error": "Only verified records can be synced to Zoho"})
        
        extraction_data = ReceiptData(**data.get("data", {}))
        entity_id = data.get("entity_id", "default")
        
        # 2. Get Zoho Config for the entity
        zoho_config = get_zoho_config(entity_id)
        if not zoho_config:
            return JSONResponse(status_code=400, content={"error": f"Zoho Books is not configured for entity {entity_id}"})
        
        # 3. Trigger Sync
        client = ZohoClient(zoho_config)
        
        # Decide whether to create invoice or expense based on category (or user preference)
        # For now, let's stick to the user's specific request for Invoices
        invoice_id = await client.create_invoice(extraction_data)
        
        # 4. Record success
        update_info = {
            "zoho_sync_status": "SUCCESS",
            "zoho_invoice_id": invoice_id,
            "zoho_sync_time": time.time()
        }
        doc_ref.update(update_info)
        
        return {"status": "success", "invoice_id": invoice_id}
        
    except Exception as e:
        print(f"Zoho Sync Error for {doc_id}: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/create-user")

async def create_user(req: UserCreate):
    try:
        from firebase_config import auth as admin_auth
        # Create user in Firebase Auth
        user_record = admin_auth.create_user(
            email=req.email,
            password=req.password
        )
        # Ensure clean team_id, strip hidden spaces, default to general
        clean_team = (req.team_id or "general").strip().lower()

        # Store rich metadata in Firestore roles table
        db.collection("users").document(user_record.uid).set({
            "email": req.email,
            "role": req.role,
            "team_id": clean_team,
            "entity_id": req.entity_id.strip() if req.entity_id else "default",
            "created_at": time.time(),
            "status": "active"
        })
        return {"status": "success", "uid": user_record.uid, "message": "User created successfully"}
    except Exception as e:
        import traceback
        error_msg = traceback.format_exc()
        print(f"Error creating user: {error_msg}")
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=400, content={"error": str(e)})

# --- CATEGORY MANAGEMENT (V3) ---
@app.get("/categories")
async def get_categories(team_id: Optional[str] = None):
    try:
        # Normalize team_id to lowercase for consistent comparison
        clean_team = team_id.lower().strip() if team_id else None
        
        if clean_team:
            docs = db.collection("categories").where("team_id", "in", ["global", clean_team]).stream()
        else:
            docs = db.collection("categories").where("team_id", "==", "global").stream()
        
        categories = [{"id": d.id, **d.to_dict()} for d in docs]
        return {"status": "success", "categories": categories}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/categories")
async def add_category(req: CategoryCreate):
    try:
        # Normalize data
        clean_team = req.team_id.lower().strip()
        clean_name = req.name.strip()
        
        # Check if already exists in this scope
        doc_id = f"{clean_team}_{req.type.lower()}_{clean_name.replace(' ', '_').replace('/', '_').lower()}"
        existing = db.collection("categories").document(doc_id).get()
        if existing.exists:
            return JSONResponse(status_code=400, content={"error": "Category already exists for this team"})

        db.collection("categories").document(doc_id).set({
            "name": clean_name,
            "type": req.type,
            "is_builtin": req.is_builtin,
            "team_id": clean_team,
            "created_at": time.time()
        })
        return {"status": "success", "id": doc_id}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.delete("/categories/{doc_id}")
async def delete_category(doc_id: str, role: str = "user", team_id: str = ""):
    try:
        print(f"DEBUG: Delete request for {doc_id} by role={role}, team_id={team_id}")
        doc_ref = db.collection("categories").document(doc_id)
        doc = doc_ref.get()
        if not doc.exists:
            return JSONResponse(status_code=404, content={"error": "Category not found"})
        
        data = doc.to_dict()
        if data.get("is_builtin"):
            return JSONResponse(status_code=403, content={"error": "Cannot delete built-in categories"})
        
        # Normalize input
        clean_role = role.strip().lower()
        clean_team = team_id.strip().lower()
        
        # RBAC: Leader can only delete their team's categories. Admin can delete global too.
        cat_team = data.get("team_id", "global").lower()
        if clean_role == "leader" and cat_team != clean_team:
            print(f"DEBUG: Permission denied. Category team={cat_team}, User team={clean_team}")
            return JSONResponse(status_code=403, content={"error": f"Permission denied: Can only delete categories for team {clean_team}"})
        if clean_role == "user":
            print(f"DEBUG: Permission denied. User is a general user.")
            return JSONResponse(status_code=403, content={"error": "General users cannot delete categories"})

        doc_ref.delete()
        print(f"DEBUG: Successfully deleted category {doc_id}")
        return {"status": "success"}
    except Exception as e:
        print(f"ERROR: Delete failed: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

# --- BANK MANAGEMENT (V4) ---
@app.get("/banks")
async def get_banks(team_id: Optional[str] = None):
    try:
        clean_team = team_id.lower().strip() if team_id else None
        
        if clean_team:
            docs = db.collection("banks").where("team_id", "in", ["global", clean_team]).stream()
        else:
            docs = db.collection("banks").where("team_id", "==", "global").stream()
        
        banks = [{"id": d.id, **d.to_dict()} for d in docs]
        return {"status": "success", "banks": banks}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/banks")
async def add_bank(req: BankCreate):
    try:
        clean_team = req.team_id.lower().strip()
        clean_name = req.name.strip()
        
        doc_id = f"bank_{clean_team}_{clean_name.replace(' ', '_').lower()}"
        existing = db.collection("banks").document(doc_id).get()
        if existing.exists:
            return JSONResponse(status_code=400, content={"error": "Bank already exists for this team"})

        db.collection("banks").document(doc_id).set({
            "name": clean_name,
            "is_builtin": req.is_builtin,
            "team_id": clean_team,
            "created_at": time.time()
        })
        return {"status": "success", "id": doc_id}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.delete("/banks/{doc_id}")
async def delete_bank(doc_id: str, role: str = "user", team_id: str = ""):
    try:
        doc_ref = db.collection("banks").document(doc_id)
        doc = doc_ref.get()
        if not doc.exists:
            return JSONResponse(status_code=404, content={"error": "Bank not found"})
        
        data = doc.to_dict()
        if data.get("is_builtin") and role != "admin":
            return JSONResponse(status_code=403, content={"error": "Built-in banks can only be deleted by Admins"})
        
        clean_role = role.strip().lower()
        clean_team = team_id.strip().lower()
        bank_team = data.get("team_id", "global").lower()

        if clean_role == "leader" and bank_team != clean_team:
            return JSONResponse(status_code=403, content={"error": f"Permission denied: Can only delete banks for team {clean_team}"})
        if clean_role == "user":
            return JSONResponse(status_code=403, content={"error": "General users cannot delete banks"})

        doc_ref.delete()
        return {"status": "success"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

# ============================================================
# GOOGLE DRIVE INTEGRATION
# Watches a shared Drive folder for new receipt uploads.
# When a new file is detected, downloads and processes it
# through the existing Gemini AI pipeline.
# ============================================================

from drive_watcher import get_drive_service, register_watch, list_new_files, download_file

# Configuration from environment
DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "1Rx6fEVyV0Ne4B-PDYHR_skFqrv4ytwKE")
DRIVE_TEAM_ID = os.getenv("GOOGLE_DRIVE_TEAM_ID", "finance1")
BACKEND_URL = os.getenv("BACKEND_URL", "https://expense-extraction.onrender.com")

# Track which files we've already processed (in-memory; resets on restart)
_processed_drive_files: set = set()

# Initialize Drive service at module level
_drive_service = None

def _get_drive():
    global _drive_service
    if _drive_service is None:
        _drive_service = get_drive_service()
    return _drive_service


async def _process_drive_files(background_tasks: BackgroundTasks = None):
    """Scan the Drive folder for new files and process any we haven't seen."""
    service = _get_drive()
    if not service:
        print("Drive service not available. Skipping scan.")
        return 0

    files = list_new_files(service, DRIVE_FOLDER_ID)
    new_count = 0

    for file_info in files:
        file_id = file_info['id']
        file_name = file_info['name']
        
        # Skip already-processed files
        if file_id in _processed_drive_files:
            continue
        
        # Also check Firestore to avoid re-processing after restarts
        existing = db.collection("extractions").where("drive_file_id", "==", file_id).limit(1).stream()
        if any(True for _ in existing):
            _processed_drive_files.add(file_id)
            continue

        print(f"New Drive file detected: {file_name} (ID: {file_id})")
        
        # Download the file
        local_path = download_file(service, file_id, file_name)
        if not local_path:
            continue

        # Create Firestore record (same structure as automation uploads)
        doc_ref = db.collection("extractions").add({
            "name": file_name,
            "status": "QUEUED",
            "upload_time": time.time(),
            "user_id": "automation",
            "team_id": DRIVE_TEAM_ID,
            "is_verified": False,
            "data": None,
            "temp_local_path": local_path,
            "source": "google_drive",
            "drive_file_id": file_id
        })
        
        _processed_drive_files.add(file_id)
        new_count += 1
        print(f"Queued Drive file for processing: {file_name}")

    # Auto-trigger the AI processor if we found new files
    if new_count > 0:
        if background_tasks:
            background_tasks.add_task(run_batch_processor)
        else:
            await run_batch_processor()
        print(f"Drive scan complete. {new_count} new files queued for AI extraction.")
    
    return new_count


@app.post("/drive-webhook")
async def drive_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Webhook endpoint that Google Drive calls when files change in the watched folder.
    Google sends minimal data in the headers; we respond by scanning for new files.
    """
    resource_state = request.headers.get("X-Goog-Resource-State", "")
    channel_id = request.headers.get("X-Goog-Channel-ID", "")
    
    print(f"Drive Webhook received: state={resource_state}, channel={channel_id}")
    
    # 'sync' = initial verification, 'update' = actual change
    if resource_state == "sync":
        print("Drive webhook sync confirmation received.")
        return {"status": "sync_ok"}
    
    # Process new files
    new_count = await _process_drive_files(background_tasks)
    return {"status": "processed", "new_files": new_count}


@app.post("/register-drive-watch")
async def register_drive_watch():
    """
    Manually register (or re-register) the Google Drive push notification channel.
    Call this once after deployment, and it will auto-renew on server restart.
    """
    service = _get_drive()
    if not service:
        return {"status": "error", "message": "Drive service not initialized. Check credentials."}
    
    webhook_url = f"{BACKEND_URL}/drive-webhook"
    channel_id = f"expense-drive-{int(time.time())}"
    
    result = register_watch(service, DRIVE_FOLDER_ID, webhook_url, channel_id)
    
    if result:
        return {
            "status": "success",
            "channel_id": result.get("id"),
            "expiration": result.get("expiration"),
            "webhook_url": webhook_url
        }
    else:
        return {"status": "error", "message": "Failed to register watch. Check server logs."}


@app.get("/scan-drive")
async def scan_drive(background_tasks: BackgroundTasks):
    """
    Manual trigger to scan the Drive folder for new files.
    Useful as a fallback if webhooks aren't working, or for testing.
    """
    new_count = await _process_drive_files(background_tasks)
    return {"status": "success", "new_files_found": new_count}


@app.on_event("startup")
async def startup_drive_watch():
    """Auto-register the Drive watch when the server starts."""
    try:
        service = _get_drive()
        if service:
            webhook_url = f"{BACKEND_URL}/drive-webhook"
            channel_id = f"expense-drive-{int(time.time())}"
            register_watch(service, DRIVE_FOLDER_ID, webhook_url, channel_id)
            print("Drive watch auto-registered on startup.")
        else:
            print("Skipping Drive watch registration (service not available).")
    except Exception as e:
        print(f"Drive watch startup registration failed (non-blocking): {e}")


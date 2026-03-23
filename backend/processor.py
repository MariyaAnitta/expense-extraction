import os
import time
import requests
import json
import extract_msg
from typing import Optional, Dict, Any
from google.cloud import aiplatform
from vertexai.generative_models import GenerativeModel, Part
import vertexai
from models import ReceiptData, ExtractionResult
from dotenv import load_dotenv

# Load from specific backend folder
current_dir = os.path.dirname(os.path.abspath(__file__))
dotenv_path = os.path.join(current_dir, '.env')

if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)
else:
    print(f"ERROR: .env file not found at {dotenv_path}")

# Helper to get credentials
def get_google_creds():
    google_creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if google_creds_path and os.path.exists(google_creds_path):
        return google_creds_path
    return None

class ReceiptProcessor:
    def __init__(self):
        # Configuration
        self.pulse_url = "https://api.runpulse.com/extract"
        self.pulse_headers = {"x-api-key": os.getenv("PULSE_API_KEY")}
        
        project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        location = os.getenv("GOOGLE_CLOUD_LOCATION")
        model_name = os.getenv("VERTEX_AI_MODEL", "gemini-2.0-flash")
        
        # Initialize Vertex AI
        creds = get_google_creds()
        if creds:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds
            
        vertexai.init(project=project_id, location=location)
        self.model = GenerativeModel(model_name)

    def _extract_text_pulse(self, file_path: str) -> tuple[str, float]:
        """Extract text from PDF/Image using Pulse OCR, returning (markdown, confidence)"""
        print(f"Calling Pulse OCR for {file_path} (Timeout: 30s)...")
        try:
            with open(file_path, "rb") as f:
                response = requests.post(
                    self.pulse_url,
                    headers=self.pulse_headers,
                    files={"file": f},
                    timeout=60 # Prevent indefinite hanging
                )
            
            if response.status_code == 200:
                data = response.json()
                markdown = data.get("markdown", "")
                # Pulse often provides 'confidence' as a 0-1 float
                confidence = data.get("confidence", 0.95) 
                print(f"DEBUG PULSE SUCCESS: Found {len(markdown)} characters. Confidence: {confidence}")
                return markdown, float(confidence) * 100
            else:
                print(f"DEBUG PULSE HTTP Error: {response.status_code} - {response.text}")
                raise Exception(f"Pulse OCR Error: {response.status_code} - {response.text}")
        except requests.exceptions.Timeout:
            print(f"Pulse OCR TIMED OUT for {file_path}")
            raise Exception("Pulse OCR Timeout: The service is taking too long to respond.")
        except Exception as e:
            print(f"Pulse OCR Request Failed: {e}")
            raise

    def _parse_msg_file(self, file_path: str) -> str:
        """Parse Outlook .msg file and return body/text"""
        msg = extract_msg.Message(file_path)
        return f"Subject: {msg.subject}\nFrom: {msg.sender}\nDate: {msg.date}\nBody: {msg.body}"

    def _structure_data_vertex(self, raw_text: str, confidence: float = 95.0) -> ReceiptData:
        """Use Gemini to structure the extracted text into ReceiptData"""
        prompt = f"""
        Extract the following information from the provided receipt/document text into a valid JSON object.
        
        Rules:
        1. If it's a purchase/expense, put the value in 'amount'.
        2. If it's a Top-Up, Deposit, or Credit, put the value in 'deposit_amount'.
        3. For 'date', use DD/MM/YYYY format.
        4. Be descriptive for 'description'.
        
        *** SPECIAL RULE FOR PETTY CASH ***
        If the document is a "Transaction Receipt" or "External Transfer" where:
        - Details mention "Petty cash advance" OR Beneficiary "Rajeev"
        THEN YOU MUST EXACTLY OUTPUT:
        - "description": "Petty Cash Top Up"
        - "received_by": "Rajeev R"
        - "category": "Deposit"
        - "deposit_amount": [The Transaction Amount value]
        - "amount": null
        
        JSON Structure:
        {{
            "date": "DD/MM/YYYY",
            "description": "Short summary of what was paid for",
            "amount": float or null,
            "deposit_amount": float or null,
            "currency": "BHD",
            "received_by": "Name of the entity or person",
            "transaction_no": "Reference string or null",
            "category": "Expense" or "Deposit",
            "remarks": "ok"
        }}

        Text to analyze:
        {raw_text}
        """
        
        try:
            print(f"DEBUG: Structuring text with Gemini. Raw text length: {len(raw_text)}")
            
            # Using specific response_mime_type ensures valid JSON
            response = self.model.generate_content(
                prompt,
                generation_config={"response_mime_type": "application/json"}
            )
            
            json_str = response.text.strip()
            print(f"DEBUG: Gemini raw response: {json_str}")
            
            # Clean up potential markdown marks if Gemini still sends them in JSON mode
            if "```" in json_str:
                json_str = json_str.split("```")[1]
                if json_str.startswith("json"):
                    json_str = json_str[4:]
            
            data_dict = json.loads(json_str)
            print(f"DEBUG: Parsed data_dict keys: {list(data_dict.keys())}")
            
            # Basic validation/mapping for critical fields
            if not data_dict.get("description"):
                data_dict["description"] = "No description available"
                
            # Add confidence score
            data_dict["confidence"] = confidence 
            
            return ReceiptData(**data_dict)
        except Exception as e:
            print(f"DEBUG ERROR: Vertex AI Structure Failed: {e}")
            # Return a valid but empty record so the table doesn't break
            return ReceiptData(
                date=datetime.now().strftime("%d/%m/%Y"),
                description=f"Analysis Error: {str(e)[:50]}",
                amount=0.0,
                confidence=0.0,
                remarks="ERROR"
            )

    def process_file(self, file_path: str) -> ExtractionResult:
        """Complete pipeline: Pulse OCR -> Vertex AI Structure"""
        file_name = os.path.basename(file_path)
        file_id = file_name # Simplified ID
        
        try:
            # 1. Extraction (Pulse if image/pdf, extract-msg if .msg)
            if file_name.lower().endswith(".msg"):
                raw_text = self._parse_msg_file(file_path)
                confidence = 100.0 # MSG files are perfectly structured natively
            else:
                raw_text, confidence = self._extract_text_pulse(file_path)
            
            # 2. Structure (Vertex AI)
            structured_data = self._structure_data_vertex(raw_text, confidence)
            
            return ExtractionResult(
                file_id=file_id,
                file_name=file_name,
                status="COMPLETED",
                data=structured_data
            )
        except Exception as e:
            return ExtractionResult(
                file_id=file_id,
                file_name=file_name,
                status="FAILED",
                error=str(e)
            )

def batch_process(file_paths: list, delay_sec: int = 5) -> list:
    """Process files in batches with delays"""
    processor = ReceiptProcessor()
    results = []
    
    for i, path in enumerate(file_paths):
        # Human-friendly delay logic could go here (e.g. every 5 files)
        if i > 0 and i % 5 == 0:
            time.sleep(delay_sec)
            
        result = processor.process_file(path)
        results.append(result)
        
    return results

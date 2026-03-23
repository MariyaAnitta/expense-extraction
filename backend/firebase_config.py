import os
import json
import tempfile
import firebase_admin
from firebase_admin import credentials, storage, firestore
from dotenv import load_dotenv

# Load from specific backend folder
current_dir = os.path.dirname(os.path.abspath(__file__))
dotenv_path = os.path.join(current_dir, '.env')

if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)
else:
    print(f"INFO: No local .env file found at {dotenv_path} (normal on Render)")

bucket_name = os.getenv("FIREBASE_STORAGE_BUCKET")

# --- Google Cloud Credentials (for Vertex AI) ---
# Priority: GOOGLE_CREDENTIALS_JSON (Render) > GOOGLE_APPLICATION_CREDENTIALS (local file)
google_creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
google_creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

if google_creds_json:
    # On Render: write JSON string to a temp file so Google SDK can read it
    tmp_gcp = os.path.join(tempfile.gettempdir(), "gcp-key.json")
    with open(tmp_gcp, "w") as f:
        f.write(google_creds_json)
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = tmp_gcp
    print("Using GOOGLE_CREDENTIALS_JSON from env var")
elif google_creds_path:
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = google_creds_path
    print(f"Using GOOGLE_APPLICATION_CREDENTIALS file: {google_creds_path}")

# --- Firebase Credentials ---
# Priority: FIREBASE_CREDENTIALS_JSON (Render) > FIREBASE_SERVICE_ACCOUNT_KEY (local file)
firebase_creds_json = os.getenv("FIREBASE_CREDENTIALS_JSON")
service_account_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_KEY")

if not firebase_admin._apps:
    if firebase_creds_json:
        cred_dict = json.loads(firebase_creds_json)
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred, {'storageBucket': bucket_name})
        print(f"Firebase initialized (Bucket: {bucket_name}) from FIREBASE_CREDENTIALS_JSON")
    elif service_account_path and os.path.exists(service_account_path):
        cred = credentials.Certificate(service_account_path)
        firebase_admin.initialize_app(cred, {'storageBucket': bucket_name})
        print(f"Firebase initialized (Bucket: {bucket_name}) from file: {service_account_path}")
    else:
        print(f"WARNING: No Firebase credentials found. Falling back to default (Bucket: {bucket_name}).")
        firebase_admin.initialize_app(options={'storageBucket': bucket_name})

db = firestore.client()
bucket = storage.bucket()


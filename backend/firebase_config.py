import os
import firebase_admin
from firebase_admin import credentials, storage, firestore
from dotenv import load_dotenv

# Load from specific backend folder
current_dir = os.path.dirname(os.path.abspath(__file__))
dotenv_path = os.path.join(current_dir, '.env')

if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)
else:
    print(f"ERROR: .env file not found at {dotenv_path}")

service_account_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_KEY")
google_creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
bucket_name = os.getenv("FIREBASE_STORAGE_BUCKET")

# CRITICAL: For Windows, ensure paths are handled correctly
if google_creds_path:
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = google_creds_path

if not firebase_admin._apps:
    if service_account_path and os.path.exists(service_account_path):
        cred = credentials.Certificate(service_account_path)
        firebase_admin.initialize_app(cred, {
            'storageBucket': bucket_name
        })
    else:
        print(f"WARNING: Firebase service account not found at {service_account_path}. Falling back to default.")
        firebase_admin.initialize_app(options={'storageBucket': bucket_name})

db = firestore.client()
bucket = storage.bucket()

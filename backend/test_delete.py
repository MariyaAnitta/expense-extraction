import sys
from firebase_config import db

docs = db.collection("extractions").where("team_id", "==", "finance1").stream()
count = 0
for doc in docs:
    print(f"Deleting {doc.id}")
    db.collection("extractions").document(doc.id).delete()
    count += 1

print(f"Deleted {count} docs.")

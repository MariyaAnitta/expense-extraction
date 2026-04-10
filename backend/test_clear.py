import os
import sys
from firebase_config import db

docs = db.collection("extractions").where("team_id", "==", "finance1").stream()
count = 0
for doc in docs:
    count += 1
    print(doc.id, doc.to_dict().get("name"))
print(f"Found {count} docs with lowercase 'finance1'")

docs = db.collection("extractions").where("team_id", "==", "Finance1").stream()
count = 0
for doc in docs:
    count += 1
    print(doc.id, doc.to_dict().get("name"))
print(f"Found {count} docs with capitalized 'Finance1'")

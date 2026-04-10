import sys
from firebase_config import db

docs = db.collection("extractions").where("team_id", "==", "finance").stream()
found = False
for doc in docs:
    found = True
    d = doc.to_dict()
    print(f"Receipt: {d.get('name')}, status: {d.get('status')}, user_id: {d.get('user_id')}, team_id: {d.get('team_id')}")

if not found:
    print("No docs found for team_id == 'finance'")

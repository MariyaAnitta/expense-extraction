import sys
import json
from firebase_config import db

docs = db.collection("extractions").where("team_id", "==", "finance").stream()
out = []
for doc in docs:
    d = doc.to_dict()
    if "Rajeev" in d.get("name", ""):
        out.append(d)

with open("debug2.json", "w") as f:
    json.dump(out, f, indent=2)

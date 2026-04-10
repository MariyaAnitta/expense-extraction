import json
from firebase_config import db

docs = db.collection("extractions").where("team_id", "==", "finance").stream()
out = []
for doc in docs:
    d = doc.to_dict()
    out.append({
        "name": d.get("name"), 
        "user_id": d.get("user_id"), 
        "team_id": d.get("team_id"),
        "is_verified": d.get("is_verified")
    })

with open("debug3.json", "w") as f:
    json.dump(out, f, indent=2)

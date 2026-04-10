import sys
import json
from firebase_config import db

docs = db.collection("extractions").limit(10).stream()
output = []
for doc in docs:
    d = doc.to_dict()
    output.append({"id": doc.id, "team_id": d.get("team_id"), "name": d.get("name")})

with open("debug.json", "w") as f:
    json.dump(output, f, indent=2)

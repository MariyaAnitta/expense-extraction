import json
from firebase_config import db

docs = db.collection("entities").stream()
out = []
for doc in docs:
    d = doc.to_dict()
    d['id'] = doc.id
    out.append(d)

with open("debug_entities.json", "w") as f:
    json.dump(out, f, indent=2)

print(f"Dumped {len(out)} entities.")

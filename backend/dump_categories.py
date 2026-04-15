import json
from firebase_config import db

docs = db.collection("categories").stream()
out = []
for doc in docs:
    d = doc.to_dict()
    d['id'] = doc.id
    out.append(d)

with open("debug_categories.json", "w") as f:
    json.dump(out, f, indent=2)

print(f"Dumped {len(out)} categories.")

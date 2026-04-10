import json
from firebase_config import db

docs = db.collection("users").stream()
out = []
for doc in docs:
    out.append(doc.to_dict())

with open("debug_users.json", "w") as f:
    json.dump(out, f, indent=2)

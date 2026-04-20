import firebase_admin
from firebase_admin import credentials, firestore

cred = credentials.Certificate('backend/cash-portal-97361-95a39c505149.json')
firebase_admin.initialize_app(cred)
db = firestore.client()

docs = db.collection('users').where('role', 'in', ['admin', 'leader']).get()
if not docs:
    print("NO ADMINS OR LEADERS FOUND IN DATABASE")
else:
    for d in docs:
        data = d.to_dict()
        print(f"ID: {d.id} | Email: {data.get('email')} | Role: {data.get('role')} | Team: {data.get('team_id')} | Entity: {data.get('entity_id')}")

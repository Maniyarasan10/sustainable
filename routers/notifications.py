from fastapi import APIRouter, Depends, HTTPException
from utils.auth import get_current_user
from db_mongo import notifications_col
from datetime import datetime
import uuid

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("")
def get_notifications(current_user: dict = Depends(get_current_user)):
    user_id = current_user.get('id')
    notes = list(notifications_col.find({"user_id": user_id}).sort("created_at", -1))
    for n in notes:
        n['id'] = n.get('_id')
    return notes


@router.post("/create")
def create_notification(payload: dict):
    # payload should include: user_id, title, message, metadata(optional)
    if 'user_id' not in payload or 'title' not in payload or 'message' not in payload:
        raise HTTPException(status_code=400, detail="user_id, title and message required")
    note = {
        '_id': str(uuid.uuid4()),
        'user_id': payload.get('user_id'),
        'title': payload.get('title'),
        'message': payload.get('message'),
        'metadata': payload.get('metadata', {}),
        'read': False,
        'created_at': datetime.utcnow()
    }
    notifications_col.insert_one(note)
    return {"status": "ok", "id": note['_id']}


@router.post("/{note_id}/mark_read")
def mark_read(note_id: str, current_user: dict = Depends(get_current_user)):
    notifications_col.update_one({"_id": note_id, "user_id": current_user.get('id')}, {"$set": {"read": True}})
    return {"status": "ok"}

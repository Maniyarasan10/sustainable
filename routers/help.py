from fastapi import APIRouter, Depends, UploadFile, File, Form
from typing import List, Optional
from datetime import datetime
from utils.auth import get_current_user
from db_mongo import help_col
from pathlib import Path
import uuid

router = APIRouter(prefix="/help", tags=["Help"])


@router.post("", response_model=dict)
def create_help(
    description: str = Form(...),
    mobile: Optional[str] = Form(None),
    latitude: Optional[float] = Form(None),
    longitude: Optional[float] = Form(None),
    address: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    current_user = Depends(get_current_user),
):
    """Create a help request stored in MongoDB; optional media upload saved to static/uploads"""
    media_url = None
    media_type = None
    if file:
        uploads_dir = Path('static/uploads')
        uploads_dir.mkdir(parents=True, exist_ok=True)
        help_id = str(uuid.uuid4())
        filename = f"{help_id}_{file.filename}"
        save_path = uploads_dir / filename
        with save_path.open('wb') as buffer:
            buffer.write(file.file.read())
        media_url = f"/static/uploads/{filename}"
        media_type = file.content_type

    doc = {
        "_id": str(uuid.uuid4()),
        "user_id": current_user.get('id') if current_user else None,
        "mobile": mobile,
        "description": description,
        "latitude": latitude,
        "longitude": longitude,
        "address": address,
        "media_url": media_url,
        "media_type": media_type,
        "created_at": datetime.utcnow(),
    }
    help_col.insert_one(doc)
    doc['id'] = doc['_id']
    return doc


@router.get("", response_model=List[dict])
def list_help(similar: Optional[bool] = False, current_user = Depends(get_current_user)):
    # If similar=true, return help requests from users with same gender as current_user
    if similar and current_user:
        # find users matching current user's gender
        from db_mongo import users_col
        gender = current_user.get('gender')
        if gender:
            users = list(users_col.find({"gender": gender}, {"_id": 1}))
            user_ids = [u.get('_id') for u in users]
            docs = list(help_col.find({"user_id": {"$in": user_ids}}).sort('created_at', -1))
        else:
            docs = list(help_col.find().sort('created_at', -1))
    else:
        docs = list(help_col.find().sort('created_at', -1))

    for d in docs:
        d['id'] = d.get('_id')
    return docs

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, status, Body
from typing import List, Optional
from datetime import datetime, timezone
from utils.auth import get_current_user
from db_mongo import help_col
from pathlib import Path
import uuid

from utils import storage

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
    """Create a help request stored in MongoDB; optional media upload with Cloudinary support"""
    help_id = str(uuid.uuid4())
    media_url = None
    media_type = None
    if file:
        try:
            # Upload to Cloudinary
            resp = storage.upload_file(file, folder='help', public_id=help_id)
            media_url = resp.get('secure_url') or resp.get('url')
            media_type = file.content_type or resp.get('resource_type')
        except Exception:
            # Fallback to local saving
            uploads_dir = Path('static/uploads')
            uploads_dir.mkdir(parents=True, exist_ok=True)
            filename = f"{help_id}_{file.filename}"
            save_path = uploads_dir / filename
            with save_path.open('wb') as buffer:
                buffer.write(file.file.read())
            media_url = f"/static/uploads/{filename}"
            media_type = file.content_type

    doc = {
        "_id": help_id,
        "user_id": current_user.get('id') if current_user else None,
        "mobile": mobile,
        "description": description,
        "latitude": latitude,
        "longitude": longitude,
        "address": address,
        "media_url": media_url,
        "media_type": media_type,
        "created_at": datetime.now(timezone.utc),
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


@router.delete("/{help_id}")
def delete_help(help_id: str, current_user=Depends(get_current_user)):
    """Delete a help request. Only the owner can delete their own request."""
    doc = help_col.find_one({"_id": help_id})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Help request not found")
    if doc.get("user_id") != current_user.get("id"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only delete your own help requests")
    help_col.delete_one({"_id": help_id})
    return {"message": "Help request deleted successfully"}


@router.patch("/{help_id}/edit", response_model=dict)
def edit_help(
    help_id: str,
    body: dict = Body(...),
    current_user=Depends(get_current_user),
):
    """Edit a help request's description and/or mobile. Only the owner can edit."""
    doc = help_col.find_one({"_id": help_id})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Help request not found")
    if doc.get("user_id") != current_user.get("id"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only edit your own help requests")

    fields: dict = {}
    if body.get("description") is not None:
        fields["description"] = body["description"]
    if body.get("mobile") is not None:
        fields["mobile"] = body["mobile"]

    if not fields:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")

    fields["updated_at"] = datetime.now(timezone.utc)
    help_col.update_one({"_id": help_id}, {"$set": fields})
    updated = help_col.find_one({"_id": help_id})
    updated["id"] = updated["_id"]
    return updated


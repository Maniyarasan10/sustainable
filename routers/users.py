from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from typing import List, Optional
from utils.auth import get_current_user
from db_mongo import users_col, issues_col
from pathlib import Path
from utils import storage
import uuid
import os

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me")
def get_me(current_user: dict = Depends(get_current_user)):
    return current_user


@router.put("/me")
def update_me(
    name: Optional[str] = Form(None),
    dob: Optional[str] = Form(None),
    gender: Optional[str] = Form(None),
    address: Optional[str] = Form(None),
    avatar: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    current_user: dict = Depends(get_current_user),
):
    update_fields = {}
    if name is not None:
        update_fields['name'] = name
    if dob is not None:
        update_fields['dob'] = dob
    if gender is not None:
        update_fields['gender'] = gender
    if address is not None:
        update_fields['address'] = address

    # handle avatar string (e.g., emoji:🙂)
    if avatar:
        update_fields['avatar'] = avatar

    # handle uploaded avatar file
    if file:
        # Upload avatar to Cloudinary and store URL
        try:
            resp = storage.upload_file(file, folder='avatars', public_id=f"avatar_{current_user.get('id')}")
            update_fields['avatar'] = resp.get('secure_url') or resp.get('url')
        except Exception:
            uploads_dir = Path('static/uploads')
            uploads_dir.mkdir(parents=True, exist_ok=True)
            filename = f"avatar_{current_user.get('id')}_{file.filename}"
            save_path = uploads_dir / filename
            with save_path.open('wb') as buffer:
                buffer.write(file.file.read())
            update_fields['avatar'] = f"/static/uploads/{filename}"

    if update_fields:
        users_col.update_one({"_id": current_user.get('id')}, {"$set": update_fields})

    user = users_col.find_one({"_id": current_user.get('id')})
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user['id'] = user.get('_id')
    return user


@router.get("/{user_id}/issues")
def get_user_issues(user_id: str, current_user: dict = Depends(get_current_user)):
    # Only allow access to own history for now
    if user_id != current_user.get('id'):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    issues = list(issues_col.find({"user_id": user_id}))
    for i in issues:
        i['id'] = i.get('_id')
    return issues


@router.post('/me/promote')
def promote_me(current_user: dict = Depends(get_current_user)):
    """Development helper: promote the current user to admin.

    Enabled only when the environment variable `ALLOW_SELF_PROMOTE` is set to 'true'.
    This is intentionally gated for safety — in production do NOT enable this.
    """
    if os.environ.get('ALLOW_SELF_PROMOTE', '').lower() != 'true':
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Self-promotion is disabled on this server")

    users_col.update_one({'_id': current_user.get('id')}, {'$set': {'is_admin': True, 'role': 'admin'}})
    user = users_col.find_one({'_id': current_user.get('id')})
    user['id'] = user.get('_id')
    return {'success': True, 'user': user}

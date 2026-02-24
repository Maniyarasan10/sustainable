from fastapi import APIRouter, Depends, HTTPException, status
from models import schemas
from utils.auth import create_access_token
from db_mongo import users_col
from datetime import datetime
import uuid

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=schemas.AuthResponse)
def register(user_data: schemas.UserCreate):
    """Register a new user (MongoDB)"""
    print(f"[AUTH] Register request: mobile={user_data.mobile}, name={user_data.name}")
    # Check if mobile number already exists
    existing_user = users_col.find_one({"mobile": user_data.mobile})
    if existing_user:
        print(f"[AUTH] Mobile {user_data.mobile} already registered")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mobile number already registered"
        )

    user_id = str(uuid.uuid4())
    doc = {
        "_id": user_id,
        "name": user_data.name,
        "mobile": user_data.mobile,
        "dob": user_data.dob,
        "gender": user_data.gender,
        "address": user_data.address,
        "avatar": getattr(user_data, 'avatar', None),
        # default role for newly registered users
        "role": "user",
        "is_admin": False,
        "created_at": datetime.utcnow()
    }
    users_col.insert_one(doc)
    print(f"[AUTH] User registered successfully: {user_id}")
    access_token = create_access_token(data={"sub": user_id})
    doc['id'] = doc['_id']
    return {"user": doc, "token": access_token}


@router.post("/login", response_model=schemas.AuthResponse)
def login(login_data: schemas.UserLogin):
    """Login with mobile number (MongoDB)"""
    print(f"[AUTH] Login request: mobile={login_data.mobile}")
    user = users_col.find_one({"mobile": login_data.mobile})
    if not user:
        print(f"[AUTH] User not found for mobile: {login_data.mobile}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found. Please register first."
        )
    print(f"[AUTH] User found: {user.get('_id')}")
    access_token = create_access_token(data={"sub": user.get('_id') or user.get('_id')})
    user['id'] = user.get('_id')
    print(f"[AUTH] Token generated for user: {user.get('_id')}")
    return {"user": user, "token": access_token}
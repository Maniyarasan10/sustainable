from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum


class IssueStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    PENDING = "pending"
    SOLVED = "solved"
    CLOSED = "closed"
    REVIEW = "review"
    VERIFIED = "verified"
    ON_PROCESSING = "on_processing"


class VoteType(str, Enum):
    UP = "up"
    DOWN = "down"


# User Schemas
class UserBase(BaseModel):
    name: str
    mobile: str
    dob: Optional[str] = None
    gender: Optional[str] = None
    address: Optional[str] = None
    avatar: Optional[str] = None


class UserCreate(UserBase):
    pass


class UserLogin(BaseModel):
    mobile: str


class User(UserBase):
    id: str
    created_at: datetime

    class Config:
        from_attributes = True


# Location Schema
class Location(BaseModel):
    latitude: float
    longitude: float
    address: Optional[str] = None


# Issue Schemas
class IssueBase(BaseModel):
    title: str
    description: str
    location: Location


class IssueCreate(IssueBase):
    pass


class Issue(BaseModel):
    id: str
    user_id: str
    user_name: str
    title: str
    description: str
    location: Location
    media_url: Optional[str] = None
    media_type: Optional[str] = None
    upvotes: int
    downvotes: int
    total_votes: int
    user_vote: Optional[str] = None
    status: IssueStatus
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# Vote Schema
class VoteInput(BaseModel):
    issue_id: str
    vote_type: VoteType


# Auth Response
class AuthResponse(BaseModel):
    user: User
    token: str
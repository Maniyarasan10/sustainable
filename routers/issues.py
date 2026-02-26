from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, BackgroundTasks, Body
from typing import List, Optional
from utils.auth import get_current_user
from db_mongo import issues_col, votes_col, users_col, notifications_col
from models import schemas
from datetime import datetime
import uuid
from pathlib import Path
from utils import storage
from datetime import timezone

router = APIRouter(prefix="/issues", tags=["Issues"])


# Simple offensive-content detector (bad words / abuse etc.)
# NOTE: adjust this list to match your context or plug in a stronger model later.
BAD_WORDS = [
    # basic insults
    "idiot",
    "stupid",
    "dumb",
    "fool",
    "moron",
    "loser",
    "jerk",
    "creep",
    "weird",
    "annoying",

    # mild abusive language
    "abuse",
    "trash",
    "nonsense",
    "useless",
    "pathetic",
    "ridiculous",
    "silly",
    "lazy",
    "ignorant",

    # frustration / rude tone
    "shut up",
    "get lost",
    "go away",
    "what the hell",
    "damn",
    "crap",

    # disrespectful terms
    "fake",
    "liar",
    "cheater",
    "scammer",
    "fraud",

    # negative attitude
    "hate",
    "worst",
    "boring",
    "mess",
    "broken",

    # casual online toxicity
    "noob",
    "clown",
    "toxic",
    "spam",
    "garbage",
]


SENSITIVE_KEYWORDS = [
    "electricity",
    "power cut",
    "powercut",
    "power outage",
    "current gone",
    "no power",
    "transformer",
    "short circuit",
    "fire",
    "shock",
    "accident",
]


def analyze_offensive_text(text: str) -> dict:
    """Simulated NLP output for offensive content using keyword matching.

    Returns:
      { is_offensive: bool, matches: [str], score: float }
    """
    if not text:
        return {"is_offensive": False, "matches": [], "score": 0.0}

    t = text.lower()
    matches = []
    for w in BAD_WORDS:
        ww = (w or "").lower().strip()
        if not ww:
            continue
        if ww in t:
            matches.append(w)

    # simple score: more matches => higher score, cap at 1.0
    score = min(1.0, len(matches) / 5.0)
    return {"is_offensive": len(matches) > 0, "matches": matches, "score": float(score)}


def is_offensive_text(text: str) -> bool:
    return bool(analyze_offensive_text(text).get("is_offensive"))


def calculate_issue_response(issue: dict, current_user_id: Optional[str] = None):
    """Build issue response including vote counts and user vote"""
    issue_id = issue.get('_id')
    upvotes = votes_col.count_documents({"issue_id": issue_id, "vote_type": "up"})
    downvotes = votes_col.count_documents({"issue_id": issue_id, "vote_type": "down"})

    user_vote = None
    if current_user_id:
        uv = votes_col.find_one({"issue_id": issue_id, "user_id": current_user_id})
        if uv:
            user_vote = uv.get('vote_type')

    user = users_col.find_one({"_id": issue.get('user_id')})
    user_name = user.get('name') if user else None
    user_avatar = user.get('avatar') if user else None

    title = issue.get('title') or ''
    description = issue.get('description') or ''

    # prefer stored simulated NLP result if present, else compute on the fly
    offensive = issue.get("offensive") or {}
    if not isinstance(offensive, dict) or "is_offensive" not in offensive:
        offensive = analyze_offensive_text(f"{title} {description}")

    # priority: sensitive keywords like electricity/power
    is_priority = bool(issue.get("is_priority"))
    if not is_priority:
        text_low = f"{title} {description}".lower()
        for kw in SENSITIVE_KEYWORDS:
            if kw in text_low:
                is_priority = True
                break

    admin_approved = bool(issue.get("admin_approved", False))

    return {
        "id": issue_id,
        "user_id": issue.get('user_id'),
        "user_name": user_name,
        "user_avatar": user_avatar,
        "title": issue.get('title'),
        "description": issue.get('description'),
        "location": {
            "latitude": issue.get('latitude'),
            "longitude": issue.get('longitude'),
            "address": issue.get('address')
        },
        # Provide both snake_case and camelCase keys for clients
        "media_url": issue.get('media_url'),
        "imageUrl": issue.get('media_url'),
        "media_type": issue.get('media_type'),
        "upvotes": upvotes,
        "downvotes": downvotes,
        "total_votes": upvotes - downvotes,
        "user_vote": user_vote,
        "status": issue.get('status', 'open'),
        "is_priority": is_priority,
        "is_offensive": bool(offensive.get("is_offensive")),
        "admin_approved": admin_approved,
        "offensive": {
            "score": offensive.get("score", 0.0),
            "matches": offensive.get("matches", []),
        },
        "created_at": issue.get('created_at'),
        "updated_at": issue.get('updated_at')
    }


@router.get("", response_model=List[schemas.Issue])
def get_all_issues(current_user: dict = Depends(get_current_user)):
    issues = list(issues_col.find())
    responses = [calculate_issue_response(i, current_user.get('id')) for i in issues]
    # Exclude offensive issues that haven't been admin-approved yet (they appear only in the admin offensive tab)
    responses = [r for r in responses if not r.get("is_offensive") or r.get("admin_approved")]
    # Sort: priority issues first, then by total_votes
    responses.sort(
        key=lambda x: (
            0 if x.get("is_priority") else 1,  # priority first
            -x.get('total_votes', 0),          # then by votes desc
        )
    )
    return responses


@router.get("/offensive", response_model=List[schemas.Issue])
def get_offensive_issues(current_user: dict = Depends(get_current_user)):
    """
    Return issues whose title/description contain offensive language (bad words)
    and have not yet been admin-approved. Admin-approved issues are visible in the
    main feed and no longer appear here.
    """
    issues = list(issues_col.find())
    flagged = []
    for i in issues:
        # Skip already admin-approved issues
        if i.get("admin_approved"):
            continue
        title = i.get("title") or ""
        desc = i.get("description") or ""
        if is_offensive_text(title) or is_offensive_text(desc):
            flagged.append(i)

    responses = [calculate_issue_response(i, current_user.get('id')) for i in flagged]
    # Show newest first
    responses.sort(key=lambda x: x.get('created_at') or datetime.min, reverse=True)
    return responses


@router.get("/{issue_id}", response_model=schemas.Issue)
def get_issue(issue_id: str, current_user: dict = Depends(get_current_user)):
    # First try the standard issues collection
    issue = issues_col.find_one({"_id": issue_id})
    if not issue:
        # Fallback to help_requests collection (for the Help section cards)
        from db_mongo import help_col
        issue = help_col.find_one({"_id": issue_id})
        if not issue:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found")
        # Ensure it has a title for the Issue schema (help requests use description only)
        if not issue.get('title'):
            issue['title'] = "Community Help Request"
            
    return calculate_issue_response(issue, current_user.get('id'))


@router.post("", response_model=schemas.Issue)
def create_issue(
    title: str = Form(...),
    description: str = Form(...),
    latitude: float = Form(...),
    longitude: float = Form(...),
    address: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    current_user: dict = Depends(get_current_user),
    background_tasks: BackgroundTasks = None,
):
    issue_id = str(uuid.uuid4())
    media_url = None
    media_type = None
    if file:
        # Upload to Cloudinary and store returned secure URL
        try:
            resp = storage.upload_file(file, folder='issues', public_id=issue_id)
            media_url = resp.get('secure_url') or resp.get('url')
            # Cloudinary reports resource_type (image/video) and content-type may still be available
            media_type = file.content_type or resp.get('resource_type')
        except Exception:
            # Fallback to local saving if Cloudinary is not configured/available
            uploads_dir = Path('static/uploads')
            uploads_dir.mkdir(parents=True, exist_ok=True)
            filename = f"{issue_id}_{file.filename}"
            save_path = uploads_dir / filename
            with save_path.open('wb') as buffer:
                buffer.write(file.file.read())
            media_url = f"/static/uploads/{filename}"
            media_type = file.content_type

    doc = {
        '_id': issue_id,
        'user_id': current_user.get('id'),
        'title': title,
        'description': description,
        'latitude': latitude,
        'longitude': longitude,
        'address': address,
        'media_url': media_url,
        'media_type': media_type,
        'status': 'open',
        # simulated NLP (keyword matching) output for moderation
        'offensive': analyze_offensive_text(f"{title} {description}"),
        'created_at': datetime.now(timezone.utc),
        'updated_at': datetime.now(timezone.utc),
    }
    issues_col.insert_one(doc)
    return calculate_issue_response(issues_col.find_one({"_id": issue_id}), current_user.get('id'))


@router.post("/vote", response_model=schemas.Issue)
def vote_on_issue(vote_data: schemas.VoteInput, current_user: dict = Depends(get_current_user)):
    issue = issues_col.find_one({"_id": vote_data.issue_id})
    if not issue:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found")

    existing = votes_col.find_one({"issue_id": vote_data.issue_id, "user_id": current_user.get('id')})
    notify = False
    action_message = None
    actor_name = current_user.get('name') or current_user.get('mobile') or 'Someone'
    if existing:
        if existing.get('vote_type') == vote_data.vote_type:
            # user removed their vote
            votes_col.delete_one({"_id": existing.get('_id')})
            notify = False
        else:
            # changed vote type
            votes_col.update_one({"_id": existing.get('_id')}, {"$set": {"vote_type": vote_data.vote_type}})
            notify = True
            action_message = f"{actor_name} changed their vote to {vote_data.vote_type}"
    else:
        votes_col.insert_one({"_id": str(uuid.uuid4()), "issue_id": vote_data.issue_id, "user_id": current_user.get('id'), "vote_type": vote_data.vote_type})
        notify = True
        action_message = f"{actor_name} {'upvoted' if vote_data.vote_type == 'up' else 'downvoted'} your issue"

    # create a notification for the issue owner when someone else votes (insert or change)
    try:
        owner_id = issue.get('user_id')
        actor_id = current_user.get('id')
        if notify and owner_id and owner_id != actor_id:
            note = {
                '_id': str(uuid.uuid4()),
                'user_id': owner_id,
                'title': 'Vote update on your issue',
                'message': action_message,
                'metadata': {'issueId': vote_data.issue_id, 'vote_type': vote_data.vote_type},
                'read': False,
                'created_at': datetime.utcnow()
            }
            notifications_col.insert_one(note)
    except Exception:
        # don't block vote operation on notification errors
        pass

    # return refreshed issue response
    issue = issues_col.find_one({"_id": vote_data.issue_id})
    return calculate_issue_response(issue, current_user.get('id'))


@router.delete("/{issue_id}")
def delete_issue(issue_id: str, current_user: dict = Depends(get_current_user)):
    issue = issues_col.find_one({"_id": issue_id})
    if not issue:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found")
    if issue.get('user_id') != current_user.get('id'):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only delete your own issues")
    issues_col.delete_one({"_id": issue_id})
    votes_col.delete_many({"issue_id": issue_id})
    return {"message": "Issue deleted successfully"}


@router.post("/{issue_id}/approve")
def admin_approve_issue(issue_id: str, current_user: dict = Depends(get_current_user)):
    """
    Admin endpoint: approve an offensive issue so it becomes visible in the frontend app.
    Clears the offensive flag and marks it as admin-approved.
    """
    issue = issues_col.find_one({"_id": issue_id})
    if not issue:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found")

    issues_col.update_one(
        {"_id": issue_id},
        {
            "$set": {
                "offensive": {"is_offensive": False, "matches": [], "score": 0.0},
                "admin_approved": True,
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )
    updated = issues_col.find_one({"_id": issue_id})
    return calculate_issue_response(updated, current_user.get("id"))


@router.delete("/{issue_id}/admin")
def admin_delete_issue(issue_id: str, current_user: dict = Depends(get_current_user)):
    """
    Admin endpoint: permanently delete any issue (including offensive ones) without ownership check.
    """
    issue = issues_col.find_one({"_id": issue_id})
    if not issue:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found")
    issues_col.delete_one({"_id": issue_id})
    votes_col.delete_many({"issue_id": issue_id})
    return {"message": "Issue removed by admin successfully"}


@router.patch("/{issue_id}/edit", response_model=schemas.Issue)
def edit_issue(
    issue_id: str,
    body: dict = Body(...),
    current_user: dict = Depends(get_current_user),
):
    """Edit issue content (title / description / address). Only owner can edit."""
    issue = issues_col.find_one({"_id": issue_id})
    if not issue:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found")
    if issue.get('user_id') != current_user.get('id'):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only edit your own issues")

    fields = {}
    title = body.get("title")
    description = body.get("description")
    address = body.get("address")

    if title is not None:
        fields["title"] = title
    if description is not None:
        fields["description"] = description
    if address is not None:
        fields["address"] = address

    if not fields:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")

    fields["updated_at"] = datetime.utcnow()
    issues_col.update_one({"_id": issue_id}, {"$set": fields})
    updated_issue = issues_col.find_one({"_id": issue_id})
    return calculate_issue_response(updated_issue, current_user.get('id'))


@router.patch("/{issue_id}", response_model=dict)
def update_issue_status(issue_id: str, new_status: str, current_user: dict = Depends(get_current_user)):
    """Update issue status (e.g., pending -> resolved)"""
    issue = issues_col.find_one({"_id": issue_id})
    if not issue:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found")
    
    # Allow any authenticated user to update status (admin privilege could be checked here)
    valid_statuses = ['open', 'pending', 'in_progress', 'resolved', 'closed', 'solved', 'review', 'verified', 'on_processing']
    if new_status not in valid_statuses:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid status. Must be one of: {valid_statuses}")
    
    issues_col.update_one({"_id": issue_id}, {"$set": {"status": new_status, "updated_at": datetime.utcnow()}})
    updated_issue = issues_col.find_one({"_id": issue_id})
    # notify owner about status change if actor is not owner
    try:
        owner_id = updated_issue.get('user_id')
        actor_id = current_user.get('id')
        if owner_id and actor_id and owner_id != actor_id:
            actor_name = current_user.get('name') or current_user.get('mobile') or 'Someone'
            note = {
                '_id': str(uuid.uuid4()),
                'user_id': owner_id,
                'title': 'Issue status updated',
                'message': f"{actor_name} changed the status of your issue to {new_status}",
                'metadata': {'issueId': issue_id, 'status': new_status},
                'read': False,
                'created_at': datetime.utcnow()
            }
            notifications_col.insert_one(note)
    except Exception:
        pass
    return calculate_issue_response(updated_issue, current_user.get('id'))

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, BackgroundTasks
from typing import List, Optional
from utils.auth import get_current_user
from db_mongo import issues_col, votes_col, users_col, notifications_col
from models import schemas
from datetime import datetime
import uuid
from pathlib import Path
from utils.nlp_service import analyze_issue_text
from utils import storage
from routers.esp32 import send_to_esp32, relay_states
from db_mongo import devices_col
from utils import nlp

router = APIRouter(prefix="/issues", tags=["Issues"])


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

    return {
        "id": issue_id,
        "user_id": issue.get('user_id'),
        "user_name": user_name,
        "title": issue.get('title'),
        "description": issue.get('description'),
        "location": {
            "latitude": issue.get('latitude'),
            "longitude": issue.get('longitude'),
            "address": issue.get('address')
        },
        "imageUrl": issue.get('media_url'),
        "media_type": issue.get('media_type'),
        "upvotes": upvotes,
        "downvotes": downvotes,
        "total_votes": upvotes - downvotes,
        "user_vote": user_vote,
        "status": issue.get('status', 'open'),
        "created_at": issue.get('created_at'),
        "updated_at": issue.get('updated_at')
    }


@router.get("", response_model=List[schemas.Issue])
def get_all_issues(current_user: dict = Depends(get_current_user)):
    issues = list(issues_col.find())
    responses = [calculate_issue_response(i, current_user.get('id')) for i in issues]
    responses.sort(key=lambda x: x['total_votes'], reverse=True)
    return responses


@router.get("/{issue_id}", response_model=schemas.Issue)
def get_issue(issue_id: str, current_user: dict = Depends(get_current_user)):
    issue = issues_col.find_one({"_id": issue_id})
    if not issue:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found")
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
        'nlp': None,
        'created_at': datetime.utcnow(),
        'updated_at': datetime.utcnow(),
    }
    # run lightweight NLP to detect device/state (uses DistilBERT if available)
    try:
        nlp_result = analyze_issue_text(description)
        doc['nlp'] = nlp_result
        # If NLP identifies a light and it's "off" then auto-flag and notify front admin(s)
        if nlp_result.get('device') and 'light' in nlp_result.get('device') and nlp_result.get('state') == 'off':
            doc['status'] = 'pending'
    except Exception:
        # non-fatal; continue with insertion
        pass

    issues_col.insert_one(doc)

    # schedule background auto-toggle if NLP detected a device offline
    async def _auto_toggle(issue_id: str, nlp_result: dict, reporter_id: str):
        try:
            device = nlp_result.get('device')
            device_id = nlp_result.get('device_id')
            if not device or 'light' not in device:
                return

            # determine relay number: prefer explicit id, otherwise map to 1
            try:
                relay_num = int(device_id) if device_id else 1
            except Exception:
                relay_num = 1

            relay_key = f"relay{relay_num}"
            # check current known relay state
            current_state = relay_states.get(relay_key)
            if current_state is True:
                # already on — update issue with note
                issues_col.update_one({"_id": issue_id}, {"$set": {"updated_at": datetime.utcnow()}})
                return

            # attempt to turn on via ESP32
            success, message = await send_to_esp32(f"/relay{relay_num}/on")
            if success:
                relay_states[relay_key] = True
                # update issue to reflect auto action
                issues_col.update_one({"_id": issue_id}, {"$set": {"status": "in_progress", "auto_action": {"action": "turned_on", "by": "system", "relay": relay_num, "message": message, "timestamp": datetime.utcnow()}}})

                # notify reporter
                try:
                    note_reporter = {
                        '_id': str(uuid.uuid4()),
                        'user_id': reporter_id,
                        'title': 'Automated action: Light turned on',
                        'message': f"We detected your reported light (relay {relay_num}) was off and turned it on automatically.",
                        'metadata': {'issueId': issue_id, 'relay': relay_num},
                        'read': False,
                        'created_at': datetime.utcnow()
                    }
                    notifications_col.insert_one(note_reporter)
                except Exception:
                    pass

                # notify admins
                try:
                    admins = list(users_col.find({'role': {'$in': ['front_admin', 'admin']}}))
                    if not admins:
                        admins = list(users_col.find({'is_admin': True}))
                    for a in admins:
                        try:
                            note_admin = {
                                '_id': str(uuid.uuid4()),
                                'user_id': a.get('_id'),
                                'title': 'Automated action performed',
                                'message': f"System turned on relay {relay_num} for issue {issue_id}.",
                                'metadata': {'issueId': issue_id, 'relay': relay_num},
                                'read': False,
                                'created_at': datetime.utcnow()
                            }
                            notifications_col.insert_one(note_admin)
                        except Exception:
                            pass
                except Exception:
                    pass

        except Exception:
            # swallow background exceptions
            pass

    if doc.get('nlp') and doc['nlp'].get('device') and doc['nlp'].get('state') == 'off' and background_tasks is not None:
        background_tasks.add_task(_auto_toggle, issue_id, doc['nlp'], current_user.get('id'))

    # If NLP detected a front-device outage, notify front admin(s) and reporter
    try:
        if doc.get('nlp') and doc['nlp'].get('device') and doc['nlp'].get('state') == 'off':
            # create a confirmation notification for reporter
            note_reporter = {
                '_id': str(uuid.uuid4()),
                'user_id': current_user.get('id'),
                'title': 'Automated detection: device offline',
                'message': f"We detected that your reported {doc['nlp'].get('device')} appears to be offline. We've forwarded this to the front admin.",
                'metadata': {'issueId': issue_id, 'nlp': doc['nlp']},
                'read': False,
                'created_at': datetime.utcnow()
            }
            notifications_col.insert_one(note_reporter)

            # notify users marked as admins/front_admins in users collection
            admins = list(users_col.find({'role': {'$in': ['front_admin', 'admin']}}))
            if not admins:
                # fallback: any user with is_admin flag true
                admins = list(users_col.find({'is_admin': True}))

            for a in admins:
                try:
                    note_admin = {
                        '_id': str(uuid.uuid4()),
                        'user_id': a.get('_id'),
                        'title': 'Citizen report: device offline',
                        'message': f"Issue {issue_id}: reported {doc['nlp'].get('device')} appears offline. Please review.",
                        'metadata': {'issueId': issue_id, 'reporter': current_user.get('id'), 'nlp': doc['nlp']},
                        'read': False,
                        'created_at': datetime.utcnow()
                    }
                    notifications_col.insert_one(note_admin)
                except Exception:
                    pass
    except Exception:
        pass
    # run automated NLP classification to detect device state (on/off)
    try:
        text = f"{title} {description}"
        cl = nlp.classify_state(text)
        detected_state = cl.get('state')
        # if detected OFF, mark or notify admin and inform reporter
        if detected_state == 'off':
            # update issue status to pending (automated)
            issues_col.update_one({"_id": issue_id}, {"$set": {"status": "pending", "updated_at": datetime.utcnow()}})

            # try to find a front admin: common possible fields
            admin = users_col.find_one({"role": "front_admin"}) or users_col.find_one({"role": "admin"}) or users_col.find_one({"is_admin": True})
            admin_id = None
            if admin:
                admin_id = admin.get('_id')
            else:
                # allow override via env var FRONT_ADMIN_ID
                admin_id = None
                from os import getenv
                env_admin = getenv('FRONT_ADMIN_ID')
                if env_admin:
                    admin_id = env_admin

            # notify admin
            if admin_id:
                note = {
                    '_id': str(uuid.uuid4()),
                    'user_id': admin_id,
                    'title': 'Automated alert: reported light issue',
                    'message': f"Issue '{title}' detected as OFF by automated NLP (reporter: {current_user.get('name')}).",
                    'metadata': {'issueId': issue_id, 'detected_state': cl},
                    'read': False,
                    'created_at': datetime.utcnow()
                }
                notifications_col.insert_one(note)

            # inform reporter via notification
            try:
                note2 = {
                    '_id': str(uuid.uuid4()),
                    'user_id': current_user.get('id'),
                    'title': 'Automated status detected',
                    'message': f"We detected your reported device appears to be OFF; front admin has been notified.",
                    'metadata': {'issueId': issue_id, 'detected_state': cl},
                    'read': False,
                    'created_at': datetime.utcnow()
                }
                notifications_col.insert_one(note2)
            except Exception:
                pass
    except Exception:
        # don't block issue creation on NLP errors
        pass

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


@router.patch("/{issue_id}", response_model=dict)
def update_issue_status(issue_id: str, status: str, current_user: dict = Depends(get_current_user)):
    """Update issue status (e.g., pending -> resolved)"""
    issue = issues_col.find_one({"_id": issue_id})
    if not issue:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found")
    
    # Allow any authenticated user to update status (admin privilege could be checked here)
    valid_statuses = ['open', 'pending', 'in_progress', 'resolved', 'closed', 'solved', 'review', 'verified', 'on_processing']
    if status not in valid_statuses:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid status. Must be one of: {valid_statuses}")
    
    issues_col.update_one({"_id": issue_id}, {"$set": {"status": status, "updated_at": datetime.utcnow()}})
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
                'message': f"{actor_name} changed the status of your issue to {status}",
                'metadata': {'issueId': issue_id, 'status': status},
                'read': False,
                'created_at': datetime.utcnow()
            }
            notifications_col.insert_one(note)
    except Exception:
        pass
    return calculate_issue_response(updated_issue, current_user.get('id'))

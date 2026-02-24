from fastapi import APIRouter, Depends
from utils.auth import get_current_user
from db_mongo import users_col, issues_col, votes_col
from typing import List

router = APIRouter(prefix="/leaderboard", tags=["Leaderboard"])


@router.get("", response_model=List[dict])
def get_leaderboard(current_user: dict = Depends(get_current_user)):
    users = list(users_col.find())
    leaderboard = []
    for u in users:
        user_id = u.get('_id')
        issues_count = issues_col.count_documents({"user_id": user_id})
        # compute upvotes on this user's issues
        user_issues = list(issues_col.find({"user_id": user_id}, {"_id": 1}))
        upvotes = 0
        for issue in user_issues:
            iid = issue.get('_id')
            upvotes += votes_col.count_documents({"issue_id": iid, "vote_type": "up"})
        score = issues_count + upvotes
        leaderboard.append({
            "user_id": user_id,
            "name": u.get('name'),
            "avatar": u.get('avatar'),
            "issues_count": issues_count,
            "upvotes": upvotes,
            "score": score,
        })
    leaderboard.sort(key=lambda x: x['score'], reverse=True)
    return leaderboard

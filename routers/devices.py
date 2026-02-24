from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from utils.auth import get_current_user
from db_mongo import devices_col
from routers.esp32 import relay_states, RELAY_LABELS
from datetime import datetime

router = APIRouter(prefix="/devices", tags=["Devices"])


@router.get("", response_model=List[dict])
def list_devices(current_user: dict = Depends(get_current_user)):
    # return configured schedules and current state
    devices = []
    for k, v in relay_states.items():
        try:
            num = int(k.replace('relay', ''))
        except Exception:
            continue
        schedule = devices_col.find_one({'relay': num}) or {}
        devices.append({
            'relay': num,
            'label': RELAY_LABELS.get(num, f'relay{num}'),
            'state': v,
            'default_on_time': schedule.get('default_on_time'),
            'default_off_time': schedule.get('default_off_time')
        })
    return devices


@router.get("/{relay_num}")
def get_device(relay_num: int, current_user: dict = Depends(get_current_user)):
    if relay_num not in RELAY_LABELS:
        raise HTTPException(status_code=404, detail="Relay not found")
    schedule = devices_col.find_one({'relay': relay_num}) or {}
    return {
        'relay': relay_num,
        'label': RELAY_LABELS[relay_num],
        'state': relay_states.get(f'relay{relay_num}'),
        'default_on_time': schedule.get('default_on_time'),
        'default_off_time': schedule.get('default_off_time')
    }


@router.post("/{relay_num}/schedule")
def set_schedule(relay_num: int, body: dict, current_user: dict = Depends(get_current_user)):
    # Allow any authenticated user to set schedule
    on_time = body.get('default_on_time')
    off_time = body.get('default_off_time')
    if not on_time and not off_time:
        raise HTTPException(status_code=400, detail="Provide at least one of default_on_time or default_off_time")

    doc = {'relay': relay_num, 'label': RELAY_LABELS.get(relay_num, f'relay{relay_num}'), 'updated_at': datetime.utcnow()}
    if on_time:
        doc['default_on_time'] = on_time
    if off_time:
        doc['default_off_time'] = off_time

    devices_col.update_one({'relay': relay_num}, {'$set': doc}, upsert=True)
    return {'success': True, 'relay': relay_num, 'default_on_time': on_time, 'default_off_time': off_time}

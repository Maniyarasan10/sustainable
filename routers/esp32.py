from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import logging

logger = logging.getLogger("esp32")

router = APIRouter(prefix="/esp32", tags=["ESP32"])

# In-memory relay state (can be moved to MongoDB later)
relay_states = {
    "relay1": False,
    "relay2": False,
    "relay3": False,
}

RELAY_LABELS = {1: "Light", 2: "Water Tank", 3: "Fan"}


class RelayCommand(BaseModel):
    relay: int
    action: str


# 🔹 ESP32 polls this endpoint every 3 seconds
@router.get("/status")
async def esp32_status():
    """
    Return current relay states for ESP32 to poll.
    ESP32 GET /api/esp32/status → applies state to GPIO pins.
    """
    return relay_states


# 🔹 Mobile app calls this to control relays
@router.post("/relay")
async def set_relay(cmd: RelayCommand):
    """
    Control relay via JSON request: { "relay": 1, "action": "on" }
    Mobile app → Backend (updates state)
    Backend → ESP32 polls and applies changes
    """
    if cmd.relay not in (1, 2, 3):
        raise HTTPException(400, "Invalid relay number")

    if cmd.action not in ("on", "off"):
        raise HTTPException(400, "Invalid action")

    # Update state
    relay_states[f"relay{cmd.relay}"] = cmd.action == "on"
    
    logger.info("Relay %d set to %s", cmd.relay, cmd.action)

    return {
        "success": True,
        "relay": cmd.relay,
        "state": cmd.action,
        "label": RELAY_LABELS[cmd.relay],
    }


# Alternative: path-based control
@router.post("/relay/{relay_num}/{action}")
async def control_relay_path(relay_num: int, action: str):
    """Alternative path-based control: POST /api/esp32/relay/1/on"""
    if relay_num not in (1, 2, 3):
        raise HTTPException(400, "Invalid relay number")
    if action not in ("on", "off"):
        raise HTTPException(400, "Invalid action")

    relay_states[f"relay{relay_num}"] = action == "on"
    
    logger.info("Relay %d set to %s (path-based)", relay_num, action)

    return {
        "success": True,
        "relay": relay_num,
        "state": action,
        "label": RELAY_LABELS[relay_num],
    }


# Control all relays at once
@router.post("/all/{action}")
async def control_all(action: str):
    """Control all relays: POST /api/esp32/all/on"""
    if action not in ("on", "off"):
        raise HTTPException(400, "Invalid action")

    results = []
    for relay_num in [1, 2, 3]:
        relay_states[f"relay{relay_num}"] = action == "on"
        
        results.append({
            "relay": relay_num,
            "label": RELAY_LABELS[relay_num],
            "state": action,
        })

    logger.info("All relays set to %s", action)
    return {"action": action, "results": results}

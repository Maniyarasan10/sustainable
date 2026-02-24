from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel
import httpx
import logging
import os

logger = logging.getLogger("esp32")

router = APIRouter(prefix="/esp32", tags=["ESP32"])

# ── ESP32 IP / ngrok URL ──────────────────────────────────────────────────────
# Load from environment variable ESP32_URL, default to actual device IP
ESP32_URL = os.getenv("ESP32_URL")
logger.info("ESP32_URL initialized to: %s", ESP32_URL)

# ── Relay state tracking ──────────────────────────────────────────────────────
relay_states: dict[str, bool] = {
    "relay1": False,
    "relay2": False,
    "relay3": False,
}

RELAY_LABELS = {1: "Light", 2: "Water Tank", 3: "Fan"}


# ── Pydantic models ───────────────────────────────────────────────────────────
class UpdateUrlRequest(BaseModel):
    url: str


class RelayStatusResponse(BaseModel):
    relay1: bool
    relay2: bool
    relay3: bool
    labels: dict[str, str]


# ── Helper ────────────────────────────────────────────────────────────────────
async def send_to_esp32(path: str) -> tuple[bool, str]:
    """Send request to ESP32 device and return (success, message).

    Try GET first (most firmwares use GET), but if the device responds with
    a non-200 status or times out, attempt POST as a fallback. Log both
    attempts for debugging.
    """
    url = f"{ESP32_URL}{path}"
    async with httpx.AsyncClient(timeout=6.0) as client:
        # Attempt GET
        try:
            resp = await client.get(url)
            body = resp.text
            logger.info("ESP32 GET %s -> %s %s", url, resp.status_code, resp.reason_phrase)
            logger.debug("ESP32 GET response body: %s", body)
            if resp.status_code == 200:
                return True, body
        except httpx.RequestError as e:
            logger.warning("ESP32 GET request failed %s: %s", url, str(e))

        # Fallback to POST
        try:
            resp = await client.post(url)
            body = resp.text
            logger.info("ESP32 POST %s -> %s %s", url, resp.status_code, resp.reason_phrase)
            logger.debug("ESP32 POST response body: %s", body)
            if resp.status_code == 200:
                return True, body
            return False, f"POST {resp.status_code} {resp.reason_phrase}: {body}"
        except httpx.RequestError as e:
            logger.error("ESP32 POST request failed %s: %s", url, str(e))
            return False, str(e)


# ── Routes ────────────────────────────────────────────────────────────────────
@router.get("/status", response_model=RelayStatusResponse)
async def get_status():
    return {
        "relay1": relay_states["relay1"],
        "relay2": relay_states["relay2"],
        "relay3": relay_states["relay3"],
        "labels": {
            "relay1": "Light",
            "relay2": "Water Tank",
            "relay3": "Fan",
        },
    }


@router.post("/relay/{relay_num}/{action}")
async def control_relay(relay_num: int = Path(..., ge=1, le=3, description="Relay number (1–3)"), action: str = Path(..., description="'on' or 'off'")):
    relay_key = f"relay{relay_num}"
    path = f"/relay{relay_num}/{action}"

    # validate action explicitly to avoid Path-level validation mismatches
    if action not in ("on", "off"):
        raise HTTPException(status_code=400, detail="action must be 'on' or 'off'")

    success, message = await send_to_esp32(path)

    if not success:
        raise HTTPException(status_code=502, detail=f"Failed to reach ESP32: {message}")

    relay_states[relay_key] = action == "on"
    return {"success": True, "relay": relay_num, "state": action, "label": RELAY_LABELS[relay_num]}


@router.post("/all/{action}")
async def control_all(action: str = Path(..., description="'on' or 'off'")):
    # validate action explicitly to avoid Path-level validation mismatches
    if action not in ("on", "off"):
        raise HTTPException(status_code=400, detail="action must be 'on' or 'off'")

    results = []
    for relay_num in [1, 2, 3]:
        path = f"/relay{relay_num}/{action}"
        success, message = await send_to_esp32(path)
        relay_key = f"relay{relay_num}"
        if success:
            relay_states[relay_key] = action == "on"
        results.append({
            "relay": relay_num,
            "label": RELAY_LABELS[relay_num],
            "success": success,
            "message": message,
        })

    return {"action": action, "results": results}


@router.get("/health")
async def health_check():
    """Check if the backend can reach the ESP32 device.
    
    Returns the current ESP32_URL and connection status.
    Use this to diagnose why relay control is failing.
    """
    url = f"{ESP32_URL}/"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
            logger.info("ESP32 health check %s -> %s", url, resp.status_code)
            return {
                "esp32_url": ESP32_URL,
                "reachable": resp.status_code == 200,
                "status_code": resp.status_code,
                "reason": resp.reason_phrase,
                "message": "ESP32 is reachable and responding" if resp.status_code == 200 else "ESP32 responded but with non-200 status"
            }
    except httpx.RequestError as e:
        logger.error("ESP32 health check failed %s: %s", url, str(e))
        return {
            "esp32_url": ESP32_URL,
            "reachable": False,
            "error": str(e),
            "message": "Cannot reach ESP32. Check IP address, network connectivity, and that the device is powered on."
        }


@router.post("/update-url")
async def update_esp32_url(body: UpdateUrlRequest):
    global ESP32_URL
    ESP32_URL = body.url.rstrip("/")
    logger.info("ESP32 URL updated to %s", ESP32_URL)
    return {"success": True, "url": ESP32_URL}

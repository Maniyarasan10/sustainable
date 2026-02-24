from typing import Dict, Optional
import re


def analyze_issue_text(text: str) -> Dict:
    """Light-weight analyzer using DistilBERT (if available) with regex fallback.

    Returns: { device: Optional[str], device_id: Optional[str], state: 'on'|'off'|'unknown', confidence: float }
    """
    if not text:
        return {"device": None, "device_id": None, "state": "unknown", "confidence": 0.0}

    text_l = text.lower()

    # simple device detection
    devices = ["light", "lamp", "fan", "ac", "air conditioner", "heater"]
    device_found: Optional[str] = None
    for d in devices:
        if d in text_l:
            device_found = d
            break

    # try to parse an identifier e.g. "light 1" or "light-1" or "light1"
    device_id = None
    if device_found:
        m = re.search(rf"{re.escape(device_found)}\s*-?\s*(\d+)", text_l)
        if m:
            device_id = m.group(1)

    # heuristic patterns
    off_patterns = ["not working", "broken", "off", "no power", "doesn't work", "doesnt work", "not turning on", "no electricity"]
    on_patterns = ["working", "turn on", "turned on", "is on", "switched on", "on"]

    state = "unknown"
    for p in off_patterns:
        if p in text_l:
            state = "off"
            break

    if state == "unknown":
        for p in on_patterns:
            if p in text_l:
                state = "on"
                break

    confidence = 0.0
    # Try to use HuggingFace DistilBERT sentiment model to corroborate
    try:
        from transformers import pipeline

        nlp = pipeline("sentiment-analysis", model="distilbert-base-uncased-finetuned-sst-2-english")
        # limit length to avoid very long inputs
        out = nlp(text[:512])[0]
        label = out.get("label", "")
        score = float(out.get("score", 0.0))
        confidence = score
        if state == "unknown":
            if label.lower() == "negative":
                state = "off"
            elif label.lower() == "positive":
                state = "on"
    except Exception:
        # transformers may not be installed in the environment; fallback to regex
        pass

    return {"device": device_found, "device_id": device_id, "state": state, "confidence": confidence}

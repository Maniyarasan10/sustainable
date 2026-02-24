import os
from typing import Dict

_classifier = None

def _get_classifier():
    global _classifier
    if _classifier is None:
        try:
            # Use a DistilBERT-based NLI model for zero-shot classification
            from transformers import pipeline
            model_name = os.getenv('NLP_MODEL', 'typeform/distilbert-base-uncased-mnli')
            _classifier = pipeline('zero-shot-classification', model=model_name)
        except Exception:
            _classifier = None
    return _classifier


def classify_state(text: str) -> Dict:
    """Classify whether a reported device (e.g., light) is 'off', 'on' or 'unknown'.

    Returns dict: {state: 'off'|'on'|'unknown', 'label':top_label, 'score':top_score}
    This uses a DistilBERT-based zero-shot classifier (NLI) by default.
    """
    clf = _get_classifier()
    if not clf or not text:
        return {'state': 'unknown', 'label': None, 'score': 0.0}

    candidate_labels = ['off', 'on', 'not working', 'flickering', 'working']
    try:
        res = clf(text, candidate_labels=candidate_labels)
        top_label = res['labels'][0]
        top_score = float(res['scores'][0])
        if top_label in ['off', 'not working', 'flickering'] and top_score >= 0.6:
            return {'state': 'off', 'label': top_label, 'score': top_score}
        if top_label in ['on', 'working'] and top_score >= 0.6:
            return {'state': 'on', 'label': top_label, 'score': top_score}
        return {'state': 'unknown', 'label': top_label, 'score': top_score}
    except Exception:
        return {'state': 'unknown', 'label': None, 'score': 0.0}

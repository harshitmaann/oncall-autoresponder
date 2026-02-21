from app.core.schemas import Incident

def classify_incident(incident: Incident) -> dict:
    name = (incident.alertname or "").lower()

    if "crashloop" in name or "crash" in name:
        return {"type": "crashloop", "confidence": 0.7}
    if "oom" in name:
        return {"type": "oomkilled", "confidence": 0.7}
    if "5xx" in name or "error" in name:
        return {"type": "error_rate", "confidence": 0.6}
    if "latency" in name:
        return {"type": "latency", "confidence": 0.6}

    return {"type": "unknown", "confidence": 0.2}

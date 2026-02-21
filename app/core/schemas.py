from typing import Any, Dict, List, Optional
from pydantic import BaseModel

class AlertmanagerAlert(BaseModel):
    status: str
    labels: Dict[str, str] = {}
    annotations: Dict[str, str] = {}
    startsAt: Optional[str] = None
    endsAt: Optional[str] = None
    generatorURL: Optional[str] = None

class AlertmanagerPayload(BaseModel):
    receiver: Optional[str] = None
    status: str
    alerts: List[AlertmanagerAlert]
    groupLabels: Dict[str, str] = {}
    commonLabels: Dict[str, str] = {}
    commonAnnotations: Dict[str, str] = {}
    externalURL: Optional[str] = None
    version: Optional[str] = None
    groupKey: Optional[str] = None
    truncatedAlerts: Optional[int] = None

class Incident(BaseModel):
    incident_id: str
    source: str
    env: str
    title: str
    severity: str
    service: str
    namespace: str
    alertname: str
    started_at: Optional[str] = None
    raw: Dict[str, Any] = {}
    evidence: Dict[str, Any] = {}

import uuid
from datetime import datetime, timezone

from app.core.schemas import AlertmanagerPayload, Incident
from app.collectors.k8s_collector import K8sCollector
from app.integrations.slack_client import SlackNotifier
from app.storage.sqlite_store import IncidentStore
from app.runbooks.router import classify_incident

class IncidentService:
    def __init__(self):
        self.store = IncidentStore()
        self.slack = SlackNotifier()
        self.k8s = K8sCollector()

    async def handle_alertmanager(self, payload: AlertmanagerPayload) -> Incident:
        alert = payload.alerts[0]
        labels = {**payload.commonLabels, **alert.labels}
        annotations = {**payload.commonAnnotations, **alert.annotations}

        incident_id = str(uuid.uuid4())[:8]
        env = "dev"
        service = labels.get("service", labels.get("app", "unknown-service"))
        namespace = labels.get("namespace", "default")
        alertname = labels.get("alertname", "unknown-alert")
        severity = labels.get("severity", "warning")

        title = f"{alertname} on {service} ({namespace})"

        incident = Incident(
            incident_id=incident_id,
            source="alertmanager",
            env=env,
            title=title,
            severity=severity,
            service=service,
            namespace=namespace,
            alertname=alertname,
            started_at=alert.startsAt or datetime.now(timezone.utc).isoformat(),
            raw={"labels": labels, "annotations": annotations, "status": alert.status},
            evidence={}
        )

        classification = classify_incident(incident)
        incident.evidence["classification"] = classification
        incident.evidence["k8s"] = self.k8s.collect_basic(namespace=namespace, service=service)

        # persist incident first
        self.store.upsert_incident(incident)

        # post to Slack and store message metadata for later updates
        meta = self.slack.post_incident_brief(incident)
        if meta and meta.get("channel") and meta.get("ts"):
            self.store.set_slack_meta(incident_id, meta["channel"], meta["ts"])

        return incident

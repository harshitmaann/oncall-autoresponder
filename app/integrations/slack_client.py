import os
from slack_bolt import App
from app.core.schemas import Incident

class SlackNotifier:
    def __init__(self):
        self.token = os.getenv("SLACK_BOT_TOKEN", "")
        self.channel = os.getenv("SLACK_CHANNEL_ID", "")
        self.enabled = bool(self.token and self.channel)
        if self.enabled:
            self.app = App(token=self.token)

    def post_incident_brief(self, incident: Incident) -> None:
        text = self._format_text(incident)
        if not self.enabled:
            print("[slack] disabled (missing SLACK_BOT_TOKEN or SLACK_CHANNEL_ID)")
            print(text)
            return
        self.app.client.chat_postMessage(channel=self.channel, text=text)

    def _format_text(self, incident: Incident) -> str:
        cls = incident.evidence.get("classification", {})
        k8s = incident.evidence.get("k8s", {})
        pods = k8s.get("pods", [])

        pod_line = "No pod data."
        if pods:
            worst = sorted(pods, key=lambda p: (p["ready"], -p["restarts"]))[0]
            pod_line = (
                f"Pod sample: `{worst['name']}` phase={worst['phase']} "
                f"restarts={worst['restarts']} ready={worst['ready']}"
            )

        return (
            f"*🚨 Incident {incident.incident_id}:* {incident.title}\n"
            f"- Severity: *{incident.severity}* | Env: `{incident.env}`\n"
            f"- Service: `{incident.service}` | Namespace: `{incident.namespace}`\n"
            f"- Classification: `{cls.get('type', 'unknown')}` (conf={cls.get('confidence', 0):.2f})\n"
            f"- {pod_line}\n"
            f"_Next: I can suggest runbook steps and propose safe mitigations with approval._"
        )

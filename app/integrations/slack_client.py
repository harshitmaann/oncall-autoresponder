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

    def post_incident_brief(self, incident: Incident):
        text, blocks = self._format_blocks(incident, include_actions=True, status_line=None)
        if not self.enabled:
            print("[slack] disabled (missing SLACK_BOT_TOKEN or SLACK_CHANNEL_ID)")
            print(text)
            return None

        resp = self.app.client.chat_postMessage(channel=self.channel, text=text, blocks=blocks)
        return {"channel": resp.get("channel"), "ts": resp.get("ts")}

    def post_text(self, text: str) -> None:
        if not self.enabled:
            print("[slack] disabled")
            print(text)
            return
        self.app.client.chat_postMessage(channel=self.channel, text=text)

    def update_incident_message(self, channel: str, ts: str, incident: Incident, status_line: str) -> None:
        text, blocks = self._format_blocks(incident, include_actions=False, status_line=status_line)
        if not self.enabled:
            print("[slack] disabled update")
            print(text)
            return
        self.app.client.chat_update(channel=channel, ts=ts, text=text, blocks=blocks)

    def _format_blocks(self, incident: Incident, include_actions: bool, status_line: str | None):
        cls = incident.evidence.get("classification", {})
        k8s = incident.evidence.get("k8s", {})
        pods = k8s.get("pods", [])

        pod_line = "No pod data."
        if pods:
            worst = sorted(pods, key=lambda p: (p["ready"], -p["restarts"]))[0]
            pod_line = f"Pod sample: `{worst['name']}` phase={worst['phase']} restarts={worst['restarts']} ready={worst['ready']}"

        text = f"Incident {incident.incident_id}: {incident.title}"

        main_text = (
            f"*🚨 Incident {incident.incident_id}:* {incident.title}\n"
            f"- Severity: *{incident.severity}* | Env: `{incident.env}`\n"
            f"- Service: `{incident.service}` | Namespace: `{incident.namespace}`\n"
            f"- Classification: `{cls.get('type','unknown')}` (conf={cls.get('confidence',0):.2f})\n"
            f"- {pod_line}\n"
        )
        if status_line:
            main_text += f"\n*Status:* {status_line}\n"

        blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": main_text}}]

        if include_actions:
            blocks.append({
                "type": "actions",
                "elements": [
                    {"type": "button",
                     "text": {"type": "plain_text", "text": "Approve: Rollout Restart"},
                     "style": "primary",
                     "action_id": "approve_rollout_restart",
                     "value": incident.incident_id},
                    {"type": "button",
                     "text": {"type": "plain_text", "text": "Reject"},
                     "style": "danger",
                     "action_id": "reject_action",
                     "value": incident.incident_id},
                ]
            })

        return text, blocks

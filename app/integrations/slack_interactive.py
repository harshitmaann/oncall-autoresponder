import os
import json
import urllib.parse
from fastapi import APIRouter, Request, HTTPException
from slack_sdk.signature import SignatureVerifier

from app.storage.sqlite_store import IncidentStore
from app.executor.k8s_actions import K8sActions
from app.integrations.slack_client import SlackNotifier

router = APIRouter()
verifier = SignatureVerifier(signing_secret=os.getenv("SLACK_SIGNING_SECRET", ""))

@router.post("/slack/actions")
async def slack_actions(req: Request):
    body_bytes = await req.body()

    if not os.getenv("SLACK_SIGNING_SECRET"):
        raise HTTPException(status_code=500, detail="Missing SLACK_SIGNING_SECRET")

    if not verifier.is_valid_request(body=body_bytes, headers=req.headers):
        raise HTTPException(status_code=401, detail="Invalid Slack signature")

    body = body_bytes.decode("utf-8")
    form = urllib.parse.parse_qs(body)
    payload_str = form.get("payload", [None])[0]
    if not payload_str:
        raise HTTPException(status_code=400, detail="Missing payload")

    payload = json.loads(payload_str)
    actions = payload.get("actions") or []
    if not actions:
        return {"ok": True}

    action = actions[0]
    action_id = action.get("action_id")
    incident_id = action.get("value")

    user = (payload.get("user") or {}).get("username") or (payload.get("user") or {}).get("id")
    channel = (payload.get("channel") or {}).get("id")
    team = (payload.get("team") or {}).get("id")
    print(f"[slack/actions] team={team} channel={channel} user={user} action_id={action_id} value={incident_id}")

    store = IncidentStore()
    slack = SlackNotifier()
    k8s = K8sActions()

    result = store.handle_slack_action(payload_str, k8s)
    slack.post_text(result["text"])

    # Disable buttons by updating the original message (if we have metadata)
    upd = result.get("update")
    if upd and upd.get("incident_id"):
        meta = store.get_slack_meta(upd["incident_id"])
        if meta:
            incident = store._get_incident(upd["incident_id"])
            # build a minimal Incident object compatible with formatter
            from app.core.schemas import Incident as IncidentModel
            inc_obj = IncidentModel(
                incident_id=incident["incident_id"],
                source="alertmanager",
                env="dev",
                title=incident["title"],
                severity=incident["severity"],
                service=incident["service"],
                namespace=incident["namespace"],
                alertname=incident["alertname"],
                started_at=None,
                raw={},
                evidence={"classification": {}, "k8s": {}},
            )
            slack.update_incident_message(meta["channel"], meta["ts"], inc_obj, upd.get("status", "Updated"))

    return {"ok": True}

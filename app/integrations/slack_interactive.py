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
        print("[slack/actions] No actions in payload")
        return {"ok": True}

    action = actions[0]
    action_id = action.get("action_id")
    value = action.get("value")

    user = (payload.get("user") or {}).get("username") or (payload.get("user") or {}).get("id")
    channel = (payload.get("channel") or {}).get("id")
    team = (payload.get("team") or {}).get("id")

    print(f"[slack/actions] team={team} channel={channel} user={user} action_id={action_id} value={value}")

    store = IncidentStore()
    k8s = K8sActions()
    slack = SlackNotifier()

    result_text = store.handle_slack_action(payload_str, k8s)
    slack.post_text(result_text)

    return {"ok": True}

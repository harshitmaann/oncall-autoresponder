from fastapi import APIRouter, Request
from app.core.incident import IncidentService
from app.core.schemas import AlertmanagerPayload

router = APIRouter()

@router.post("/alertmanager")
async def alertmanager_webhook(req: Request):
    payload_json = await req.json()
    payload = AlertmanagerPayload.model_validate(payload_json)

    service = IncidentService()
    incident = await service.handle_alertmanager(payload)

    return {"status": "ok", "incident_id": incident.incident_id}

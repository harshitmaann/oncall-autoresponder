from fastapi import FastAPI
from app.api.webhooks import router as webhook_router

app = FastAPI(title="On-call Autoresponder", version="0.1.0")
app.include_router(webhook_router, prefix="/webhooks")

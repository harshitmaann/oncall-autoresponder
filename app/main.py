from dotenv import load_dotenv
load_dotenv(".env")  # load environment variables for local dev

from fastapi import FastAPI
from app.api.webhooks import router as webhook_router
from app.integrations.slack_interactive import router as slack_router

app = FastAPI(title="On-call Autoresponder", version="0.2.0")
app.include_router(webhook_router, prefix="/webhooks")
app.include_router(slack_router, prefix="/integrations")

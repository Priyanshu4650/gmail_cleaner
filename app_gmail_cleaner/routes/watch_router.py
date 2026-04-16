from fastapi import APIRouter, Request, HTTPException
from app_gmail_cleaner.controllers.watch_controller import start_watch, stop_watch, handle_pubsub_push

router = APIRouter(prefix="/watch", tags=["watch"])


@router.post("/start")
def watch_start():
    """Register Gmail push notifications via Pub/Sub."""
    result = start_watch()
    return {"status": 200, "data": result}


@router.post("/stop")
def watch_stop():
    """Stop Gmail push notifications."""
    stop_watch()
    return {"status": 200, "message": "Watch stopped"}


@router.post("/webhook")
async def pubsub_webhook(request: Request):
    """
    Pub/Sub push subscription endpoint.
    Google calls this whenever a new mail arrives in INBOX.
    """
    payload = await request.json()
    result = await handle_pubsub_push(payload)
    # Must return 2xx to acknowledge the Pub/Sub message
    return {"status": 200, "data": result}

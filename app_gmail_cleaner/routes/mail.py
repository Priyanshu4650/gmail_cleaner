from fastapi import APIRouter
from app_gmail_cleaner.controllers.mail_controller import get_mails

router = APIRouter(prefix="/emails", tags=["emails"])


@router.get("/list")
async def list_emails(number_of_mails: int = 10):
    result = await get_mails(number_of_mails)
    return {"status": 200, "data": {"emails": result}}
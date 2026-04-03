from fastapi import APIRouter

from app_gmail_cleaner.controllers.mail_controller import get_mails

router = APIRouter()

@router.get("/list_emails")
async def list_emails () :
    result = await get_mails()
    return {
        "status": 200,
        "data": {
            "subjects": result
        }
    }

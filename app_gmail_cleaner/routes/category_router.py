from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app_gmail_cleaner.models.database import get_db
from app_gmail_cleaner.controllers.category_controller import (
    get_all_categories, get_emails_by_category,
    move_email_to_category, delete_email_from_db,
    delete_category_and_emails, get_audit_logs,
)
from app_gmail_cleaner.controllers.mail_controller import delete_gmail_message

router = APIRouter(prefix="/categories", tags=["categories"])


class MoveEmailRequest(BaseModel):
    new_category_id: str


# ── Category endpoints ────────────────────────────────────────────────────────
@router.get("/")
def list_categories(db: Session = Depends(get_db)):
    return {"status": 200, "data": get_all_categories(db)}


@router.get("/{category_id}/emails")
def list_emails_in_category(category_id: str, db: Session = Depends(get_db)):
    return {"status": 200, "data": get_emails_by_category(db, category_id)}


@router.delete("/{category_id}")
def delete_category(category_id: str, db: Session = Depends(get_db)):
    success = delete_category_and_emails(db, category_id)
    if not success:
        raise HTTPException(status_code=404, detail="Category not found")
    return {"status": 200, "message": "Category and its emails deleted from local DB"}


# ── Email endpoints ───────────────────────────────────────────────────────────
@router.patch("/emails/{email_id}/move")
def move_email(email_id: str, body: MoveEmailRequest, db: Session = Depends(get_db)):
    result = move_email_to_category(db, email_id, body.new_category_id)
    if not result:
        raise HTTPException(status_code=404, detail="Email not found")
    return {"status": 200, "message": "Email moved"}


@router.delete("/emails/{email_id}")
async def delete_email(email_id: str, trash_in_gmail: bool = True, db: Session = Depends(get_db)):
    """Delete from local DB. Optionally also trash in Gmail."""
    success = delete_email_from_db(db, email_id)
    if not success:
        raise HTTPException(status_code=404, detail="Email not found")
    if trash_in_gmail:
        await delete_gmail_message(email_id)
    return {"status": 200, "message": "Email deleted"}


# ── Audit endpoint ────────────────────────────────────────────────────────────
@router.get("/audit/logs")
def audit_logs(limit: int = 50, db: Session = Depends(get_db)):
    return {"status": 200, "data": get_audit_logs(db, limit)}
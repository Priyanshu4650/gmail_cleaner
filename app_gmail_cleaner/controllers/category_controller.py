from sqlalchemy.orm import Session
from typing import List, Optional
from app_gmail_cleaner.models.database import Category, Email, AuditLog
import json


def get_all_categories(db: Session):
    categories = db.query(Category).all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "description": c.description,
            "email_count": len(c.emails),
        }
        for c in categories
    ]


def get_emails_by_category(db: Session, category_id: str):
    emails = db.query(Email).filter_by(category_id=category_id).all()
    return [
        {
            "id": e.id,
            "subject": e.subject,
            "sender": e.sender,
            "body_snippet": e.body_snippet,
            "received_at": str(e.received_at),
        }
        for e in emails
    ]


def move_email_to_category(db: Session, email_id: str, new_category_id: str):
    email = db.query(Email).filter_by(id=email_id).first()
    if not email:
        return None
    old_cat = email.category_id
    email.category_id = new_category_id
    db.add(AuditLog(action="moved", detail=json.dumps({
        "email_id": email_id,
        "from": old_cat,
        "to": new_category_id,
    })))
    db.commit()
    return email


def delete_email_from_db(db: Session, email_id: str):
    email = db.query(Email).filter_by(id=email_id).first()
    if not email:
        return False
    db.delete(email)
    db.add(AuditLog(action="deleted_email", detail=json.dumps({"email_id": email_id})))
    db.commit()
    return True


def delete_category_and_emails(db: Session, category_id: str):
    cat = db.query(Category).filter_by(id=category_id).first()
    if not cat:
        return False
    db.add(AuditLog(action="deleted_category", detail=json.dumps({
        "category": cat.name,
        "email_count": len(cat.emails),
    })))
    db.delete(cat)   # cascade deletes emails
    db.commit()
    return True


def get_audit_logs(db: Session, limit: int = 50):
    logs = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit).all()
    return [{"id": l.id, "action": l.action, "detail": l.detail, "created_at": str(l.created_at)} for l in logs]
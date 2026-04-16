from sqlalchemy import create_engine, Column, String, Text, Integer, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import uuid

DATABASE_URL = "sqlite:///./gmail_cleaner.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class Category(Base):
    __tablename__ = "categories"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, unique=True, nullable=False)
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    emails = relationship("Email", back_populates="category", cascade="all, delete-orphan")


class Email(Base):
    __tablename__ = "emails"
    id = Column(String, primary_key=True)          # Gmail message ID
    subject = Column(Text)
    sender = Column(String)
    body_snippet = Column(Text)
    category_id = Column(String, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    received_at = Column(DateTime)
    category = relationship("Category", back_populates="emails")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    action = Column(String)          # "categorized", "moved", "deleted"
    detail = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


Base.metadata.create_all(bind=engine)
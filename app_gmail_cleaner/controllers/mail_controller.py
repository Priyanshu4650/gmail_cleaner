import os
import base64
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from pathlib import Path
from typing import List, Dict
from datetime import datetime

SCOPES = ['https://www.googleapis.com/auth/gmail.modify']  # upgraded from readonly to allow delete


def _get_gmail_service():
    creds = None
    path = Path(__file__).resolve().parent.parent.parent
    credentials_file = path / "credentials.json"
    token_file = path / "token.json"

    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not credentials_file.exists():
                raise FileNotFoundError(f"{credentials_file} not found.")
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_file), SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_file, 'w') as token:
            token.write(creds.to_json())

    return build('gmail', 'v1', credentials=creds)


def _extract_body(payload: dict) -> str:
    """Recursively extract plain text body from Gmail payload."""
    if payload.get("mimeType") == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")[:500]

    for part in payload.get("parts", []):
        result = _extract_body(part)
        if result:
            return result
    return ""


async def get_mails(number_of_mails: int = 100) -> List[Dict]:
    service = _get_gmail_service()
    results = service.users().messages().list(userId='me', maxResults=number_of_mails).execute()
    messages = results.get('messages', [])

    emails = []
    for msg in messages:
        msg_data = service.users().messages().get(userId='me', id=msg['id'], format='full').execute()
        headers = msg_data['payload']['headers']

        subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
        sender = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')
        date_str = next((h['value'] for h in headers if h['name'] == 'Date'), None)
        body = _extract_body(msg_data['payload']) or msg_data.get('snippet', '')

        emails.append({
            "id": msg['id'],
            "subject": subject,
            "sender": sender,
            "body_snippet": body[:300],
            "received_at": date_str,
        })

    return emails


async def delete_gmail_message(message_id: str) -> bool:
    service = _get_gmail_service()
    service.users().messages().trash(userId='me', id=message_id).execute()
    return True
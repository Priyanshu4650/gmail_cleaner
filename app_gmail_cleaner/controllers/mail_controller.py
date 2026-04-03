import os.path
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from pathlib import Path

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

async def get_mails() :
    creds = None

    # Paths
    path = Path(__file__).resolve().parent.parent.parent
    credentials_file = path / "credentials.json"   # OAuth 2.0 client_id and client_secret
    token_file = path / "token.json"               # Stored user access/refresh token

    # Load token if exists
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)

    # If not valid, login
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not credentials_file.exists():
                raise FileNotFoundError(
                    f"{credentials_file} not found. Put Google OAuth client secret JSON there.")
            flow = InstalledAppFlow.from_client_secrets_file(
                credentials_file, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(token_file, 'w') as token:
            token.write(creds.to_json())

    service = build('gmail', 'v1', credentials=creds)

    # Fetch messages
    results = service.users().messages().list(userId='me', maxResults=100).execute()
    messages = results.get('messages', [])

    subjects = []

    for msg in messages:
        msg_data = service.users().messages().get(userId='me', id=msg['id']).execute()
        headers = msg_data['payload']['headers']
        
        subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')

        subjects.append(subject)

    return subjects
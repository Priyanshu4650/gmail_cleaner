import base64
import json
from pathlib import Path
import logging

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from app_gmail_cleaner.controllers.agent_controller import run_agent, extract_json_list
from app_gmail_cleaner.shared.llm import llm
from app_gmail_cleaner.controllers.mail_controller import get_mails

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
TOPIC_NAME = "projects/gmail-cleaner-492208/topics/Gmail-Cleaner-Pub-Sub"


logger = logging.getLogger("watch")
path = Path(__file__).resolve().parent.parent.parent
credentials_file = path / "credentials.json"
token_file = path / "token.json"


def _get_service():
    creds = None
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_file, 'w') as f:
            f.write(creds.to_json())
    return build('gmail', 'v1', credentials=creds)


def start_watch() -> dict:
    service = _get_service()
    response = service.users().watch(
        userId='me',
        body={
            'labelIds': ['INBOX'],
            'topicName': TOPIC_NAME,
            'labelFilterBehavior': 'INCLUDE',
        }
    ).execute()
    # response contains: { historyId, expiration (unix ms) }
    return response


def stop_watch() -> None:
    service = _get_service()
    service.users().stop(userId='me').execute()


async def handle_pubsub_push(payload: dict) -> dict:
    """
    Pub/Sub push delivers:
    { "message": { "data": "<base64>", "messageId": "...", "publishTime": "..." }, "subscription": "..." }
    The decoded data is: { "emailAddress": "...", "historyId": "..." }
    """
    message = payload.get("message", {})
    raw_data = message.get("data", "")

    if not raw_data:
        return {"status": "ignored", "reason": "empty data"}

    decoded = json.loads(base64.b64decode(raw_data).decode("utf-8"))
    email_address = decoded.get("emailAddress")
    history_id = decoded.get("historyId")

    print(f"New mail event for {email_address}, historyId={history_id}")

    # Trigger the categorization agent on new mail
    # result = await run_agent()

    # TODO: 1. It should check whether there is anything important in the mail or not, that needs a reminder.
    # 2. If anything is there that needs a reminder, I should be adding an event to Google Calendar on that account. 

    SYSTEM_PROMPT = """
        You are a person assistant who checks emails, and adds events to calendar if anything is important. Here is the mail that got triggered. I will give you the mail content as well. You check the content and think about 
        Categorize it into 3 severity levels, High, Medium, Low. If High, then add it to google calendar with a reminder of 10 minutes before. If no time is there in the mail, add it for the next day.
        All the mails related to job assessment exams or interviews, etc. are High priority.
    """

    recent_mails = await get_mails(2)

    response  = llm.invoke([
        ("system", SYSTEM_PROMPT),
        ("human", f"Here are the mails, {recent_mails}, return me only the high severity level mails.")
    ])

    result = response.content

    logger.info(f"Agent executed. Result: {result}")

    high_priority_mails = extract_json_list(result)

    logger.info(f"There are the high priority mails {high_priority_mails}")

    SCOPES = ['https://www.googleapis.com/auth/calendar']
    from google.oauth2 import service_account
    creds = service_account.Credentials.from_service_account_file(
        path/"gmail-cleaner-492208-d2aa9a71e136.json", scopes=SCOPES)

    service = build('calendar', 'v3', credentials=creds)
    from datetime import date, timedelta, time, datetime
    tomorrow = date.today() + timedelta(days=1)
    tomorrow_at_9 = datetime.combine(tomorrow, time(9, 0)).isoformat()
    tomorrow_at_10 = datetime.combine(tomorrow, time(10, 0)).isoformat()

    events = [
        {
        "summary": hpm["subject"],
        "description": hpm["body_snippet"],
        "start": {
            "dateTime": tomorrow_at_9,
            "timeZone": "Asia/Kolkata",
        },
        "end": {
            "dateTime": tomorrow_at_10,
            "timeZone": "Asia/Kolkata",
        },
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "email", "minutes": 24 * 60},
                {"method": "popup", "minutes": 10},
            ],
        },
    } for hpm in high_priority_mails]

    logger.info(f"Adding events to calendar {events}")

    for event in events :
        service.events().insert(calendarId='priyanshu022017@gmail.com', body=event).execute()

    return {
        "email_address": email_address,
        "history_id": history_id,
        # "agent_result": result.get("audit_summary", {}),
    }

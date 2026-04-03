from fastapi import FastAPI
from app_gmail_cleaner.routes.mail import router as mail_router

app = FastAPI()

@app.get("/healtz")
async def get_health () :
    return { "status" : "OK" }

app.include_router(mail_router, prefix="/mail")
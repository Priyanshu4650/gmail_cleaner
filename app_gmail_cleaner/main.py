from fastapi import FastAPI
from app_gmail_cleaner.routes.mail import router as mail_router
from app_gmail_cleaner.routes.agent_router import router as agent_router
from app_gmail_cleaner.routes.category_router import router as category_router
from app_gmail_cleaner.routes.watch_router import router as watch_router

app = FastAPI()

@app.get("/healtz")
async def get_health () :
    return { "status" : "OK" }

app.include_router(mail_router)
app.include_router(agent_router)
app.include_router(category_router)
app.include_router(watch_router)
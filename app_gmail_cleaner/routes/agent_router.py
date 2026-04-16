from fastapi import APIRouter
from app_gmail_cleaner.controllers.agent_controller import run_agent

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/run")
async def run_categorization_agent():
    """Trigger the LangGraph agent: fetch → plan → categorize → audit."""
    result = await run_agent()
    if result.get("error"):
        return {"status": 500, "error": result["error"]}
    return {
        "status": 200,
        "data": {
            "categories_created": result["planned_categories"],
            "audit_summary": result["audit_summary"],
            "total_processed": len(result["categorized"]),
        }
    }
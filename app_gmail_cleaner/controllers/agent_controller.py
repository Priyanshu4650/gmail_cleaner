import json
import re
import logging
from typing import TypedDict, List, Dict, Any
from langgraph.graph import StateGraph, END
from sqlalchemy.orm import Session
from datetime import datetime

from app_gmail_cleaner.controllers.mail_controller import get_mails
from app_gmail_cleaner.models.database import Email, Category, AuditLog, SessionLocal
from app_gmail_cleaner.shared.llm import llm

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("agent")


def extract_json_list(text: str) -> List:
    """Extract a JSON list from LLM response, handling all Ollama output shapes."""
    logger.debug("[extract_json_list] raw LLM output:\n%s", text)

    for pattern in (r'(\[.*\])', r'(\{.*\})'):
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(1))
                if isinstance(parsed, list):
                    logger.debug("[extract_json_list] got list with %d items", len(parsed))
                    return parsed
                if isinstance(parsed, dict):
                    # Unwrap first list value e.g. {"categories": [...]} or {"emails": [...]}
                    for v in parsed.values():
                        if isinstance(v, list):
                            logger.debug("[extract_json_list] unwrapped dict -> list with %d items", len(v))
                            return v
                    # Single object returned instead of array — wrap it
                    logger.warning("[extract_json_list] single dict returned, wrapping in list: %s", parsed)
                    return [parsed]
            except json.JSONDecodeError as e:
                logger.warning("[extract_json_list] JSONDecodeError on pattern %s: %s", pattern, e)
                continue
    raise ValueError(f"No valid JSON list found in LLM response: {text!r}")


class AgentState(TypedDict):
    emails: List[Dict]
    planned_categories: List[Dict]
    categorized: List[Dict]
    audit_summary: Dict[str, int]
    error: str


async def fetch_emails_node(state: AgentState) -> AgentState:
    logger.info("[fetch_emails] starting")
    try:
        emails = await get_mails(10)
        logger.info("[fetch_emails] fetched %d emails", len(emails))
        return {**state, "emails": emails}
    except Exception as e:
        logger.error("[fetch_emails] error: %s", e)
        return {**state, "error": str(e)}


async def plan_categories_node(state: AgentState) -> AgentState:
    if state.get("error"):
        return state

    logger.info("[plan_categories] loading existing categories from DB")
    db: Session = SessionLocal()
    try:
        existing = db.query(Category).all()
        existing_categories = [{"name": c.name, "description": c.description} for c in existing]
        logger.info("[plan_categories] found %d existing categories: %s", len(existing_categories), [c["name"] for c in existing_categories])
    finally:
        db.close()

    email_summaries = [
        f"Subject: {e['subject']} | From: {e['sender']}"
        for e in state["emails"][:100]
    ]
    logger.info("[plan_categories] building prompt with %d email summaries", len(email_summaries))

    existing_block = ""
    if existing_categories:
        existing_block = f"""Existing categories (reuse these where possible):
{json.dumps(existing_categories, indent=2)}

"""

    prompt = f"""You are analyzing {len(email_summaries)} emails to decide the best category taxonomy.

{existing_block}Email list:
{chr(10).join(email_summaries)}

Return the FULL final list of categories to use — include all existing ones (unchanged) plus any new ones needed.
Do NOT rename or drop existing categories.

Respond ONLY with a JSON array like:
[{{"name": "Newsletters", "description": "Subscription newsletters and digests"}}, ...]"""

    logger.debug("[plan_categories] prompt:\n%s", prompt)
    response = llm.invoke(prompt)
    logger.info("[plan_categories] raw LLM response:\n%s", response.content)
    categories = extract_json_list(response.content)
    logger.info("[plan_categories] parsed %d categories: %s", len(categories), [c.get("name") for c in categories])
    return {**state, "planned_categories": categories}


async def categorize_emails_node(state: AgentState) -> AgentState:
    if state.get("error"):
        return state

    category_names = [c["name"] for c in state["planned_categories"]]
    logger.info("[categorize_emails] categorizing with %d categories: %s", len(category_names), category_names)

    all_categorized = []
    chunk_size = 20
    emails = state["emails"]

    for i in range(0, len(emails), chunk_size):
        chunk = emails[i:i + chunk_size]
        logger.info("[categorize_emails] processing chunk %d-%d of %d", i, i + len(chunk), len(emails))
        email_list = "\n".join([
            f"{idx}. Subject: {e['subject']} | From: {e['sender']} | Snippet: {e['body_snippet'][:100]}"
            for idx, e in enumerate(chunk)
        ])
        prompt = f"""Categorize each email into exactly one of these categories: {category_names}

Emails:
{email_list}

Respond ONLY with a JSON array matching email index to category:
[{{"index": 0, "category": "Newsletters"}}, ...]"""

        logger.debug("[categorize_emails] prompt for chunk %d:\n%s", i, prompt)
        response = llm.invoke(prompt)
        logger.info("[categorize_emails] raw LLM response for chunk %d:\n%s", i, response.content)
        chunk_result = extract_json_list(response.content)
        logger.info("[categorize_emails] parsed %d results for chunk %d", len(chunk_result), i)

        for item in chunk_result:
            logger.debug("[categorize_emails] item: %s", item)
            email = chunk[item["index"]]
            all_categorized.append({
                "email_id": email["id"],
                "category_name": item["category"],
                "email": email,
            })

    logger.info("[categorize_emails] total categorized: %d", len(all_categorized))
    return {**state, "categorized": all_categorized}


async def persist_and_audit_node(state: AgentState) -> AgentState:
    if state.get("error"):
        return state

    logger.info("[persist_and_audit] persisting %d categorized emails", len(state["categorized"]))
    db: Session = SessionLocal()
    try:
        cat_map = {}
        for c in state["planned_categories"]:
            existing = db.query(Category).filter_by(name=c["name"]).first()
            if not existing:
                existing = Category(name=c["name"], description=c["description"])
                db.add(existing)
                db.flush()
                logger.info("[persist_and_audit] created new category: %s", c["name"])
            else:
                logger.debug("[persist_and_audit] reusing existing category: %s", c["name"])
            cat_map[c["name"]] = existing.id

        audit_counts: Dict[str, int] = {}
        for item in state["categorized"]:
            e = item["email"]
            cat_name = item["category_name"]
            cat_id = cat_map.get(cat_name)

            existing_email = db.query(Email).filter_by(id=e["id"]).first()
            if not existing_email:
                db.add(Email(
                    id=e["id"],
                    subject=e["subject"],
                    sender=e["sender"],
                    body_snippet=e["body_snippet"],
                    category_id=cat_id,
                    received_at=datetime.utcnow(),
                ))
                logger.debug("[persist_and_audit] inserted email id=%s into category=%s", e["id"], cat_name)
            else:
                logger.debug("[persist_and_audit] skipping duplicate email id=%s", e["id"])
            audit_counts[cat_name] = audit_counts.get(cat_name, 0) + 1

        db.add(AuditLog(action="categorized", detail=json.dumps(audit_counts)))
        db.commit()
        logger.info("[persist_and_audit] done. audit summary: %s", audit_counts)
        return {**state, "audit_summary": audit_counts}
    finally:
        db.close()


def build_agent():
    graph = StateGraph(AgentState)
    graph.add_node("fetch_emails", fetch_emails_node)
    graph.add_node("plan_categories", plan_categories_node)
    graph.add_node("categorize_emails", categorize_emails_node)
    graph.add_node("persist_and_audit", persist_and_audit_node)

    graph.set_entry_point("fetch_emails")
    graph.add_edge("fetch_emails", "plan_categories")
    graph.add_edge("plan_categories", "categorize_emails")
    graph.add_edge("categorize_emails", "persist_and_audit")
    graph.add_edge("persist_and_audit", END)

    return graph.compile()


agent = build_agent()


async def run_agent() -> Dict[str, Any]:
    initial_state: AgentState = {
        "emails": [],
        "planned_categories": [],
        "categorized": [],
        "audit_summary": {},
        "error": "",
    }
    result = await agent.ainvoke(initial_state)
    return result
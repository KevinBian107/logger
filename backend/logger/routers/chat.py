"""Chat router: query parsing, approval flow, Claude streaming."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from logger.database import get_db, async_session
from logger.models import ChatMessage, Setting
from logger.schemas import (
    ChatQueryRequest, ChatApprovalResponse, ChatContextInfo,
    ChatApproveRequest, ChatMessageResponse, ChatStatusResponse,
    ApiKeySaveRequest,
)
from logger.services.api_key_service import save_api_key, get_api_key, has_api_key
from logger.services.chat_query_service import parse_query
from logger.services.chat_context_service import build_context

router = APIRouter(prefix="/chat", tags=["chat"])

# Ephemeral in-memory pending approvals
_pending_approvals: dict[str, dict] = {}

AVAILABLE_MODELS = [
    {"id": "claude-sonnet-4-20250514", "name": "Claude Sonnet 4"},
    {"id": "claude-haiku-4-5-20251001", "name": "Claude Haiku 4.5"},
    {"id": "claude-opus-4-20250514", "name": "Claude Opus 4"},
]

DEFAULT_MODEL = "claude-sonnet-4-20250514"

SYSTEM_PROMPT = """You are an AI assistant helping a user understand their productivity data. \
You have been provided with their logged study/work time data.

Rules:
- Only reference the provided data. Do not invent or assume data that isn't shown.
- Be precise with numbers. Show both hours and minutes (e.g., "12h 30m" or "750 minutes").
- Use markdown formatting for clarity: headers, bold for emphasis, lists for breakdowns.
- When data is insufficient to answer a question, say so clearly.
- Be concise but thorough. Highlight interesting patterns or trends if they exist.
- When comparing periods, show the numbers side by side.
"""


async def _get_selected_model(db: AsyncSession) -> str:
    result = await db.execute(select(Setting).where(Setting.key == "chat_model"))
    setting = result.scalar_one_or_none()
    return setting.value if setting else DEFAULT_MODEL


@router.get("/status", response_model=ChatStatusResponse)
async def chat_status(db: AsyncSession = Depends(get_db)):
    has_key = await has_api_key(db)
    model = await _get_selected_model(db)
    return ChatStatusResponse(
        has_api_key=has_key,
        selected_model=model,
        available_models=AVAILABLE_MODELS,
    )


@router.get("/history", response_model=list[ChatMessageResponse])
async def chat_history(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ChatMessage).order_by(ChatMessage.id.desc()).limit(50)
    )
    messages = list(reversed(result.scalars().all()))
    return [
        ChatMessageResponse(
            id=m.id, role=m.role, content=m.content, created_at=m.created_at
        )
        for m in messages
    ]


@router.post("/query", response_model=ChatApprovalResponse)
async def chat_query(req: ChatQueryRequest, db: AsyncSession = Depends(get_db)):
    """Parse query, build context, return approval card data."""
    if not await has_api_key(db):
        raise HTTPException(status_code=400, detail="API key not configured")

    parsed = await parse_query(req.message, db)
    context = await build_context(parsed, db)

    approval_id = str(uuid.uuid4())

    # Store user message in DB
    user_msg = ChatMessage(role="user", content=req.message)
    db.add(user_msg)
    await db.commit()

    # Store pending approval in memory
    _pending_approvals[approval_id] = {
        "user_message": req.message,
        "context_markdown": context["context_markdown"],
        "parsed_query": parsed,
        "context_info": context,
    }

    # Truncate context preview for the approval card
    preview = context["context_markdown"]
    if len(preview) > 2000:
        preview = preview[:2000] + "\n\n... [truncated]"

    return ChatApprovalResponse(
        approval_id=approval_id,
        user_message=req.message,
        context_info=ChatContextInfo(
            summary=context["summary"],
            sessions_included=context["sessions_included"],
            categories_included=context["categories_included"],
            date_range=context["date_range"],
            data_points=context["data_points"],
            context_preview=preview,
        ),
    )


@router.post("/approve")
async def chat_approve(req: ChatApproveRequest):
    """Retrieve pending approval, stream Claude's response via SSE."""
    pending = _pending_approvals.pop(req.approval_id, None)
    if not pending:
        raise HTTPException(status_code=404, detail="Approval not found or expired")

    async def generate() -> AsyncGenerator[str, None]:
        # Open a fresh DB session for the streaming generator
        async with async_session() as db:
            api_key = await get_api_key(db)
            if not api_key:
                yield f"data: {json.dumps({'type': 'error', 'content': 'API key not configured'})}\n\n"
                return

            model = await _get_selected_model(db)

            try:
                import anthropic
                client = anthropic.AsyncAnthropic(api_key=api_key)

                user_content = (
                    f"User question: {pending['user_message']}\n\n"
                    f"--- DATA ---\n{pending['context_markdown']}"
                )

                full_response = ""
                async with client.messages.stream(
                    model=model,
                    max_tokens=2048,
                    system=SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": user_content}],
                ) as stream:
                    async for text in stream.text_stream:
                        full_response += text
                        yield f"data: {json.dumps({'type': 'token', 'content': text})}\n\n"

                # Persist assistant message
                assistant_msg = ChatMessage(
                    role="assistant",
                    content=full_response,
                    metadata_=json.dumps({"model": model}),
                )
                db.add(assistant_msg)
                await db.commit()

                yield f"data: {json.dumps({'type': 'done', 'message_id': assistant_msg.id})}\n\n"

            except anthropic.AuthenticationError:
                yield f"data: {json.dumps({'type': 'error', 'content': 'Invalid API key. Please check your settings.'})}\n\n"
            except anthropic.RateLimitError:
                yield f"data: {json.dumps({'type': 'error', 'content': 'Rate limited. Please wait a moment and try again.'})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/reject")
async def chat_reject(req: ChatApproveRequest, db: AsyncSession = Depends(get_db)):
    """Remove pending approval and persist a rejection note."""
    _pending_approvals.pop(req.approval_id, None)
    # Add a system note to chat history
    note = ChatMessage(role="system", content="[Query cancelled by user]")
    db.add(note)
    await db.commit()
    return {"status": "rejected"}


@router.delete("/history")
async def clear_history(db: AsyncSession = Depends(get_db)):
    await db.execute(delete(ChatMessage))
    await db.commit()
    return {"status": "cleared"}


@router.post("/api-key")
async def save_key(req: ApiKeySaveRequest, db: AsyncSession = Depends(get_db)):
    if not req.api_key.startswith("sk-"):
        raise HTTPException(status_code=400, detail="Invalid API key format")
    await save_api_key(req.api_key, db)
    return {"status": "saved"}


@router.delete("/api-key")
async def delete_key(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Setting).where(Setting.key == "anthropic_api_key")
    )
    setting = result.scalar_one_or_none()
    if setting:
        await db.delete(setting)
        await db.commit()
    return {"status": "deleted"}


@router.put("/model")
async def set_model(data: dict, db: AsyncSession = Depends(get_db)):
    model_id = data.get("model_id", "")
    valid_ids = {m["id"] for m in AVAILABLE_MODELS}
    if model_id not in valid_ids:
        raise HTTPException(status_code=400, detail="Invalid model ID")

    result = await db.execute(select(Setting).where(Setting.key == "chat_model"))
    setting = result.scalar_one_or_none()
    if setting:
        setting.value = model_id
    else:
        db.add(Setting(key="chat_model", value=model_id))
    await db.commit()
    return {"status": "updated", "model_id": model_id}

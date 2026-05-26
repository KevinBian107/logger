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
from logger.services.chat_tools_service import TOOLS, execute_tool

router = APIRouter(prefix="/chat", tags=["chat"])

# Ephemeral in-memory pending approvals
_pending_approvals: dict[str, dict] = {}

AVAILABLE_MODELS = [
    {"id": "claude-sonnet-4-20250514", "name": "Claude Sonnet 4"},
    {"id": "claude-haiku-4-5-20251001", "name": "Claude Haiku 4.5"},
    {"id": "claude-opus-4-20250514", "name": "Claude Opus 4"},
]

DEFAULT_MODEL = "claude-sonnet-4-20250514"

SYSTEM_PROMPT = """You are an AI assistant for log(ger), a personal time-tracking app. \
You answer questions about the user's logged study/work time by calling tools \
to query their local SQLite database.

DATA MODEL — always reason and report along this hierarchy:
  - Group (top-level): Research, Training, Personal, Courses
  - Family (mid): a project that spans sessions — e.g., "Salk Research", "MPI Research",
    "Enigmorphic", "COGS" (department family), "Training", "Personal Projects (PP)"
  - Category (leaf): a per-session instance of a family — e.g., "Salk" in Spring 2026
  - Sessions are academic-quarter-sized periods (e.g. "Spring 2026"); one is active at a time
  - Entries are timer or manual records logging minutes against a category

HOW TO ANSWER:
1. Use tools to fetch only what you need. Don't ask the user — query the database directly.
2. Prefer Group → Family → Category framing. For "how much research?" call
   get_group_breakdown; for "how much Salk?" call get_family_breakdown.
3. Verify numbers via tools. NEVER make up totals or session names — if you didn't fetch it,
   don't say it.
4. When listing time, always include both hours and minutes (e.g. "12h 30m" / "750 min").
5. Refer to projects by family display name (e.g. "Salk Research" not "salk").
6. When the question is open-ended ("how was my year"), start with list_sessions, then pick a
   couple of relevant get_group_breakdown / get_family_breakdown calls.
7. For "when did I do X" or text-content questions, use search_text_entries.
8. If a tool returns an error or empty result, say so plainly. Don't pretend data exists.

Use markdown for structure: headers, bold for key numbers, lists for breakdowns.
Be concise but thorough. Highlight interesting patterns if they're real.
"""

# Cap the agentic loop so a misbehaving Claude can't infinite-loop on tools.
MAX_TOOL_ITERATIONS = 8


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
    """Stage a pending query. With tool use, there's no pre-built context —
    Claude will fetch what it needs via tools when the user approves.
    The approval card now just confirms the user wants to spend an API call.
    """
    if not await has_api_key(db):
        raise HTTPException(status_code=400, detail="API key not configured")

    approval_id = str(uuid.uuid4())

    # Persist the user message
    user_msg = ChatMessage(role="user", content=req.message)
    db.add(user_msg)
    await db.commit()

    _pending_approvals[approval_id] = {"user_message": req.message}

    # The "preview" tells the user what Claude can do here.
    preview = (
        "Claude will query your database directly using read-only tools "
        f"({len(TOOLS)} available) and respond based on what it finds. "
        "Tool calls happen automatically; you'll see each one as it runs."
    )
    tool_names = [t["name"] for t in TOOLS]

    return ChatApprovalResponse(
        approval_id=approval_id,
        user_message=req.message,
        context_info=ChatContextInfo(
            summary=f"Tool-use mode · {len(TOOLS)} read-only tools available",
            sessions_included=[],
            categories_included=tool_names,
            date_range=[None, None],
            data_points=0,
            context_preview=preview,
        ),
    )


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _summarize_tool_result(name: str, result: dict) -> str:
    """One-line summary shown in the chat UI as Claude's progress."""
    if "error" in result:
        return result["error"]
    if name == "list_sessions":
        return f"found {result.get('count', 0)} sessions"
    if name == "list_families":
        return f"found {result.get('count', 0)} families"
    if name == "get_family_breakdown":
        fam = result.get("family", {}).get("name", "?")
        mins = result.get("total_minutes", 0)
        return f"{fam}: {mins // 60}h {mins % 60}m total"
    if name == "get_group_breakdown":
        grp = result.get("group", {}).get("name", "?")
        mins = result.get("total_minutes", 0)
        return f"{grp}: {mins // 60}h {mins % 60}m across {len(result.get('by_family', []))} families"
    if name == "get_session_breakdown":
        sess = result.get("session", {}).get("label", "?")
        return f"{sess}: {len(result.get('items', []))} {result.get('by', 'family')}s"
    if name == "get_daily_breakdown":
        d = result.get("date", "?")
        mins = result.get("total_minutes", 0)
        return f"{d}: {mins // 60}h {mins % 60}m"
    if name == "search_text_entries":
        return f"matched {result.get('count', 0)} entries"
    return "ok"


@router.post("/approve")
async def chat_approve(req: ChatApproveRequest):
    """Run the multi-turn tool-use loop and stream events back over SSE.

    Events:
      tool_call   {name, input}            — Claude is about to call a tool
      tool_result {name, summary}          — Tool returned (just a short summary,
                                              not the full payload, to keep
                                              the SSE channel small)
      token       {content}                — Final response text (one big chunk
                                              in this version; can be split later)
      done        {message_id}             — Conversation turn complete
      error       {content}                — Aborted
    """
    pending = _pending_approvals.pop(req.approval_id, None)
    if not pending:
        raise HTTPException(status_code=404, detail="Approval not found or expired")

    user_message = pending["user_message"]

    async def generate() -> AsyncGenerator[str, None]:
        async with async_session() as db:
            api_key = await get_api_key(db)
            if not api_key:
                yield _sse({"type": "error", "content": "API key not configured"})
                return

            model = await _get_selected_model(db)

            try:
                import anthropic
                client = anthropic.AsyncAnthropic(api_key=api_key)

                # Conversation history accumulates as we loop.
                messages: list[dict] = [{"role": "user", "content": user_message}]
                final_text = ""

                for iteration in range(MAX_TOOL_ITERATIONS):
                    resp = await client.messages.create(
                        model=model,
                        max_tokens=2048,
                        system=SYSTEM_PROMPT,
                        tools=TOOLS,
                        messages=messages,
                    )

                    if resp.stop_reason == "tool_use":
                        # Append Claude's turn (text + tool_use blocks) to history
                        messages.append({"role": "assistant", "content": resp.content})

                        # Execute every tool block in this turn, build tool_result blocks
                        tool_result_blocks = []
                        for block in resp.content:
                            if getattr(block, "type", None) != "tool_use":
                                continue
                            tool_name = block.name
                            tool_input = block.input or {}
                            yield _sse({"type": "tool_call", "name": tool_name, "input": tool_input})

                            result = await execute_tool(tool_name, tool_input, db)
                            yield _sse({
                                "type": "tool_result",
                                "name": tool_name,
                                "summary": _summarize_tool_result(tool_name, result),
                            })

                            tool_result_blocks.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": json.dumps(result),
                            })

                        messages.append({"role": "user", "content": tool_result_blocks})
                        continue  # Loop to get Claude's next response

                    # end_turn (or anything non-tool_use) → final response is the text blocks
                    final_text = "".join(
                        b.text for b in resp.content if getattr(b, "type", None) == "text"
                    ).strip()
                    break
                else:
                    # Hit iteration cap
                    yield _sse({
                        "type": "error",
                        "content": f"Stopped after {MAX_TOOL_ITERATIONS} tool calls without a final answer.",
                    })
                    return

                if not final_text:
                    yield _sse({
                        "type": "error",
                        "content": "Claude returned no text response.",
                    })
                    return

                # Stream the final text (single chunk for V1; can be split later).
                yield _sse({"type": "token", "content": final_text})

                assistant_msg = ChatMessage(
                    role="assistant",
                    content=final_text,
                    metadata_=json.dumps({"model": model, "tool_iterations": iteration + 1}),
                )
                db.add(assistant_msg)
                await db.commit()
                yield _sse({"type": "done", "message_id": assistant_msg.id})

            except anthropic.AuthenticationError:
                yield _sse({"type": "error", "content": "Invalid API key. Check Settings."})
            except anthropic.RateLimitError:
                yield _sse({"type": "error", "content": "Rate limited. Wait a moment and try again."})
            except Exception as e:  # noqa: BLE001
                yield _sse({"type": "error", "content": f"{type(e).__name__}: {e}"})

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

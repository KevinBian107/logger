"""Chat router: approval flow + Claude tool-use loop streamed over SSE.

Flow: POST /chat/query stages the question (and persists it); the UI shows an
approval card; POST /chat/approve runs the agentic loop:

    system = static instructions + live data catalog (cached prefix)
    messages = recent conversation turns + the new question
    loop: Claude streams text / calls read-only tools -> we run them -> repeat

What makes it smarter than the first version:
  * a data catalog in the system prompt (today's date, sessions, the full
    Group > Family > Category map) so names like "Finches" can be resolved;
  * find_topic / get_time_breakdown tools and forgiving name resolution;
  * conversation memory (follow-ups like "and last quarter?" work);
  * adaptive thinking with a real token budget (2048 used to truncate answers).
"""

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
from logger.services.chat_catalog_service import build_data_catalog
from logger.services.chat_tools_service import TOOLS, execute_tool

router = APIRouter(prefix="/chat", tags=["chat"])

# Ephemeral in-memory pending approvals
_pending_approvals: dict[str, dict] = {}

AVAILABLE_MODELS = [
    {"id": "claude-opus-5-5", "name": "Claude Opus 5.5"},
    {"id": "claude-sonnet-5-5", "name": "Claude Sonnet 5.5"},
    {"id": "claude-haiku-5-5", "name": "Claude Haiku 5.5"},
    # Previous generation, kept so an existing selection keeps working.
    {"id": "claude-sonnet-5", "name": "Claude Sonnet 5 (previous)"},
    {"id": "claude-opus-4-8", "name": "Claude Opus 4.8 (previous)"},
    {"id": "claude-haiku-4-5", "name": "Claude Haiku 4.5 (previous)"},
]
_MODEL_IDS = {m["id"] for m in AVAILABLE_MODELS}
# Older builds stored a date-suffixed Haiku id; map it onto the current alias.
_MODEL_ALIASES = {"claude-haiku-4-5-20251001": "claude-haiku-4-5"}

DEFAULT_MODEL = "claude-opus-5-5"

# Per-iteration output cap. Thinking tokens count against it, so it has to be
# generous — the old 2048 cut long summaries off mid-answer.
MAX_TOKENS = 32000
# Cap the agentic loop so a misbehaving model can't call tools forever.
MAX_TOOL_ITERATIONS = 12
# How many previous question/answer pairs to replay for follow-up questions.
HISTORY_TURNS = 8
HISTORY_CHAR_CAP = 6000

SYSTEM_PROMPT = """\
You are the assistant inside log(ger), the user's personal time-tracking app. You answer \
questions about how they spent their time — research, courses, training, personal \
projects — using read-only tools over their local database. You are talking to the person \
whose data this is.

## How the data is organized
- Sessions are academic-quarter-sized periods (e.g. "Fall 2026"); exactly one is active.
- Group > Family > Category. Groups are broad areas (Research, Courses, Personal, \
Training). A family is a project or subject that can span many sessions (e.g. "Salk \
Research"). A category is that family's instance inside one session, and is what time is \
logged against. Same-named categories in different sessions are the same activity.
- Minutes per category per day are the source of truth for time totals, for every session.
- Imported sessions (older, from CSV) have per-category daily minutes plus one free-text \
narrative per day that is not tied to a category; it often has inline durations like "(60m)".
- Live-tracked sessions (newer) also have individual timer/manual entries, each with a \
category, minutes, a start time, a free-text description and a location. Those \
descriptions are the richest record of what was actually done.

## Resolving what the user means
Users name things the database may not use as a family: a lab, sub-project, paper, \
person, tool, course nickname or place ("Finches", "the NeurIPS paper", "Jure"). Such a \
name may be a category inside another family, or appear only inside entry descriptions. \
Before saying there is no data about something, call find_topic with the name (and \
obvious variants); it searches every group, family, category and description and \
tolerates spacing, casing, plurals and typos. A failed family lookup alone never means \
"no data".

When a topic appears both as a category and in descriptions under other categories, \
report both and keep them distinct: direct time is minutes logged in the matching \
categories; related time is minutes of entries in other categories whose descriptions \
mention it. An entry's minutes belong to its own category, so related time is an upper \
bound on time spent on the topic, not an exact figure — say so when you use it.

## Using the tools
- The data catalog below already lists sessions, groups, families and categories with \
all-time totals. Use it to choose names and ids; don't call list_sessions or \
list_families just to discover what exists.
- Resolve relative dates ("last week", "this quarter", "in May") against today's date in \
the catalog. Weeks run Monday to Sunday. "This quarter" usually means the active session.
- get_time_breakdown covers most "how much / when / trend / compare" questions over any \
date range. find_topic and search_text_entries cover "what did I do for X". \
summarize_text_in_range returns all descriptions for a period so you can write a \
narrative. get_daily_breakdown shows a single day in full.
- Call independent tools in parallel, and prefer one well-scoped call over many tiny ones.
- Only state numbers that come from the catalog or a tool result. If a search comes back \
empty, say what you searched and mention the closest matches the tool suggested.

## Answering
- Lead with the direct answer, then supporting detail. Match length to the question: a \
quick question gets a few lines; a quarter or year summary can use short sections.
- Write durations like "12h 30m".
- For "what did I do" questions, synthesize from the descriptions: the main threads of \
work, milestones and outcomes, people involved, and how it evolved over time, with dates. \
Quote sparingly; don't paste raw entries.
- Use markdown: headers only for longer answers, bold for key numbers, short bullet lists \
for breakdowns.
- Point out genuinely interesting patterns (peaks, streaks, shifts between projects) when \
the data supports them. Don't invent motivations or outcomes the text doesn't state.
- This is a continuing conversation: earlier turns are included, so resolve follow-ups \
("and last month?", "what about Salk?") against them.
"""


def _request_options(model: str) -> dict:
    """Per-model thinking/effort settings.

    Adaptive thinking with high effort on every current model: questions here
    are multi-step (resolve names, pick date ranges, cross-check numbers), and
    effort is what buys that care. Haiku 4.5 predates adaptive thinking and
    the effort parameter, so it gets neither."""
    if model.startswith("claude-haiku-4-5"):
        return {}
    return {"thinking": {"type": "adaptive"}, "output_config": {"effort": "high"}}


async def _get_selected_model(db: AsyncSession) -> str:
    result = await db.execute(select(Setting).where(Setting.key == "chat_model"))
    setting = result.scalar_one_or_none()
    model = _MODEL_ALIASES.get(setting.value, setting.value) if setting else DEFAULT_MODEL
    return model if model in _MODEL_IDS else DEFAULT_MODEL


async def _history_messages(db: AsyncSession, before_id: int | None) -> list[dict]:
    """Recent completed question/answer pairs, oldest first.

    Only user messages that got an assistant answer are replayed (a cancelled
    question followed by a new one would otherwise read as two questions)."""
    stmt = select(ChatMessage).order_by(ChatMessage.id.desc()).limit(HISTORY_TURNS * 4)
    if before_id is not None:
        stmt = stmt.where(ChatMessage.id < before_id)
    rows = list(reversed((await db.execute(stmt)).scalars().all()))

    pairs: list[tuple[str, str]] = []
    pending_user: str | None = None
    for m in rows:
        if m.role == "user":
            pending_user = m.content
        elif m.role == "assistant" and pending_user is not None:
            answer = m.content
            if len(answer) > HISTORY_CHAR_CAP:
                answer = answer[:HISTORY_CHAR_CAP] + "\n\n[earlier answer truncated]"
            pairs.append((pending_user, answer))
            pending_user = None
        else:
            pending_user = None  # system note (e.g. cancelled) breaks the pair

    messages: list[dict] = []
    for q, a in pairs[-HISTORY_TURNS:]:
        messages.append({"role": "user", "content": q})
        messages.append({"role": "assistant", "content": a})
    return messages


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
    """Stage a pending query. Nothing is sent to Claude until the user approves;
    the approval card just confirms the user wants to spend an API call."""
    if not await has_api_key(db):
        raise HTTPException(status_code=400, detail="API key not configured")

    approval_id = str(uuid.uuid4())

    # Persist the user message
    user_msg = ChatMessage(role="user", content=req.message)
    db.add(user_msg)
    await db.commit()

    _pending_approvals[approval_id] = {"user_message": req.message, "user_msg_id": user_msg.id}

    history_turns = len(await _history_messages(db, user_msg.id)) // 2
    model = await _get_selected_model(db)
    model_name = next((m["name"] for m in AVAILABLE_MODELS if m["id"] == model), model)
    memory = (f" Your last {history_turns} question{'s' if history_turns != 1 else ''} and "
              "answers are included for context." if history_turns else "")
    preview = (
        f"{model_name} will read a summary of your sessions and projects, then query your "
        f"database with read-only tools ({len(TOOLS)} available) and answer from what it "
        f"finds.{memory} Tool calls happen automatically; you'll see each one as it runs."
    )
    tool_names = [t["name"] for t in TOOLS]

    return ChatApprovalResponse(
        approval_id=approval_id,
        user_message=req.message,
        context_info=ChatContextInfo(
            summary=f"Tool-use mode · {len(TOOLS)} read-only tools · {model_name}",
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
        return str(result["error"])
    if name == "find_topic":
        cats = [c["name"] for c in result.get("matched_categories", [])]
        fams = [f["name"] for f in result.get("matched_families", [])]
        found = ", ".join((fams + cats)[:3])
        mentions = result.get("mentions", {}).get("entries", 0) + \
            result.get("mentions", {}).get("daily_narratives", 0)
        if result.get("no_match"):
            return "no matches" + (f" · try {', '.join(result.get('did_you_mean', [])[:3])}"
                                   if result.get("did_you_mean") else "")
        direct = (result.get("direct_time") or {}).get("total")
        parts = []
        if found:
            parts.append(found)
        if direct:
            parts.append(f"{direct} direct")
        parts.append(f"{mentions} mention{'s' if mentions != 1 else ''}")
        return " · ".join(parts)
    if name == "get_time_breakdown":
        return f"{result.get('total', '0m')} across {len(result.get('items', []))} {result.get('group_by', 'item')}s"
    if name == "list_sessions":
        return f"found {result.get('count', 0)} sessions"
    if name == "list_families":
        return f"found {result.get('count', 0)} families"
    if name == "get_family_breakdown":
        scope = result.get("scope", {}).get("name") or result.get("family", {}).get("name", "?")
        return f"{scope}: {result.get('total', '0m')} total"
    if name == "get_group_breakdown":
        grp = result.get("group", {}).get("name", "?")
        return f"{grp}: {result.get('total', '0m')} across {len(result.get('by_family', []))} families"
    if name == "get_session_breakdown":
        sess = result.get("session", {}).get("label", "?")
        return f"{sess}: {result.get('total', '0m')} · {len(result.get('items', []))} {result.get('by', 'family')}s"
    if name == "get_daily_breakdown":
        return f"{result.get('date', '?')}: {result.get('total', '0m')}"
    if name == "search_text_entries":
        return f"matched {result.get('total_matches', result.get('count', 0))} records"
    if name == "summarize_text_in_range":
        return f"{result.get('total_records', 0)} text records · {(result.get('time_summary') or {}).get('total', '0m')} logged"
    return "ok"


def _text_of(content) -> str:
    """Join a response's text blocks (thinking/tool blocks are skipped)."""
    parts = [b.text for b in content if getattr(b, "type", None) == "text" and b.text]
    return "\n\n".join(p.strip() for p in parts if p.strip())


@router.post("/approve")
async def chat_approve(req: ChatApproveRequest):
    """Run the multi-turn tool-use loop and stream events back over SSE.

    Events:
      tool_call   {name, input}     — Claude is about to call a tool
      tool_result {name, summary}   — Tool returned (short summary only, to keep
                                       the SSE channel small)
      token       {content}         — Streamed response text
      reset       {}                — Discard text streamed so far this turn
                                       (it was a preamble before more tool calls)
      done        {message_id}      — Conversation turn complete
      error       {content}         — Aborted
    """
    pending = _pending_approvals.pop(req.approval_id, None)
    if not pending:
        raise HTTPException(status_code=404, detail="Approval not found or expired")

    user_message = pending["user_message"]
    user_msg_id = pending.get("user_msg_id")

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

                catalog = await build_data_catalog(db)
                # Tools render before system, so the cache breakpoint on the
                # catalog covers tools + instructions + catalog. The catalog is
                # fixed for this turn, so every loop iteration reads the cache.
                system = [
                    {"type": "text", "text": SYSTEM_PROMPT},
                    {"type": "text", "text": catalog, "cache_control": {"type": "ephemeral"}},
                ]
                messages: list[dict] = await _history_messages(db, user_msg_id)
                messages.append({"role": "user", "content": user_message})
                options = _request_options(model)

                final_text = ""
                iterations = 0
                truncated = False
                while True:
                    if iterations >= MAX_TOOL_ITERATIONS:
                        yield _sse({
                            "type": "error",
                            "content": f"Stopped after {MAX_TOOL_ITERATIONS} rounds of tool calls without a final answer.",
                        })
                        return
                    iterations += 1

                    streamed_text = False
                    async with client.messages.stream(
                        model=model,
                        max_tokens=MAX_TOKENS,
                        system=system,
                        tools=TOOLS,
                        messages=messages,
                        **options,
                    ) as stream:
                        async for event in stream:
                            if event.type == "content_block_start" and \
                                    getattr(event.content_block, "type", None) == "text" and streamed_text:
                                yield _sse({"type": "token", "content": "\n\n"})
                            elif event.type == "text" and event.text:
                                streamed_text = True
                                yield _sse({"type": "token", "content": event.text})
                        resp = await stream.get_final_message()

                    if resp.stop_reason == "refusal":
                        yield _sse({"type": "error",
                                    "content": "Claude declined to answer this request. Try rephrasing it."})
                        return

                    if resp.stop_reason == "tool_use":
                        if streamed_text:
                            # Text before a tool call is a preamble, not the answer.
                            yield _sse({"type": "reset"})
                        # Append the assistant turn unchanged (thinking blocks included).
                        messages.append({"role": "assistant", "content": resp.content})

                        tool_result_blocks = []
                        for block in resp.content:
                            if getattr(block, "type", None) != "tool_use":
                                continue
                            tool_name = block.name
                            tool_input = block.input if isinstance(block.input, dict) else {}
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
                                "content": json.dumps(result, default=str, ensure_ascii=False,
                                                      separators=(",", ":")),
                                **({"is_error": True} if "error" in result else {}),
                            })

                        # All results go back in ONE user message (keeps parallel calls working).
                        messages.append({"role": "user", "content": tool_result_blocks})
                        continue

                    # end_turn / max_tokens / stop_sequence → this is the answer.
                    final_text = _text_of(resp.content)
                    truncated = resp.stop_reason == "max_tokens"
                    break

                if not final_text:
                    yield _sse({"type": "error", "content": "Claude returned no text response."})
                    return
                if truncated:
                    note = "\n\n*(Answer cut off at the length limit — ask a narrower question for the rest.)*"
                    final_text += note
                    yield _sse({"type": "token", "content": note})

                assistant_msg = ChatMessage(
                    role="assistant",
                    content=final_text,
                    metadata_=json.dumps({
                        "model": model,
                        "tool_iterations": iterations,
                        "input_tokens": resp.usage.input_tokens,
                        "cache_read_input_tokens": getattr(resp.usage, "cache_read_input_tokens", None),
                        "output_tokens": resp.usage.output_tokens,
                    }),
                )
                db.add(assistant_msg)
                await db.commit()
                yield _sse({"type": "done", "message_id": assistant_msg.id})

            except anthropic.AuthenticationError:
                yield _sse({"type": "error", "content": "Invalid API key. Check Settings."})
            except anthropic.RateLimitError:
                yield _sse({"type": "error", "content": "Rate limited. Wait a moment and try again."})
            except anthropic.NotFoundError:
                yield _sse({"type": "error", "content": f"Model '{model}' is not available to this API key. Pick another model in Settings."})
            except anthropic.BadRequestError as e:
                yield _sse({"type": "error", "content": f"Request rejected by the API: {e.message}"})
            except anthropic.APIConnectionError:
                yield _sse({"type": "error", "content": "Couldn't reach the Claude API. Check your internet connection."})
            except anthropic.APIStatusError as e:
                yield _sse({"type": "error", "content": f"Claude API error ({e.status_code}). Try again shortly."})
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
    if model_id not in _MODEL_IDS:
        raise HTTPException(status_code=400, detail="Invalid model ID")

    result = await db.execute(select(Setting).where(Setting.key == "chat_model"))
    setting = result.scalar_one_or_none()
    if setting:
        setting.value = model_id
    else:
        db.add(Setting(key="chat_model", value=model_id))
    await db.commit()
    return {"status": "updated", "model_id": model_id}

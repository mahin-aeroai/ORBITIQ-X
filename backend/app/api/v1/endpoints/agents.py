"""
ORBITIQ-X — Multi-Agent Reasoning Endpoints
=============================================
REST API for submitting tasks to the ORBITIQ-X agent orchestrator
and streaming agent reasoning traces.
"""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.core.config import Settings, get_settings
from app.schemas.agents import (
    AgentTask,
    AgentTaskResult,
    AgentTaskStatus,
    TaskSubmitRequest,
    TaskSubmitResponse,
)
from app.services.agent_service import AgentOrchestrationService

logger = structlog.get_logger(__name__)
router = APIRouter()


def get_agent_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> AgentOrchestrationService:
    return AgentOrchestrationService(settings=settings)


@router.post(
    "/task",
    response_model=TaskSubmitResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit reasoning task to agent orchestrator",
    description=(
        "Submits a natural-language task to the ORBITIQ-X multi-agent system. "
        "Tasks are routed to the appropriate specialist agent(s) by the LangGraph "
        "supervisor. Returns a task ID for status polling or WebSocket streaming."
    ),
)
async def submit_agent_task(
    request: TaskSubmitRequest,
    service: AgentOrchestrationService = Depends(get_agent_service),
) -> TaskSubmitResponse:
    logger.info("agent.task.submitted", task_type=request.task_type, query_len=len(request.query))
    task_id = await service.submit_task(request=request)
    return TaskSubmitResponse(
        task_id=task_id,
        status="queued",
        message="Task submitted. Poll /agents/task/{task_id} for status or stream via WebSocket.",
    )


@router.get(
    "/task/{task_id}",
    response_model=AgentTaskResult,
    summary="Get agent task result",
    description=(
        "Returns the current status and result (if complete) for an agent task. "
        "Includes the full reasoning trace with tool calls and agent thoughts."
    ),
)
async def get_task_result(
    task_id: UUID,
    service: AgentOrchestrationService = Depends(get_agent_service),
) -> AgentTaskResult:
    result = await service.get_task(task_id=task_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found.",
        )
    return result


@router.get(
    "/task/{task_id}/stream",
    summary="Stream agent reasoning trace (SSE)",
    description=(
        "Server-Sent Events stream of real-time agent reasoning. Emits agent "
        "thoughts, tool calls, tool results, and final answer as they are generated."
    ),
    response_class=StreamingResponse,
)
async def stream_task_reasoning(
    task_id: UUID,
    service: AgentOrchestrationService = Depends(get_agent_service),
) -> StreamingResponse:
    async def sse_generator():
        async for event in service.stream_task(task_id=task_id):
            yield f"data: {event}\n\n"

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get(
    "/tasks",
    response_model=list[AgentTaskStatus],
    summary="List recent agent tasks",
)
async def list_recent_tasks(
    limit: int = 20,
    service: AgentOrchestrationService = Depends(get_agent_service),
) -> list[AgentTaskStatus]:
    return await service.list_tasks(limit=limit)

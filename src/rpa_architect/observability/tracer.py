"""Structured tracing for lifecycle agent reasoning and node execution."""

from __future__ import annotations

import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncGenerator

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class AgentSpan(BaseModel):
    """A single span in an agent trace."""

    span_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    parent_id: str | None = None
    name: str = Field(description="Node or operation name.")
    start_time: datetime = Field(default_factory=datetime.utcnow)
    end_time: datetime | None = None
    duration_ms: float = 0.0
    attributes: dict[str, Any] = Field(default_factory=dict)
    status: str = "ok"
    error: str | None = None


class AgentTrace(BaseModel):
    """A complete trace of an agent lifecycle run."""

    trace_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    process_name: str = ""
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    spans: list[AgentSpan] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def duration_ms(self) -> float:
        if self.completed_at and self.started_at:
            return (self.completed_at - self.started_at).total_seconds() * 1000
        return 0.0

    @property
    def has_errors(self) -> bool:
        return any(s.status == "error" for s in self.spans)


class LifecycleTracer:
    """Collects spans during lifecycle agent execution."""

    def __init__(self, process_name: str = "") -> None:
        self._trace = AgentTrace(process_name=process_name)
        self._span_stack: list[AgentSpan] = []

    @property
    def trace(self) -> AgentTrace:
        return self._trace

    @asynccontextmanager
    async def span(
        self,
        name: str,
        attributes: dict[str, Any] | None = None,
    ) -> AsyncGenerator[AgentSpan, None]:
        """Context manager for tracing a lifecycle node or operation."""
        parent_id = self._span_stack[-1].span_id if self._span_stack else None
        s = AgentSpan(
            name=name,
            parent_id=parent_id,
            attributes=attributes or {},
        )
        self._span_stack.append(s)
        start = time.monotonic()

        try:
            yield s
            s.status = "ok"
        except Exception as exc:
            s.status = "error"
            s.error = str(exc)
            raise
        finally:
            s.end_time = datetime.utcnow()
            s.duration_ms = (time.monotonic() - start) * 1000
            self._span_stack.pop()
            self._trace.spans.append(s)
            logger.debug(
                "Span %s [%s] %.1fms",
                name,
                s.status,
                s.duration_ms,
            )

    def complete(self) -> AgentTrace:
        """Finalize the trace."""
        self._trace.completed_at = datetime.utcnow()
        return self._trace

    def export_json(self, path: Path | None = None) -> str:
        """Export the trace as JSON."""
        data = self._trace.model_dump_json(indent=2)
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(data, encoding="utf-8")
            logger.info("Trace exported to %s", path)
        return data

"""Tests for Action Center integration (mocked REST)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from rpa_architect.platform.action_center import (
    TaskOutput,
    TaskResult,
    create_review_task,
    wait_for_task,
)


class TestCreateReviewTask:
    @pytest.mark.asyncio
    async def test_creates_task(self):
        mock_client = AsyncMock()
        mock_client._request.return_value = {"Id": "task-42"}

        result = await create_review_task(
            title="Review invoice",
            data={"amount": 100},
            client=mock_client,
        )

        assert isinstance(result, TaskResult)
        assert result.task_id == "task-42"
        assert result.title == "Review invoice"
        mock_client._request.assert_called_once()

    @pytest.mark.asyncio
    async def test_requires_client(self):
        with pytest.raises(RuntimeError, match="UiPathClient instance"):
            await create_review_task("Title", {})


class TestWaitForTask:
    @pytest.mark.asyncio
    async def test_completed(self):
        mock_client = AsyncMock()
        mock_client._request.return_value = {
            "Status": "Completed",
            "Data": {"approved": True},
            "CompletedByUser": "john",
        }

        result = await wait_for_task("task-1", poll_interval=0.01, client=mock_client)

        assert isinstance(result, TaskOutput)
        assert result.status == "Completed"
        assert result.data == {"approved": True}
        assert result.completed_by == "john"

    @pytest.mark.asyncio
    async def test_failed(self):
        mock_client = AsyncMock()
        mock_client._request.return_value = {"Status": "Failed"}

        result = await wait_for_task("task-2", poll_interval=0.01, client=mock_client)
        assert result.status == "Failed"

    @pytest.mark.asyncio
    async def test_timeout(self):
        mock_client = AsyncMock()
        mock_client._request.return_value = {"Status": "Pending"}

        with pytest.raises(TimeoutError):
            await wait_for_task("task-3", timeout=0.05, poll_interval=0.01, client=mock_client)

    @pytest.mark.asyncio
    async def test_requires_client(self):
        with pytest.raises(RuntimeError, match="UiPathClient instance"):
            await wait_for_task("task-x")

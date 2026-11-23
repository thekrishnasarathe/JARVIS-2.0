from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from backend.core.swarm import SubagentManager, manager, spawn_subagent
from shared.event_bus import drain_all


@pytest.fixture
def fresh_global_manager():
    """Fixture to temporarily replace the global manager with a clean instance and shut it down after testing."""
    import backend.core.swarm

    orig_manager = backend.core.swarm.manager

    # Create a fresh manager for the test to ensure clean state
    fresh_mgr = SubagentManager(max_workers=3)
    backend.core.swarm.manager = fresh_mgr

    yield fresh_mgr

    # Ensure executor is shut down cleanly to prevent hanging threads
    fresh_mgr.executor.shutdown(wait=True)
    backend.core.swarm.manager = orig_manager


def test_subagent_manager_non_blocking():
    # Verify that calling spawn_subagent returns instantly
    # We mock requests.post to block, but spawn_subagent should return immediately
    block_event = threading.Event()

    def mock_blocking_post(*args, **kwargs):
        block_event.wait(timeout=2.0)  # avoid infinite hang in case of failure
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"message": {"content": "Done"}}
        return resp

    # Create a local manager to avoid polluting the global manager state
    local_mgr = SubagentManager(max_workers=1)

    with patch("requests.post", side_effect=mock_blocking_post):
        start_time = time.time()
        # Submit a task
        local_mgr.spawn_subagent(role="Worker", task="Blocking task")
        elapsed = time.time() - start_time

        # Must return immediately (should be under 10ms, but we use 100ms as a safe threshold)
        assert elapsed < 0.1

        # Release the blocking thread
        block_event.set()
        local_mgr.executor.shutdown(wait=True)


def test_subagent_manager_concurrency_limit():
    # Submit 5 tasks to a manager with max_workers=3
    # Verify that at most 3 run in parallel
    lock = threading.Lock()
    active_workers = 0
    max_observed_workers = 0

    worker_entered_event = threading.Event()
    release_workers_event = threading.Event()

    def mock_post_concurrency(*args, **kwargs):
        nonlocal active_workers, max_observed_workers
        with lock:
            active_workers += 1
            if active_workers > max_observed_workers:
                max_observed_workers = active_workers

        # Signal that a worker has entered
        worker_entered_event.set()

        # Block until released by the test
        release_workers_event.wait()

        with lock:
            active_workers -= 1

        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"message": {"content": "Result"}}
        return resp

    local_mgr = SubagentManager(max_workers=3)

    with patch("requests.post", side_effect=mock_post_concurrency):
        # Spawn 5 subagents
        for i in range(5):
            local_mgr.spawn_subagent(role=f"Sub-{i}", task="Task")

        # Give worker threads a moment to start
        time.sleep(0.1)

        # Verify that max_observed_workers is exactly 3 (the cap)
        with lock:
            assert max_observed_workers == 3
            assert active_workers == 3

        # Release all workers
        release_workers_event.set()

        # Clean shutdown (waits for all threads to finish)
        local_mgr.executor.shutdown(wait=True)

        # Verify all threads exited successfully
        assert active_workers == 0


def test_global_spawn_subagent_helper():
    drain_all()

    # Mock requests.post to return success immediately
    with patch("requests.post") as mock_post:
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"message": {"content": "Helper Result"}}
        mock_post.return_value = resp

        # Trigger global helper
        spawn_subagent(role="GlobalHelper", task="Global Task")

        # Verify spawn event was pushed immediately
        events = drain_all()
        assert len(events) > 0
        spawn_evts = [
            e
            for e in events
            if e.source == "swarm"
            and e.data
            and e.data.get("type") == "subagent_spawned"
        ]
        assert len(spawn_evts) == 1
        assert spawn_evts[0].data["role"] == "GlobalHelper"


def test_global_manager_config():
    """Verify that the global manager is configured with max_workers=3."""
    assert manager.executor._max_workers == 3


def test_global_manager_spawn_non_blocking(fresh_global_manager):
    """Verify that calling manager.spawn_subagent() multiple times does not block the main thread."""
    block_event = threading.Event()

    def mock_blocking_post(*args, **kwargs):
        block_event.wait(timeout=2.0)
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"message": {"content": "Done"}}
        return resp

    with patch("requests.post", side_effect=mock_blocking_post):
        start_time = time.time()
        # Spawn 5 subagents on the global manager
        for i in range(5):
            fresh_global_manager.spawn_subagent(role=f"SubGlobal-{i}", task="Task")
        elapsed = time.time() - start_time

        # Must return immediately
        assert elapsed < 0.1

        # Release and teardown is handled by fixture/block_event
        block_event.set()


def test_global_manager_spawn_concurrency_limit(fresh_global_manager):
    """Verify that manager.spawn_subagent() correctly limits execution to max_workers=3."""
    lock = threading.Lock()
    active_workers = 0
    max_observed_workers = 0

    release_workers_event = threading.Event()

    def mock_post_concurrency(*args, **kwargs):
        nonlocal active_workers, max_observed_workers
        with lock:
            active_workers += 1
            if active_workers > max_observed_workers:
                max_observed_workers = active_workers

        release_workers_event.wait()

        with lock:
            active_workers -= 1

        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"message": {"content": "Result"}}
        return resp

    with patch("requests.post", side_effect=mock_post_concurrency):
        # Spawn 5 subagents
        for i in range(5):
            fresh_global_manager.spawn_subagent(role=f"SubGlobal-{i}", task="Task")

        # Let workers start
        time.sleep(0.1)

        # Verify exactly 3 workers run concurrently
        with lock:
            assert max_observed_workers == 3
            assert active_workers == 3

        # Release them
        release_workers_event.set()


def test_subagent_manager_connection_error():
    import requests

    from shared.schemas import Severity

    drain_all()
    local_mgr = SubagentManager(max_workers=1)

    with patch(
        "requests.post", side_effect=requests.ConnectionError("Connection refused")
    ):
        local_mgr.spawn_subagent(role="WorkerConnError", task="Task")
        local_mgr.executor.shutdown(wait=True)

        events = drain_all()
        completed_events = [
            e
            for e in events
            if e.data
            and e.data.get("type") == "subagent_completed"
            and e.data.get("role") == "WorkerConnError"
        ]
        assert len(completed_events) == 1
        assert completed_events[0].data["result"] == "Connection Refused"
        assert completed_events[0].severity == Severity.ERROR

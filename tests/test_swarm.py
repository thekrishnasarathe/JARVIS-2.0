from __future__ import annotations

import pytest
import time
import threading
from unittest.mock import patch, MagicMock
from backend.core.swarm import SubagentManager, spawn_subagent, manager
from backend.modules.llm_fallback import ask_llm
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
        block_event.wait(timeout=2.0) # avoid infinite hang in case of failure
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
        spawn_evts = [e for e in events if e.source == "swarm" and e.data and e.data.get("type") == "subagent_spawned"]
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


def test_llm_fallback_spawn_subagent_tool_integration():
    """Verify integration where ask_llm executes the spawn_subagent tool."""
    drain_all()
    
    # We patch requests.post to return the tool call, then mock the tool call's side effects
    with patch("requests.post") as mock_post, \
         patch("backend.core.swarm.manager.spawn_subagent") as mock_spawn:
         
        # First response triggers tool call
        resp1 = MagicMock()
        resp1.status_code = 200
        resp1.json.return_value = {
            "message": {
                "role": "assistant",
                "tool_calls": [
                    {
                        "function": {
                            "name": "spawn_subagent",
                            "arguments": {
                                "role": "Researcher Agent",
                                "task": "Search details on Quantum Computing"
                            }
                        }
                    }
                ]
            }
        }
        
        # Second response returns final natural response
        resp2 = MagicMock()
        resp2.status_code = 200
        resp2.json.return_value = {
            "message": {
                "role": "assistant",
                "content": "I have successfully spawned the Researcher Agent to look into Quantum Computing."
            }
        }
        
        mock_post.side_effect = [resp1, resp2]
        
        result = ask_llm("Can you delegate quantum computing research to a subagent?")
        
        assert "spawned the Researcher Agent" in result.text
        # Verify manager's spawn_subagent was called with correct arguments
        mock_spawn.assert_called_once_with("Researcher Agent", "Search details on Quantum Computing")
        
        # Verify event bus event was emitted
        events = drain_all()
        tool_events = [e for e in events if e.data and e.data.get("type") == "tool_call"]
        assert len(tool_events) == 1
        assert tool_events[0].data["tool"] == "spawn_subagent"
        assert tool_events[0].data["args"] == {
            "role": "Researcher Agent",
            "task": "Search details on Quantum Computing"
        }

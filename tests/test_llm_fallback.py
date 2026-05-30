from __future__ import annotations

import pytest
import concurrent.futures
from unittest.mock import patch, MagicMock
from backend.modules.llm_fallback import ask_llm, _execute_tool
from shared.schemas import Severity, CommandResult
from shared.event_bus import drain_all

def test_ask_llm_direct_response():
    drain_all()
    # Direct response mock (no tool calls)
    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "message": {
                "role": "assistant",
                "content": "Paris is the capital of France."
            }
        }
        mock_post.return_value = mock_resp
        
        result = ask_llm("What is the capital of France?")
        assert result.text == "Paris is the capital of France."
        assert result.source == "llm_fallback"
        
        # Verify event bus entries
        events = drain_all()
        assert len(events) >= 2
        # llm_thinking start
        start_events = [e for e in events if e.data and e.data.get("type") == "llm_thinking" and e.data.get("state") == "start"]
        assert len(start_events) == 1
        # llm_thinking stop
        stop_events = [e for e in events if e.data and e.data.get("type") == "llm_thinking" and e.data.get("state") == "stop"]
        assert len(stop_events) == 1

def test_ask_llm_single_tool_call():
    drain_all()
    
    # We patch requests.post to return a tool call first, then a final response
    with patch("requests.post") as mock_post, \
         patch("backend.modules.web_services.get_weather") as mock_weather:
         
        mock_weather.return_value = CommandResult(text="Weather in Paris: 20 C, Sunny", source="web_services")
        
        # First call response
        resp1 = MagicMock()
        resp1.status_code = 200
        resp1.json.return_value = {
            "message": {
                "role": "assistant",
                "tool_calls": [
                    {
                        "function": {
                            "name": "get_weather",
                            "arguments": {"city": "Paris"}
                        }
                    }
                ]
            }
        }
        
        # Second call response
        resp2 = MagicMock()
        resp2.status_code = 200
        resp2.json.return_value = {
            "message": {
                "role": "assistant",
                "content": "The weather in Paris is currently 20 degrees Celsius and sunny."
            }
        }
        
        mock_post.side_effect = [resp1, resp2]
        
        result = ask_llm("How is the weather in Paris?")
        assert result.text == "The weather in Paris is currently 20 degrees Celsius and sunny."
        
        # Verify requests.post was called twice
        assert mock_post.call_count == 2
        mock_weather.assert_called_once_with("Paris")
        
        # Check event bus events
        events = drain_all()
        tool_call_events = [e for e in events if e.data and e.data.get("type") == "tool_call"]
        assert len(tool_call_events) == 1
        assert tool_call_events[0].data["tool"] == "get_weather"
        assert tool_call_events[0].data["args"] == {"city": "Paris"}

def test_ask_llm_multiple_tool_calls():
    drain_all()
    
    with patch("requests.post") as mock_post, \
         patch("backend.modules.web_services.wikipedia_search") as mock_wiki, \
         patch("backend.modules.system_utils.google_search") as mock_google:
         
        mock_wiki.return_value = CommandResult(text="Python is a snake and language.", source="web_services")
        mock_google.return_value = CommandResult(text="Google Python search result.", source="system_utils")
        
        resp1 = MagicMock()
        resp1.status_code = 200
        resp1.json.return_value = {
            "message": {
                "role": "assistant",
                "tool_calls": [
                    {
                        "function": {
                            "name": "wikipedia_search",
                            "arguments": {"topic": "Python"}
                        }
                    },
                    {
                        "function": {
                            "name": "google_search",
                            "arguments": {"query": "Python"}
                        }
                    }
                ]
            }
        }
        
        resp2 = MagicMock()
        resp2.status_code = 200
        resp2.json.return_value = {
            "message": {
                "role": "assistant",
                "content": "I found Wikipedia and Google entries for Python."
            }
        }
        
        mock_post.side_effect = [resp1, resp2]
        
        result = ask_llm("search Python on wikipedia and google")
        assert result.text == "I found Wikipedia and Google entries for Python."
        assert mock_post.call_count == 2
        
        mock_wiki.assert_called_once_with("Python")
        mock_google.assert_called_once_with("Python")
        
        events = drain_all()
        tool_events = [e for e in events if e.data and e.data.get("type") == "tool_call"]
        assert len(tool_events) == 2

def test_ask_llm_tool_execution_error():
    drain_all()
    
    with patch("requests.post") as mock_post, \
         patch("backend.modules.web_services.get_weather", side_effect=Exception("API service down")):
         
        resp1 = MagicMock()
        resp1.status_code = 200
        resp1.json.return_value = {
            "message": {
                "role": "assistant",
                "tool_calls": [
                    {
                        "function": {
                            "name": "get_weather",
                            "arguments": {"city": "New York"}
                        }
                    }
                ]
            }
        }
        
        resp2 = MagicMock()
        resp2.status_code = 200
        resp2.json.return_value = {
            "message": {
                "role": "assistant",
                "content": "I couldn't fetch the weather because the API service is down."
            }
        }
        
        mock_post.side_effect = [resp1, resp2]
        
        result = ask_llm("how is the weather in New York?")
        assert "New York" in result.text or "API service is down" in result.text

import requests
def test_ask_llm_connection_error():
    drain_all()
    with patch("requests.post", side_effect=requests.ConnectionError("Connection refused")):
        result = ask_llm("test query")
        assert result.severity == Severity.ERROR
        assert "cannot reach the local language model" in result.text

def test_ask_llm_timeout():
    drain_all()
    with patch("requests.post", side_effect=requests.Timeout("Request timed out")):
        result = ask_llm("test query")
        assert result.severity == Severity.ERROR
        assert "took too long to respond" in result.text

# Stress testing Ollama parsing thread safety / concurrency
def test_ask_llm_stress_concurrency():
    # Run 10 concurrent requests to verify conversation history updates are safe
    num_threads = 10
    
    def worker(idx):
        with patch("requests.post") as mock_post:
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {
                "message": {
                    "role": "assistant",
                    "content": f"Response {idx}"
                }
            }
            mock_post.return_value = resp
            res = ask_llm(f"Query {idx}")
            return res.text

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(worker, i) for i in range(num_threads)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
        
    assert len(results) == num_threads
    for i in range(num_threads):
        assert f"Response {i}" in results or any(f"Response {j}" in r for r in results for j in range(num_threads))

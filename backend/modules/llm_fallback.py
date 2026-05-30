"""Ollama local LLM fallback with dynamic Tool Calling capabilities."""
from __future__ import annotations

import logging
import requests
import json

from shared import config
from shared.schemas import CommandResult, Severity, JarvisEvent
from shared.event_bus import push_event

from backend.modules import web_services, system_utils
from backend.core.swarm import spawn_subagent

logger = logging.getLogger(__name__)

# Short-term conversational memory buffer (keep last 10 messages)
_conversation_history: list[dict] = []
_MAX_HISTORY_LEN = 10

# Define tools available to the LLM
_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Fetch the current weather for a specified city",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "The name of the city, e.g. Tokyo"
                    }
                },
                "required": ["city"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "wikipedia_search",
            "description": "Search Wikipedia for general knowledge and summaries",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "The topic to search for"
                    }
                },
                "required": ["topic"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "play_youtube",
            "description": "Play a specific video on YouTube",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The video search term"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "google_search",
            "description": "Perform an automated Google search",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search term"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "spawn_subagent",
            "description": "Spawn a background subagent (LLM) to perform complex research or tasks concurrently.",
            "parameters": {
                "type": "object",
                "properties": {
                    "role": {
                        "type": "string",
                        "description": "The specialized role of the subagent, e.g., 'Researcher' or 'Coder'"
                    },
                    "task": {
                        "type": "string",
                        "description": "The highly detailed task/prompt for the subagent to execute"
                    }
                },
                "required": ["role", "task"]
            }
        }
    }
]

def _execute_tool(name: str, args: dict) -> str:
    """Execute the mapped backend tool and return the resulting text."""
    logger.info("Executing LLM Tool: %s with args: %s", name, args)
    
    # Emit tool call event so UI can render a 3D widget/indicator
    push_event(JarvisEvent(
        message=f"Invoking {name}...",
        severity=Severity.INFO,
        source="llm_fallback",
        data={"type": "tool_call", "tool": name, "args": args}
    ))
    
    try:
        if name == "get_weather":
            return web_services.get_weather(args.get("city", "")).text
        elif name == "wikipedia_search":
            return web_services.wikipedia_search(args.get("topic", "")).text
        elif name == "play_youtube":
            return system_utils.play_youtube("play " + args.get("query", "")).text
        elif name == "google_search":
            return system_utils.google_search(args.get("query", "")).text
        elif name == "spawn_subagent":
            role = args.get("role", "Assistant")
            task = args.get("task", "")
            spawn_subagent(role, task)
            return f"Subagent '{role}' spawned successfully. It is working on the task in the background."
        else:
            return f"Error: Tool '{name}' is not recognized."
    except Exception as exc:
        logger.error("Tool execution failed: %s", exc)
        return f"Error executing tool {name}: {exc}"

def ask_llm(query: str) -> CommandResult:
    """Send an unrecognized query to a local Ollama LLM instance with tools.

    Uses short-term conversational memory, tool calling, and emits events.

    Args:
        query: The user's natural-language query.
    """
    global _conversation_history
    
    push_event(JarvisEvent(
        message="LLM is thinking...",
        severity=Severity.INFO,
        source="llm_fallback",
        data={"type": "llm_thinking", "state": "start"}
    ))

    try:
        _conversation_history.append({"role": "user", "content": query})
        
        if len(_conversation_history) > _MAX_HISTORY_LEN:
            _conversation_history = _conversation_history[-_MAX_HISTORY_LEN:]

        payload = {
            'model': config.OLLAMA_MODEL,
            'messages': _conversation_history,
            'stream': False,
            'tools': _TOOLS,
        }

        response = requests.post(
            f'{config.OLLAMA_BASE_URL}/api/chat',
            json=payload,
            timeout=config.OLLAMA_TIMEOUT,
        )
        response.raise_for_status()

        data = response.json()
        message = data.get('message', {})
        
        # Check if the LLM decided to call a tool
        if 'tool_calls' in message and message['tool_calls']:
            # Append the assistant's tool call message to history
            _conversation_history.append(message)
            
            for tool_call in message['tool_calls']:
                tool_name = tool_call['function']['name']
                tool_args = tool_call['function']['arguments']
                
                # Execute tool
                tool_result = _execute_tool(tool_name, tool_args)
                
                # Append tool result to history
                _conversation_history.append({
                    "role": "tool",
                    "content": tool_result
                })
                
            # Send the updated history back to the LLM to generate the final natural language answer
            payload['messages'] = _conversation_history
            
            # Second call
            response2 = requests.post(
                f'{config.OLLAMA_BASE_URL}/api/chat',
                json=payload,
                timeout=config.OLLAMA_TIMEOUT,
            )
            response2.raise_for_status()
            
            data = response2.json()
            message = data.get('message', {})
            
        answer: str = message.get('content', '').strip()

        if not answer:
            _conversation_history.pop()
            return CommandResult(
                text='I received an empty response from the language model.',
                severity=Severity.WARNING,
                source="llm_fallback",
            )

        if len(answer) > config.LLM_MAX_RESPONSE_LENGTH:
            answer = answer[:config.LLM_MAX_RESPONSE_LENGTH].rsplit(' ', 1)[0] + '...'
            logger.info('LLM response truncated to %d chars.', config.LLM_MAX_RESPONSE_LENGTH)

        # Ensure we only append the final assistant content if it wasn't a tool call (handled above)
        if message.get('role') == 'assistant' and not message.get('tool_calls'):
            _conversation_history.append({"role": "assistant", "content": answer})

        return CommandResult(text=answer, source="llm_fallback")

    except requests.ConnectionError:
        logger.warning('Ollama connection refused at %s', config.OLLAMA_BASE_URL)
        if _conversation_history:
            _conversation_history.pop()
        return CommandResult(
            text='I cannot reach the local language model. Please make sure Ollama is running with: ollama serve',
            severity=Severity.ERROR,
            source="llm_fallback",
        )
    except requests.Timeout:
        logger.warning('Ollama request timed out after %ds.', config.OLLAMA_TIMEOUT)
        if _conversation_history:
            _conversation_history.pop()
        return CommandResult(
            text='The language model took too long to respond. Please try again.',
            severity=Severity.ERROR,
            source="llm_fallback",
        )
    except Exception as exc:
        logger.error('LLM fallback error: %s', exc)
        if _conversation_history:
            _conversation_history.pop()
        return CommandResult(
            text='Sorry, I encountered an error while processing your request.',
            severity=Severity.ERROR,
            source="llm_fallback",
        )
    finally:
        push_event(JarvisEvent(
            message="LLM finished thinking.",
            severity=Severity.INFO,
            source="llm_fallback",
            data={"type": "llm_thinking", "state": "stop"}
        ))

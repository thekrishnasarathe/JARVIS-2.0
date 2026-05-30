"""Agent Swarm & Subagent Delegation Architecture."""
from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
import requests

from shared import config
from shared.schemas import JarvisEvent, Severity
from shared.event_bus import push_event

logger = logging.getLogger(__name__)


class SubagentManager:
    """Manages background LLM tasks (subagents) with a concurrency limit."""
    
    def __init__(self, max_workers: int = 3):
        self.executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="SubagentWorker"
        )

    def spawn_subagent(self, role: str, task: str) -> None:
        """Submit a task to the subagent thread pool.
        
        Args:
            role: The title or role of the subagent (e.g., 'Researcher').
            task: The prompt/task description.
        """
        # Emit spawn event immediately
        push_event(JarvisEvent(
            message=f"Subagent '{role}' spawned and is working in the background.",
            severity=Severity.INFO,
            source="swarm",
            data={"type": "subagent_spawned", "role": role, "task": task}
        ))
        
        self.executor.submit(self._run_inference, role, task)

    def _run_inference(self, role: str, task: str) -> None:
        """Execute the Ollama API call without conversational memory."""
        logger.info("Subagent '%s' starting task: %s", role, task)
        
        system_prompt = (
            f"You are a specialized subagent. Your role is: {role}. "
            "You must complete the assigned task efficiently and return only the final results."
        )
        
        try:
            response = requests.post(
                f'{config.OLLAMA_BASE_URL}/api/chat',
                json={
                    'model': config.OLLAMA_MODEL,
                    'messages': [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": task}
                    ],
                    'stream': False,
                },
                timeout=config.OLLAMA_TIMEOUT * 2,  # Subagents might take longer
            )
            response.raise_for_status()

            data = response.json()
            message = data.get('message', {})
            answer: str = message.get('content', '').strip()

            if not answer:
                answer = "Error: Subagent returned an empty response."
                severity = Severity.WARNING
            else:
                severity = Severity.SUCCESS

            # Truncate if insanely long
            if len(answer) > 4000:
                answer = answer[:4000] + "\n...[TRUNCATED]"

            # Emit completion event
            push_event(JarvisEvent(
                message=f"Subagent '{role}' completed its task.",
                severity=severity,
                source="swarm",
                data={"type": "subagent_completed", "role": role, "result": answer}
            ))
            
        except requests.ConnectionError:
            logger.warning("Subagent '%s' failed: Ollama connection refused.", role)
            push_event(JarvisEvent(
                message=f"Subagent '{role}' failed: Cannot connect to Ollama.",
                severity=Severity.ERROR,
                source="swarm",
                data={"type": "subagent_completed", "role": role, "result": "Connection Refused"}
            ))
        except requests.Timeout:
            logger.warning("Subagent '%s' failed: Ollama timeout.", role)
            push_event(JarvisEvent(
                message=f"Subagent '{role}' failed: Timeout.",
                severity=Severity.ERROR,
                source="swarm",
                data={"type": "subagent_completed", "role": role, "result": "Timeout"}
            ))
        except Exception as exc:
            logger.error("Subagent '%s' execution error: %s", role, exc)
            push_event(JarvisEvent(
                message=f"Subagent '{role}' encountered an error.",
                severity=Severity.ERROR,
                source="swarm",
                data={"type": "subagent_completed", "role": role, "result": str(exc)}
            ))


# Global singleton instance
manager = SubagentManager(max_workers=3)

def spawn_subagent(role: str, task: str) -> None:
    """Module-level helper to submit a subagent task to the global manager."""
    manager.spawn_subagent(role, task)

"""Aulinx agent adapter for OSWorld benchmark.

Implements the predict(instruction, obs) interface expected by
OSWorld's run harness. Uses Aulinx's semantic a11y understanding
to control the desktop with structured actions.
"""

from __future__ import annotations

import asyncio
import logging
import time

from aulinx.llm import create_client

from .action_mapper import parse_response
from .prompt_builder import build_prompt

logger = logging.getLogger(__name__)


class AulinxAgent:
    """OSWorld-compatible agent using Aulinx's semantic approach.

    Instead of pixel-based screenshot analysis, this agent reads the
    accessibility tree to understand UI state and outputs structured
    actions. This is 10-50x more token-efficient than vision-based agents.
    """

    def __init__(
        self,
        model: str = "qwen2.5:14b",
        base_url: str = "http://localhost:11434",
        api_type: str = "ollama",
        max_tokens: int = 1024,
        temperature: float = 0.3,
        max_trajectory_length: int = 10,
        observation_type: str = "a11y_tree",
        action_space: str = "computer_13",
        max_retries: int = 6,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_type = api_type  # "ollama", "openai", "anthropic", "gemini"
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.max_trajectory_length = max_trajectory_length
        self.observation_type = observation_type
        self.action_space = action_space
        self.max_retries = max_retries

        # Create shared LLM client
        self._llm = create_client(
            provider=api_type,
            model=model,
            base_url=base_url,
            temperature=temperature,
        )

        # State
        self.history: list[dict] = []
        self.total_tokens_in = 0
        self.total_tokens_out = 0
        self.total_calls = 0

    def reset(self, runtime_logger=None, **kwargs):
        """Reset agent state between tasks."""
        self.history = []
        self._step_count = 0
        self.total_tokens_in = 0
        self.total_tokens_out = 0
        self.total_calls = 0
        if runtime_logger:
            logger.handlers = runtime_logger.handlers

    def predict(self, instruction: str, obs: dict) -> tuple[str, list]:
        """Predict the next action(s) given an observation.

        Args:
            instruction: Natural language task description
            obs: Observation dict with keys:
                - screenshot: bytes (PNG image)
                - accessibility_tree: str (XML)
                - terminal: str | None
                - instruction: str

        Returns:
            (response_text, actions_list)
        """
        a11y_tree = obs.get("accessibility_tree", "") or ""
        messages = build_prompt(instruction, a11y_tree, history=self.history)

        # Call LLM
        response_text = self._call_llm(messages)
        self.total_calls += 1

        # Parse response into action
        thought, action = parse_response(response_text)

        # Record history — include action taken and key UI state
        self._step_count = getattr(self, '_step_count', 0) + 1

        from .prompt_builder import parse_a11y_tree
        parsed_tree = parse_a11y_tree(a11y_tree, max_elements=15)
        obs_summary = f"[Step {self._step_count}] Screen state:\n{parsed_tree}"
        self.history.append({
            "observation": obs_summary,
            "response": response_text.split("\n")[0],  # Keep compact — first line only
        })

        # Trim history to fit context
        if len(self.history) > self.max_trajectory_length:
            self.history = self.history[-self.max_trajectory_length:]

        logger.info("Step %d — thought: %s", self._step_count, thought)
        logger.info("Action: %s", action)

        # OSWorld expects a list of actions
        actions = [action] if not isinstance(action, list) else action
        return response_text, actions

    def _call_llm(self, messages: list[dict]) -> str:
        """Call the LLM using the shared client and return response text."""
        for attempt in range(self.max_retries):
            try:
                return self._call_llm_sync(messages)
            except Exception as e:
                logger.warning("LLM call attempt %d/%d failed: %s", attempt + 1, self.max_retries, e)
                if attempt < self.max_retries - 1:
                    wait = min(3 * (2 ** attempt), 30)
                    logger.info("Retrying in %ds...", wait)
                    time.sleep(wait)
                else:
                    logger.error("All %d LLM call attempts failed", self.max_retries)
                    return "action: wait()\nthought: LLM call failed, waiting"

    def _call_llm_sync(self, messages: list[dict]) -> str:
        """Synchronous wrapper around the async LLM client."""
        full_content = ""

        async def _run():
            nonlocal full_content
            async for event in self._llm.chat_with_tools(messages, []):
                if event.type == "token":
                    full_content += event.data.get("content", "")
                elif event.type == "done":
                    full_content = event.data.get("content", full_content)
                elif event.type == "error":
                    raise RuntimeError(event.data.get("message", "LLM error"))

        # Use existing event loop if available, otherwise create one
        try:
            asyncio.get_running_loop()
            # If we're already in an async context, run in a new thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                pool.submit(lambda: asyncio.run(_run())).result(timeout=120)
        except RuntimeError:
            # No running loop — safe to use asyncio.run
            asyncio.run(_run())

        return full_content

    def get_token_stats(self) -> dict:
        """Return token usage statistics."""
        return {
            "total_input_tokens": self.total_tokens_in,
            "total_output_tokens": self.total_tokens_out,
            "total_calls": self.total_calls,
            "avg_input_tokens": self.total_tokens_in / max(1, self.total_calls),
            "avg_output_tokens": self.total_tokens_out / max(1, self.total_calls),
        }

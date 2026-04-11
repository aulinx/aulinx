"""Aulinx agent adapter for OSWorld benchmark.

Implements the predict(instruction, obs) interface expected by
OSWorld's run harness. Uses Aulinx's semantic a11y understanding
to control the desktop with structured actions.
"""

from __future__ import annotations

import logging
import time

import httpx

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
        max_retries: int = 3,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_type = api_type  # "ollama", "openai", "anthropic"
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.max_trajectory_length = max_trajectory_length
        self.observation_type = observation_type
        self.action_space = action_space
        self.max_retries = max_retries

        # State
        self.history: list[dict] = []
        self.total_tokens_in = 0
        self.total_tokens_out = 0
        self.total_calls = 0

    def reset(self, runtime_logger=None, **kwargs):
        """Reset agent state between tasks."""
        self.history = []
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
        from .prompt_builder import parse_a11y_tree
        parsed_tree = parse_a11y_tree(a11y_tree, max_elements=15)
        obs_summary = f"[Step {len(self.history) + 1}] Screen state:\n{parsed_tree}"
        self.history.append({
            "observation": obs_summary,
            "response": response_text.split("\n")[0],  # Keep compact — first line only
        })

        # Trim history to fit context
        if len(self.history) > self.max_trajectory_length:
            self.history = self.history[-self.max_trajectory_length:]

        logger.info("Step %d — thought: %s", len(self.history), thought)
        logger.info("Action: %s", action)

        # OSWorld expects a list of actions
        actions = [action] if not isinstance(action, list) else action
        return response_text, actions

    def _call_llm(self, messages: list[dict]) -> str:
        """Call the LLM and return the response text."""
        for attempt in range(self.max_retries):
            try:
                if self.api_type == "ollama":
                    return self._call_ollama(messages)
                elif self.api_type == "openai":
                    return self._call_openai(messages)
                elif self.api_type == "anthropic":
                    return self._call_anthropic(messages)
                else:
                    raise ValueError(f"Unknown api_type: {self.api_type}")
            except Exception as e:
                logger.warning("LLM call attempt %d failed: %s", attempt + 1, e)
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                else:
                    logger.error("All LLM call attempts failed")
                    return "action: wait()\nthought: LLM call failed, waiting"

    def _call_ollama(self, messages: list[dict]) -> str:
        """Call Ollama's chat completion API."""
        resp = httpx.post(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": self.temperature,
                    "num_predict": self.max_tokens,
                },
            },
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()

        # Track tokens
        self.total_tokens_in += data.get("prompt_eval_count", 0)
        self.total_tokens_out += data.get("eval_count", 0)

        return data["message"]["content"]

    def _call_openai(self, messages: list[dict]) -> str:
        """Call OpenAI-compatible chat completion API."""
        headers = {}
        api_key = self._get_env("OPENAI_API_KEY", "")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        resp = httpx.post(
            f"{self.base_url}/v1/chat/completions",
            headers=headers,
            json={
                "model": self.model,
                "messages": messages,
                "max_tokens": self.max_tokens,
                "temperature": self.temperature,
            },
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()

        usage = data.get("usage", {})
        self.total_tokens_in += usage.get("prompt_tokens", 0)
        self.total_tokens_out += usage.get("completion_tokens", 0)

        return data["choices"][0]["message"]["content"]

    def _call_anthropic(self, messages: list[dict]) -> str:
        """Call Anthropic's Messages API."""
        import os
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")

        # Separate system message
        system = ""
        chat_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system = msg["content"]
            else:
                chat_messages.append(msg)

        resp = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": self.model,
                "system": system,
                "messages": chat_messages,
                "max_tokens": self.max_tokens,
                "temperature": self.temperature,
            },
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()

        usage = data.get("usage", {})
        self.total_tokens_in += usage.get("input_tokens", 0)
        self.total_tokens_out += usage.get("output_tokens", 0)

        return data["content"][0]["text"]

    @staticmethod
    def _get_env(key: str, default: str = "") -> str:
        import os
        return os.environ.get(key, default)

    def get_token_stats(self) -> dict:
        """Return token usage statistics."""
        return {
            "total_input_tokens": self.total_tokens_in,
            "total_output_tokens": self.total_tokens_out,
            "total_calls": self.total_calls,
            "avg_input_tokens": self.total_tokens_in / max(1, self.total_calls),
            "avg_output_tokens": self.total_tokens_out / max(1, self.total_calls),
        }

"""Aulinx agent adapter for OSWorld benchmark.

Implements the predict(instruction, obs) interface expected by
OSWorld's run harness. Uses Aulinx's semantic a11y understanding
to control the desktop with structured actions.

v0.6: Adds action grounding (element→coords) and perception-aware observation.
"""

from __future__ import annotations

import asyncio
import logging
import time

from aulinx.grounding import ground_element_from_tree
from aulinx.llm import create_client
from aulinx.perception import ObservationMode, count_interactive_elements, decide_observation_mode

from .action_mapper import parse_response
from .prompt_builder import build_prompt, parse_a11y_tree

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
        self._last_parsed_tree = ""  # cached for grounding

    def reset(self, runtime_logger=None, **kwargs):
        """Reset agent state between tasks."""
        self.history = []
        self._step_count = 0
        self.total_tokens_in = 0
        self.total_tokens_out = 0
        self.total_calls = 0
        self._last_parsed_tree = ""
        if runtime_logger:
            logger.handlers = runtime_logger.handlers

    def predict(self, instruction: str, obs: dict) -> tuple[str, list]:
        """Predict the next action(s) given an observation.

        v0.6: Uses perception module to decide observation mode and
        grounding module to validate/correct click coordinates.
        """
        a11y_tree = obs.get("accessibility_tree", "") or ""
        parsed_tree = parse_a11y_tree(a11y_tree)
        self._last_parsed_tree = parsed_tree

        # Perception: decide observation mode
        element_count = count_interactive_elements(parsed_tree)
        obs_mode = decide_observation_mode(
            parsed_tree,
            focused_app="",  # not available from OSWorld obs
            element_count=element_count,
        )

        if obs_mode == ObservationMode.SCREENSHOT:
            logger.info("Observation: SCREENSHOT mode (sparse tree, %d elements)", element_count)
        elif obs_mode == ObservationMode.HYBRID:
            logger.info("Observation: HYBRID mode (%d elements)", element_count)

        messages = build_prompt(instruction, a11y_tree, history=self.history)

        # Call LLM
        response_text = self._call_llm(messages)
        self.total_calls += 1

        # Parse response into action
        thought, action = parse_response(response_text)

        # Grounding: try to correct coordinates for click actions
        action = self._try_ground(action, thought)

        # Record history
        self._step_count = getattr(self, '_step_count', 0) + 1
        obs_summary = f"[Step {self._step_count}] Screen state:\n{parsed_tree}"
        self.history.append({
            "observation": obs_summary,
            "response": response_text.split("\n")[0],
        })

        if len(self.history) > self.max_trajectory_length:
            self.history = self.history[-self.max_trajectory_length:]

        logger.info("Step %d — thought: %s", self._step_count, thought)
        logger.info("Action: %s", action)

        actions = [action] if not isinstance(action, list) else action
        return response_text, actions

    def _try_ground(self, action: dict | str, thought: str = "") -> dict | str:
        """Try to ground click coordinates using the cached a11y tree.

        If the LLM's click coordinates are (0,0) or look wrong, search the
        a11y tree for the target element mentioned in the thought text and
        correct the coordinates.

        Also validates non-zero coordinates: if the click target is named
        in the thought and we can find it, verify the coords are close.
        """
        if not isinstance(action, dict) or not self._last_parsed_tree:
            return action

        action_type = action.get("action_type", "")
        if action_type not in ("CLICK", "DOUBLE_CLICK", "RIGHT_CLICK"):
            return action

        coord = action.get("coordinate", [0, 0])

        # Extract target element name from thought text
        target = _extract_click_target(thought)
        if not target:
            return action

        # Try to find the element in the tree
        grounded = ground_element_from_tree(target, self._last_parsed_tree)
        if not grounded:
            return action

        # Case 1: Zero coordinates — replace with grounded coords
        if coord == [0, 0]:
            logger.info(
                "Grounding: (0,0) → (%d,%d) for '%s' (confidence=%.2f)",
                grounded.center_x, grounded.center_y, target, grounded.confidence,
            )
            action["coordinate"] = [grounded.center_x, grounded.center_y]
            return action

        # Case 2: Non-zero but far from the grounded element — correct if confident
        dx = abs(coord[0] - grounded.center_x)
        dy = abs(coord[1] - grounded.center_y)
        if (dx > 100 or dy > 100) and grounded.confidence >= 0.7:
            logger.info(
                "Grounding: (%d,%d) → (%d,%d) for '%s' (off by %d,%d, confidence=%.2f)",
                coord[0], coord[1], grounded.center_x, grounded.center_y,
                target, dx, dy, grounded.confidence,
            )
            action["coordinate"] = [grounded.center_x, grounded.center_y]

        return action

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

        try:
            asyncio.get_running_loop()
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                pool.submit(lambda: asyncio.run(_run())).result(timeout=120)
        except RuntimeError:
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


def _extract_click_target(thought: str) -> str:
    """Extract the target element name from an LLM thought string.

    Patterns:
    - "I need to click on Documents" → "Documents"
    - "click the Save button" → "Save"
    - "I'll click 'New Folder'" → "New Folder"
    - "clicking on the OK button" → "OK"
    """
    import re

    if not thought:
        return ""

    # Pattern 1: quoted target — 'Name' or "Name"
    quoted = re.search(r"""['"]([^'"]+)['"]""", thought)
    if quoted:
        return quoted.group(1)

    # Pattern 2: "click (on|the) <target> (button|link|tab|...)"
    click_match = re.search(
        r"click(?:ing)?\s+(?:on\s+)?(?:the\s+)?(\w[\w\s]*?)(?:\s+(?:button|link|tab|menu|item|icon|folder|file|option|checkbox))?[.,!]?\s*$",
        thought,
        re.IGNORECASE,
    )
    if click_match:
        target = click_match.group(1).strip()
        if len(target) >= 2:
            return target

    # Pattern 3: "select <target>"
    select_match = re.search(
        r"select\s+(?:the\s+)?(\w[\w\s]*?)(?:\s+(?:option|item|entry))?[.,!]?\s*$",
        thought,
        re.IGNORECASE,
    )
    if select_match:
        target = select_match.group(1).strip()
        if len(target) >= 2:
            return target

    # Pattern 4: "open <target>"
    open_match = re.search(
        r"open\s+(?:the\s+)?(\w[\w\s]*?)(?:\s+(?:folder|file|app|application))?[.,!]?\s*$",
        thought,
        re.IGNORECASE,
    )
    if open_match:
        target = open_match.group(1).strip()
        if len(target) >= 2:
            return target

    return ""

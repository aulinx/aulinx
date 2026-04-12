"""Learning from outcomes — records task results and retrieves relevant past experience.

After each task, records the goal, plan, actions taken, and whether it succeeded.
On future similar tasks, retrieves past attempts to inject into the planning prompt,
allowing the agent to learn from experience and avoid repeating mistakes.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

OUTCOMES_DIR = Path.home() / ".local/share/aulinx/outcomes"

# Maximum past outcomes to retrieve for context
MAX_RELEVANT_OUTCOMES = 3


@dataclass
class TaskOutcome:
    """Record of a completed task attempt."""
    goal: str
    plan_steps: list[str] = field(default_factory=list)  # ["1. tool — desc", ...]
    actions_taken: list[str] = field(default_factory=list)  # ["tool(args)", ...]
    success: bool = False
    failure_reason: str = ""
    duration_s: float = 0.0
    model: str = ""
    timestamp: str = ""
    keywords: list[str] = field(default_factory=list)


class OutcomeStore:
    """Persistent store for task outcomes, enabling learning across sessions."""

    def __init__(self, store_dir: Path | None = None):
        self._dir = store_dir or OUTCOMES_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._outcomes_file = self._dir / "outcomes.jsonl"

    def record(self, outcome: TaskOutcome):
        """Append a task outcome to the store."""
        if not outcome.timestamp:
            outcome.timestamp = time.strftime("%Y-%m-%dT%H:%M:%S")
        if not outcome.keywords:
            outcome.keywords = sorted(_extract_keywords(outcome.goal))

        try:
            data = asdict(outcome)
            data["keywords"] = list(data.get("keywords", []))  # sets aren't JSON-serializable
            with open(self._outcomes_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(data, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def retrieve_relevant(self, goal: str, limit: int = MAX_RELEVANT_OUTCOMES) -> list[TaskOutcome]:
        """Find past outcomes relevant to the current goal.

        Uses keyword overlap scoring to find similar past tasks.
        """
        goal_keywords = _extract_keywords(goal)
        if not goal_keywords:
            return []

        scored: list[tuple[float, TaskOutcome]] = []

        for outcome in self._load_all():
            score = _keyword_overlap(goal_keywords, set(outcome.keywords))
            if score > 0:
                scored.append((score, outcome))

        # Sort by relevance, then recency (timestamp)
        scored.sort(key=lambda x: (-x[0], x[1].timestamp), reverse=False)
        scored.sort(key=lambda x: -x[0])

        return [outcome for _, outcome in scored[:limit]]

    def build_experience_context(self, goal: str) -> str:
        """Build a context string from relevant past outcomes for the LLM.

        Returns an empty string if no relevant outcomes are found.
        """
        relevant = self.retrieve_relevant(goal)
        if not relevant:
            return ""

        parts = ["## Past Experience (similar tasks)"]
        for i, outcome in enumerate(relevant, 1):
            status = "SUCCEEDED" if outcome.success else "FAILED"
            part = f"\n### Attempt {i} [{status}]"
            part += f"\nGoal: {outcome.goal}"
            if outcome.plan_steps:
                part += f"\nPlan: {'; '.join(outcome.plan_steps[:5])}"
            if outcome.actions_taken:
                part += f"\nActions: {'; '.join(outcome.actions_taken[:5])}"
            if not outcome.success and outcome.failure_reason:
                part += f"\nFailed because: {outcome.failure_reason}"
            parts.append(part)

        parts.append("\nLearn from these past attempts. Repeat what worked, avoid what failed.")
        return "\n".join(parts)

    def get_stats(self) -> dict:
        """Get summary statistics about recorded outcomes."""
        outcomes = self._load_all()
        if not outcomes:
            return {"total": 0, "success_rate": 0.0}

        total = len(outcomes)
        successes = sum(1 for o in outcomes if o.success)
        return {
            "total": total,
            "successes": successes,
            "failures": total - successes,
            "success_rate": round(successes / total * 100, 1) if total else 0.0,
        }

    def _load_all(self) -> list[TaskOutcome]:
        """Load all outcomes from the JSONL file."""
        if not self._outcomes_file.exists():
            return []

        outcomes = []
        try:
            with open(self._outcomes_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        outcomes.append(TaskOutcome(**data))
                    except (json.JSONDecodeError, TypeError):
                        continue
        except OSError:
            pass

        return outcomes


def _extract_keywords(text: str) -> set[str]:
    """Extract meaningful keywords from a goal/task description."""
    # Common stop words to filter out
    stop_words = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been",
        "being", "have", "has", "had", "do", "does", "did", "will",
        "would", "could", "should", "may", "might", "can", "shall",
        "to", "of", "in", "for", "on", "with", "at", "by", "from",
        "and", "or", "but", "not", "no", "if", "then", "else",
        "this", "that", "it", "its", "my", "your", "me", "i",
        "what", "how", "when", "where", "which", "who", "please",
    }

    words = set()
    for word in text.lower().split():
        # Strip punctuation
        word = word.strip(".,!?;:'\"()[]{}")
        if len(word) >= 2 and word not in stop_words:
            words.add(word)

    return words


def _keyword_overlap(set_a: set[str], set_b: set[str]) -> float:
    """Score the overlap between two keyword sets (0-1)."""
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    # Jaccard-like similarity, weighted toward the query
    return len(intersection) / len(set_a)

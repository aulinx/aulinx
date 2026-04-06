"""Git tools — status, log, diff, commit, branch operations."""

import subprocess
from pathlib import Path

from aulinx.tools.base import Tier, Tool


def _git(*args: str, cwd: str = ".", timeout: int = 15) -> dict:
    """Run a git command and return output."""
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True, text=True, timeout=timeout,
            cwd=Path(cwd).expanduser().resolve(),
        )
        return {
            "stdout": result.stdout.strip(),
            "returncode": result.returncode,
            "stderr": result.stderr.strip(),
        }
    except FileNotFoundError:
        return {"error": "git not found"}
    except subprocess.TimeoutExpired:
        return {"error": "git timed out"}


async def git_status(path: str = ".") -> dict:
    """Get git status — branch, modified files, staged files, untracked files."""
    r = _git("status", "--porcelain=v2", "--branch", cwd=path)
    if "error" in r:
        return r
    if r["returncode"] != 0:
        return {"error": r["stderr"] or "Not a git repository"}

    info = {"branch": "", "modified": [], "staged": [], "untracked": []}

    for line in r["stdout"].splitlines():
        if line.startswith("# branch.head"):
            info["branch"] = line.split()[-1]
        elif line.startswith("# branch.ab"):
            parts = line.split()
            info["ahead"] = int(parts[2].lstrip("+"))
            info["behind"] = int(parts[3].lstrip("-"))
        elif line.startswith("1 ") or line.startswith("2 "):
            parts = line.split()
            xy = parts[1]
            filename = parts[-1]
            if xy[0] != ".":
                info["staged"].append(filename)
            if xy[1] != ".":
                info["modified"].append(filename)
        elif line.startswith("? "):
            info["untracked"].append(line[2:])

    return info


async def git_log(path: str = ".", limit: int = 10) -> list[dict]:
    """Get recent git commits."""
    r = _git(
        "log", f"-{limit}", "--format=%H|%h|%an|%ae|%ar|%s",
        cwd=path,
    )
    if "error" in r:
        return [r]
    if r["returncode"] != 0:
        return [{"error": r["stderr"]}]

    commits = []
    for line in r["stdout"].splitlines():
        parts = line.split("|", 5)
        if len(parts) >= 6:
            commits.append({
                "hash": parts[0],
                "short_hash": parts[1],
                "author": parts[2],
                "email": parts[3],
                "relative_date": parts[4],
                "message": parts[5],
            })
    return commits


async def git_diff(path: str = ".", staged: bool = False) -> str:
    """Get git diff — unstaged changes by default, or staged with staged=true."""
    args = ["diff", "--stat"]
    if staged:
        args.append("--cached")
    r = _git(*args, cwd=path)
    if "error" in r:
        return str(r)
    return r["stdout"] or "(no changes)"


async def git_commit(path: str = ".", message: str = "") -> dict:
    """Create a git commit with the given message. Stages all changes first."""
    if not message:
        return {"error": "Commit message is required"}

    # Stage all changes
    r = _git("add", "-A", cwd=path)
    if r.get("returncode", 1) != 0:
        return {"error": f"git add failed: {r.get('stderr', '')}"}

    # Commit
    r = _git("commit", "-m", message, cwd=path)
    if r["returncode"] == 0:
        return {"committed": True, "message": message, "output": r["stdout"][:300]}
    return {"error": r["stderr"] or r["stdout"]}


async def git_branch(path: str = ".") -> dict:
    """List git branches and show current branch."""
    r = _git("branch", "-a", "--format=%(refname:short) %(HEAD)", cwd=path)
    if "error" in r:
        return r
    if r["returncode"] != 0:
        return {"error": r["stderr"]}

    branches = []
    current = ""
    for line in r["stdout"].splitlines():
        parts = line.strip().split()
        name = parts[0]
        is_current = len(parts) > 1 and parts[1] == "*"
        if is_current:
            current = name
        branches.append(name)

    return {"current": current, "branches": branches}


async def git_stash(path: str = ".", action: str = "list") -> dict:
    """Git stash operations: list, push, pop."""
    if action == "list":
        r = _git("stash", "list", cwd=path)
        if r["returncode"] == 0:
            entries = r["stdout"].splitlines() if r["stdout"] else []
            return {"stashes": entries}
    elif action == "push":
        r = _git("stash", "push", cwd=path)
        if r["returncode"] == 0:
            return {"stashed": True, "output": r["stdout"]}
    elif action == "pop":
        r = _git("stash", "pop", cwd=path)
        if r["returncode"] == 0:
            return {"popped": True, "output": r["stdout"]}
    else:
        return {"error": "Action must be: list, push, or pop"}

    return {"error": r.get("stderr", "") or r.get("stdout", "")}


TOOLS = [
    Tool(
        name="git_status",
        description="Get git status — branch, modified, staged, and untracked files",
        fn=git_status,
        parameters={"path": "string (repo path, default: current dir)"},
        tier=Tier.OBSERVE,
    ),
    Tool(
        name="git_log",
        description="Get recent git commits with hash, author, date, and message",
        fn=git_log,
        parameters={"path": "string", "limit": "int (default 10)"},
        tier=Tier.OBSERVE,
    ),
    Tool(
        name="git_diff",
        description="Show git diff summary. Use staged=true for staged changes.",
        fn=git_diff,
        parameters={"path": "string", "staged": "bool (default false)"},
        tier=Tier.OBSERVE,
    ),
    Tool(
        name="git_commit",
        description="Stage all changes and create a git commit. Requires a message.",
        fn=git_commit,
        parameters={"path": "string", "message": "string (commit message)"},
        tier=Tier.DESTRUCTIVE,
    ),
    Tool(
        name="git_branch",
        description="List git branches and show current branch",
        fn=git_branch,
        parameters={"path": "string"},
        tier=Tier.OBSERVE,
    ),
    Tool(
        name="git_stash",
        description="Git stash operations: list, push (save changes), pop (restore changes)",
        fn=git_stash,
        parameters={"path": "string", "action": "list|push|pop (default: list)"},
        tier=Tier.MUTATE,
    ),
]

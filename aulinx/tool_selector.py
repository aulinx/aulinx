"""Dynamic tool selection — picks the right tools for each task.

Instead of always sending the same ~50 CORE_TOOLS to the LLM, this module
selects tools based on the user's intent and current desktop state. This
reduces prompt tokens while increasing tool relevance.

For example:
- "manage files" → file, git, text tools
- "browse the web" → web, input, window tools
- "configure system" → services, packages, sysadmin tools
"""

from __future__ import annotations

# Tool groups organized by task domain
TOOL_GROUPS: dict[str, set[str]] = {
    "files": {
        "file_read", "file_write", "file_edit", "file_list", "file_search",
        "file_move", "file_trash", "text_grep", "text_count", "text_replace",
        "text_head", "text_tail", "archive_create", "archive_extract",
        "xdg_open",
    },
    "git": {
        "git_status", "git_log", "git_diff", "git_commit", "git_branch",
        "git_stash", "shell_exec",
    },
    "gui_interaction": {
        "window_list", "window_get_focused", "window_focus", "window_close",
        "atspi_get_tree", "atspi_find_elements", "atspi_do_action",
        "atspi_read_text", "atspi_set_text",
        "input_type_text", "input_key_combo",
        "app_launch", "app_list_running",
    },
    "web_browser": {
        "web_search", "web_fetch",
        "input_type_text", "input_key_combo",
        "window_list", "window_focus",
        "atspi_get_tree", "atspi_find_elements", "atspi_do_action",
        "screenshot", "screenshot_ocr",
    },
    "system_admin": {
        "system_info", "shell_exec", "process_list", "process_kill",
        "services_list", "services_status", "services_start", "services_stop",
        "packages_search", "packages_install", "packages_list_installed",
        "journal_logs", "docker_ps", "docker_logs", "port_list",
        "firewall_status", "disk_usage", "disk_info",
    },
    "network": {
        "network_status", "wifi_list", "wifi_connect", "wifi_disconnect",
        "bluetooth_status", "bluetooth_scan", "bluetooth_connect",
        "port_list", "shell_exec",
    },
    "media_audio": {
        "audio_get_volume", "audio_set_volume", "audio_mute",
        "display_list", "display_brightness",
        "theme_get", "theme_set_dark", "theme_wallpaper_set",
    },
    "productivity": {
        "note_add", "note_list", "todo_add", "todo_list", "todo_done",
        "set_timer", "cancel_timer", "list_timers",
        "schedule_at", "schedule_daily",
        "notification_send", "date_now", "calendar_show",
    },
    "memory": {
        "memory_store", "memory_get", "memory_delete",
        "remember", "recall", "recall_recent", "forget",
    },
    "compositor": {
        "compositor_summary", "compositor_describe", "compositor_ascii",
        "compositor_suggest", "compositor_windows", "compositor_focused",
        "compositor_type", "compositor_key", "compositor_click",
        "compositor_screenshot", "compositor_annotated_screenshot",
        "compositor_spawn", "compositor_focus", "compositor_close",
        "compositor_wait_for", "compositor_diff",
        "compositor_find_window", "compositor_run_and_type",
    },
}

# Keywords that map to tool groups
_INTENT_KEYWORDS: dict[str, list[str]] = {
    "files": [
        "file", "folder", "directory", "read", "write", "edit", "create",
        "delete", "move", "copy", "rename", "find", "search file", "open",
        "save", "document", "download", "archive", "zip", "extract",
    ],
    "git": [
        "git", "commit", "branch", "merge", "diff", "push", "pull",
        "repository", "repo", "stash", "checkout",
    ],
    "gui_interaction": [
        "click", "button", "window", "app", "launch", "open app",
        "type", "field", "menu", "dialog", "gui", "interface", "ui",
        "close window", "switch window", "text field",
    ],
    "web_browser": [
        "browse", "browser", "firefox", "chrome", "chromium", "web",
        "website", "url", "search online", "google", "internet",
        "navigate", "bookmark",
    ],
    "system_admin": [
        "system", "process", "service", "package", "install",
        "docker", "container", "port", "firewall", "log", "journal",
        "disk", "cpu", "memory usage", "systemctl", "server",
    ],
    "network": [
        "network", "wifi", "bluetooth", "connect", "disconnect",
        "internet", "ip address", "ping", "ssh",
    ],
    "media_audio": [
        "volume", "audio", "sound", "mute", "brightness", "display",
        "screen", "theme", "dark mode", "wallpaper", "monitor",
    ],
    "productivity": [
        "note", "todo", "timer", "alarm", "schedule", "remind",
        "notification", "calendar", "date", "time",
    ],
    "memory": [
        "remember", "recall", "forget", "memory", "store", "save info",
    ],
    "compositor": [
        "compositor", "tiling", "layout", "workspace", "gap", "ratio",
        "master", "stack", "spawn",
    ],
}

# Universal tools always included regardless of intent
_ALWAYS_INCLUDED = {
    "shell_exec", "system_info", "who_am_i", "context_get",
    "clipboard_get", "clipboard_set",
}


def select_tools(
    user_query: str,
    mode: str = "desktop",
    available_tools: set[str] | None = None,
    max_tools: int = 55,
) -> set[str]:
    """Select the most relevant tools for a user query.

    Args:
        user_query: The user's natural language request
        mode: Operating mode (core/desktop/compositor)
        available_tools: Set of all available tool names (for filtering)
        max_tools: Maximum number of tools to return

    Returns:
        Set of tool names to send to the LLM
    """
    query_lower = user_query.lower()

    # Score each group by keyword matches
    group_scores: dict[str, float] = {}
    for group, keywords in _INTENT_KEYWORDS.items():
        score = 0.0
        for keyword in keywords:
            if keyword in query_lower:
                # Longer keyword matches are more specific
                score += len(keyword) / 10.0
        if score > 0:
            group_scores[group] = score

    # Always include the top-scoring groups
    selected: set[str] = set(_ALWAYS_INCLUDED)

    if group_scores:
        # Sort groups by score, pick top ones
        ranked = sorted(group_scores.items(), key=lambda x: -x[1])
        for group_name, _score in ranked:
            if len(selected) >= max_tools:
                break
            group_tools = TOOL_GROUPS.get(group_name, set())
            selected |= group_tools
    else:
        # No clear intent — fall back to a general set
        selected |= TOOL_GROUPS["files"]
        selected |= TOOL_GROUPS["gui_interaction"]
        selected |= TOOL_GROUPS["system_admin"]
        if mode == "compositor":
            selected |= TOOL_GROUPS["compositor"]

    # Mode-specific additions
    if mode == "compositor" and "compositor" not in group_scores:
        # Always include basic compositor tools in compositor mode
        selected |= {
            "compositor_summary", "compositor_suggest",
            "compositor_click", "compositor_type", "compositor_key",
        }

    # Filter to only available tools
    if available_tools is not None:
        selected &= available_tools

    # Trim to max_tools if needed (keep always-included, then highest-scored groups)
    if len(selected) > max_tools:
        # Keep _ALWAYS_INCLUDED, then trim from lowest-scored groups
        must_keep = selected & _ALWAYS_INCLUDED
        rest = list(selected - must_keep)
        selected = must_keep | set(rest[:max_tools - len(must_keep)])

    return selected


def classify_intent(user_query: str) -> list[str]:
    """Classify the user's intent into tool group names.

    Returns a list of group names sorted by relevance.
    """
    query_lower = user_query.lower()
    scores: dict[str, float] = {}

    for group, keywords in _INTENT_KEYWORDS.items():
        score = sum(len(kw) / 10.0 for kw in keywords if kw in query_lower)
        if score > 0:
            scores[group] = score

    return [g for g, _ in sorted(scores.items(), key=lambda x: -x[1])]

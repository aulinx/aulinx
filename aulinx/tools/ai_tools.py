"""AI-powered tools — summarize, explain, translate using the LLM itself."""

import httpx

from aulinx.tools.base import Tier, Tool

# These tools use the LLM as a sub-tool — they send a prompt to Ollama
# and return the response. The main agent's model handles tool calling,
# and these tools use the same or different model for text generation.

_DEFAULT_URL = "http://localhost:11434"


async def _ask_llm(prompt: str, model: str = "", base_url: str = "") -> str:
    """Send a prompt to Ollama and get a text response."""
    url = base_url or _DEFAULT_URL
    mdl = model or "qwen2.5:14b"

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{url}/api/generate",
                json={"model": mdl, "prompt": prompt, "stream": False, "options": {"temperature": 0.3}},
                timeout=httpx.Timeout(connect=5, read=60, write=5, pool=5),
            )
            resp.raise_for_status()
            return resp.json().get("response", "").strip()
    except Exception as e:
        return f"Error: {e}"


async def summarize_text(text: str, max_words: int = 100) -> dict:
    """Summarize a piece of text using the LLM."""
    prompt = f"Summarize the following text in {max_words} words or less. Be concise.\n\n{text[:5000]}"
    result = await _ask_llm(prompt)
    return {"summary": result}


async def summarize_file(path: str, max_words: int = 100) -> dict:
    """Summarize a file's contents using the LLM."""
    from pathlib import Path
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        return {"error": f"File not found: {path}"}
    try:
        content = p.read_text(errors="replace")[:5000]
    except Exception as e:
        return {"error": str(e)}

    prompt = f"Summarize this file ({p.name}) in {max_words} words or less:\n\n{content}"
    result = await _ask_llm(prompt)
    return {"file": str(p), "summary": result}


async def explain_code(code: str, language: str = "") -> dict:
    """Explain what a piece of code does."""
    lang_hint = f" ({language})" if language else ""
    prompt = f"Explain what this code{lang_hint} does in simple terms:\n\n```\n{code[:3000]}\n```"
    result = await _ask_llm(prompt)
    return {"explanation": result}


async def translate_text(text: str, target_language: str = "English") -> dict:
    """Translate text to a target language."""
    prompt = f"Translate the following text to {target_language}. Only output the translation, nothing else.\n\n{text[:3000]}"
    result = await _ask_llm(prompt)
    return {"original": text[:200], "translated": result, "language": target_language}


async def rewrite_text(text: str, style: str = "professional") -> dict:
    """Rewrite text in a different style (professional, casual, concise, formal)."""
    prompt = f"Rewrite the following text in a {style} style. Only output the rewritten text.\n\n{text[:3000]}"
    result = await _ask_llm(prompt)
    return {"original": text[:200], "rewritten": result, "style": style}


TOOLS = [
    Tool(
        name="summarize_text",
        description="Summarize text using AI. Give it any text and get a concise summary.",
        fn=summarize_text,
        parameters={"text": "string (text to summarize)", "max_words": "int (default 100)"},
        tier=Tier.OBSERVE,
    ),
    Tool(
        name="summarize_file",
        description="Summarize a file's contents using AI",
        fn=summarize_file,
        parameters={"path": "string (file path)", "max_words": "int (default 100)"},
        tier=Tier.OBSERVE,
    ),
    Tool(
        name="explain_code",
        description="Explain what a piece of code does in simple terms",
        fn=explain_code,
        parameters={"code": "string (code to explain)", "language": "string (optional: python, rust, etc.)"},
        tier=Tier.OBSERVE,
    ),
    Tool(
        name="translate_text",
        description="Translate text to another language using AI",
        fn=translate_text,
        parameters={"text": "string", "target_language": "string (default: English)"},
        tier=Tier.OBSERVE,
    ),
    Tool(
        name="rewrite_text",
        description="Rewrite text in a different style (professional, casual, concise, formal)",
        fn=rewrite_text,
        parameters={"text": "string", "style": "professional|casual|concise|formal (default: professional)"},
        tier=Tier.OBSERVE,
    ),
]

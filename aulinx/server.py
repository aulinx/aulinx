"""WebSocket server — bridges the UI command palette to the agent with native tool calling."""

import asyncio
import json
import time

import httpx
import websockets
from rich.console import Console

from aulinx.agent import Agent, _strip_json_blocks
from aulinx.config import load_config

console = Console()


class WebSocketServer:
    """Serves the Aulinx agent over WebSocket for the UI palette."""

    def __init__(self, host: str = "0.0.0.0", port: int = 8765):
        self.host = host
        self.port = port
        self.agent: Agent | None = None

    async def start(self, model: str = "", base_url: str = ""):
        """Initialize agent and start WebSocket server."""
        config = load_config()
        self.agent = Agent(
            model=model or config.llm.model,
            base_url=base_url or config.llm.base_url,
            temperature=config.llm.temperature,
            max_history=config.context.max_history,
        )
        await self.agent.initialize()

        console.print(f"[bold gold1]Aulinx[/bold gold1] WebSocket server on ws://{self.host}:{self.port}")

        import logging
        logging.getLogger("websockets").setLevel(logging.CRITICAL)

        async with websockets.serve(
            self._handle_client,
            self.host,
            self.port,
            logger=logging.getLogger("websockets.server"),
            ping_interval=30,
            ping_timeout=10,
        ):
            await asyncio.Future()

    async def _handle_client(self, ws):
        """Handle a single WebSocket client connection."""
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=5)
        except Exception:
            return

        console.print("[dim]Client connected[/dim]")
        agent = self.agent

        try:
            # Process first message
            await self._handle_raw_message(ws, agent, raw)

            # Process remaining messages
            async for raw in ws:
                await self._handle_raw_message(ws, agent, raw)

        except websockets.ConnectionClosed:
            console.print("[dim]Client disconnected[/dim]")
        except Exception as e:
            console.print(f"[red]Client handler error: {e}[/red]")

    async def _handle_raw_message(self, ws, agent: Agent, raw: str):
        """Parse and process a single WebSocket message."""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            await ws.send(json.dumps({"type": "error", "message": "Invalid JSON"}))
            return

        if data.get("type") != "message":
            return

        user_input = data.get("content", "").strip()
        if not user_input:
            return

        agent.history.append({"role": "user", "content": user_input})

        try:
            await self._process_with_tools(ws, agent, depth=0)
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            try:
                await ws.send(json.dumps({"type": "error", "message": str(e)}))
                await ws.send(json.dumps({"type": "done"}))
            except Exception:
                pass

    async def _process_with_tools(self, ws, agent: Agent, depth: int = 0):
        """Call Ollama with native tool calling and stream results to UI."""
        if depth > 5:
            await ws.send(json.dumps({"type": "done"}))
            return

        from aulinx.agent import SYSTEM_PROMPT
        ctx = await agent.context.snapshot()
        system_msg = SYSTEM_PROMPT + f"\n\nCurrent desktop state:\n{ctx}"

        messages = [
            {"role": "system", "content": system_msg},
            *agent.history[-agent.max_history:],
        ]

        tools = agent.tools.to_ollama_tools()

        # Call Ollama (non-streaming for tool calling)
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{agent.base_url}/api/chat",
                    json={
                        "model": agent.model,
                        "messages": messages,
                        "tools": tools,
                        "stream": False,
                        "options": {"temperature": agent.temperature},
                    },
                    timeout=httpx.Timeout(connect=10, read=120, write=10, pool=10),
                )
                resp.raise_for_status()
                result = resp.json()
        except Exception as e:
            await ws.send(json.dumps({"type": "error", "message": str(e)}))
            await ws.send(json.dumps({"type": "done"}))
            return

        response_msg = result.get("message", {})
        content = response_msg.get("content", "")
        tool_calls = response_msg.get("tool_calls")

        # Send text content to UI
        if content:
            cleaned = _strip_json_blocks(content)
            if cleaned:
                await ws.send(json.dumps({"type": "token", "content": cleaned}))

        # Save to history
        history_entry = {"role": "assistant", "content": content or ""}
        if tool_calls:
            history_entry["tool_calls"] = tool_calls
        agent.history.append(history_entry)
        agent.history_mgr.save(agent.history)

        # Execute tool calls
        if tool_calls:
            for tc in tool_calls:
                fn = tc.get("function", {})
                tool_name = fn.get("name", "")
                args = fn.get("arguments", {})

                if not tool_name or tool_name not in agent.tools:
                    continue

                # Notify UI
                await ws.send(json.dumps({"type": "tool_call", "tool": tool_name, "args": args}))

                # Execute
                t0 = time.monotonic()
                tool_result = await agent.tools.execute(tool_name, args)
                duration_ms = int((time.monotonic() - t0) * 1000)
                result_str = json.dumps(tool_result, indent=2, ensure_ascii=False, default=str)

                agent.audit.log(tool_name, args, result_str, duration_ms)

                if len(result_str) > 3000:
                    result_str = result_str[:3000] + "\n... (truncated)"

                # Send result to UI
                await ws.send(json.dumps({
                    "type": "tool_result",
                    "tool": tool_name,
                    "result": tool_result,
                    "duration_ms": duration_ms,
                }))

                # Add to history for LLM
                agent.history.append({
                    "role": "tool",
                    "content": result_str,
                })

            # Let LLM process results
            await self._process_with_tools(ws, agent, depth + 1)
        else:
            await ws.send(json.dumps({"type": "done"}))


async def run_server(host: str = "localhost", port: int = 8765, model: str = "", base_url: str = ""):
    server = WebSocketServer(host, port)
    await server.start(model=model, base_url=base_url)

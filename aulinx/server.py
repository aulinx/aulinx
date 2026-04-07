"""WebSocket server — bridges the UI command palette to the agent via streaming."""

import asyncio
import json
import logging
import time

import websockets
from rich.console import Console

from aulinx.agent import SYSTEM_PROMPT, Agent
from aulinx.config import load_config

console = Console()


class WebSocketServer:
    """Serves the Aulinx agent over WebSocket for the UI palette."""

    def __init__(self, host: str = "0.0.0.0", port: int = 8765):
        self.host = host
        self.port = port
        self.agent: Agent | None = None

    async def start(self, model: str = "", base_url: str = ""):
        config = load_config()
        self.agent = Agent(
            model=model or config.llm.model,
            base_url=base_url or config.llm.base_url,
            temperature=config.llm.temperature,
            max_history=config.context.max_history,
        )
        await self.agent.initialize()

        console.print(f"[bold gold1]Aulinx[/bold gold1] WebSocket server on ws://{self.host}:{self.port}")

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
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=5)
        except Exception:
            return

        console.print("[dim]Client connected[/dim]")
        agent = self.agent

        try:
            await self._handle_raw(ws, agent, raw)
            async for raw in ws:
                await self._handle_raw(ws, agent, raw)
        except websockets.ConnectionClosed:
            console.print("[dim]Client disconnected[/dim]")
        except Exception as e:
            console.print(f"[red]Client error: {e}[/red]")

    async def _handle_raw(self, ws, agent: Agent, raw: str):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            await ws.send(json.dumps({"type": "error", "message": "Invalid JSON"}))
            return

        # Handle API requests from the dashboard
        if data.get("type") == "api":
            from aulinx.api import handle_api_request
            result = await handle_api_request(
                data.get("path", ""),
                data.get("method", "GET"),
                data.get("body"),
            )
            await ws.send(json.dumps({"type": "api_response", "path": data.get("path"), "data": result}))
            return

        if data.get("type") != "message":
            return

        user_input = data.get("content", "").strip()
        if not user_input:
            return

        agent.history.append({"role": "user", "content": user_input})

        try:
            await self._process(ws, agent, depth=0)
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            try:
                await ws.send(json.dumps({"type": "error", "message": str(e)}))
                await ws.send(json.dumps({"type": "done"}))
            except Exception:
                pass

    async def _process(self, ws, agent: Agent, depth: int = 0):
        if depth > 5:
            await ws.send(json.dumps({"type": "done"}))
            return

        ctx = await agent.context.snapshot()
        system_msg = SYSTEM_PROMPT + f"\n\nDesktop state:\n{ctx}"

        messages = [
            {"role": "system", "content": system_msg},
            *agent.history[-agent.max_history:],
        ]

        tools = agent.tools.to_ollama_tools()
        full_content = ""
        tool_calls = None

        # Stream from LLM
        async for event in agent.llm.chat_with_tools(messages, tools):
            if event.type == "token":
                full_content = event.data.get("content", "")
                # Stream tokens to UI (skip if tool calls will follow)
                await ws.send(json.dumps({"type": "token", "content": event.data.get("content", "")}))

            elif event.type == "tool_calls":
                tool_calls = event.data.get("calls")

            elif event.type == "done":
                full_content = event.data.get("content", "")
                tool_calls = event.data.get("tool_calls")

            elif event.type == "error":
                await ws.send(json.dumps({"type": "error", "message": event.data.get("message", "")}))
                await ws.send(json.dumps({"type": "done"}))
                return

        # Save to history
        history_entry = {"role": "assistant", "content": full_content or ""}
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

                await ws.send(json.dumps({"type": "tool_call", "tool": tool_name, "args": args}))

                t0 = time.monotonic()
                result = await agent.tools.execute(tool_name, args)
                duration_ms = int((time.monotonic() - t0) * 1000)
                result_str = json.dumps(result, indent=2, ensure_ascii=False, default=str)

                agent.audit.log(tool_name, args, result_str, duration_ms)

                if len(result_str) > 3000:
                    result_str = result_str[:3000] + "\n... (truncated)"

                await ws.send(json.dumps({
                    "type": "tool_result",
                    "tool": tool_name,
                    "result": result,
                    "duration_ms": duration_ms,
                }))

                agent.history.append({"role": "tool", "content": result_str})

            await self._process(ws, agent, depth + 1)
        else:
            await ws.send(json.dumps({"type": "done"}))


async def run_server(host: str = "localhost", port: int = 8765, model: str = "", base_url: str = ""):
    server = WebSocketServer(host, port)
    await server.start(model=model, base_url=base_url)

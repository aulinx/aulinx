"""WebSocket server — bridges the UI command palette to the agent."""

import asyncio
import json

import websockets
from rich.console import Console

from aulinx.agent import Agent, _extract_tool_call
from aulinx.config import load_config

console = Console()

SYSTEM_PROMPT_FOR_WS = None  # populated from agent


class WebSocketServer:
    """Serves the Aulinx agent over WebSocket for the UI palette."""

    def __init__(self, host: str = "localhost", port: int = 8765):
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
        logging.getLogger("websockets").setLevel(logging.ERROR)

        async with websockets.serve(self._handle_client, self.host, self.port):
            await asyncio.Future()  # run forever

    async def _handle_client(self, ws):
        """Handle a single WebSocket client connection."""
        console.print("[dim]Client connected[/dim]")
        agent = self.agent

        try:
            async for raw in ws:
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    await ws.send(json.dumps({"type": "error", "message": "Invalid JSON"}))
                    continue

                if data.get("type") != "message":
                    continue

                user_input = data.get("content", "").strip()
                if not user_input:
                    continue

                agent.history.append({"role": "user", "content": user_input})

                # Process with streaming
                await self._process_message(ws, agent)

        except websockets.ConnectionClosed:
            console.print("[dim]Client disconnected[/dim]")

    async def _process_message(self, ws, agent: Agent, depth: int = 0):
        """Process a message through the agent and stream results to WebSocket."""
        if depth > 5:
            return

        # Build messages
        ctx = await agent.context.snapshot()
        from aulinx.agent import SYSTEM_PROMPT
        system = SYSTEM_PROMPT.format(
            context=ctx,
            tools=agent.tools.describe(compact=True),
        )

        messages = [
            {"role": "system", "content": system},
            *agent.history[-agent.max_history:],
        ]

        # Stream from Ollama
        import httpx
        response_text = ""

        try:
            async with httpx.AsyncClient() as client:
                async with client.stream(
                    "POST",
                    f"{agent.base_url}/api/chat",
                    json={
                        "model": agent.model,
                        "messages": messages,
                        "stream": True,
                        "options": {"temperature": agent.temperature},
                    },
                    timeout=httpx.Timeout(connect=10, read=90, write=10, pool=10),
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        try:
                            chunk = json.loads(line)
                            token = chunk.get("message", {}).get("content", "")
                            if token:
                                response_text += token
                                # Stream tokens to UI (skip JSON blocks)
                                if "```json" not in response_text:
                                    await ws.send(json.dumps({"type": "token", "content": token}))
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            await ws.send(json.dumps({"type": "error", "message": str(e)}))
            return

        agent.history.append({"role": "assistant", "content": response_text})
        agent.history_mgr.save(agent.history)

        # Check for tool call
        tool_call = _extract_tool_call(response_text)
        if tool_call:
            tool_name, args = tool_call

            if tool_name not in agent.tools:
                await ws.send(json.dumps({"type": "error", "message": f"Unknown tool: {tool_name}"}))
                return

            # Notify UI about tool call
            await ws.send(json.dumps({"type": "tool_call", "tool": tool_name, "args": args}))

            # Execute
            import time
            t0 = time.monotonic()
            result = await agent.tools.execute(tool_name, args)
            duration_ms = int((time.monotonic() - t0) * 1000)
            result_str = json.dumps(result, indent=2, ensure_ascii=False, default=str)

            agent.audit.log(tool_name, args, result_str, duration_ms)

            # Send result to UI
            await ws.send(json.dumps({
                "type": "tool_result",
                "tool": tool_name,
                "result": result,
                "duration_ms": duration_ms,
            }))

            # Truncate for LLM history
            if len(result_str) > 3000:
                result_str = result_str[:3000] + "\n... (truncated)"

            agent.history.append({
                "role": "system",
                "content": f"Tool '{tool_name}' returned:\n{result_str}",
            })

            # Let LLM continue
            await self._process_message(ws, agent, depth + 1)
        else:
            await ws.send(json.dumps({"type": "done"}))


async def run_server(host: str = "localhost", port: int = 8765, model: str = "", base_url: str = ""):
    server = WebSocketServer(host, port)
    await server.start(model=model, base_url=base_url)

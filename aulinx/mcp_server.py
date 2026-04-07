"""MCP (Model Context Protocol) server — exposes Aulinx tools to Claude Desktop and other AI clients.

Run with: aulinx --mcp
Connects to Claude Desktop, Cursor, or any MCP-compatible AI client.
"""

import asyncio
import json
import sys

from aulinx.tools.registry import ToolRegistry


async def run_mcp_server():
    """Run an MCP server over stdio (standard MCP transport).

    The server exposes all Aulinx tools as MCP tools that any AI client can call.
    Communication is via JSON-RPC over stdin/stdout.
    """
    registry = ToolRegistry()

    # Build the tool list in MCP format
    mcp_tools = []
    for name, tool in sorted(registry._tools.items()):
        schema = tool.to_ollama_schema()
        fn_schema = schema.get("function", {})
        mcp_tools.append({
            "name": name,
            "description": tool.description,
            "inputSchema": fn_schema.get("parameters", {"type": "object", "properties": {}}),
        })

    sys.stderr.write(f"Aulinx MCP server ready — {len(mcp_tools)} tools\n")

    # MCP stdio transport: read JSON-RPC from stdin, write to stdout
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await asyncio.get_event_loop().connect_read_pipe(lambda: protocol, sys.stdin)

    writer_transport, writer_protocol = await asyncio.get_event_loop().connect_write_pipe(
        asyncio.streams.FlowControlMixin, sys.stdout
    )
    writer = asyncio.StreamWriter(writer_transport, writer_protocol, reader, asyncio.get_event_loop())

    async def send_response(response: dict):
        data = json.dumps(response) + "\n"
        writer.write(data.encode())
        await writer.drain()

    # Process JSON-RPC messages
    while True:
        try:
            line = await reader.readline()
            if not line:
                break

            request = json.loads(line.decode().strip())
            method = request.get("method", "")
            req_id = request.get("id")
            params = request.get("params", {})

            if method == "initialize":
                await send_response({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "aulinx", "version": "0.2.0"},
                    },
                })

            elif method == "notifications/initialized":
                pass  # client acknowledged init

            elif method == "tools/list":
                await send_response({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"tools": mcp_tools},
                })

            elif method == "tools/call":
                tool_name = params.get("name", "")
                tool_args = params.get("arguments", {})

                result = await registry.execute(tool_name, tool_args)
                result_text = json.dumps(result, indent=2, ensure_ascii=False, default=str)

                await send_response({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": result_text}],
                    },
                })

            elif method == "ping":
                await send_response({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {},
                })

            else:
                await send_response({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                })

        except json.JSONDecodeError:
            continue
        except Exception as e:
            sys.stderr.write(f"MCP error: {e}\n")
            if req_id:
                await send_response({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32603, "message": str(e)},
                })

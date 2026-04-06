import { useEffect, useRef, useState } from "react";
import Markdown from "react-markdown";

type Message = {
  id: number;
  role: "user" | "assistant" | "tool_call" | "tool_result" | "error";
  content: string;
  toolName?: string;
  toolArgs?: Record<string, unknown>;
  durationMs?: number;
  collapsed?: boolean;
};

const WS_URL = "ws://localhost:8765";
let msgId = 0;

function App() {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [connected, setConnected] = useState(false);
  const [thinking, setThinking] = useState(false);
  const [toolCount, setToolCount] = useState(92);
  const wsRef = useRef<WebSocket | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const messagesRef = useRef<HTMLDivElement>(null);
  const autoScrollRef = useRef(true);

  useEffect(() => {
    connect();
    return () => wsRef.current?.close();
  }, []);

  useEffect(() => {
    if (autoScrollRef.current && messagesRef.current) {
      messagesRef.current.scrollTop = messagesRef.current.scrollHeight;
    }
  }, [messages, thinking]);

  function handleScroll() {
    if (!messagesRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = messagesRef.current;
    autoScrollRef.current = scrollHeight - scrollTop - clientHeight < 80;
  }

  function connect() {
    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => {
      setConnected(false);
      setTimeout(connect, 3000);
    };
    ws.onerror = () => {};

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.type === "token") {
        setThinking(false);
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          if (last?.role === "assistant") {
            return [
              ...prev.slice(0, -1),
              { ...last, content: last.content + data.content },
            ];
          }
          return [...prev, { id: ++msgId, role: "assistant", content: data.content }];
        });
      } else if (data.type === "tool_call") {
        setMessages((prev) => [
          ...prev,
          {
            id: ++msgId,
            role: "tool_call",
            content: "",
            toolName: data.tool,
            toolArgs: data.args,
          },
        ]);
      } else if (data.type === "tool_result") {
        const content =
          typeof data.result === "string"
            ? data.result
            : JSON.stringify(data.result, null, 2);
        setMessages((prev) => [
          ...prev,
          {
            id: ++msgId,
            role: "tool_result",
            content: content.slice(0, 1500),
            toolName: data.tool,
            durationMs: data.duration_ms,
            collapsed: content.length > 300,
          },
        ]);
      } else if (data.type === "error") {
        setThinking(false);
        setMessages((prev) => [
          ...prev,
          { id: ++msgId, role: "error", content: data.message },
        ]);
      } else if (data.type === "done") {
        setThinking(false);
      }
    };
  }

  function send() {
    if (!input.trim() || !wsRef.current || thinking) return;
    const text = input.trim();
    setInput("");
    setMessages((prev) => [...prev, { id: ++msgId, role: "user", content: text }]);
    setThinking(true);
    autoScrollRef.current = true;
    wsRef.current.send(JSON.stringify({ type: "message", content: text }));
    inputRef.current?.focus();
  }

  function toggleCollapse(id: number) {
    setMessages((prev) =>
      prev.map((m) => (m.id === id ? { ...m, collapsed: !m.collapsed } : m))
    );
  }

  return (
    <div className="palette">
      <div className="palette-messages" ref={messagesRef} onScroll={handleScroll}>
        {messages.length === 0 && !thinking && (
          <div className="empty-state">
            <div className="empty-logo">Au</div>
            <div className="empty-title">Aulinx</div>
            <div className="empty-subtitle">Ask anything to control your desktop</div>
            <div className="empty-hints">
              <span>who am I?</span>
              <span>list files in ~/Documents</span>
              <span>what's using CPU?</span>
              <span>git status</span>
            </div>
          </div>
        )}

        {messages.map((msg) => {
          if (msg.role === "user") {
            return (
              <div key={msg.id} className="message user">
                {msg.content}
              </div>
            );
          }

          if (msg.role === "assistant") {
            // Strip ```json tool call blocks from displayed text
            const cleaned = msg.content
              .replace(/```json\s*\n?\{[\s\S]*?\}\s*\n?```/g, "")
              .replace(/\{"\s*tool"\s*:[\s\S]*?\}/g, "")
              .trim();
            if (!cleaned) return null;
            return (
              <div key={msg.id} className="message assistant">
                <Markdown>{cleaned}</Markdown>
              </div>
            );
          }

          if (msg.role === "tool_call") {
            return (
              <div key={msg.id} className="message tool-call">
                <span className="tool-icon">{">"}</span>
                <span className="tool-name">{msg.toolName}</span>
                <span className="tool-args">
                  ({formatArgs(msg.toolArgs || {})})
                </span>
              </div>
            );
          }

          if (msg.role === "tool_result") {
            const isLong = (msg.content?.length || 0) > 300;
            return (
              <div key={msg.id} className="message tool-result">
                <div
                  className="tool-result-header"
                  onClick={() => isLong && toggleCollapse(msg.id)}
                >
                  <span className="tool-result-label">Result</span>
                  {msg.durationMs != null && (
                    <span className="tool-duration">{msg.durationMs}ms</span>
                  )}
                  {isLong && (
                    <span className="tool-collapse">
                      {msg.collapsed ? "Show" : "Hide"}
                    </span>
                  )}
                </div>
                {!msg.collapsed && (
                  <pre className="tool-result-body">{msg.content}</pre>
                )}
              </div>
            );
          }

          if (msg.role === "error") {
            return (
              <div key={msg.id} className="message error">
                {msg.content}
              </div>
            );
          }

          return null;
        })}

        {thinking && (
          <div className="thinking">
            <div className="thinking-dots">
              <span />
              <span />
              <span />
            </div>
            Thinking...
          </div>
        )}
      </div>

      <div className="palette-input-area">
        <span className="palette-logo">Au</span>
        <input
          ref={inputRef}
          className="palette-input"
          placeholder="Ask anything..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          disabled={!connected}
          autoFocus
        />
        {input.trim() && (
          <button className="send-btn" onClick={send} disabled={thinking}>
            {thinking ? "..." : "Go"}
          </button>
        )}
      </div>

      <div className="palette-status">
        <span className={connected ? "status-connected" : "status-disconnected"}>
          {connected ? "Connected" : "Reconnecting..."}
        </span>
        <span>{toolCount} tools</span>
      </div>
    </div>
  );
}

function formatArgs(args: Record<string, unknown>): string {
  const entries = Object.entries(args);
  if (entries.length === 0) return "";
  return entries
    .map(([k, v]) => {
      const val = typeof v === "string" ? v : JSON.stringify(v);
      return `${k}=${val.length > 40 ? val.slice(0, 40) + "..." : val}`;
    })
    .join(", ");
}

export default App;

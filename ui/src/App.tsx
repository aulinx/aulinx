import { useEffect, useRef, useState } from "react";

type Message = {
  role: "user" | "assistant" | "tool" | "error";
  content: string;
};

const WS_URL = "ws://localhost:8765";

function App() {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [connected, setConnected] = useState(false);
  const [thinking, setThinking] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    connect();
    return () => wsRef.current?.close();
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  function connect() {
    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => {
      setConnected(false);
      setTimeout(connect, 3000);
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.type === "token") {
        setThinking(false);
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          if (last?.role === "assistant") {
            return [...prev.slice(0, -1), { ...last, content: last.content + data.content }];
          }
          return [...prev, { role: "assistant", content: data.content }];
        });
      } else if (data.type === "tool_call") {
        setMessages((prev) => [
          ...prev,
          { role: "tool", content: `> ${data.tool}(${formatArgs(data.args)})` },
        ]);
      } else if (data.type === "tool_result") {
        const content = typeof data.result === "string" ? data.result : JSON.stringify(data.result, null, 2);
        setMessages((prev) => [
          ...prev,
          { role: "tool", content: content.slice(0, 500) },
        ]);
      } else if (data.type === "error") {
        setThinking(false);
        setMessages((prev) => [...prev, { role: "error", content: data.message }]);
      } else if (data.type === "done") {
        setThinking(false);
      }
    };
  }

  function send() {
    if (!input.trim() || !wsRef.current) return;
    const text = input.trim();
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setThinking(true);
    wsRef.current.send(JSON.stringify({ type: "message", content: text }));
    inputRef.current?.focus();
  }

  return (
    <div className="palette">
      <div className="palette-messages">
        {messages.length === 0 && (
          <div style={{ color: "var(--text-dim)", textAlign: "center", padding: "40px 0" }}>
            Type a command to control your desktop
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`message ${msg.role}`}>
            {msg.content}
          </div>
        ))}
        {thinking && (
          <div className="spinner">
            <div className="spinner-dot" />
            Thinking...
          </div>
        )}
        <div ref={messagesEndRef} />
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
          autoFocus
        />
      </div>

      <div className="palette-status">
        <span>{connected ? "Connected" : "Reconnecting..."}</span>
        <span>92 tools</span>
      </div>
    </div>
  );
}

function formatArgs(args: Record<string, unknown>): string {
  return Object.entries(args)
    .map(([k, v]) => `${k}=${typeof v === "string" ? v : JSON.stringify(v)}`)
    .join(", ");
}

export default App;

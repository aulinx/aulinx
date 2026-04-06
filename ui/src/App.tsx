import { useCallback, useEffect, useRef, useState } from "react";
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
const HISTORY_KEY = "aulinx-cmd-history";
const MAX_HISTORY = 50;
let msgId = 0;

function loadHistory(): string[] {
  try {
    return JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]");
  } catch {
    return [];
  }
}

function saveHistory(history: string[]) {
  localStorage.setItem(HISTORY_KEY, JSON.stringify(history.slice(-MAX_HISTORY)));
}

function App() {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [connected, setConnected] = useState(false);
  const [thinking, setThinking] = useState(false);
  const [thinkingLabel, setThinkingLabel] = useState("Thinking...");
  const [copied, setCopied] = useState<number | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const messagesRef = useRef<HTMLDivElement>(null);
  const autoScrollRef = useRef(true);
  const cmdHistory = useRef<string[]>(loadHistory());
  const historyIdx = useRef(-1);

  useEffect(() => {
    connect();
    return () => wsRef.current?.close();
  }, []);

  useEffect(() => {
    if (autoScrollRef.current && messagesRef.current) {
      messagesRef.current.scrollTop = messagesRef.current.scrollHeight;
    }
  }, [messages, thinking]);

  // Global keyboard shortcuts
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      // Ctrl+K → clear conversation
      if (e.ctrlKey && e.key === "k") {
        e.preventDefault();
        setMessages([]);
        setThinking(false);
        return;
      }
      // Ctrl+L → focus input
      if (e.ctrlKey && e.key === "l") {
        e.preventDefault();
        inputRef.current?.focus();
        return;
      }
      // Escape → clear input
      if (e.key === "Escape") {
        setInput("");
        inputRef.current?.focus();
        return;
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);

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
        setThinkingLabel(`Running ${data.tool}...`);
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
        setThinkingLabel("Thinking...");
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
        setThinkingLabel("Thinking...");
        setMessages((prev) => [
          ...prev,
          { id: ++msgId, role: "error", content: data.message },
        ]);
      } else if (data.type === "done") {
        setThinking(false);
        setThinkingLabel("Thinking...");
      }
    };
  }

  function sendMessage(text: string) {
    if (!text.trim() || !wsRef.current || thinking) return;
    const cleaned = text.trim();
    setInput("");
    historyIdx.current = -1;

    // Save to command history
    cmdHistory.current = [...cmdHistory.current.filter((c) => c !== cleaned), cleaned];
    saveHistory(cmdHistory.current);

    setMessages((prev) => [...prev, { id: ++msgId, role: "user", content: cleaned }]);
    setThinking(true);
    setThinkingLabel("Thinking...");
    autoScrollRef.current = true;
    wsRef.current.send(JSON.stringify({ type: "message", content: cleaned }));
    inputRef.current?.focus();
  }

  function handleInputKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter") {
      sendMessage(input);
      return;
    }
    // Up arrow → previous command
    if (e.key === "ArrowUp") {
      e.preventDefault();
      const hist = cmdHistory.current;
      if (hist.length === 0) return;
      const newIdx = historyIdx.current < hist.length - 1 ? historyIdx.current + 1 : historyIdx.current;
      historyIdx.current = newIdx;
      setInput(hist[hist.length - 1 - newIdx] || "");
      return;
    }
    // Down arrow → next command
    if (e.key === "ArrowDown") {
      e.preventDefault();
      const hist = cmdHistory.current;
      const newIdx = historyIdx.current > 0 ? historyIdx.current - 1 : -1;
      historyIdx.current = newIdx;
      setInput(newIdx >= 0 ? hist[hist.length - 1 - newIdx] || "" : "");
      return;
    }
  }

  function toggleCollapse(id: number) {
    setMessages((prev) =>
      prev.map((m) => (m.id === id ? { ...m, collapsed: !m.collapsed } : m))
    );
  }

  const copyText = useCallback((id: number, text: string) => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(id);
      setTimeout(() => setCopied(null), 1500);
    });
  }, []);

  return (
    <div className="palette">
      <div className="palette-messages" ref={messagesRef} onScroll={handleScroll}>
        {messages.length === 0 && !thinking && (
          <div className="empty-state">
            <div className="empty-logo">Au</div>
            <div className="empty-title">Aulinx</div>
            <div className="empty-subtitle">Ask anything to control your desktop</div>
            <div className="empty-hints">
              {["who am I?", "list files in ~/Documents", "what's using CPU?", "git status", "what time is it?", "disk usage"].map((hint) => (
                <span key={hint} className="hint-chip" onClick={() => sendMessage(hint)}>
                  {hint}
                </span>
              ))}
            </div>
            <div className="empty-shortcuts">
              <span>Esc clear</span>
              <span>Ctrl+K clear chat</span>
              <span>Ctrl+L focus</span>
              <span>Up/Down history</span>
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
            const cleaned = msg.content
              .replace(/```json[\s\S]*?```/g, "")
              .replace(/```json[\s\S]*/g, "")
              .replace(/```\s*$/g, "")
              .replace(/\{\s*"tool"\s*:[\s\S]*?\}/g, "")
              .replace(/\{\s*"tool"\s*:[\s\S]*/g, "")
              .trim();
            if (!cleaned || cleaned.length < 2) return null;
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
                  <button
                    className="copy-btn"
                    onClick={(e) => { e.stopPropagation(); copyText(msg.id, msg.content); }}
                    title="Copy result"
                  >
                    {copied === msg.id ? "Copied" : "Copy"}
                  </button>
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
            {thinkingLabel}
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
          onKeyDown={handleInputKeyDown}
          disabled={!connected || thinking}
          autoFocus
        />
        {input.trim() && (
          <button className="send-btn" onClick={() => sendMessage(input)} disabled={thinking}>
            {thinking ? "..." : "Go"}
          </button>
        )}
      </div>

      <div className="palette-status">
        <span className={connected ? "status-connected" : "status-disconnected"}>
          {connected ? "Connected" : "Reconnecting..."}
        </span>
        <span className="status-shortcuts">Esc · Ctrl+K · Up/Down</span>
        <span>92 tools</span>
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

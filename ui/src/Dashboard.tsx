import { useEffect, useRef, useState } from "react";

const WS_URL = "ws://localhost:8765";

type Tab = "tools" | "audit" | "settings" | "memory" | "stats";

function Dashboard({ onClose }: { onClose: () => void }) {
  const [tab, setTab] = useState<Tab>("stats");
  const [data, setData] = useState<Record<string, unknown>>({});
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;
    ws.onopen = () => fetchTab(tab);
    ws.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      if (msg.type === "api_response") {
        setData((prev) => ({ ...prev, [msg.path]: msg.data }));
      }
    };
    return () => ws.close();
  }, []);

  function fetchTab(t: Tab) {
    setTab(t);
    const paths: Record<Tab, string> = {
      stats: "/api/stats",
      tools: "/api/tools",
      audit: "/api/audit",
      settings: "/api/config",
      memory: "/api/memory",
    };
    wsRef.current?.send(JSON.stringify({ type: "api", path: paths[t] }));
  }

  return (
    <div className="dashboard">
      <div className="dash-header">
        <span className="dash-title">Aulinx Dashboard</span>
        <div className="dash-tabs">
          {(["stats", "tools", "audit", "memory", "settings"] as Tab[]).map((t) => (
            <button
              key={t}
              className={`dash-tab ${tab === t ? "active" : ""}`}
              onClick={() => fetchTab(t)}
            >
              {t}
            </button>
          ))}
        </div>
        <button className="dash-close" onClick={onClose}>Back to Chat</button>
      </div>
      <div className="dash-content">
        {tab === "stats" && <StatsView data={data["/api/stats"] as Record<string, number> | undefined} />}
        {tab === "tools" && <ToolsView data={data["/api/tools"] as { tools: ToolInfo[]; count: number } | undefined} />}
        {tab === "audit" && <AuditView data={data["/api/audit"] as { entries: AuditEntry[] } | undefined} />}
        {tab === "memory" && <MemoryView data={data["/api/memory"] as { count: number; recent: MemEntry[] } | undefined} />}
        {tab === "settings" && <SettingsView data={data["/api/config"] as Record<string, unknown> | undefined} />}
      </div>
    </div>
  );
}

// --- Sub-views ---

type ToolInfo = { name: string; description: string; tier: string; module: string };
type AuditEntry = { ts: string; tool: string; duration_ms: number; result_preview: string };
type MemEntry = { content: string; category: string; timestamp: string };

function StatsView({ data }: { data?: Record<string, number> }) {
  if (!data) return <div className="dash-loading">Loading...</div>;
  return (
    <div className="stats-grid">
      {Object.entries(data).map(([key, val]) => (
        <div key={key} className="stat-card">
          <div className="stat-value">{val}</div>
          <div className="stat-label">{key}</div>
        </div>
      ))}
    </div>
  );
}

function ToolsView({ data }: { data?: { tools: ToolInfo[]; count: number } }) {
  const [filter, setFilter] = useState("");
  if (!data) return <div className="dash-loading">Loading...</div>;
  const filtered = data.tools.filter(
    (t) =>
      t.name.includes(filter.toLowerCase()) ||
      t.description.toLowerCase().includes(filter.toLowerCase())
  );
  return (
    <div>
      <input
        className="dash-search"
        placeholder={`Search ${data.count} tools...`}
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
      />
      <div className="tools-list">
        {filtered.map((t) => (
          <div key={t.name} className="tool-card">
            <div className="tool-card-name">{t.name}</div>
            <div className="tool-card-desc">{t.description}</div>
            <div className="tool-card-meta">
              <span className={`tier-badge tier-${t.tier}`}>{t.tier}</span>
              <span className="module-badge">{t.module}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function AuditView({ data }: { data?: { entries: AuditEntry[] } }) {
  if (!data) return <div className="dash-loading">Loading...</div>;
  return (
    <div className="audit-list">
      {data.entries.length === 0 && <div className="dash-empty">No audit entries yet</div>}
      {data.entries.map((e, i) => (
        <div key={i} className="audit-row">
          <span className="audit-time">{e.ts}</span>
          <span className="audit-tool">{e.tool}</span>
          <span className="audit-duration">{e.duration_ms}ms</span>
          <span className="audit-preview">{e.result_preview.slice(0, 80)}</span>
        </div>
      ))}
    </div>
  );
}

function MemoryView({ data }: { data?: { count: number; recent: MemEntry[] } }) {
  if (!data) return <div className="dash-loading">Loading...</div>;
  return (
    <div>
      <div className="dash-stat">Total memories: {data.count}</div>
      <div className="memory-list">
        {data.recent.map((m, i) => (
          <div key={i} className="memory-card">
            <div className="memory-content">{m.content}</div>
            <div className="memory-meta">
              <span className="memory-cat">{m.category}</span>
              <span className="memory-time">{m.timestamp}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function SettingsView({ data }: { data?: Record<string, unknown> }) {
  if (!data) return <div className="dash-loading">Loading...</div>;
  return (
    <div className="settings-list">
      {Object.entries(data).map(([key, val]) => (
        <div key={key} className="setting-row">
          <span className="setting-key">{key}</span>
          <span className="setting-val">{String(val)}</span>
        </div>
      ))}
    </div>
  );
}

export default Dashboard;

import { useEffect, useRef, useState } from "react";
import "./App.css";
import { Line } from "react-chartjs-2";
import "chartjs-adapter-date-fns";
import {
  Chart as ChartJS,
  LineElement,
  PointElement,
  CategoryScale,
  LinearScale,
  TimeScale,
  Tooltip,
  Legend
} from "chart.js";

ChartJS.register(
  LineElement,
  PointElement,
  CategoryScale,
  LinearScale,
  TimeScale,
  Tooltip,
  Legend
);

// ---------------------------------------------------------------------------
// Backend call helper. package.json sets "proxy" to the Flask server, so a
// relative path like /api/query/... is forwarded to http://127.0.0.1:5001.
// Every endpoint returns [columnNames, ...rows]; errors come back as
// { error: "..." } with a non-2xx status.
// ---------------------------------------------------------------------------
async function callApi(op, params) {
  const path =
    op.kind === "query"
      ? `/api/query/${op.endpoint}`
      : `/api/proc/${op.endpoint}`;

  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ params }),
  });

  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.error || "Request failed");
  }
  return data;
}

// ---------------------------------------------------------------------------
// Parameter definitions per operation. Each param is a typed object:
//   type "text"   -> free text
//   type "number" -> numeric field
//   type "select" -> dropdown; options is "seasons" | "positions" | [..]
//   type "player" -> search-by-name box that resolves to a player_id
//   type "club"   -> search-by-name box that resolves to a club_id
// For player/club params, `def` holds a starter { id, label } so the demo
// opens with a recognizable name already filled in.
// ---------------------------------------------------------------------------
const POSITION_ALL = [
  { value: "", label: "All positions" },
  "Attack",
  "Defender",
  "Goalkeeper",
  "Midfield",
];

const PLAYERS_CLUBS_OPS = [
  {
    label: "Search Players",
    kind: "query",
    endpoint: "q1_search_players",
    params: [
      { name: "Position 1", type: "select", options: "positions", def: "Attack" },
      { name: "Position 2", type: "select", options: "positions", def: "Midfield" },
      { name: "Min Goal Average", type: "number", def: "0.3" },
      { name: "Min Appearances", type: "number", def: "50" },
    ],
  },
  {
    label: "Club Performance by Competition",
    kind: "query",
    endpoint: "q4_club_performance",
    params: [
      { name: "Club", type: "club", def: { id: "281", label: "Manchester City  (#281)" } },
    ],
  },
  {
    label: "Top Scorers by Season",
    kind: "query",
    endpoint: "q5_top_scorers",
    params: [{ name: "Season", type: "select", options: "seasons", def: "2024" }],
  },
  {
    label: "Most Valuable Players by Age Group",
    kind: "query",
    endpoint: "q9_most_valuable_by_age",
    params: [{ name: "Count per Group", type: "number", def: "3" }],
  },
  {
    label: "Best Goal Contribution per 90 Minutes",
    kind: "query",
    endpoint: "q10_best_contribution_per90",
    params: [{ name: "Season", type: "select", options: "seasons", def: "2024" }],
  },
  {
    label: "Get Player Career Summary",
    kind: "proc",
    endpoint: "sp3_career_summary",
    params: [
      { name: "Player", type: "player", def: { id: "28003", label: "Lionel Messi  (#28003)" } },
    ],
  },
  {
    label: "Get Top Performers by Position",
    kind: "proc",
    endpoint: "sp5_top_performers",
    params: [
      { name: "Position", type: "select", options: POSITION_ALL, def: "Attack" },
      { name: "Season", type: "select", options: "seasons", def: "2024" },
      { name: "Minimum Games", type: "number", def: "5" },
      { name: "Limit", type: "number", def: "10" },
    ],
  },
];

const COMPARE_OPS = [
  {
    label: "Head-to-Head Player Comparison",
    kind: "query",
    endpoint: "q3_head_to_head",
    params: [
      { name: "Player 1", type: "player", def: { id: "28003", label: "Lionel Messi  (#28003)" } },
      { name: "Player 2", type: "player", def: { id: "342229", label: "Kylian Mbappé  (#342229)" } },
    ],
  },
  {
    label: "Position Comparison",
    kind: "query",
    endpoint: "q7_position_comparison",
    params: [],
  },
  {
    label: "Career Club History",
    kind: "query",
    endpoint: "q8_career_club_history",
    params: [
      { name: "Player", type: "player", def: { id: "8198", label: "Cristiano Ronaldo  (#8198)" } },
    ],
  },
];

const GRAPH_OPS = [
  {
    label: "Market Value Trend",
    kind: "query",
    endpoint: "q2_market_value_trend",
    params: [
      { name: "Player", type: "player", def: { id: "342229", label: "Kylian Mbappé  (#342229)" } },
    ],
  },
  {
    label: "Transfer Activity (biggest fees)",
    kind: "query",
    endpoint: "q6_transfer_activity",
    params: [{ name: "Minimum Transfer Fee (EUR)", type: "number", def: "50000000" }],
  },
];

const EDIT_OPS = [
  {
    label: "Add Player Performance",
    kind: "proc",
    endpoint: "sp1_add_performance",
    params: [
      { name: "Player", type: "player", def: "" },
      { name: "Game ID", type: "number", def: "" },
      { name: "Club", type: "club", def: "" },
      { name: "Minutes Played", type: "number", def: "90" },
      { name: "Goals", type: "number", def: "0" },
      { name: "Assists", type: "number", def: "0" },
      { name: "Yellow Cards", type: "number", def: "0" },
      { name: "Red Cards", type: "number", def: "0" },
    ],
  },
  {
    label: "Update Player Valuation",
    kind: "proc",
    endpoint: "sp2_update_valuation",
    params: [
      { name: "Player", type: "player", def: "" },
      { name: "Valuation Date (YYYY-MM-DD)", type: "text", def: "" },
      { name: "Market Value (EUR)", type: "number", def: "" },
      { name: "Club", type: "club", def: "" },
    ],
  },
  {
    label: "Transfer Player",
    kind: "proc",
    endpoint: "sp4_transfer_player",
    params: [
      { name: "Player", type: "player", def: "" },
      { name: "From Club (optional)", type: "club", def: "" },
      { name: "To Club", type: "club", def: "" },
      { name: "Transfer Date (YYYY-MM-DD)", type: "text", def: "" },
      { name: "Transfer Fee (EUR)", type: "number", def: "0" },
      { name: "Season (e.g. 2024/2025)", type: "text", def: "" },
    ],
  },
];

// Fixed option lists are loaded once from the backend so dropdowns match data.
function useOptions() {
  const [options, setOptions] = useState({ seasons: [], positions: [] });
  useEffect(() => {
    fetch("/api/options")
      .then((r) => r.json())
      .then(setOptions)
      .catch(() => {});
  }, []);
  return options;
}

// ---------------------------------------------------------------------------
// Search-by-name input. Type a player/club name, pick from the suggestions,
// and the underlying id is what gets submitted.
// ---------------------------------------------------------------------------
function EntityInput({ kind, initialLabel, onResolve }) {
  const [text, setText] = useState(initialLabel || "");
  const [suggestions, setSuggestions] = useState([]);
  const [open, setOpen] = useState(false);
  const boxRef = useRef(null);

  useEffect(() => {
    function handleOutside(e) {
      if (boxRef.current && !boxRef.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener("mousedown", handleOutside);
    return () => document.removeEventListener("mousedown", handleOutside);
  }, []);

  async function handleType(v) {
    setText(v);
    // Submit the raw text; the backend resolves a name to its id (picking a
    // suggestion below just fills in the exact name for you).
    onResolve(v);
    if (v.trim().length < 2) {
      setSuggestions([]);
      setOpen(false);
      return;
    }
    try {
      const res = await fetch(`/api/search/${kind}s?q=${encodeURIComponent(v)}`);
      const data = await res.json();
      setSuggestions(data);
      setOpen(true);
    } catch {
      setSuggestions([]);
    }
  }

  function pick(s) {
    setText(s.label);
    onResolve(String(s.id));
    setOpen(false);
  }

  return (
    <div className="entity-input" ref={boxRef}>
      <input
        type="text"
        placeholder={`Type a ${kind} name…`}
        value={text}
        onChange={(e) => handleType(e.target.value)}
        onFocus={() => suggestions.length && setOpen(true)}
      />
      {open && suggestions.length > 0 && (
        <ul className="suggestions">
          {suggestions.map((s) => (
            <li key={s.id} onMouseDown={() => pick(s)}>
              {s.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function normalizeOptions(options, loaded) {
  let list = options;
  if (options === "seasons") list = loaded.seasons;
  if (options === "positions") list = loaded.positions;
  return (list || []).map((o) =>
    typeof o === "object" ? o : { value: String(o), label: String(o) }
  );
}

function ParamField({ param, value, onChange, loaded }) {
  if (param.type === "player" || param.type === "club") {
    const initialLabel =
      param.def && typeof param.def === "object" ? param.def.label : "";
    return (
      <EntityInput
        kind={param.type}
        initialLabel={initialLabel}
        onResolve={onChange}
      />
    );
  }

  if (param.type === "select") {
    const opts = normalizeOptions(param.options, loaded);
    return (
      <select
        className="field-select"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {opts.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    );
  }

  return (
    <input
      type={param.type === "number" ? "number" : "text"}
      placeholder="Value"
      value={value}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}

// ---------------------------------------------------------------------------
// Result renderers.
// ---------------------------------------------------------------------------
function ResultTable({ data }) {
  if (!data || data.length === 0) return <p className="muted">No data.</p>;
  const [columns, ...rows] = data;
  if (rows.length === 0) return <p className="muted">No matching rows.</p>;

  return (
    <table className="result-table">
      <thead>
        <tr>
          {columns.map((c) => (
            <th key={c}>{c}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, i) => (
          <tr key={i}>
            {row.map((v, j) => (
              <td key={j}>{v === null ? "—" : String(v)}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function BarChart({ data }) {
  if (!data || data.length < 2) return <p className="muted">No data to graph.</p>;
  const [columns, ...rows] = data;

  const valueIdx = columns.length - 2;
  const labelIdx = 0;
  const values = rows.map((r) => Number(r[valueIdx]) || 0);
  const max = Math.max(...values, 1);

  return (
    <div className="bar-chart">
      <div className="bar-chart-title">
        {columns[valueIdx]} by {columns[labelIdx]}
      </div>
      {rows.map((r, i) => (
        <div className="bar-row" key={i}>
          <span className="bar-label">{String(r[labelIdx])}</span>
          <div className="bar-track">
            <div
              className="bar-fill"
              style={{ width: `${(values[i] / max) * 100}%` }}
            />
          </div>
          <span className="bar-value">{String(r[valueIdx])}</span>
        </div>
      ))}
    </div>
  );
}

function GraphChart({ data }) {
  if (!data || data.length < 2) return <p className="muted">No data to graph.</p>;
  const [columns, ...rows] = data;

  const valueIdx = 2;
  const dateIdx = 1;

  const chartData = rows.map((r) => ({
    x: new Date(r[dateIdx]), // spacing comes from this date
    y: Number(r[valueIdx]) || 0
  }));

  const colors = getComputedStyle(document.documentElement);

  const accent = colors.getPropertyValue("--accent").trim();
  const text = colors.getPropertyValue("--text").trim();
  const line = colors.getPropertyValue("--line").trim();

  return (
    <div className="graph-chart">
      <div className="graph-chart-title">
        {columns[valueIdx]} by {columns[dateIdx]}
      </div>

      <Line
        data={{
          datasets: [
            {
              label: columns[valueIdx],
              data: chartData,
              borderColor: accent,
              backgroundColor: accent,
              pointBackgroundColor: accent,
              pointBorderColor: accent,
              borderWidth: 2,
              tension: 0
            }
          ]
        }}
        options={{
          responsive: true,
          plugins: {
            legend: {
              labels: {
                color: text
              }
            }
          },
          scales: {
            x: {
              type: "time",
              time: {
                unit: "month",
                displayFormats: {
                  month: "M/d/yyyy"
                }
              },
              ticks: {
                color: text,
                maxTicksLimit: 10
              },
              grid: {
                color: line
              }
            },
            y: {
              ticks: {
                color: text
              },
              grid: {
                color: line
              }
            }
          }
        }}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Shared operation panel used by every tab.
//   variant: "table" | "graph" | "edit"
// ---------------------------------------------------------------------------
function OperationPanel({ operations, variant }) {
  const loaded = useOptions();
  const [selected, setSelected] = useState(operations[0].label);
  const current = operations.find((o) => o.label === selected);

  const initParams = (op) =>
    op.params.map((p) =>
      p.def && typeof p.def === "object" ? p.def.id : p.def ?? ""
    );

  const [params, setParams] = useState(() => initParams(current));
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(false);

  function changeOperation(e) {
    const op = operations.find((o) => o.label === e.target.value);
    setSelected(op.label);
    setParams(initParams(op));
    setData(null);
    setError("");
    setStatus("");
  }

  function updateParam(i, value) {
    setParams((prev) => {
      const next = [...prev];
      next[i] = value;
      return next;
    });
  }

  async function run() {
    setLoading(true);
    setError("");
    setStatus("");
    setData(null);
    try {
      const result = await callApi(current, params);
      if (variant === "edit") {
        // Edit ops return [["Status"], [message]].
        setStatus(result[1] ? result[1][0] : "Done");
      } else {
        setData(result);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  const actionLabel = variant === "edit" ? "SUBMIT" : "RUN";

  return (
    <div className="op-panel">
      <div className="left-panel">
        <select className="dropdown" value={selected} onChange={changeOperation}>
          {operations.map((o) => (
            <option key={o.label}>{o.label}</option>
          ))}
        </select>

        {current.params.map((param, index) => (
          <div className="param-row" key={`${selected}-${param.name}`}>
            <label>{param.name}:</label>
            <ParamField
              param={param}
              value={params[index] ?? ""}
              onChange={(v) => updateParam(index, v)}
              loaded={loaded}
            />
          </div>
        ))}

        <button className="search-btn" onClick={run} disabled={loading}>
          {loading ? "…" : actionLabel}
        </button>
      </div>

      <div className="right-panel">
        {error && <div className="error-box">Error: {error}</div>}
        {status && <div className="status-box">{status}</div>}
        {!error && loading && <p className="muted">Loading…</p>}
        {!error && !loading && data && variant === "graph" && (
          <>
            {current.endpoint === "q2_market_value_trend" && (
              <GraphChart data={data} />
            )}

            {current.endpoint === "q6_transfer_activity" && (
              <BarChart data={data} />
            )}

            <ResultTable data={data} />
          </>
        )}
        {!error && !loading && data && variant !== "graph" && (
          <ResultTable data={data} />
        )}
      </div>
    </div>
  );
}

function PlayersClubs() {
  return <OperationPanel operations={PLAYERS_CLUBS_OPS} variant="table" />;
}

function Compare() {
  return <OperationPanel operations={COMPARE_OPS} variant="table" />;
}

function Graph() {
  return <OperationPanel operations={GRAPH_OPS} variant="graph" />;
}

function Edit() {
  return <OperationPanel operations={EDIT_OPS} variant="edit" />;
}

function App() {
  const tabs = [
    { name: "Players/Clubs", component: <PlayersClubs /> },
    { name: "Compare", component: <Compare /> },
    { name: "Graph", component: <Graph /> },
    { name: "Edit", component: <Edit /> },
  ];

  const [activeTab, setActiveTab] = useState(0);

  return (
    <div className="App">
      <header className="App-header">
        <div className="brand">
          <span className="brand-mark">⚽</span> PitchStats
        </div>

        <div className="tab-menu">
          {tabs.map((tab, index) => (
            <div
              key={tab.name}
              className={`tab-box ${activeTab === index ? "selected" : ""}`}
              onClick={() => setActiveTab(index)}
            >
              {tab.name}
            </div>
          ))}
        </div>

        <div className="tab-section">{tabs[activeTab].component}</div>
      </header>
    </div>
  );
}

export default App;

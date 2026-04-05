import { useState, useEffect, useRef, useCallback } from "react";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

// ── Helpers ──────────────────────────────────────────────────────────────────

function getGrade(score) {
  if (score >= 95) return { label: "S", cls: "grade-s" };
  if (score >= 85) return { label: "A", cls: "grade-a" };
  if (score >= 70) return { label: "B", cls: "grade-b" };
  if (score >= 55) return { label: "C", cls: "grade-c" };
  if (score >= 35) return { label: "D", cls: "grade-d" };
  return { label: "F", cls: "grade-f" };
}

function scoreColor(s) {
  if (s >= 85) return "#16a34a";
  if (s >= 60) return "#ca8a04";
  return "#dc2626";
}

// ── Components ───────────────────────────────────────────────────────────────

function UploadZone({ label, hint, icon, file, onFile, disabled }) {
  const [drag, setDrag] = useState(false);
  const inputRef = useRef();

  const handle = (f) => {
    if (!f || !f.name.endsWith(".csv")) {
      alert("Only .csv files are accepted.");
      return;
    }
    onFile(f);
  };

  return (
    <div
      className={`upload-zone${file ? " has-file" : ""}${drag ? " drag" : ""}${disabled ? " disabled" : ""}`}
      onClick={() => !disabled && inputRef.current.click()}
      onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
      onDragLeave={() => setDrag(false)}
      onDrop={(e) => { e.preventDefault(); setDrag(false); if (!disabled) handle(e.dataTransfer.files[0]); }}
    >
      <input ref={inputRef} type="file" accept=".csv" style={{ display: "none" }} onChange={(e) => handle(e.target.files[0])} />
      <div className="upload-icon">{icon}</div>
      <p className={file ? "filename" : ""}>{file ? file.name : label}</p>
      <p className="hint">{hint}</p>
    </div>
  );
}

function ScoreRing({ score }) {
  const r = 40, circ = 2 * Math.PI * r;
  const offset = circ * (1 - score / 100);
  return (
    <svg width="100" height="100" viewBox="0 0 100 100">
      <circle cx="50" cy="50" r={r} fill="none" stroke="#e5e7eb" strokeWidth="8" />
      <circle cx="50" cy="50" r={r} fill="none" stroke={scoreColor(score)} strokeWidth="8"
        strokeDasharray={circ} strokeDashoffset={offset}
        strokeLinecap="round" transform="rotate(-90 50 50)" style={{ transition: "stroke-dashoffset 0.6s ease" }} />
      <text x="50" y="50" dominantBaseline="middle" textAnchor="middle"
        fontSize="18" fontWeight="600" fill={scoreColor(score)}>{score}</text>
    </svg>
  );
}

function StatCard({ label, value, sub }) {
  return (
    <div className="stat-card">
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {sub && <div className="stat-sub">{sub}</div>}
    </div>
  );
}

function DiffTable({ result }) {
  if (!result?.diff?.length) return null;
  const cols = result.ref_columns || [];
  return (
    <div className="diff-wrap">
      <p className="section-label">Diff view</p>
      <div className="scroll-x">
        <table className="diff-table">
          <thead>
            <tr>
              <th>#</th>
              <th>status</th>
              {cols.map((c) => <th key={c}>{c}</th>)}
            </tr>
          </thead>
          <tbody>
            {result.diff.map((row, i) => (
              <tr key={i} className={`row-${row.status}`}>
                <td className="muted">{row.ref_row + 1}</td>
                <td>
                  {row.status === "match" && <span className="badge badge-a">✓</span>}
                  {row.status === "partial" && <span className="badge badge-c">{Math.round((row.row_score || 0) * 100)}%</span>}
                  {row.status === "missing" && <span className="badge badge-f">✗</span>}
                </td>
                {row.status === "missing"
                  ? <td colSpan={cols.length} className="missing-cell">row missing in submission</td>
                  : cols.map((c) => {
                      const cell = row.cells?.[c];
                      if (!cell) return <td key={c} />;
                      const cls = cell.score >= 0.99 ? "" : cell.score >= 0.5 ? "cell-warn" : "cell-bad";
                      return (
                        <td key={c}>
                          <span className={cls || undefined} title={cls ? `sub: ${cell.sub}` : undefined}>
                            {cell.ref}
                          </span>
                        </td>
                      );
                    })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ColBreakdown({ result }) {
  if (!result?.column_scores) return null;
  return (
    <div className="col-breakdown">
      <p className="section-label">Column scores</p>
      <div className="col-grid">
        {result.ref_columns?.map((h) => {
          const s = result.column_scores[h] ?? 0;
          const pct = Math.round(s * 100);
          const mapped = result.column_mapping?.[h];
          return (
            <div key={h} className="col-card">
              <div className="col-name" title={h}>{h}</div>
              {mapped?.mapped_to && mapped.mapped_to !== h && (
                <div className="col-mapped">→ {mapped.mapped_to}</div>
              )}
              {!mapped?.found && <div className="col-missing">not found</div>}
              <div className="col-pct" style={{ color: scoreColor(pct) }}>{pct}%</div>
              <div className="mini-bar">
                <div className="mini-fill" style={{ width: `${pct}%`, background: scoreColor(pct) }} />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Main App ──────────────────────────────────────────────────────────────────

export default function App() {
  const [tab, setTab] = useState("upload");
  const [sessionId, setSessionId] = useState(() => localStorage.getItem("csv_judge_session") || "");
  const [refFile, setRefFile] = useState(null);
  const [subFile, setSubFile] = useState(null);
  const [subLabel, setSubLabel] = useState("");
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState(null);
  const [lastResult, setLastResult] = useState(null);
  const [submissions, setSubmissions] = useState([]);
  const [sortBy, setSortBy] = useState("time-desc");

  // Config
  const [cfgLower, setCfgLower] = useState(true);
  const [cfgTrim, setCfgTrim] = useState(true);
  const [cfgNumTol, setCfgNumTol] = useState(true);
  const [cfgTol, setCfgTol] = useState(0.01);
  const [cfgExtra, setCfgExtra] = useState(true);

  useEffect(() => {
    if (sessionId) localStorage.setItem("csv_judge_session", sessionId);
  }, [sessionId]);

  const fetchResults = useCallback(async () => {
    try {
      const res = await fetch(`${API}/results`, { headers: { "X-Session-Id": sessionId } });
      const data = await res.json();
      if (data.session_id) setSessionId(data.session_id);
      setSubmissions(data.submissions || []);
    } catch (_) {}
  }, [sessionId]);

  useEffect(() => { if (tab === "results" || tab === "leaderboard") fetchResults(); }, [tab]);

  const handleRefFile = async (file) => {
    setRefFile(file);
    setMsg({ type: "info", text: "Uploading reference file…" });
    const fd = new FormData();
    fd.append("file", file);
    try {
      const res = await fetch(`${API}/upload-reference`, {
        method: "POST", body: fd, headers: { "X-Session-Id": sessionId },
      });
      const data = await res.json();
      if (data.session_id) setSessionId(data.session_id);
      setMsg({ type: "success", text: `Reference uploaded: ${file.name}` });
    } catch (e) {
      setMsg({ type: "error", text: "Failed to upload reference: " + e.message });
    }
  };

  const handleSubmit = async () => {
    if (!subFile) return;
    setLoading(true);
    setMsg(null);
    const fd = new FormData();
    fd.append("file", subFile);
    fd.append("label", subLabel || subFile.name);
    fd.append("lowercase", cfgLower);
    fd.append("trim", cfgTrim);
    fd.append("numeric_tolerance", cfgNumTol);
    fd.append("tolerance", cfgTol);
    fd.append("penalize_extra", cfgExtra);
    try {
      const res = await fetch(`${API}/submit`, {
        method: "POST", body: fd, headers: { "X-Session-Id": sessionId },
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Server error");
      }
      const data = await res.json();
      if (data.session_id) setSessionId(data.session_id);
      setLastResult(data);
      const g = getGrade(data.score);
      setMsg({ type: "success", text: `Score: ${data.score}/100 — Grade: ${g.label}` });
    } catch (e) {
      setMsg({ type: "error", text: "Comparison failed: " + e.message });
    }
    setLoading(false);
  };

  const clearHistory = async () => {
    if (!confirm("Clear all submission history?")) return;
    await fetch(`${API}/results`, { method: "DELETE", headers: { "X-Session-Id": sessionId } });
    setSubmissions([]);
  };

  const sorted = [...submissions].sort((a, b) => {
    if (sortBy === "score-desc") return b.score - a.score;
    if (sortBy === "score-asc") return a.score - b.score;
    return new Date(b.timestamp) - new Date(a.timestamp);
  });

  const topSubmissions = [...submissions].sort((a, b) => b.score - a.score).slice(0, 20);

  return (
    <div className="app">
      <header className="app-header">
        <h1>CSV Judge</h1>
        <p>Upload a reference CSV, then submit files to score against it.</p>
      </header>

      <nav className="tabs">
        {["upload", "results", "leaderboard", "config"].map((t) => (
          <button key={t} className={`tab${tab === t ? " active" : ""}`} onClick={() => setTab(t)}>
            {t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
      </nav>

      {/* ── UPLOAD TAB ── */}
      {tab === "upload" && (
        <div className="panel">
          <div className="upload-grid">
            <div>
              <p className="step-label">1. Reference file (ground truth)</p>
              <UploadZone label="Click or drag a .csv file" hint="Answer key" icon="📋" file={refFile} onFile={handleRefFile} />
            </div>
            <div>
              <p className="step-label">2. Submission file</p>
              <UploadZone label="Click or drag a .csv file" hint="Will be scored" icon="📤" file={subFile} onFile={(f) => { setSubFile(f); setSubLabel(f.name.replace(".csv", "")); }} disabled={!refFile} />
            </div>
          </div>

          {subFile && (
            <div style={{ marginBottom: "1rem" }}>
              <label className="field-label">Submission label</label>
              <input className="text-input" value={subLabel} onChange={(e) => setSubLabel(e.target.value)} placeholder="e.g. student_alice" />
            </div>
          )}

          <div className="btn-row">
            <button className="btn btn-primary" onClick={handleSubmit} disabled={!refFile || !subFile || loading}>
              {loading ? "Comparing…" : "Compare"}
            </button>
          </div>

          {msg && <div className={`msg msg-${msg.type}`}>{msg.text}</div>}

          {lastResult && (
            <div className="result-section">
              <div className="result-top">
                <ScoreRing score={lastResult.score} />
                <div className="stat-row">
                  <StatCard label="Matched rows" value={lastResult.matched_rows} />
                  <StatCard label="Partial rows" value={lastResult.partial_rows} />
                  <StatCard label="Missing rows" value={lastResult.missing_rows} />
                  <StatCard label="Extra rows" value={lastResult.extra_rows} />
                </div>
              </div>
              <ColBreakdown result={lastResult} />
              <DiffTable result={lastResult} />
            </div>
          )}
        </div>
      )}

      {/* ── RESULTS TAB ── */}
      {tab === "results" && (
        <div className="panel">
          <div className="results-header">
            <span className="muted">{submissions.length} submission{submissions.length !== 1 ? "s" : ""}</span>
            <div className="flex-row">
              <select value={sortBy} onChange={(e) => setSortBy(e.target.value)}>
                <option value="time-desc">Newest first</option>
                <option value="score-desc">Highest score</option>
                <option value="score-asc">Lowest score</option>
              </select>
              <button className="btn btn-sm danger" onClick={clearHistory}>Clear</button>
            </div>
          </div>
          {sorted.length === 0
            ? <div className="empty-state">No submissions yet.</div>
            : sorted.map((s) => {
                const g = getGrade(s.score);
                return (
                  <div key={s.id} className="sub-row">
                    <div className="avatar">{s.label.slice(0, 2).toUpperCase()}</div>
                    <div className="sub-info">
                      <div className="sub-name">{s.label}</div>
                      <div className="sub-meta">{s.filename} · {new Date(s.timestamp).toLocaleString()}</div>
                      <div className="mini-bar" style={{ marginTop: 5 }}>
                        <div className="mini-fill" style={{ width: `${s.score}%`, background: scoreColor(s.score) }} />
                      </div>
                    </div>
                    <div className="sub-score">
                      <div style={{ fontSize: 22, fontWeight: 600, color: scoreColor(s.score) }}>{s.score}</div>
                      <span className={`badge ${g.cls}`}>{g.label}</span>
                    </div>
                  </div>
                );
              })}
        </div>
      )}

      {/* ── LEADERBOARD TAB ── */}
      {tab === "leaderboard" && (
        <div className="panel">
          {topSubmissions.length === 0
            ? <div className="empty-state">No submissions yet.</div>
            : <>
                <p className="section-label" style={{ marginBottom: "1rem" }}>Top {topSubmissions.length} scores</p>
                {topSubmissions.map((s, i) => {
                  const g = getGrade(s.score);
                  const maxS = topSubmissions[0].score || 1;
                  return (
                    <div key={s.id} className="lb-row">
                      <div className={`lb-rank rank-${i}`}>{i === 0 ? "🥇" : i === 1 ? "🥈" : i === 2 ? "🥉" : i + 1}</div>
                      <div className="lb-info">
                        <div className="sub-name">{s.label}</div>
                        <div className="mini-bar">
                          <div className="mini-fill" style={{ width: `${(s.score / maxS) * 100}%`, background: scoreColor(s.score) }} />
                        </div>
                      </div>
                      <div className="sub-score">
                        <div style={{ fontSize: 20, fontWeight: 600, color: scoreColor(s.score) }}>{s.score}</div>
                        <span className={`badge ${g.cls}`}>{g.label}</span>
                      </div>
                    </div>
                  );
                })}
              </>}
        </div>
      )}

      {/* ── CONFIG TAB ── */}
      {tab === "config" && (
        <div className="panel">
          <div className="card">
            <p className="card-header">Comparison settings</p>
            {[
              ["Case-insensitive matching", cfgLower, setCfgLower],
              ["Trim whitespace", cfgTrim, setCfgTrim],
              ["Numeric tolerance", cfgNumTol, setCfgNumTol],
              ["Penalize extra rows", cfgExtra, setCfgExtra],
            ].map(([label, val, setter]) => (
              <div key={label} className="config-row">
                <span>{label}</span>
                <label className="toggle">
                  <input type="checkbox" checked={val} onChange={(e) => setter(e.target.checked)} />
                  <span className="slider" />
                </label>
              </div>
            ))}
            <div className="config-row">
              <span>Tolerance (±)</span>
              <input type="number" value={cfgTol} onChange={(e) => setCfgTol(parseFloat(e.target.value))} step="0.001" min="0" className="num-input" />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

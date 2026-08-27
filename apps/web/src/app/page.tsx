"use client";

import { FormEvent, useEffect, useState } from "react";
import "./styles.css";

type Question = { id: string; prompt: string; dimension_label: string; choices: number[] };
type Dimension = { key: string; label: string; score: number; confidence: number; evidence: string[] };

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function api(path: string, options: RequestInit = {}, token = "") {
  const response = await fetch(`${API}${path}`, { ...options, headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(options.headers ?? {}) } });
  if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail ?? `Request failed (${response.status})`);
  return response.status === 204 ? null : response.json();
}

export default function Home() {
  const [token, setToken] = useState("");
  const [email, setEmail] = useState("");
  const [profile, setProfile] = useState<any>(null);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [answers, setAnswers] = useState<Record<string, number>>({});
  const [dimensions, setDimensions] = useState<Dimension[]>([]);
  const [scenario, setScenario] = useState("");
  const [result, setResult] = useState<any>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => { const saved = window.localStorage.getItem("dt-token"); if (saved) { setToken(saved); load(saved); } }, []);

  async function load(auth = token) {
    try { const profiles = await api("/profiles", {}, auth); if (profiles.profiles[0]) { setProfile(profiles.profiles[0]); const detail = await api(`/profiles/${profiles.profiles[0].id}`, {}, auth); setDimensions(detail.dimensions.map((d: any) => ({ key: d.key, label: d.label, score: d.score, confidence: d.confidence, evidence: JSON.parse(d.evidence) }))); } } catch (e) { setMessage((e as Error).message); }
  }

  async function login(event: FormEvent) {
    event.preventDefault(); setBusy(true); setMessage("");
    try {
      const body = await api("/auth/dev-login", { method: "POST", body: JSON.stringify({ email }) });
      setToken(body.token); window.localStorage.setItem("dt-token", body.token);
      const existing = await api("/profiles", {}, body.token);
      const active = existing.profiles[0] ?? (await api("/profiles", { method: "POST", body: JSON.stringify({ name: "My Digital Twin", description: "Personal decision-support profile" }) }, body.token)).profile;
      setProfile(active);
      const detail = await api(`/profiles/${active.id}`, {}, body.token);
      setDimensions(detail.dimensions.map((d: any) => ({ key: d.key, label: d.label, score: d.score, confidence: d.confidence, evidence: JSON.parse(d.evidence) })));
      const bank = await api("/assessment/questions", {}, body.token); setQuestions(bank.questions);
      setMessage("Workspace ready. Complete or refine the assessment to update your baseline.");
    } catch (e) { setMessage((e as Error).message); } finally { setBusy(false); }
  }

  async function beginAssessment() { if (!questions.length) { const bank = await api("/assessment/questions", {}, token); setQuestions(bank.questions); } }
  async function submitAssessment() { if (!profile) return; setBusy(true); try { const body = await api(`/profiles/${profile.id}/assessment`, { method: "POST", body: JSON.stringify({ answers: Object.entries(answers).map(([question_id, value]) => ({ question_id, value })) }) }, token); setDimensions(body.dimensions); setMessage("Profile updated. Each dimension includes confidence and evidence."); } catch (e) { setMessage((e as Error).message); } finally { setBusy(false); } }
  async function simulate(event: FormEvent) { event.preventDefault(); if (!profile) return; setBusy(true); try { const body = await api(`/profiles/${profile.id}/scenarios`, { method: "POST", body: JSON.stringify({ prompt: scenario }) }, token); setResult(body.result); } catch (e) { setMessage((e as Error).message); } finally { setBusy(false); } }
  async function train() { if (!profile) return; try { await api(`/profiles/${profile.id}/training`, { method: "POST", body: JSON.stringify({ idempotency_key: `manual-${Date.now()}`, config: { algorithm: "baseline-validation" } }) }, token); setMessage("Training job queued. The baseline worker will validate and publish metadata."); } catch (e) { setMessage((e as Error).message); } }

  if (!token) return <main className="landing"><div className="eyebrow">PRIVATE DECISION SUPPORT</div><h1>A clearer mirror for the way you think.</h1><p className="lede">Build a consent-first digital twin from your own answers and observations. See the evidence, confidence, and limits behind every suggestion.</p><form onSubmit={login} className="login"><label>Email address<input required type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" /></label><button disabled={busy}>{busy ? "Preparing…" : "Create private workspace"}</button></form>{message && <p className="notice">{message}</p>}</main>;

  return <main className="shell"><header><div><div className="eyebrow">DIGITAL TWIN / PRIVATE BETA</div><h1>{profile?.name ?? "Your twin"}</h1><p className="muted">Interpretable signals, not certainty.</p></div><button className="ghost" onClick={() => { window.localStorage.removeItem("dt-token"); setToken(""); }}>Sign out</button></header>
    {message && <div className="notice">{message}</div>}
    <section className="grid"><article className="card hero"><span className="card-label">PROFILE STATUS</span><h2>{dimensions.length ? "Your baseline is taking shape." : "Start with a short baseline."}</h2><p>{dimensions.length ? "Review the dimensions below, then test a real decision in the simulator." : "Your answers remain scoped to this profile and can be exported or deleted at any time."}</p><button onClick={beginAssessment}>{questions.length ? "Continue assessment" : "Begin assessment"}</button></article><article className="card"><span className="card-label">MODEL</span><div className="metric">{dimensions.length ? `${Math.round(dimensions.reduce((a,d) => a + d.confidence, 0) / dimensions.length * 100)}%` : "—"}</div><p className="muted">Average confidence</p><button className="ghost" onClick={train}>Queue validation run</button></article></section>
    {questions.length > 0 && <section className="card assessment"><div className="section-head"><div><span className="card-label">ASSESSMENT</span><h2>What tends to be true for you?</h2></div><button className="ghost" onClick={() => setQuestions([])}>Close</button></div>{questions.map((q) => <div className="question" key={q.id}><label>{q.prompt}<span>{q.dimension_label}</span></label><div className="scale">{q.choices.map((choice) => <button className={answers[q.id] === choice ? "selected" : ""} key={choice} onClick={() => setAnswers({ ...answers, [q.id]: choice })}>{choice}</button>)}</div></div>)}<button onClick={submitAssessment} disabled={busy || Object.keys(answers).length === 0}>Save baseline</button></section>}
    <section className="card"><div className="section-head"><div><span className="card-label">DIMENSIONS</span><h2>Signals with provenance</h2></div><span className="muted">{dimensions.length} tracked</span></div>{dimensions.length ? <div className="dimensions">{dimensions.map((d) => <div className="dimension" key={d.key}><div className="dimension-top"><strong>{d.label}</strong><span>{Math.round(d.score * 100)} · {Math.round(d.confidence * 100)}% confidence</span></div><div className="bar"><i style={{ width: `${d.score * 100}%` }} /></div>{d.evidence?.[0] && <small>{d.evidence[0]}</small>}</div>)}</div> : <p className="empty">Complete the assessment to see your initial dimensions. No dimension is asserted without evidence.</p>}</section>
    <section className="card simulator"><span className="card-label">SCENARIO SIMULATOR</span><h2>Test a decision before you make it.</h2><form onSubmit={simulate}><textarea value={scenario} onChange={(e) => setScenario(e.target.value)} placeholder="Example: Should I accept a new project with an ambiguous deadline?" required /><button disabled={busy || !dimensions.length}>Run interpretable simulation</button></form>{result && <div className="result"><strong>{result.recommended_next_step}</strong><p>{result.summary}</p><div className="pills">{result.likely_strengths?.map((s: string) => <span key={s}>{s}</span>)}</div><small>Confidence: {Math.round(result.confidence * 100)}%. This is a heuristic, not a factual prediction.</small></div>}</section>
    <footer><button className="ghost" onClick={async () => { const data = await api("/privacy/export", {}, token); const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }); const url = URL.createObjectURL(blob); const a = document.createElement("a"); a.href = url; a.download = "digital-twin-export.json"; a.click(); URL.revokeObjectURL(url); }}>Export my data</button><span>Consent-first · explainable · deleteable</span></footer>
  </main>;
}

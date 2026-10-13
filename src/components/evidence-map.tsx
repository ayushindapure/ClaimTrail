"use client";
import { useRef, useState } from "react";
import { AlertTriangle, BookOpen, GitBranch, Fingerprint, Quote, Plus, Minus, Maximize, X, ArrowUpRight, Pin, Search } from "lucide-react";
import { type Investigation, type Match } from "@/lib/types";

const groups = [
  { id: "evidence", title: "Evidence", Icon: BookOpen, color: "green", x: 90, y: 110 },
  { id: "sources", title: "Sources", Icon: Fingerprint, color: "purple", x: 555, y: 110 },
  { id: "provenance", title: "Provenance", Icon: GitBranch, color: "teal", x: 90, y: 430 },
  { id: "warnings", title: "Warnings", Icon: AlertTriangle, color: "amber", x: 555, y: 430 },
];

export function EvidenceMap({ investigation, onOpen, onCategory }: { investigation: Investigation; onOpen: (match: Match) => void; onCategory: (id: string) => void }) {
  const [preview, setPreview] = useState<string | null>(null);
  const [pinned, setPinned] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);
  const [query, setQuery] = useState("");
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const drag = useRef<{ x: number; y: number; px: number; py: number } | null>(null);
  const focus = investigation.focus;
  const matches = investigation.matches;
  const repeats = matches.filter(m => m.proposed_relationship === "Repeats" && m.review_state !== "Dismissed");
  const support = matches.filter(m => m.relationship === "Supports");
  const visible = preview || pinned;
  const children = visible === "evidence" ? support : visible === "warnings" ? repeats : matches.slice(0, 2);
  const enter = (id: string) => { if (timer.current) clearTimeout(timer.current); timer.current = setTimeout(() => setPreview(id), 180); };
  const leave = () => { if (timer.current) clearTimeout(timer.current); timer.current = setTimeout(() => setPreview(null), 160); };
  const pin = (id: string) => { setPinned(pinned === id ? null : id); setPreview(null); };
  const counts: Record<string, number> = { evidence: support.length, sources: new Set(matches.map(m => m.document.creator)).size, provenance: investigation.provenance.citations.length, warnings: repeats.length };
  if (!focus) return <div className="empty-state"><Quote/><h3>No supported claims extracted</h3><p>This local extractor recognises named project costs, amounts and reporting years. Other content is available in Document view.</p></div>;
  return <section className="map" aria-label="Interactive evidence map" onKeyDown={e => { if (e.key === "Escape") { setPreview(null); setPinned(null); } }}>
    <div className="map-top"><label className="map-search"><Search size={15}/><input value={query} onChange={e => setQuery(e.target.value)} placeholder="Find a branch…" aria-label="Find map branch"/></label><span className="map-hint">Hover to preview. Click to explore.</span></div>
    <div className="map-scroll" onPointerDown={e => {
      if ((e.target as HTMLElement).closest("button,input,a,[role='button'],.map-preview")) return;
      drag.current = {x:e.clientX,y:e.clientY,px:pan.x,py:pan.y}; e.currentTarget.setPointerCapture(e.pointerId);
    }} onPointerMove={e => { if (drag.current) setPan({x:drag.current.px+e.clientX-drag.current.x,y:drag.current.py+e.clientY-drag.current.y}); }} onPointerUp={() => {drag.current = null;}}>
      <div className="map-stage" style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})` }}>
        <svg className="map-lines" viewBox="0 0 800 620" role="group" aria-label="Claim relationship branches">
          <defs><filter id="soft"><feGaussianBlur stdDeviation="1"/></filter></defs>
          {groups.map((g, i) => <g key={g.id} className={`map-path ${g.color} ${visible && visible !== g.id ? "dim" : ""}`}>
            <path className="path-glow" d={`M400 304 C${i%2 ? 525 : 275} 304 ${i%2 ? 480 : 315} ${i<2 ? 165 : 485} ${g.x+80} ${g.y+38}`}/>
            <path className="main-path" d={`M400 304 C${i%2 ? 525 : 275} 304 ${i%2 ? 480 : 315} ${i<2 ? 165 : 485} ${g.x+80} ${g.y+38}`}/>
            <path className="twig" d={`M${i%2 ? 540 : 260} ${i<2 ? 197 : 413} Q${i%2 ? 500 : 300} ${i<2 ? 180 : 460} ${i%2 ? 525 : 280} ${i<2 ? 145 : 490}`}/>
            <circle cx={i%2 ? 525 : 280} cy={i<2 ? 145 : 490} r="3.5"/>
            <path className="edge-hit" role="button" tabIndex={0} aria-label={`Explain proposed ${g.title.toLowerCase()} relationship`} d={`M400 304 C${i%2 ? 525 : 275} 304 ${i%2 ? 480 : 315} ${i<2 ? 165 : 485} ${g.x+80} ${g.y+38}`} fill="none" stroke="transparent" strokeWidth="16" onClick={() => onCategory(g.id)} onKeyDown={e => {if (e.key === "Enter" || e.key === " ") {e.preventDefault();onCategory(g.id);}}}/>
          </g>)}
          <circle cx="400" cy="304" r="102" fill="none" stroke="#e7ecf7" strokeDasharray="3 7"/>
        </svg>
        <button className="focus-node" onClick={() => onCategory("claim")}><span className="node-label blue"><Quote size={14}/>Selected claim</span><strong>${focus.amount} million</strong><span>{focus.subject}</span><small>{focus.period} · p. {focus.page} · {focus.stance}</small><span className="status-pill">Proposed</span></button>
        {groups.map(g => <div key={g.id} style={{ left: g.x, top: g.y }} className={`map-group ${g.color} ${query && !g.title.toLowerCase().includes(query.toLowerCase()) ? "dim" : ""}`} onMouseEnter={() => enter(g.id)} onMouseLeave={leave}>
          <button className={`branch-node ${pinned === g.id ? "pinned" : ""}`} onFocus={() => { setPreview(g.id); }} onBlur={leave} onClick={() => pin(g.id)} aria-expanded={pinned === g.id} aria-label={`${g.title}, ${counts[g.id]} findings`}><g.Icon size={21}/><span><strong>{g.title}</strong><small>{g.id === "warnings" ? "Potential repeats" : g.id === "sources" ? "Attributed creators" : g.id === "provenance" ? "Explicit citations" : "Matching passages"}</small></span><span className="node-count">{counts[g.id]}</span></button>
          {visible === g.id && <div className="map-preview" onMouseEnter={() => { if(timer.current) clearTimeout(timer.current); }} onMouseLeave={leave}>
            <div className="preview-title"><span>{pinned === g.id ? <Pin size={13}/> : <g.Icon size={13}/>} {g.title}</span><button className="icon-button" aria-label={`Close ${g.title} preview`} onClick={() => {setPreview(null);setPinned(null);}}><X size={14}/></button></div>
            {g.id === "provenance" ? <><strong>Documented citations</strong><p>{counts.provenance} explicit references in the original source text. The earliest dated record is {investigation.provenance.earliest?.record_id || "unknown"}; original origin remains unestablished.</p></> : g.id === "sources" ? <><strong>{counts.sources} attributed creators</strong><p>Creators and holding institution remain separate. Repetition does not establish source independence.</p></> : <><strong>{g.id === "warnings" ? "Follow the earlier figure" : "A fuller picture of the cost"}</strong><p>{g.id === "warnings" ? "Same project and year; candidate occurrences require individual review." : "Matching figures support comparison. They do not guarantee factual accuracy."}</p></>}
            {pinned === g.id && children.slice(0, 2).map(m => <button className="preview-child" key={m.id} onClick={() => onOpen(m)}><span>{m.document.title}<small>{m.document.record_id} · p. {m.claim.page}</small></span><ArrowUpRight size={14}/></button>)}
            <button className="text-button" onClick={() => onCategory(g.id)}>View details <ArrowUpRight size={14}/></button>
          </div>}
        </div>)}
      </div>
    </div>
    <div className="map-bottom"><div className="map-legend"><span><i className="solid-line"/>Source passage</span><span><i className="dashed-line"/>Proposed relationship</span></div><div className="map-controls"><button aria-label="Zoom map out" onClick={() => setZoom(Math.max(.6, zoom-.1))}><Minus size={16}/></button><span>{Math.round(zoom*100)}%</span><button aria-label="Zoom map in" onClick={() => setZoom(Math.min(1.5, zoom+.1))}><Plus size={16}/></button><button aria-label="Fit map to view" onClick={() => {setZoom(1);setPan({x:0,y:0});}}><Maximize size={16}/></button></div></div>
  </section>;
}

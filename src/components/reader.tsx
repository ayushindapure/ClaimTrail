"use client";
import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, Download, Eye, EyeOff, Minus, Plus, ScanText, Search, AlertTriangle } from "lucide-react";
import { api, type Claim, type Document } from "@/lib/types";

export function Reader({ id, claim, onError, onSelectClaim }: { id: string; claim?: Claim | null; onError: (message: string) => void; onSelectClaim?: (claim: Claim) => void }) {
  const [document, setDocument] = useState<Document | null>(null);
  const [page, setPage] = useState(claim?.page || 1);
  const [show, setShow] = useState(true);
  const [ocr, setOcr] = useState(false);
  const [zoom, setZoom] = useState(100);
  const [search, setSearch] = useState("");
  useEffect(() => {
    let active = true;
    setDocument(null); setPage(claim?.page || 1);
    api<Document>(`/documents/${id}`).then(d => { if (active) setDocument(d); }).catch(e => onError(e.message));
    return () => { active = false; };
  }, [id, claim?.page, onError]);
  const source = document?.pages?.[page-1];
  const currentClaims = claim ? [claim] : (document?.claims || []);
  const hits = (document?.pages || []).map((p, i) => p.text.toLowerCase().includes(search.toLowerCase()) ? i+1 : 0).filter(Boolean);
  return <section className="reader" aria-label="Document reader">
    <div className="reader-toolbar">
      <div className="inline"><button className="icon-button" aria-label="Previous page" disabled={page <= 1} onClick={() => setPage(page-1)}><ChevronLeft size={16}/></button><span>Page {page} of {document?.pages?.length || "…"}</span><button className="icon-button" aria-label="Next page" disabled={page >= (document?.pages?.length || 1)} onClick={() => setPage(page+1)}><ChevronRight size={16}/></button></div>
      <div className="inline"><button className="icon-button" aria-label="Zoom out" onClick={() => setZoom(Math.max(50, zoom-25))}><Minus size={15}/></button><span>{zoom}%</span><button className="icon-button" aria-label="Zoom in" onClick={() => setZoom(Math.min(200, zoom+25))}><Plus size={15}/></button><button className={`icon-button ${show ? "selected" : ""}`} aria-label={show ? "Hide all annotations" : "Show annotations"} title="Toggle claim annotations" onClick={() => setShow(!show)}>{show ? <Eye size={17}/> : <EyeOff size={17}/>}</button><button className={`icon-button ${ocr ? "selected" : ""}`} aria-label="Toggle extracted text" title="Show extracted text" onClick={() => setOcr(!ocr)}><ScanText size={17}/></button></div>
    </div>
    <div className="reader-search"><Search size={14}/><input aria-label="Search document pages" placeholder="Search this record…" value={search} onChange={e => setSearch(e.target.value)}/>{search && <span>{hits.length} matching pages <button onClick={() => hits.length && setPage(hits[0])}>Go</button></span>}</div>
    {source?.uncertain && <div className="warning-banner"><AlertTriangle size={16}/>{source.uncertainty_note || "OCR confidence is uncertain in this page. Compare the transcription with the original."}</div>}
    {!document && <div className="empty-state">Loading original page…</div>}
    {document && <div className="reader-scroll"><div className="page-image" style={{ width: `${zoom}%` }}>
      {/* The source image is served from retained original bytes, independently of transcription. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={`/api/documents/${id}/pages/${page}.png`} alt={`${document.title}, original page ${page}`} onError={() => onError("The original page image could not be loaded.")}/>
      {show && currentClaims.filter(c => c.page === page).flatMap(c => c.boxes.map((box, i) => {
        const props = {className: `passage-highlight ${c.uncertain ? "uncertain" : ""}`, style: {left: `${box[0]*100}%`, top: `${box[1]*100}%`, width: `${box[2]*100}%`, height: `${box[3]*100}%`}, title: `Claim · ${c.quote}`};
        return i === 0 ? <button key={`${c.id}-${i}`} {...props} aria-label={`Open evidence for highlighted claim on page ${page}`} onClick={() => onSelectClaim?.(c)}/> : <span key={`${c.id}-${i}`} {...props} onClick={() => onSelectClaim?.(c)}/>;
      }))}
      {show && source?.uncertain_words?.map((word, i) => <span key={`ocr-${i}`} className="ocr-highlight" title={`Uncertain OCR: ${word.text}`} style={{left: `${word.box[0]*100}%`, top: `${word.box[1]*100}%`, width: `${word.box[2]*100}%`, height: `${word.box[3]*100}%`}}/>)}
    </div>{show && claim && !claim.boxes.length && <p className="muted">Page-level reference only. Exact coordinates could not be aligned.</p>}
    {ocr && <div className="transcription"><span className="eyebrow">{source?.method} · Extraction revision 1</span><h3>Extracted transcription</h3><p>{source?.text || "No readable text was extracted."}</p></div>}
    </div>}
    <div className="reader-footer"><span><i className="legend-dot blue"/>Extracted claim <i className="legend-dot amber"/>OCR uncertainty</span><a href={`/api/documents/${id}/original`} download><Download size={14}/>Original</a></div>
  </section>;
}

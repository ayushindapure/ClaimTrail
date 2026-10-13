export type Box = [number, number, number, number];
export type Claim = {
  id: string; document_id: string; page: number; quote: string; statement: string;
  subject: string; period: string; amount: number; old_amount: number | null;
  stance: string; boxes: Box[]; method: string; uncertain: boolean; review_state: string;
};
export type Document = {
  id: string; title: string; date: string; creator: string; institution: string; record_id: string;
  page_count: number; methods: string[]; uncertain: boolean; hash: string; synthetic: boolean;
  source_url: string | null; pages?: Page[]; claims?: Claim[];
};
export type Page = {
  text: string; method: string; uncertain: boolean; uncertainty_note?: string;
  width: number; height: number; uncertain_words: {text: string; box: Box; confidence: number}[];
};
export type Match = {
  id: string; claim: Claim; document: Document; relationship: string; proposed_relationship: string;
  rationale: string; review_state: string; reason: string | null;
};
export type Investigation = {
  id: string; document: Document; claims: Claim[]; focus: Claim | null; matches: Match[];
  indexed_count: number; created_at: string; history: ReviewHistory[]; limitations: string;
  provenance: { earliest: Document | null; citations: {from_id:string;from_title:string;to_id:string;date:string;basis:string}[] };
};
export type ReviewHistory = {
  id: number; target_id: string; action: string; relationship: string; reason: string; actor: string;
  created_at: string; evidence_hashes: string;
};
export type Collection = { id: string; name: string; synthetic: boolean; documents: Document[]; indexed_count: number };

export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, options);
  if (!response.ok) {
    let message = `Request failed (${response.status}).`;
    try { const body = await response.json(); message = typeof body.detail === "string" ? body.detail : "Check the input and try again."; } catch {}
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}
export function date(value: string) {
  if (value === "Unknown") return value;
  return new Date(value).toLocaleDateString("en-AU", { day: "numeric", month: "short", year: "numeric", timeZone: "Australia/Melbourne" });
}

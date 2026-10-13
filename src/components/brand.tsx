export function Brand({ compact = false }: { compact?: boolean }) {
  return <span className="brand"><svg width="31" height="31" viewBox="0 0 32 32" aria-hidden="true"><path d="M7 25C7 18 16 21 16 14M16 14C16 7 25 9 25 4M16 14C16 7 7 11 7 4M16 14v13" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round"/><circle cx="7" cy="4" r="2.5" fill="currentColor"/><circle cx="25" cy="4" r="2.5" fill="currentColor"/><circle cx="7" cy="25" r="2.5" fill="currentColor"/><circle cx="16" cy="27" r="2.5" fill="currentColor"/></svg>{!compact && <span>ClaimTrail</span>}</span>;
}

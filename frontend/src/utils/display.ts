/// Shared display utilities for legislation explorer.

const ACT_SHORT: Record<string, string> = {
  'itaa-1997': 'ITAA97',
  'itaa-1936': 'ITAA36',
  'gst-1999': 'GST99',
  'taa-1953': 'TAA53',
  'master-tax-guide': 'CCH MTG',
  'master-tax-examples': 'CCH Example',
  'master-gst-guide': 'CCH GST Guide',
  'nz-it-2007': 'NZ IT07',
  'tax-cases': 'Tax Cases',
  'corporations-act-2001': 'Corps Act',
  'regulatory-guides': 'ASIC RGs',
  'aml-ctf-2006': 'AML/CTF Act',
  'aml-ctf-rules-2007': 'AML/CTF Rules',
  'insolvency-keays': 'Keays Insolvency',
}

/** Short display name for an act ID. Falls back to the original name. */
export function shortActName(actId: string): string {
  return ACT_SHORT[actId] || actId.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

/** Format a section reference like "ITAA97 s8-1". */
export function formatSectionRef(actId: string, section: string): string {
  return `${shortActName(actId)} s${section}`
}

/** Format a search result's act+snippet into a short label. */
export function formatSearchResult(result: { act: string; section?: string; title?: string }): string {
  const ref = result.section ? formatSectionRef(result.act, result.section) : shortActName(result.act)
  return result.title ? `${ref} — ${result.title}` : ref
}
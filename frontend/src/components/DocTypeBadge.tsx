/** Badge naming the kind of BIS document a passage or knowledge-base entry belongs to. */

/** Matches DOC_TYPE_LABELS in src/ingestion.py. */
export const DOC_TYPE_NAMES: Record<string, string> = {
  standard: 'Indian Standard',
  act: 'Act',
  product_manual: 'Product manual',
  press_release: 'Press release',
  summary: 'Standard summary',
  document: 'BIS document',
}

/** Colour per type, so a standard is told apart from a document *about* a standard. */
const DOC_TYPE_STYLES: Record<string, string> = {
  standard: 'bg-bis-100 text-bis-800',
  act: 'bg-indigo-100 text-indigo-800',
  product_manual: 'bg-emerald-100 text-emerald-800',
  summary: 'bg-amber-100 text-amber-800',
  press_release: 'bg-slate-200 text-slate-700',
  document: 'bg-slate-200 text-slate-700',
}

export default function DocTypeBadge({ docType, label }: { docType: string; label?: string }) {
  return (
    <span
      className={`rounded-md px-1.5 py-0.5 text-[11px] font-semibold ${DOC_TYPE_STYLES[docType] ?? DOC_TYPE_STYLES.document}`}
    >
      {label ?? DOC_TYPE_NAMES[docType] ?? DOC_TYPE_NAMES.document}
    </span>
  )
}

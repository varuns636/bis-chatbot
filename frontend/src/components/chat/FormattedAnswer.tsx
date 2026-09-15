import { BadgeCheck, CircleHelp, FileText } from 'lucide-react'
import type { ReactNode } from 'react'

// Citation markers exactly as the backend writes them, plus **bold** text.
const INLINE = /\[Source:\s*([^,\]]+?)\s*,\s*page\s*(\d+)[^\]]*\]|\*\*(.+?)\*\*/gi

function renderInline(text: string): ReactNode[] {
  const nodes: ReactNode[] = []
  let last = 0
  for (const match of text.matchAll(INLINE)) {
    const index = match.index ?? 0
    if (index > last) nodes.push(text.slice(last, index))
    if (match[3] !== undefined) {
      nodes.push(
        <strong key={index} className="font-semibold text-slate-900">
          {match[3]}
        </strong>,
      )
    } else {
      nodes.push(
        <span
          key={index}
          title={match[0]}
          className="mx-0.5 inline-flex items-center gap-1 whitespace-nowrap rounded-md border border-bis-200 bg-bis-50 px-1.5 py-px align-baseline text-xs font-medium text-bis-800"
        >
          <FileText className="h-3 w-3" aria-hidden="true" />
          <span className="sr-only">Source:</span>
          {match[1]} · p. {match[2]}
        </span>,
      )
    }
    last = index + match[0].length
  }
  if (last < text.length) nodes.push(text.slice(last))
  return nodes
}

type Block = { kind: 'p' | 'ul' | 'ol'; lines: string[] }

function toBlocks(text: string): Block[] {
  const blocks: Block[] = []
  for (const raw of text.split('\n')) {
    const line = raw.trim()
    if (!line) continue
    const bullet = line.match(/^[-*•]\s+(.*)$/)
    const numbered = line.match(/^\d+[.)]\s+(.*)$/)
    const kind = bullet ? 'ul' : numbered ? 'ol' : 'p'
    const content = bullet?.[1] ?? numbered?.[1] ?? line
    const previous = blocks.at(-1)
    if (kind !== 'p' && previous?.kind === kind) previous.lines.push(content)
    else blocks.push({ kind, lines: [content] })
  }
  return blocks
}

function Paragraph({ line }: { line: string }) {
  // The English answer format marks uncertainty and "check with BIS" advice with these prefixes.
  const note = line.match(/^(Uncertain|Verify with BIS):\s*(.*)$/i)
  if (note) {
    const verify = note[1].toLowerCase().startsWith('verify')
    const Icon = verify ? BadgeCheck : CircleHelp
    return (
      <p className="flex gap-2 rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-600">
        <Icon className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" aria-hidden="true" />
        <span>
          <span className="font-semibold text-slate-700">{note[1]}:</span> {renderInline(note[2])}
        </span>
      </p>
    )
  }
  return <p>{renderInline(line)}</p>
}

export default function FormattedAnswer({ text, lang }: { text: string; lang: string }) {
  return (
    <div lang={lang} className="space-y-3 text-[0.95rem] leading-7 text-slate-700">
      {toBlocks(text).map((block, index) => {
        if (block.kind === 'p') return block.lines.map((line, i) => <Paragraph key={`${index}-${i}`} line={line} />)
        const List = block.kind === 'ul' ? 'ul' : 'ol'
        return (
          <List key={index} className={`space-y-2 pl-5 ${block.kind === 'ul' ? 'list-disc' : 'list-decimal'} marker:text-bis-400`}>
            {block.lines.map((line, i) => (
              <li key={i}>{renderInline(line)}</li>
            ))}
          </List>
        )
      })}
    </div>
  )
}

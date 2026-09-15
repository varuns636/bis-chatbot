export default function Logo({ className = 'h-8 w-8' }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" fill="none" aria-hidden="true" className={className}>
      <rect width="32" height="32" rx="8" className="fill-bis-700" />
      <path d="M10 7.5h8.5L23 12v12.5a1 1 0 0 1-1 1H10a1 1 0 0 1-1-1v-16a1 1 0 0 1 1-1Z" fill="#fff" />
      <path d="M18.5 7.5V12H23" className="fill-bis-200" />
      <path
        d="m12.5 18.2 2.4 2.4 4.6-4.9"
        className="stroke-bis-700"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

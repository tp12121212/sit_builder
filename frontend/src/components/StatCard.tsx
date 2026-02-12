interface StatCardProps {
  label: string
  value: number
  accent: 'teal' | 'amber' | 'ink' | 'coral'
}

export function StatCard({ label, value, accent }: StatCardProps) {
  return (
    <article className={`stat-card stat-${accent}`}>
      <p className="stat-label">{label}</p>
      <p className="stat-value">{value}</p>
    </article>
  )
}

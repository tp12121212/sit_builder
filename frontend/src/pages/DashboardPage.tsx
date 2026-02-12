import { StatCard } from '../components/StatCard'
import type { RulepackSummary, ScanSummary, SitSummary } from '../types/api'

interface DashboardPageProps {
  scans: ScanSummary[]
  sits: SitSummary[]
  rulepacks: RulepackSummary[]
}

export function DashboardPage({ scans, sits, rulepacks }: DashboardPageProps) {
  const activeScans = scans.filter((scan) => !['COMPLETED', 'FAILED'].includes(scan.status)).length

  return (
    <section className="panel">
      <h2>Command Center</h2>
      <p className="muted">Purview-style SIT discovery and rulepack operations overview.</p>
      <div className="stats-grid">
        <StatCard label="Total Scans" value={scans.length} accent="teal" />
        <StatCard label="Active Scans" value={activeScans} accent="amber" />
        <StatCard label="SIT Definitions" value={sits.length} accent="ink" />
        <StatCard label="Rulepacks" value={rulepacks.length} accent="coral" />
      </div>
    </section>
  )
}

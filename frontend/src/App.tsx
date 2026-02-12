import { useEffect, useMemo, useState } from 'react'

import { api } from './api/client'
import { DashboardPage } from './pages/DashboardPage'
import { RulepackPage } from './pages/RulepackPage'
import { ScanWorkbenchPage } from './pages/ScanWorkbenchPage'
import { SitLibraryPage } from './pages/SitLibraryPage'
import type { RulepackSummary, ScanSummary, SitSummary } from './types/api'

type Tab = 'dashboard' | 'scans' | 'sits' | 'rulepacks'
const TAB_STORAGE_KEY = 'sit_builder_active_tab'

function getInitialTab(): Tab {
  const stored = window.localStorage.getItem(TAB_STORAGE_KEY)
  if (stored === 'dashboard' || stored === 'scans' || stored === 'sits' || stored === 'rulepacks') {
    return stored
  }
  return 'dashboard'
}

export default function App() {
  const [tab, setTab] = useState<Tab>(getInitialTab)
  const [scans, setScans] = useState<ScanSummary[]>([])
  const [sits, setSits] = useState<SitSummary[]>([])
  const [rulepacks, setRulepacks] = useState<RulepackSummary[]>([])
  const [error, setError] = useState<string | null>(null)

  const refreshScans = async () => {
    const data = await api.listScans()
    setScans(data.scans)
  }

  const refreshSits = async () => {
    const data = await api.listSits()
    setSits(data.sits)
  }

  const refreshRulepacks = async () => {
    const data = await api.listRulepacks()
    setRulepacks(data.rulepacks)
  }

  const refreshAll = async () => {
    try {
      setError(null)
      await Promise.all([refreshScans(), refreshSits(), refreshRulepacks()])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load dashboard data')
    }
  }

  useEffect(() => {
    void refreshAll()
    const timer = window.setInterval(() => {
      void refreshScans()
    }, 5000)
    return () => window.clearInterval(timer)
  }, [])

  useEffect(() => {
    window.localStorage.setItem(TAB_STORAGE_KEY, tab)
  }, [tab])

  const tabTitle = useMemo(() => {
    switch (tab) {
      case 'dashboard':
        return 'Dashboard'
      case 'scans':
        return 'Scan Workbench'
      case 'sits':
        return 'SIT Library'
      case 'rulepacks':
        return 'Rulepack Generator'
      default:
        return 'SIT Builder'
    }
  }, [tab])

  return (
    <div className="shell">
      <aside className="sidebar">
        <h1>SIT Builder</h1>
        <p className="muted">Purview-style classification studio</p>
        <nav>
          <button className={tab === 'dashboard' ? 'active' : ''} onClick={() => setTab('dashboard')}>Dashboard</button>
          <button className={tab === 'scans' ? 'active' : ''} onClick={() => setTab('scans')}>Scans</button>
          <button className={tab === 'sits' ? 'active' : ''} onClick={() => setTab('sits')}>SIT Library</button>
          <button className={tab === 'rulepacks' ? 'active' : ''} onClick={() => setTab('rulepacks')}>Rulepacks</button>
        </nav>
      </aside>

      <main className="content">
        <header className="topbar">
          <h2>{tabTitle}</h2>
          <button onClick={() => void refreshAll()}>Refresh Data</button>
        </header>

        {tab === 'dashboard' && <DashboardPage scans={scans} sits={sits} rulepacks={rulepacks} />}
        {tab === 'scans' && <ScanWorkbenchPage scans={scans} refreshScans={refreshScans} />}
        {tab === 'sits' && <SitLibraryPage sits={sits} refreshSits={refreshSits} />}
        {tab === 'rulepacks' && (
          <RulepackPage sits={sits} rulepacks={rulepacks} refreshRulepacks={refreshRulepacks} />
        )}

        {error && <p className="error-text">{error}</p>}
      </main>
    </div>
  )
}

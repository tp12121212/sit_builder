import { FormEvent, useMemo, useState } from 'react'

import { api } from '../api/client'
import type { RulepackSummary, SitSummary } from '../types/api'

interface RulepackPageProps {
  sits: SitSummary[]
  rulepacks: RulepackSummary[]
  refreshRulepacks: () => Promise<void>
}

export function RulepackPage({ sits, rulepacks, refreshRulepacks }: RulepackPageProps) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [selectedSitIds, setSelectedSitIds] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const publishedSits = useMemo(() => sits.filter((sit) => sit.status !== 'ARCHIVED'), [sits])

  const toggleSit = (sitId: string) => {
    setSelectedSitIds((prev) => (prev.includes(sitId) ? prev.filter((id) => id !== sitId) : [...prev, sitId]))
  }

  const createRulepack = async (event: FormEvent) => {
    event.preventDefault()
    if (!name.trim() || selectedSitIds.length === 0) {
      setError('Provide a rulepack name and select at least one SIT.')
      return
    }

    setBusy(true)
    setError(null)
    try {
      await api.createRulepack({
        name: name.trim(),
        description: description.trim() || undefined,
        sit_ids: selectedSitIds,
      })
      setName('')
      setDescription('')
      setSelectedSitIds([])
      await refreshRulepacks()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create rulepack')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="panel">
      <h2>Rulepack Generator</h2>
      <div className="two-col">
        <form className="form" onSubmit={createRulepack}>
          <label>
            Rulepack name
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Q1 2026 Custom SITs" />
          </label>
          <label>
            Description
            <textarea rows={3} value={description} onChange={(e) => setDescription(e.target.value)} />
          </label>
          <fieldset className="checklist">
            <legend>Select SITs</legend>
            {publishedSits.map((sit) => (
              <label key={sit.sit_id} className="check-row">
                <input
                  type="checkbox"
                  checked={selectedSitIds.includes(sit.sit_id)}
                  onChange={() => toggleSit(sit.sit_id)}
                />
                <span>{sit.name} v{sit.version}</span>
              </label>
            ))}
            {publishedSits.length === 0 && <p className="muted">Create SITs first.</p>}
          </fieldset>
          <button type="submit" disabled={busy}>Generate Rulepack</button>
        </form>

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>SIT Count</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {rulepacks.map((rulepack) => (
                <tr key={rulepack.rulepack_id}>
                  <td>{rulepack.name}</td>
                  <td>{rulepack.sit_count ?? '-'}</td>
                  <td>{new Date(rulepack.created_at).toLocaleString()}</td>
                </tr>
              ))}
              {rulepacks.length === 0 && (
                <tr>
                  <td colSpan={3} className="muted">No rulepacks generated yet.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {error && <p className="error-text">{error}</p>}
    </section>
  )
}

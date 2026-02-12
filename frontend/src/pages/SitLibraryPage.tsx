import { FormEvent, useMemo, useState } from 'react'

import { api } from '../api/client'
import type { SitSummary } from '../types/api'

interface SitLibraryPageProps {
  sits: SitSummary[]
  refreshSits: () => Promise<void>
}

export function SitLibraryPage({ sits, refreshSits }: SitLibraryPageProps) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [confidenceLevel, setConfidenceLevel] = useState(85)
  const [selectedSitId, setSelectedSitId] = useState('')
  const [elementPattern, setElementPattern] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const selectedSit = useMemo(
    () => sits.find((sit) => sit.sit_id === selectedSitId) ?? null,
    [selectedSitId, sits],
  )

  const createSit = async (event: FormEvent) => {
    event.preventDefault()
    if (!name.trim()) {
      setError('Name is required.')
      return
    }

    setBusy(true)
    setError(null)
    try {
      await api.createSit({
        name: name.trim(),
        description: description.trim() || undefined,
        confidence_level: confidenceLevel,
      })
      setName('')
      setDescription('')
      await refreshSits()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create SIT')
    } finally {
      setBusy(false)
    }
  }

  const addPrimaryElement = async (event: FormEvent) => {
    event.preventDefault()
    if (!selectedSitId || !elementPattern.trim()) {
      setError('Select a SIT and provide a regex pattern.')
      return
    }

    setBusy(true)
    setError(null)
    try {
      await api.addElement(selectedSitId, {
        element_role: 'PRIMARY',
        element_type: 'REGEX',
        pattern: elementPattern.trim(),
        case_sensitive: false,
        word_boundary: true,
      })
      setElementPattern('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add element')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="panel">
      <h2>SIT Library</h2>
      <div className="two-col">
        <form className="form" onSubmit={createSit}>
          <label>
            SIT name
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Custom Employee ID" />
          </label>
          <label>
            Description
            <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={4} />
          </label>
          <label>
            Confidence
            <select value={confidenceLevel} onChange={(e) => setConfidenceLevel(Number(e.target.value))}>
              <option value={75}>75</option>
              <option value={85}>85</option>
              <option value={95}>95</option>
            </select>
          </label>
          <button type="submit" disabled={busy}>Create Draft SIT</button>
        </form>

        <div>
          <div className="toolbar">
            <select value={selectedSitId} onChange={(e) => setSelectedSitId(e.target.value)}>
              <option value="">Select SIT</option>
              {sits.map((sit) => (
                <option key={sit.sit_id} value={sit.sit_id}>
                  {sit.name} v{sit.version} ({sit.status})
                </option>
              ))}
            </select>
            <button type="button" onClick={refreshSits}>Refresh</button>
          </div>

          {selectedSit && (
            <div className="highlight">
              <p><strong>{selectedSit.name}</strong></p>
              <p className="muted">{selectedSit.description ?? 'No description'}</p>
            </div>
          )}

          <form className="form" onSubmit={addPrimaryElement}>
            <label>
              Add primary regex element
              <input
                value={elementPattern}
                onChange={(e) => setElementPattern(e.target.value)}
                placeholder="\\b\\d{3}-\\d{2}-\\d{4}\\b"
              />
            </label>
            <button type="submit" disabled={busy || !selectedSitId}>Add Element</button>
          </form>

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Status</th>
                  <th>Version</th>
                  <th>Confidence</th>
                </tr>
              </thead>
              <tbody>
                {sits.map((sit) => (
                  <tr key={sit.sit_id}>
                    <td>{sit.name}</td>
                    <td>{sit.status}</td>
                    <td>{sit.version}</td>
                    <td>{sit.confidence_level}</td>
                  </tr>
                ))}
                {sits.length === 0 && (
                  <tr>
                    <td colSpan={4} className="muted">No SIT definitions yet.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {error && <p className="error-text">{error}</p>}
    </section>
  )
}

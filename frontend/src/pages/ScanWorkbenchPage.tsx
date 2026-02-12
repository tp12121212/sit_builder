import { FormEvent, useEffect, useMemo, useRef, useState } from 'react'

import { api } from '../api/client'
import { getActiveAccount, getTokenSilently, loginAndGetToken } from '../auth/msal'
import type { Candidate, ScanDetail, ScanSummary } from '../types/api'

interface ScanWorkbenchPageProps {
  scans: ScanSummary[]
  refreshScans: () => Promise<void>
}

const SCAN_DRAFT_STORAGE_KEY = 'sit_builder_scan_draft'

async function readAllDirectoryEntries(
  reader: FileSystemDirectoryReader,
): Promise<FileSystemEntry[]> {
  const all: FileSystemEntry[] = []
  while (true) {
    const batch = await new Promise<FileSystemEntry[]>((resolve, reject) => {
      reader.readEntries(resolve, reject)
    })
    if (batch.length === 0) {
      break
    }
    all.push(...batch)
  }
  return all
}

async function collectFilesFromEntry(entry: FileSystemEntry, parentPath = ''): Promise<File[]> {
  if (entry.isFile) {
    const fileEntry = entry as FileSystemFileEntry
    const file = await new Promise<File>((resolve, reject) => {
      fileEntry.file(resolve, reject)
    })
    if (!parentPath) {
      return [file]
    }

    // Preserve folder path in filename for visibility and uniqueness.
    const relativeName = `${parentPath}/${file.name}`
    return [new File([file], relativeName, { type: file.type, lastModified: file.lastModified })]
  }

  if (entry.isDirectory) {
    const dirEntry = entry as FileSystemDirectoryEntry
    const reader = dirEntry.createReader()
    const children = await readAllDirectoryEntries(reader)
    const nextPath = parentPath ? `${parentPath}/${entry.name}` : entry.name
    const nested = await Promise.all(children.map((child) => collectFilesFromEntry(child, nextPath)))
    return nested.flat()
  }

  return []
}

async function extractDroppedFiles(dataTransfer: DataTransfer): Promise<File[]> {
  const items = Array.from(dataTransfer.items ?? [])
  const entries = items
    .map((item) => (item as DataTransferItem & { webkitGetAsEntry?: () => FileSystemEntry | null }).webkitGetAsEntry?.())
    .filter((entry): entry is FileSystemEntry => Boolean(entry))

  if (entries.length === 0) {
    return Array.from(dataTransfer.files ?? [])
  }

  const collected = await Promise.all(entries.map((entry) => collectFilesFromEntry(entry)))
  const files = collected.flat()
  return files.length > 0 ? files : Array.from(dataTransfer.files ?? [])
}

export function ScanWorkbenchPage({ scans, refreshScans }: ScanWorkbenchPageProps) {
  const sitCategoryOptions = [
    'Financial Services',
    'Healthcare',
    'Insurance',
    'Government',
    'Legal',
    'Education',
    'Retail',
    'Telecommunications',
    'Energy and Utilities',
    'Technology',
    'Manufacturing',
    'Transportation and Logistics',
    'Hospitality and Travel',
    'Custom',
  ] as const
  const [selectedScanId, setSelectedScanId] = useState<string>('')
  const [justCreatedScanId, setJustCreatedScanId] = useState<string | null>(null)
  const [scanName, setScanName] = useState('')
  const [sitCategory, setSitCategory] = useState<(typeof sitCategoryOptions)[number]>('Financial Services')
  const [customSitCategory, setCustomSitCategory] = useState('')
  const [preserveCase, setPreserveCase] = useState(false)
  const [forceOcr, setForceOcr] = useState(false)
  const [scanType, setScanType] = useState<'classic_nlp' | 'sentence_transformer'>('classic_nlp')
  const [userPrincipalName, setUserPrincipalName] = useState('')
  const [exchangeToken, setExchangeToken] = useState<string | null>(null)
  const [exchangeOrganization, setExchangeOrganization] = useState('')
  const [authMessage, setAuthMessage] = useState<string | null>(null)
  const [files, setFiles] = useState<File[]>([])
  const [isDragOver, setIsDragOver] = useState(false)
  const [deleteMode, setDeleteMode] = useState(false)
  const [scanIdsToDelete, setScanIdsToDelete] = useState<Set<string>>(new Set())
  const [scanDetails, setScanDetails] = useState<ScanDetail | null>(null)
  const [lastCandidatesLoadKey, setLastCandidatesLoadKey] = useState('')
  const [candidates, setCandidates] = useState<Candidate[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const draftHydrated = useRef(false)
  const isMobileDevice = useMemo(() => /iPhone|iPad|iPod|Android|Mobile/i.test(navigator.userAgent || ''), [])

  const selectedScan = useMemo(
    () => scans.find((scan) => scan.scan_id === selectedScanId) ?? null,
    [selectedScanId, scans],
  )
  const hasSelectedInList = !!(selectedScanId && scans.some((scan) => scan.scan_id === selectedScanId))
  const activeScanSummary = selectedScan ?? (scanDetails
    ? {
        scan_type: scanDetails.scan_type,
        status: scanDetails.status,
        source_files_count: scanDetails.source_files_count,
      }
    : null)
  const progressPctRaw = scanDetails?.metadata?.processing_progress_pct
  const progressPct = typeof progressPctRaw === 'number' ? Math.max(0, Math.min(100, progressPctRaw)) : null
  const phaseRaw = scanDetails?.metadata?.processing_phase
  const progressPhase = typeof phaseRaw === 'string' ? phaseRaw : null
  const currentFileRaw = scanDetails?.metadata?.current_file_name
  const currentFileName = typeof currentFileRaw === 'string' ? currentFileRaw : null
  const filesDoneRaw = scanDetails?.metadata?.files_completed
  const filesTotalRaw = scanDetails?.metadata?.files_total
  const filesDone = typeof filesDoneRaw === 'number' ? filesDoneRaw : null
  const filesTotal = typeof filesTotalRaw === 'number' ? filesTotalRaw : null
  const scanSitCategoryRaw = scanDetails?.metadata?.sit_category
  const scanSitCategory = typeof scanSitCategoryRaw === 'string' ? scanSitCategoryRaw : null
  const groupedCandidates = useMemo(() => {
    const grouped = new Map<
      string,
      {
        key: string
        candidate_id: string
        candidate_type: string
        value: string
        score: number | null
        frequency: number
        fileNames: string[]
        sitCategory: string | null
        extractionModules: string[]
        ocrStates: boolean[]
      }
    >()

    for (const candidate of candidates) {
      const key = `${candidate.candidate_type}::${candidate.value}`
      const fileName = candidate.metadata?.file_name
      const sitCategory = candidate.metadata?.sit_category ?? scanSitCategory
      const extractionModule = typeof candidate.metadata?.extraction_module === 'string' ? candidate.metadata.extraction_module : null
      const ocrPerformed = typeof candidate.metadata?.ocr_performed === 'boolean' ? candidate.metadata.ocr_performed : null
      const existing = grouped.get(key)
      if (!existing) {
        grouped.set(key, {
          key,
          candidate_id: candidate.candidate_id,
          candidate_type: candidate.candidate_type,
          value: candidate.value,
          score: candidate.score,
          frequency: candidate.frequency,
          fileNames: fileName ? [fileName] : [],
          sitCategory: sitCategory ?? null,
          extractionModules: extractionModule ? [extractionModule] : [],
          ocrStates: ocrPerformed === null ? [] : [ocrPerformed],
        })
        continue
      }

      existing.frequency += candidate.frequency
      if ((candidate.score ?? -1) > (existing.score ?? -1)) {
        existing.score = candidate.score
      }
      if (fileName && !existing.fileNames.includes(fileName)) {
        existing.fileNames.push(fileName)
      }
      if (!existing.sitCategory && sitCategory) {
        existing.sitCategory = sitCategory
      }
      if (extractionModule && !existing.extractionModules.includes(extractionModule)) {
        existing.extractionModules.push(extractionModule)
      }
      if (ocrPerformed !== null && !existing.ocrStates.includes(ocrPerformed)) {
        existing.ocrStates.push(ocrPerformed)
      }
    }

    return Array.from(grouped.values()).sort((a, b) => (b.score ?? -1) - (a.score ?? -1))
  }, [candidates, scanSitCategory])

  const allScansSelected = scans.length > 0 && scanIdsToDelete.size === scans.length
  const selectedFileNames = files.map((file) => file.name).join(', ')
  const forceOcrDisabled = scanType === 'sentence_transformer'
  const ocrColumnNotApplicable = activeScanSummary?.scan_type === 'sentence_transformer'
  const requiresAuthBeforeFiles =
    isMobileDevice && scanType === 'sentence_transformer' && !exchangeToken

  const mergeFiles = (incoming: File[]) => {
    if (incoming.length === 0) {
      return
    }
    setFiles((prev) => {
      const map = new Map(prev.map((file) => [`${file.name}:${file.size}:${file.lastModified}`, file] as const))
      incoming.forEach((file) => {
        map.set(`${file.name}:${file.size}:${file.lastModified}`, file)
      })
      return Array.from(map.values())
    })
  }

  const formatDefaultScanName = (fileName: string) => {
    const now = new Date()
    const yyyy = String(now.getFullYear())
    const mm = String(now.getMonth() + 1).padStart(2, '0')
    const dd = String(now.getDate()).padStart(2, '0')
    const hh = String(now.getHours()).padStart(2, '0')
    const min = String(now.getMinutes()).padStart(2, '0')
    return `${fileName}-${yyyy}-${mm}-${dd}-${hh}${min}`
  }

  const toggleDeleteMode = async () => {
    const next = !deleteMode
    setDeleteMode(next)
    setScanIdsToDelete(new Set())
    if (next) {
      await refreshScans()
    }
  }

  const toggleScanForDelete = (scanId: string) => {
    setScanIdsToDelete((prev) => {
      const next = new Set(prev)
      if (next.has(scanId)) {
        next.delete(scanId)
      } else {
        next.add(scanId)
      }
      return next
    })
  }

  const toggleSelectAllForDelete = () => {
    if (allScansSelected) {
      setScanIdsToDelete(new Set())
      return
    }
    setScanIdsToDelete(new Set(scans.map((scan) => scan.scan_id)))
  }

  const deleteSelectedScans = async () => {
    if (scanIdsToDelete.size === 0) {
      setError('Select at least one scan to delete.')
      return
    }

    setBusy(true)
    setError(null)
    try {
      await Promise.all(Array.from(scanIdsToDelete).map((scanId) => api.deleteScan(scanId)))
      if (selectedScanId && scanIdsToDelete.has(selectedScanId)) {
        setSelectedScanId('')
      }
      setScanIdsToDelete(new Set())
      await refreshScans()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete scans')
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    if (draftHydrated.current) {
      return
    }
    draftHydrated.current = true
    try {
      const raw = window.sessionStorage.getItem(SCAN_DRAFT_STORAGE_KEY)
      if (!raw) {
        return
      }
      const parsed = JSON.parse(raw) as {
        selectedScanId?: string
        scanName?: string
        sitCategory?: (typeof sitCategoryOptions)[number]
        customSitCategory?: string
        preserveCase?: boolean
        forceOcr?: boolean
        scanType?: 'classic_nlp' | 'sentence_transformer'
        userPrincipalName?: string
        exchangeOrganization?: string
      }
      if (parsed.selectedScanId) setSelectedScanId(parsed.selectedScanId)
      if (parsed.scanName) setScanName(parsed.scanName)
      if (parsed.sitCategory && sitCategoryOptions.includes(parsed.sitCategory)) {
        setSitCategory(parsed.sitCategory)
      }
      if (parsed.customSitCategory) setCustomSitCategory(parsed.customSitCategory)
      if (typeof parsed.preserveCase === 'boolean') setPreserveCase(parsed.preserveCase)
      if (typeof parsed.forceOcr === 'boolean') setForceOcr(parsed.forceOcr)
      if (parsed.scanType) setScanType(parsed.scanType)
      if (parsed.userPrincipalName) setUserPrincipalName(parsed.userPrincipalName)
      if (parsed.exchangeOrganization) setExchangeOrganization(parsed.exchangeOrganization)
    } catch {
      // Ignore malformed draft storage.
    }
  }, [sitCategoryOptions])

  useEffect(() => {
    const draft = {
      selectedScanId,
      scanName,
      sitCategory,
      customSitCategory,
      preserveCase,
      forceOcr,
      scanType,
      userPrincipalName,
      exchangeOrganization,
    }
    window.sessionStorage.setItem(SCAN_DRAFT_STORAGE_KEY, JSON.stringify(draft))
    window.localStorage.setItem('sit_builder_active_tab', 'scans')
  }, [
    selectedScanId,
    scanName,
    sitCategory,
    customSitCategory,
    preserveCase,
    forceOcr,
    scanType,
    userPrincipalName,
    exchangeOrganization,
  ])

  useEffect(() => {
    if (scanType === 'sentence_transformer' && forceOcr) {
      setForceOcr(false)
    }
  }, [scanType, forceOcr])

  useEffect(() => {
    const hydrateAuth = async () => {
      const token = await getTokenSilently()
      if (!token) {
        return
      }
      setExchangeToken(token.accessToken)
      const account = getActiveAccount()
      const upn = account?.username ?? token.account?.username ?? ''
      if (upn) {
        setUserPrincipalName((existing) => existing || upn)
      }
    }
    void hydrateAuth()
  }, [])

  useEffect(() => {
    if (!selectedScanId) {
      setScanDetails(null)
      return
    }

    let cancelled = false

    const pollScanDetails = async () => {
      try {
        const details = await api.getScan(selectedScanId)
        if (!cancelled) {
          setScanDetails(details)
          if (justCreatedScanId === details.scan_id && ['COMPLETED', 'FAILED'].includes(details.status)) {
            setJustCreatedScanId(null)
          }
        }
      } catch {
        // Keep last known details during transient polling failures.
      }
    }

    void pollScanDetails()
    const timer = window.setInterval(() => {
      void pollScanDetails()
    }, 2000)

    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [selectedScanId, justCreatedScanId])

  useEffect(() => {
    if (justCreatedScanId) {
      if (selectedScanId !== justCreatedScanId) {
        setSelectedScanId(justCreatedScanId)
      }
      return
    }

    if (selectedScanId || scans.length === 0) {
      return
    }

    const preferred =
      scans.find((scan) => ['PENDING', 'EXTRACTING', 'ANALYZING'].includes(scan.status)) ??
      scans[0]
    setSelectedScanId(preferred.scan_id)
  }, [selectedScanId, scans, justCreatedScanId])

  const authenticateMicrosoft = async () => {
    setBusy(true)
    setError(null)
    setAuthMessage(null)
    try {
      window.localStorage.setItem('sit_builder_active_tab', 'scans')
      const token = await loginAndGetToken()
      if (!token) {
        setAuthMessage('Redirecting to Microsoft sign-in...')
        return
      }
      setExchangeToken(token.accessToken)
      const account = getActiveAccount()
      const upn = account?.username ?? token.account?.username ?? ''
      if (upn) {
        setUserPrincipalName(upn)
      }
      const org = upn.includes('@') ? upn.split('@')[1] : ''
      if (org) {
        setExchangeOrganization(org)
      }
      setAuthMessage(`Authenticated as ${upn || 'Microsoft account'}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Microsoft authentication failed')
    } finally {
      setBusy(false)
    }
  }

  const submitScan = async (event: FormEvent) => {
    event.preventDefault()
    if (files.length === 0) {
      setError('Select at least one file to scan.')
      return
    }
    if (scanType === 'sentence_transformer' && !userPrincipalName.trim()) {
      setError('User principal name is required for SentenceTransformer scans.')
      return
    }
    if (scanType === 'sentence_transformer' && !exchangeToken) {
      setError('Authenticate with Microsoft before running a SentenceTransformer scan.')
      return
    }

    setBusy(true)
    setError(null)
    try {
      const effectiveScanName = scanName.trim() || formatDefaultScanName(files[0].name)
      const effectiveSitCategory = sitCategory === 'Custom' ? customSitCategory.trim() : sitCategory
      if (!effectiveSitCategory) {
        setError('Enter a custom SIT Category or select a predefined category.')
        setBusy(false)
        return
      }
      const created = await api.createScan(files, {
        name: effectiveScanName,
        scanType,
        sitCategory: effectiveSitCategory,
        userPrincipalName: userPrincipalName || undefined,
        exchangeAccessToken: exchangeToken || undefined,
        exchangeOrganization: exchangeOrganization || undefined,
        preserveCase,
        forceOcr: scanType === 'classic_nlp' ? forceOcr : false,
      })
      const newScanId = String(created.scan_id)
      setJustCreatedScanId(newScanId)
      setSelectedScanId(newScanId)
      setLastCandidatesLoadKey('')
      setScanDetails({
        scan_id: newScanId,
        name: effectiveScanName,
        scan_type: scanType,
        status: created.status,
        source_files_count: files.length,
        extracted_text_length: null,
        ocr_confidence_avg: null,
        extraction_duration_sec: null,
        analysis_duration_sec: null,
        created_at: new Date().toISOString(),
        completed_at: null,
        metadata: {
          processing_phase: 'pending',
          processing_progress_pct: 0,
          files_completed: 0,
          files_total: files.length,
        },
      })
      setScanName('')
      setFiles([])
      await refreshScans()
      // Re-apply selection after refresh and fetch details immediately so progress appears at once.
      setSelectedScanId(newScanId)
      try {
        const details = await api.getScan(newScanId)
        setScanDetails(details)
      } catch {
        // Polling effect will retry shortly.
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create scan')
    } finally {
      setBusy(false)
    }
  }

  const loadCandidates = async (scanId: string, silent = false) => {
    if (!scanId) {
      return
    }
    if (!silent) {
      setBusy(true)
    }
    setError(null)
    try {
      const data = await api.getCandidates(scanId)
      setCandidates(data.candidates)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch candidates')
    } finally {
      if (!silent) {
        setBusy(false)
      }
    }
  }

  useEffect(() => {
    if (!selectedScanId) {
      setCandidates([])
      setLastCandidatesLoadKey('')
      return
    }

    const statusKey = scanDetails?.status ?? selectedScan?.status ?? 'UNKNOWN'
    const loadKey = `${selectedScanId}:${statusKey}`
    if (loadKey === lastCandidatesLoadKey) {
      return
    }

    setLastCandidatesLoadKey(loadKey)
    void loadCandidates(selectedScanId, true)
  }, [selectedScanId, selectedScan?.status, scanDetails?.status, lastCandidatesLoadKey])

  return (
    <section className="panel">
      <h2>Scan Workbench</h2>
      <div className="two-col">
        <form className="form" onSubmit={submitScan}>
          <label>
            Scan name
            <input value={scanName} onChange={(e) => setScanName(e.target.value)} placeholder="Q1 Financial Docs" />
          </label>
          <label>
            SIT Category
            <select value={sitCategory} onChange={(e) => setSitCategory(e.target.value as (typeof sitCategoryOptions)[number])}>
              {sitCategoryOptions.map((option) => (
                <option key={option} value={option}>{option}</option>
              ))}
            </select>
          </label>
          {sitCategory === 'Custom' && (
            <label>
              Custom SIT Category
              <input
                value={customSitCategory}
                onChange={(e) => setCustomSitCategory(e.target.value)}
                placeholder="Enter custom category"
              />
            </label>
          )}
          <label className="check-row">
            <input
              type="checkbox"
              checked={preserveCase}
              onChange={(e) => setPreserveCase(e.target.checked)}
            />
            <span>Allow case (do not normalize to lower case)</span>
          </label>
          <label className="check-row">
            <input
              type="checkbox"
              checked={forceOcr}
              onChange={(e) => setForceOcr(e.target.checked)}
              disabled={forceOcrDisabled}
            />
            <span>Force OCR extraction</span>
            <span className="tooltip">
              <button
                type="button"
                className="info-tip"
                aria-label="Force OCR help"
                aria-describedby="force-ocr-tooltip"
              >
                ?
              </button>
              <span id="force-ocr-tooltip" role="tooltip" className="tooltip-content">
                Auto mode applies OCR to images and image-based PDFs. Force OCR requests OCR for
                files that normally use native parsing. Results show whether OCR was used.
              </span>
            </span>
          </label>
          {forceOcrDisabled && (
            <p className="muted">Not available for SentenceTransformer scans. OCR column is shown as N/A.</p>
          )}
          {requiresAuthBeforeFiles ? (
            <p className="muted">
              On mobile with SentenceTransformer, authenticate Microsoft first, then file selection will appear.
            </p>
          ) : (
            <>
              <label>
                Files
                <input
                  type="file"
                  multiple
                  onChange={(e) => {
                    const next = Array.from(e.target.files ?? [])
                    mergeFiles(next)
                    e.currentTarget.value = ''
                  }}
                />
              </label>
              <div
                className={`drop-zone${isDragOver ? ' is-drag-over' : ''}`}
                onDragOver={(event) => {
                  event.preventDefault()
                  setIsDragOver(true)
                }}
                onDragLeave={() => setIsDragOver(false)}
                onDrop={(event) => {
                  event.preventDefault()
                  setIsDragOver(false)
                  void (async () => {
                    const droppedFiles = await extractDroppedFiles(event.dataTransfer)
                    mergeFiles(droppedFiles)
                  })()
                }}
              >
                Drag and drop one or more files here
              </div>
              <p className="muted">{selectedFileNames || 'No files selected.'}</p>
            </>
          )}
          <label>
            Scan type
            <select value={scanType} onChange={(e) => setScanType(e.target.value as 'classic_nlp' | 'sentence_transformer')}>
              <option value="classic_nlp">Classic NLP (Current)</option>
              <option value="sentence_transformer">SentenceTransformer</option>
            </select>
          </label>
          {scanType === 'classic_nlp' ? (
            <p className="muted">
              Uses the built-in NLP pipeline over extracted text. Requirements: no Microsoft auth and no PowerShell dependency.
            </p>
          ) : (
            <p className="muted">
              Uses PowerShell Test-TextExtraction + Python SentenceTransformer keyword scoring. Requirements: Microsoft browser auth,
              `pwsh` installed, ExchangeOnline module available, and Python dependencies installed.
            </p>
          )}
          {scanType === 'sentence_transformer' && (
            <>
              <button type="button" onClick={authenticateMicrosoft} disabled={busy}>
                Authenticate Microsoft (Browser Popup)
              </button>
              {authMessage && <p className="muted">{authMessage}</p>}
              <label>
                User principal name
                <input
                  value={userPrincipalName}
                  onChange={(e) => setUserPrincipalName(e.target.value)}
                  placeholder="name@company.com"
                />
              </label>
              <label>
                Exchange organization (optional)
                <input
                  value={exchangeOrganization}
                  onChange={(e) => setExchangeOrganization(e.target.value)}
                  placeholder="contoso.onmicrosoft.com"
                />
              </label>
              <p className="muted">
                Auth happens in this browser via MSAL popup, then the backend uses the token for non-interactive Exchange connection.
              </p>
            </>
          )}
          <button type="submit" disabled={busy}>Start Scan</button>
        </form>

        <div>
          <div className="toolbar">
            <select value={selectedScanId} onChange={(e) => setSelectedScanId(e.target.value)}>
              <option value="">Select scan</option>
              {selectedScanId && !hasSelectedInList && (
                <option value={selectedScanId}>
                  Current scan ({scanDetails?.status ?? 'PENDING'})
                </option>
              )}
              {scans.map((scan) => (
                <option key={scan.scan_id} value={scan.scan_id}>
                  {scan.name ?? scan.scan_id} ({scan.scan_type} · {scan.status})
                </option>
              ))}
            </select>
            <button type="button" onClick={refreshScans}>Refresh</button>
            <button type="button" onClick={() => void toggleDeleteMode()} disabled={busy}>
              {deleteMode ? 'Close Delete Scan' : 'Delete Scan'}
            </button>
          </div>

          {deleteMode && (
            <div className="checklist">
              <div className="toolbar">
                <button type="button" onClick={toggleSelectAllForDelete} disabled={busy || scans.length === 0}>
                  {allScansSelected ? 'Clear All' : 'Select All'}
                </button>
                <button type="button" onClick={deleteSelectedScans} disabled={busy || scanIdsToDelete.size === 0}>
                  Delete Selected
                </button>
              </div>
              {scans.length === 0 && <p className="muted">No scans available.</p>}
              {scans.map((scan) => (
                <label key={scan.scan_id} className="check-row">
                  <input
                    type="checkbox"
                    checked={scanIdsToDelete.has(scan.scan_id)}
                    onChange={() => toggleScanForDelete(scan.scan_id)}
                    disabled={busy}
                  />
                  <span>{scan.name ?? scan.scan_id}</span>
                  <span className="muted">({scan.scan_type} · {scan.status})</span>
                </label>
              ))}
            </div>
          )}

          {activeScanSummary && (
            <>
              <p className="muted">
                {activeScanSummary.scan_type} · {activeScanSummary.status} · files: {activeScanSummary.source_files_count ?? 0}
              </p>
              {progressPct !== null && (
                <div className="scan-progress">
                  <div className="scan-progress-bar">
                    <div className="scan-progress-fill" style={{ width: `${progressPct}%` }} />
                  </div>
                  <p className="muted">
                    Progress: {progressPct.toFixed(0)}%
                    {progressPhase ? ` · phase: ${progressPhase}` : ''}
                    {filesDone !== null && filesTotal !== null ? ` · files: ${filesDone}/${filesTotal}` : ''}
                  </p>
                  {currentFileName && <p className="muted">Processing file: {currentFileName}</p>}
                </div>
              )}
            </>
          )}

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>File</th>
                  <th>SIT Category</th>
                  <th>Scan Module</th>
                  <th>OCR</th>
                  <th>Type</th>
                  <th>Value</th>
                  <th>Score</th>
                  <th>Freq</th>
                </tr>
              </thead>
              <tbody>
                {groupedCandidates.map((candidate) => (
                  <tr key={candidate.key}>
                    <td>{candidate.fileNames.length > 0 ? candidate.fileNames.join(', ') : '-'}</td>
                    <td>{candidate.sitCategory ?? '-'}</td>
                    <td>{candidate.extractionModules.length > 0 ? candidate.extractionModules.join(', ') : '-'}</td>
                    <td>
                      {ocrColumnNotApplicable
                        ? 'N/A'
                        : candidate.ocrStates.length === 0
                          ? '-'
                          : candidate.ocrStates.length === 1
                            ? candidate.ocrStates[0] ? 'Yes' : 'No'
                            : 'Mixed'}
                    </td>
                    <td>{candidate.candidate_type}</td>
                    <td>{candidate.value}</td>
                    <td>{candidate.score?.toFixed(1) ?? '-'}</td>
                    <td>{candidate.frequency}</td>
                  </tr>
                ))}
                {groupedCandidates.length === 0 && (
                  <tr>
                    <td colSpan={8} className="muted">No candidates loaded.</td>
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

import type { Candidate, RulepackSummary, ScanDetail, ScanSummary, SitSummary, UUID } from '../types/api'

const configuredApiBase = import.meta.env.VITE_API_BASE as string | undefined
const isLocalHost = ['localhost', '127.0.0.1', '::1'].includes(window.location.hostname)
const pointsToLocalhost = !!configuredApiBase && /(localhost|127\.0\.0\.1|\[::1\])/.test(configuredApiBase)
const API_BASE =
  configuredApiBase && !(pointsToLocalhost && !isLocalHost)
    ? configuredApiBase
    : '/v1'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      ...(options?.headers ?? {}),
    },
  })

  if (!response.ok) {
    const message = await response.text()
    throw new Error(message || `Request failed (${response.status})`)
  }

  if (response.status === 204) {
    return {} as T
  }

  return (await response.json()) as T
}

export const api = {
  listScans: () => request<{ scans: ScanSummary[] }>('/scans'),
  getScan: (scanId: UUID) => request<ScanDetail>(`/scans/${scanId}`),
  getCandidates: (scanId: UUID) => request<{ candidates: Candidate[]; total: number; page: number; page_size: number }>(`/scans/${scanId}/candidates`),
  createScan: (
    files: File[],
    options?: {
      name?: string
      scanType?: string
      sitCategory?: string
      userPrincipalName?: string
      exchangeAccessToken?: string
      exchangeOrganization?: string
      preserveCase?: boolean
      forceOcr?: boolean
    },
  ) => {
    const form = new FormData()
    files.forEach((file) => form.append('files', file))
    if (options?.name) {
      form.append('name', options.name)
    }
    if (options?.scanType) {
      form.append('scan_type', options.scanType)
    }
    if (options?.sitCategory) {
      form.append('sit_category', options.sitCategory)
    }
    if (options?.userPrincipalName) {
      form.append('user_principal_name', options.userPrincipalName)
    }
    if (options?.exchangeAccessToken) {
      form.append('exchange_access_token', options.exchangeAccessToken)
    }
    if (options?.exchangeOrganization) {
      form.append('exchange_organization', options.exchangeOrganization)
    }
    if (options?.preserveCase) {
      form.append('preserve_case', 'true')
    }
    if (options?.forceOcr) {
      form.append('force_ocr', 'true')
    }

    return request<{ scan_id: UUID; status: string }>('/scans', {
      method: 'POST',
      body: form,
    })
  },
  deleteScan: (scanId: UUID) =>
    request(`/scans/${scanId}`, {
      method: 'DELETE',
    }),
  listSits: () => request<{ sits: SitSummary[]; total: number }>('/sits'),
  createSit: (payload: { name: string; description?: string; confidence_level: number; tags?: string[] }) =>
    request<SitSummary>('/sits', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  addElement: (sitId: UUID, payload: Record<string, unknown>) =>
    request(`/sits/${sitId}/elements`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  listRulepacks: () => request<{ rulepacks: RulepackSummary[] }>('/rulepacks'),
  createRulepack: (payload: { name: string; description?: string; sit_ids: UUID[] }) =>
    request('/rulepacks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
}

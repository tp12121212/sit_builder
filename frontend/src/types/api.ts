export type UUID = string

export interface ScanSummary {
  scan_id: UUID
  name: string | null
  scan_type: string
  status: string
  source_files_count: number | null
  created_at: string
  completed_at: string | null
}

export interface ScanDetail {
  scan_id: UUID
  name: string | null
  scan_type: string
  status: string
  source_files_count: number | null
  extracted_text_length: number | null
  ocr_confidence_avg: number | null
  extraction_duration_sec: number | null
  analysis_duration_sec: number | null
  created_at: string
  completed_at: string | null
  metadata: Record<string, unknown> | null
}

export interface Candidate {
  candidate_id: UUID
  candidate_type: string
  element_type_hint: string
  value: string
  pattern_template: string | null
  frequency: number
  confidence: number
  score: number | null
  evidence?: Array<{ context: string; position: number; confidence?: number }>
  metadata?: {
    file_name?: string
    stream_name?: string
    sit_category?: string
    extraction_module?: string
    ocr_performed?: boolean
    [key: string]: unknown
  }
}

export interface SitSummary {
  sit_id: UUID
  name: string
  description: string | null
  confidence_level: number
  status: string
  version: number
  tags: string[] | null
  created_at: string
  updated_at: string
}

export interface RulepackSummary {
  rulepack_id: UUID
  name: string
  sit_count: number | null
  created_at: string
}

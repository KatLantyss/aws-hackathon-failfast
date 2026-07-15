/**
 * Metadata shape for the dev-only data-source inspector (<DataSourceTag>).
 * Verdicts here should stay in sync with docs/frontend-backend-integration-status.html —
 * that doc and these in-app tags describe the same audit, just in two places.
 */
export type DataSourceStatus = 'real' | 'hybrid' | 'stub' | 'unreachable'

export interface DataSourceFieldMapping {
  /** What the user sees on screen, e.g. "Speed Loss %" */
  ui: string
  /** Where it actually comes from: a response field path, or a description of the frontend computation */
  source: string
  /** Extra caveat, e.g. "前端寫死 1.8 係數換算，非後端欄位" */
  note?: string
}

export interface DataSourceInfo {
  status: DataSourceStatus
  /** Endpoint(s) actually called to populate this block, e.g. "GET /api/v1/fleet/summary" */
  endpoint?: string | string[]
  /** One-line summary of this block's data provenance */
  description: string
  /** Displayed value → backend field / computation mapping table */
  fields?: DataSourceFieldMapping[]
}

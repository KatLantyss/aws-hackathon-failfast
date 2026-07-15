/**
 * Dev-only "data-source inspector" toggle. Set VITE_DEBUG_DATA_SOURCE=true in
 * .env.local to overlay <DataSourceTag> badges showing which backend endpoint
 * (if any) backs each block, and how displayed values map to response fields.
 * Off by default — zero DOM/visual footprint in normal use and in production.
 */
export const dataSourceDebugEnabled = import.meta.env.VITE_DEBUG_DATA_SOURCE === 'true'

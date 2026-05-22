/**
 * Capa de servicio — actualmente retorna datos mock.
 * Cuando los microservicios estén conectados, reemplazar cada función
 * con la llamada axios correspondiente al endpoint real.
 *
 * TIF:  http://localhost:8001
 * IA:   http://localhost:8002
 */
import {
  LOTES, ANALISIS_POR_LOTE, ALERTAS, JOBS,
  SERVICIOS_HEALTH, CONFIG_VALIDACION, RESUMEN_DASHBOARD,
} from '@/mock/data'

const delay = (ms = 400) => new Promise(r => setTimeout(r, ms))

export const IS_MOCK = true

// ─── Dashboard ───────────────────────────────────────────────────────────────
export async function getDashboardResumen() {
  await delay()
  return { ...RESUMEN_DASHBOARD }
}

// ─── Lotes ───────────────────────────────────────────────────────────────────
export async function getLotes() {
  await delay()
  return [...LOTES]
}

export async function getLote(id) {
  await delay()
  return LOTES.find(l => l.id === Number(id)) || null
}

// ─── Análisis ────────────────────────────────────────────────────────────────
export async function getAnalisisPorLote(lotId) {
  await delay()
  return ANALISIS_POR_LOTE[Number(lotId)] || []
}

export async function solicitarAnalisis(/* payload */) {
  await delay(600)
  return { job_id: 'job_MOCK_' + Date.now(), status: 'processing' }
}

// ─── Alertas ─────────────────────────────────────────────────────────────────
export async function getAlertas() {
  await delay()
  return [...ALERTAS]
}

// ─── Jobs ────────────────────────────────────────────────────────────────────
export async function getJobs() {
  await delay()
  return [...JOBS]
}

export async function getJobStatus(jobId) {
  await delay()
  return JOBS.find(j => j.job_id === jobId) || null
}

// ─── Health / Configuración ──────────────────────────────────────────────────
export async function getHealth() {
  await delay()
  return { ...SERVICIOS_HEALTH }
}

export async function getConfigValidacion() {
  await delay()
  return { ...CONFIG_VALIDACION }
}

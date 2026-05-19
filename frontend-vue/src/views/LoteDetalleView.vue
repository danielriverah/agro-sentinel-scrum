<template>
  <div>
    <dev-banner servicio="GET /lots/{id}/results → TIF :8001 · GET /lots/{id}/history → IA :8002" sprint="7 y 11" />

    <loading-spinner v-if="loading" />
    <template v-else-if="lote">

      <!-- Header del lote -->
      <div class="as-page-header flex-wrap">
        <div>
          <div class="d-flex align-items-center gap-2 mb-1">
            <router-link to="/lotes" class="text-muted small">
              <i class="fas fa-arrow-left mr-1"></i>Lotes
            </router-link>
            <span class="text-muted small">/</span>
            <span class="small">{{ lote.nombre }}</span>
          </div>
          <h1>{{ lote.nombre }}</h1>
          <span class="text-muted small text-capitalize">{{ lote.cultivo }} · {{ lote.etapa }} · {{ lote.area_ha }} ha · {{ lote.municipio }}, {{ lote.estado }}</span>
        </div>
        <div class="d-flex align-items-center gap-2 mt-2 mt-md-0">
          <risk-badge :risk="lote.riesgo" />
          <button class="as-btn as-btn--primary" disabled title="Disponible en Sprint 7">
            <i class="fas fa-satellite-dish mr-1"></i>Nuevo análisis
          </button>
        </div>
      </div>

      <!-- Último análisis -->
      <template v-if="analisisReciente">
        <div class="row">
          <!-- Índices espectrales -->
          <div class="col-md-5 mb-4">
            <div class="as-card h-100">
              <div class="as-card__title">Índices espectrales — {{ analisisReciente.fecha }}</div>
              <index-gauge
                v-for="(data, name) in analisisReciente.indices"
                :key="name"
                :name="name.toUpperCase()"
                :data="data"
              />
              <div class="mt-3 pt-3 border-top d-flex gap-3">
                <div class="text-center">
                  <div class="small text-muted">Nubosidad</div>
                  <div class="font-weight-bold">{{ analisisReciente.nubosidad_pct }}%</div>
                </div>
                <div class="text-center">
                  <div class="small text-muted">Píxeles válidos</div>
                  <div class="font-weight-bold">{{ analisisReciente.pixeles_validos_pct }}%</div>
                </div>
                <div class="text-center">
                  <div class="small text-muted">Confianza</div>
                  <span :class="['badge', confianzaClass(analisisReciente.confianza)]">
                    {{ analisisReciente.confianza }}
                  </span>
                </div>
              </div>
            </div>
          </div>

          <!-- Diagnóstico IA -->
          <div class="col-md-7 mb-4">
            <div class="as-card h-100">
              <div class="d-flex justify-content-between align-items-start mb-3">
                <div class="as-card__title mb-0">Diagnóstico IA</div>
                <risk-badge :risk="analisisReciente.riesgo" />
              </div>

              <div class="diagnostico-resumen mb-3">
                <i class="fas fa-robot mr-2 text-muted"></i>
                <em>{{ analisisReciente.resumen }}</em>
              </div>

              <!-- Alertas -->
              <template v-if="analisisReciente.alertas && analisisReciente.alertas.length">
                <div class="as-card__title">Alertas detectadas</div>
                <ul class="alert-list mb-3">
                  <li v-for="(a, i) in analisisReciente.alertas" :key="i">
                    <i class="fas fa-exclamation-triangle mr-2 text-warning"></i>{{ a }}
                  </li>
                </ul>
              </template>

              <!-- Causas -->
              <div class="as-card__title">Causas probables</div>
              <ul class="causas-list mb-3">
                <li v-for="(c, i) in analisisReciente.causas" :key="i">
                  <i class="fas fa-circle mr-2" style="font-size:.5rem;color:#9ca3af;vertical-align:middle"></i>{{ c }}
                </li>
              </ul>

              <!-- Recomendaciones -->
              <div class="as-card__title">Recomendaciones</div>
              <ol class="recomendaciones-list">
                <li v-for="(r, i) in analisisReciente.recomendaciones" :key="i">{{ r }}</li>
              </ol>

              <div class="mt-3 pt-3 border-top text-muted" style="font-size:.75rem">
                <i class="fas fa-robot mr-1"></i>Generado por Anthropic claude-sonnet-4-5 ·
                job_id: <code>{{ analisisReciente.job_id }}</code>
              </div>
            </div>
          </div>

          <!-- PNG mapa mock -->
          <div class="col-md-6 mb-4">
            <div class="as-card">
              <div class="as-card__title">Visualización NDVI</div>
              <div class="map-placeholder">
                <i class="fas fa-image fa-3x text-muted mb-2"></i>
                <p class="text-muted small mb-1">Mapa de índice NDVI</p>
                <p class="text-muted" style="font-size:.73rem">Disponible en Sprint 6 (generación de PNGs)</p>
                <span class="badge badge-secondary">PNG · S3</span>
              </div>
            </div>
          </div>

          <!-- Historial de análisis -->
          <div class="col-md-6 mb-4">
            <div class="as-card">
              <div class="as-card__title">Historial de análisis</div>
              <div v-if="analisis.length === 0" class="text-muted text-center py-3">
                Sin análisis previos
              </div>
              <table v-else class="as-table">
                <thead>
                  <tr><th>Fecha</th><th>Riesgo</th><th>Confianza</th><th>Job ID</th></tr>
                </thead>
                <tbody>
                  <tr v-for="a in analisis" :key="a.job_id" :class="{ 'table-active': a === analisisReciente }">
                    <td>{{ a.fecha }}</td>
                    <td><risk-badge :risk="a.riesgo" /></td>
                    <td>
                      <span :class="['badge', confianzaClass(a.confianza)]">{{ a.confianza }}</span>
                    </td>
                    <td><code style="font-size:.72rem">{{ a.job_id.slice(0, 18) }}…</code></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </template>

      <div v-else class="as-card text-center py-5 text-muted">
        <i class="fas fa-satellite fa-3x mb-3"></i>
        <p>Este lote no tiene análisis registrados todavía.</p>
        <button class="as-btn as-btn--primary mt-2" disabled>
          <i class="fas fa-satellite-dish mr-1"></i>Solicitar primer análisis
        </button>
      </div>

    </template>

    <div v-else class="as-card text-center py-5 text-muted">
      <i class="fas fa-map-marked-alt fa-3x mb-3"></i>
      <p>Lote no encontrado.</p>
      <router-link to="/lotes" class="as-btn as-btn--outline mt-2">Volver a lotes</router-link>
    </div>
  </div>
</template>

<script>
import DevBanner from '@/components/DevBanner.vue'
import RiskBadge from '@/components/RiskBadge.vue'
import IndexGauge from '@/components/IndexGauge.vue'
import LoadingSpinner from '@/components/LoadingSpinner.vue'
import { getLote, getAnalisisPorLote } from '@/services/api'

export default {
  name: 'LoteDetalleView',
  components: { DevBanner, RiskBadge, IndexGauge, LoadingSpinner },
  props: ['id'],
  data() {
    return { loading: true, lote: null, analisis: [] }
  },
  computed: {
    analisisReciente() { return this.analisis[0] || null },
  },
  methods: {
    confianzaClass(c) {
      return { high: 'badge-success', medium: 'badge-info', low: 'badge-secondary' }[c] || 'badge-secondary'
    },
  },
  async created() {
    const [lote, analisis] = await Promise.all([
      getLote(this.id),
      getAnalisisPorLote(this.id),
    ])
    this.lote    = lote
    this.analisis = analisis
    this.loading  = false
  },
}
</script>

<style scoped>
.gap-2 { gap: 8px; }
.gap-3 { gap: 14px; }
.diagnostico-resumen { font-size: .9rem; color: #374151; line-height: 1.5; }
.alert-list, .causas-list, .recomendaciones-list {
  padding-left: 0; list-style: none; font-size: .87rem; color: #374151;
}
.alert-list li, .causas-list li, .recomendaciones-list li { padding: 4px 0; }
.recomendaciones-list { list-style: decimal; padding-left: 1.3rem; }
.map-placeholder {
  background: #f9fafb; border: 2px dashed #e5e7eb;
  border-radius: 8px; padding: 40px;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  min-height: 200px;
}
</style>

<template>
  <div>
    <dev-banner servicio="API TIF :8001 e IA :8002" sprint="3" />

    <div class="as-page-header">
      <div>
        <h1>Dashboard</h1>
        <small>Resumen general del sistema AgroSentinel</small>
      </div>
      <span class="text-muted small">
        <i class="fas fa-sync-alt mr-1"></i>Última actualización: {{ ahora }}
      </span>
    </div>

    <!-- Stats row -->
    <loading-spinner v-if="loading" />
    <template v-else>
      <div class="row mb-4">
        <div class="col-6 col-md-3 mb-3">
          <div class="as-stat">
            <div class="as-stat__icon" style="background:#d8f3dc">
              <i class="fas fa-map-marked-alt" style="color:#2d6a4f"></i>
            </div>
            <div>
              <div class="as-stat__value">{{ resumen.total_lotes }}</div>
              <div class="as-stat__label">Lotes registrados</div>
            </div>
          </div>
        </div>
        <div class="col-6 col-md-3 mb-3">
          <div class="as-stat">
            <div class="as-stat__icon" style="background:#fee2e2">
              <i class="fas fa-bell" style="color:#dc2626"></i>
            </div>
            <div>
              <div class="as-stat__value" style="color:#dc2626">{{ resumen.alertas_activas }}</div>
              <div class="as-stat__label">Alertas activas</div>
            </div>
          </div>
        </div>
        <div class="col-6 col-md-3 mb-3">
          <div class="as-stat">
            <div class="as-stat__icon" style="background:#dbeafe">
              <i class="fas fa-satellite-dish" style="color:#2563eb"></i>
            </div>
            <div>
              <div class="as-stat__value">{{ resumen.analisis_mes }}</div>
              <div class="as-stat__label">Análisis este mes</div>
            </div>
          </div>
        </div>
        <div class="col-6 col-md-3 mb-3">
          <div class="as-stat">
            <div class="as-stat__icon" style="background:#fef3c7">
              <i class="fas fa-exclamation-triangle" style="color:#d97706"></i>
            </div>
            <div>
              <div class="as-stat__value" style="color:#d97706">{{ resumen.lotes_riesgo_high + resumen.lotes_riesgo_medium_high }}</div>
              <div class="as-stat__label">Lotes con riesgo ≥ Medio-Alto</div>
            </div>
          </div>
        </div>
      </div>

      <div class="row">
        <!-- Distribución de riesgo -->
        <div class="col-md-5 mb-4">
          <div class="as-card h-100">
            <div class="as-card__title">Distribución de riesgo</div>
            <div class="risk-bars">
              <div v-for="item in riskDistribution" :key="item.key" class="risk-bar-row">
                <span class="risk-bar-label">{{ item.label }}</span>
                <div class="risk-bar-track">
                  <div
                    class="risk-bar-fill"
                    :style="{ width: barWidth(item.count) + '%', background: item.color }"
                  ></div>
                </div>
                <span class="risk-bar-count">{{ item.count }} lote{{ item.count !== 1 ? 's' : '' }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Alertas recientes -->
        <div class="col-md-7 mb-4">
          <div class="as-card h-100">
            <div class="d-flex justify-content-between align-items-center mb-3">
              <div class="as-card__title mb-0">Alertas activas</div>
              <router-link to="/alertas" class="as-btn as-btn--outline" style="padding:4px 12px;font-size:.78rem">
                Ver todas <i class="fas fa-arrow-right ml-1"></i>
              </router-link>
            </div>
            <div v-if="alertas.length === 0" class="text-muted text-center py-4">
              <i class="fas fa-check-circle fa-2x text-success"></i>
              <p class="mt-2">Sin alertas activas</p>
            </div>
            <table v-else class="as-table">
              <thead>
                <tr>
                  <th>Lote</th>
                  <th>Cultivo</th>
                  <th>Riesgo</th>
                  <th>Fecha</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="a in alertas" :key="a.lot_id">
                  <td>
                    <router-link :to="'/lotes/' + a.lot_id">{{ a.lot_nombre }}</router-link>
                  </td>
                  <td class="text-capitalize">{{ a.cultivo }}</td>
                  <td><risk-badge :risk="a.risk_level" /></td>
                  <td class="text-muted">{{ a.fecha_analisis }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- Lotes con análisis recientes -->
        <div class="col-12 mb-4">
          <div class="as-card">
            <div class="d-flex justify-content-between align-items-center mb-3">
              <div class="as-card__title mb-0">Lotes — último análisis</div>
              <router-link to="/lotes" class="as-btn as-btn--outline" style="padding:4px 12px;font-size:.78rem">
                Todos los lotes <i class="fas fa-arrow-right ml-1"></i>
              </router-link>
            </div>
            <table class="as-table">
              <thead>
                <tr>
                  <th>Nombre</th>
                  <th>Cultivo</th>
                  <th>Área</th>
                  <th>Municipio</th>
                  <th>Último análisis</th>
                  <th>Riesgo</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="l in lotes" :key="l.id">
                  <td><router-link :to="'/lotes/' + l.id">{{ l.nombre }}</router-link></td>
                  <td class="text-capitalize">{{ l.cultivo }}</td>
                  <td>{{ l.area_ha }} ha</td>
                  <td>{{ l.municipio }}</td>
                  <td class="text-muted">{{ l.ultimo_analisis }}</td>
                  <td><risk-badge :risk="l.riesgo" /></td>
                  <td>
                    <router-link :to="'/lotes/' + l.id" class="btn btn-sm btn-outline-secondary">
                      <i class="fas fa-eye"></i>
                    </router-link>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script>
import DevBanner from '@/components/DevBanner.vue'
import RiskBadge from '@/components/RiskBadge.vue'
import LoadingSpinner from '@/components/LoadingSpinner.vue'
import { getDashboardResumen, getAlertas, getLotes } from '@/services/api'

export default {
  name: 'DashboardView',
  components: { DevBanner, RiskBadge, LoadingSpinner },
  data() {
    return {
      loading: true,
      resumen: {},
      alertas: [],
      lotes: [],
      ahora: new Date().toLocaleString('es-MX', { dateStyle: 'medium', timeStyle: 'short' }),
    }
  },
  computed: {
    riskDistribution() {
      return [
        { key: 'high',        label: 'Alto',       count: this.resumen.lotes_riesgo_high        || 0, color: '#dc2626' },
        { key: 'medium_high', label: 'Medio-Alto',  count: this.resumen.lotes_riesgo_medium_high || 0, color: '#d97706' },
        { key: 'medium',      label: 'Medio',       count: this.resumen.lotes_riesgo_medium      || 0, color: '#2563eb' },
        { key: 'low',         label: 'Bajo',        count: this.resumen.lotes_riesgo_low         || 0, color: '#16a34a' },
      ]
    },
  },
  methods: {
    barWidth(count) {
      const max = Math.max(...this.riskDistribution.map(r => r.count), 1)
      return Math.round((count / max) * 100)
    },
  },
  async created() {
    const [resumen, alertas, lotes] = await Promise.all([
      getDashboardResumen(), getAlertas(), getLotes(),
    ])
    this.resumen = resumen
    this.alertas = alertas
    this.lotes   = lotes
    this.loading = false
  },
}
</script>

<style scoped>
.risk-bars { display: flex; flex-direction: column; gap: 14px; }
.risk-bar-row { display: flex; align-items: center; gap: 10px; }
.risk-bar-label { width: 88px; font-size: .82rem; color: #374151; flex-shrink: 0; }
.risk-bar-track { flex: 1; height: 10px; background: #f3f4f6; border-radius: 999px; overflow: hidden; }
.risk-bar-fill  { height: 100%; border-radius: 999px; transition: width .4s ease; }
.risk-bar-count { width: 60px; text-align: right; font-size: .82rem; color: #6b7280; flex-shrink: 0; }
</style>

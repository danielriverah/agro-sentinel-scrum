<template>
  <div>
    <dev-banner servicio="GET /lots → TIF :8001" sprint="7" />

    <div class="as-page-header">
      <div>
        <h1>Lotes Agrícolas</h1>
        <small>{{ lotes.length }} lotes registrados</small>
      </div>
      <button class="as-btn as-btn--primary" @click="nuevaAnalisis = true" disabled title="Disponible en Sprint 7">
        <i class="fas fa-plus"></i> Nuevo análisis
      </button>
    </div>

    <!-- Filtros -->
    <div class="as-card mb-3" style="padding:14px 20px;">
      <div class="row align-items-center" style="gap:0;">
        <div class="col-md-4 mb-2 mb-md-0">
          <div class="input-group input-group-sm">
            <div class="input-group-prepend">
              <span class="input-group-text"><i class="fas fa-search"></i></span>
            </div>
            <input v-model="filtro" type="text" class="form-control" placeholder="Buscar lote o cultivo..." />
          </div>
        </div>
        <div class="col-md-3 mb-2 mb-md-0">
          <select v-model="filtroRiesgo" class="form-control form-control-sm">
            <option value="">Todos los riesgos</option>
            <option value="high">Alto</option>
            <option value="medium_high">Medio-Alto</option>
            <option value="medium">Medio</option>
            <option value="low">Bajo</option>
          </select>
        </div>
        <div class="col-md-3">
          <select v-model="filtroCultivo" class="form-control form-control-sm">
            <option value="">Todos los cultivos</option>
            <option v-for="c in cultivos" :key="c" :value="c" class="text-capitalize">{{ c }}</option>
          </select>
        </div>
      </div>
    </div>

    <loading-spinner v-if="loading" />
    <div v-else class="as-card p-0">
      <table class="as-table">
        <thead>
          <tr>
            <th>Nombre</th>
            <th>Cultivo</th>
            <th>Etapa fenológica</th>
            <th>Área</th>
            <th>Municipio</th>
            <th>Último análisis</th>
            <th>Riesgo</th>
            <th style="width:80px"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="lotesFiltrados.length === 0">
            <td colspan="8" class="text-center text-muted py-4">
              <i class="fas fa-search mr-2"></i>Sin resultados para los filtros aplicados
            </td>
          </tr>
          <tr v-for="l in lotesFiltrados" :key="l.id">
            <td>
              <div class="d-flex align-items-center gap-2">
                <span class="lot-dot" :style="{ background: riskColor(l.riesgo) }"></span>
                <router-link :to="'/lotes/' + l.id" class="font-weight-semibold">{{ l.nombre }}</router-link>
              </div>
            </td>
            <td class="text-capitalize">{{ l.cultivo }}</td>
            <td class="text-muted" style="font-size:.83rem">{{ l.etapa }}</td>
            <td>{{ l.area_ha }} ha</td>
            <td class="text-muted">{{ l.municipio }}, {{ l.estado }}</td>
            <td class="text-muted">{{ l.ultimo_analisis }}</td>
            <td><risk-badge :risk="l.riesgo" /></td>
            <td class="text-center">
              <router-link :to="'/lotes/' + l.id" class="as-btn as-btn--outline" style="padding:4px 10px;font-size:.78rem">
                <i class="fas fa-chart-line mr-1"></i>Ver
              </router-link>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script>
import DevBanner from '@/components/DevBanner.vue'
import RiskBadge from '@/components/RiskBadge.vue'
import LoadingSpinner from '@/components/LoadingSpinner.vue'
import { getLotes } from '@/services/api'

const RISK_COLORS = { high:'#dc2626', medium_high:'#d97706', medium:'#2563eb', low:'#16a34a' }

export default {
  name: 'LotesView',
  components: { DevBanner, RiskBadge, LoadingSpinner },
  data() {
    return { loading: true, lotes: [], filtro: '', filtroRiesgo: '', filtroCultivo: '' }
  },
  computed: {
    cultivos() {
      return [...new Set(this.lotes.map(l => l.cultivo))].sort()
    },
    lotesFiltrados() {
      return this.lotes.filter(l => {
        const q = this.filtro.toLowerCase()
        const matchQ = !q || l.nombre.toLowerCase().includes(q) || l.cultivo.toLowerCase().includes(q)
        const matchR = !this.filtroRiesgo || l.riesgo === this.filtroRiesgo
        const matchC = !this.filtroCultivo || l.cultivo === this.filtroCultivo
        return matchQ && matchR && matchC
      })
    },
  },
  methods: {
    riskColor(r) { return RISK_COLORS[r] || '#9ca3af' },
  },
  async created() {
    this.lotes   = await getLotes()
    this.loading = false
  },
}
</script>

<style scoped>
.lot-dot { width:10px;height:10px;border-radius:50%;display:inline-block;margin-right:8px;flex-shrink:0; }
.gap-2 { gap: 8px; }
.font-weight-semibold { font-weight: 600; }
</style>

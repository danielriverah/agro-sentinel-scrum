<template>
  <div>
    <dev-banner servicio="GET /alerts → IA :8002" sprint="11" />

    <div class="as-page-header">
      <div>
        <h1>Alertas Activas</h1>
        <small>Lotes con nivel de riesgo Medio-Alto o Alto en el último análisis</small>
      </div>
      <span class="badge badge-danger px-3 py-2" style="font-size:.9rem">
        {{ alertas.length }} alerta{{ alertas.length !== 1 ? 's' : '' }} activa{{ alertas.length !== 1 ? 's' : '' }}
      </span>
    </div>

    <loading-spinner v-if="loading" />

    <div v-else-if="alertas.length === 0" class="as-card text-center py-5">
      <i class="fas fa-check-circle fa-3x text-success mb-3"></i>
      <h5 class="text-muted">Sin alertas activas</h5>
      <p class="text-muted small">Todos los lotes presentan riesgo Bajo o Medio.</p>
    </div>

    <template v-else>
      <!-- Cards de alerta por lote -->
      <div v-for="a in alertas" :key="a.lot_id" :class="['alerta-card', 'alerta-card--' + a.risk_level]">
        <div class="alerta-card__header">
          <div>
            <router-link :to="'/lotes/' + a.lot_id" class="alerta-card__title">
              {{ a.lot_nombre }}
            </router-link>
            <span class="alerta-card__meta text-capitalize">{{ a.cultivo }} · {{ a.area_ha }} ha · {{ a.municipio }}</span>
          </div>
          <div class="d-flex align-items-center gap-2">
            <risk-badge :risk="a.risk_level" />
            <span class="text-muted small">{{ a.fecha_analisis }}</span>
          </div>
        </div>

        <div v-if="a.alertas && a.alertas.length" class="alerta-card__body">
          <div class="alerta-card__section-title">Alertas detectadas por IA</div>
          <div v-for="(item, i) in a.alertas" :key="i" class="alerta-item">
            <i class="fas fa-exclamation-circle mr-2"></i>{{ item }}
          </div>
        </div>

        <div class="alerta-card__footer">
          <router-link :to="'/lotes/' + a.lot_id" class="as-btn as-btn--outline" style="font-size:.8rem;padding:5px 12px">
            <i class="fas fa-chart-line mr-1"></i>Ver análisis completo
          </router-link>
        </div>
      </div>
    </template>
  </div>
</template>

<script>
import DevBanner from '@/components/DevBanner.vue'
import RiskBadge from '@/components/RiskBadge.vue'
import LoadingSpinner from '@/components/LoadingSpinner.vue'
import { getAlertas } from '@/services/api'

export default {
  name: 'AlertasView',
  components: { DevBanner, RiskBadge, LoadingSpinner },
  data() { return { loading: true, alertas: [] } },
  async created() {
    this.alertas = await getAlertas()
    this.loading = false
  },
}
</script>

<style scoped>
.gap-2 { gap: 8px; }
.alerta-card {
  background: #fff; border-radius: 8px;
  box-shadow: 0 1px 4px rgba(0,0,0,.08);
  margin-bottom: 16px;
  border-left: 5px solid #9ca3af;
  overflow: hidden;
}
.alerta-card--high        { border-left-color: #dc2626; }
.alerta-card--medium_high { border-left-color: #d97706; }
.alerta-card__header {
  display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap;
  padding: 16px 20px 12px;
  border-bottom: 1px solid #f3f4f6;
}
.alerta-card__title {
  font-size: 1.05rem; font-weight: 700; color: #1c2b20; display: block;
}
.alerta-card__title:hover { color: #2d6a4f; text-decoration: underline; }
.alerta-card__meta { font-size: .8rem; color: #6b7280; margin-top: 2px; display: block; }
.alerta-card__body { padding: 14px 20px; background: #fffbf2; }
.alerta-card__section-title {
  font-size: .72rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: .05em; color: #92400e; margin-bottom: 8px;
}
.alerta-item { font-size: .88rem; color: #78350f; padding: 3px 0; }
.alerta-card__footer { padding: 12px 20px; background: #f9fafb; }
</style>

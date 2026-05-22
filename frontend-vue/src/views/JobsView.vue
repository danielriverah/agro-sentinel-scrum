<template>
  <div>
    <dev-banner servicio="GET /jobs/{id}/status → TIF :8001" sprint="7" />

    <div class="as-page-header">
      <div>
        <h1>Trabajos (Jobs)</h1>
        <small>Historial de análisis solicitados y su estado</small>
      </div>
      <button class="as-btn as-btn--outline" @click="recargar">
        <i class="fas fa-sync-alt mr-1"></i>Actualizar
      </button>
    </div>

    <loading-spinner v-if="loading" />
    <div v-else class="as-card p-0">
      <table class="as-table">
        <thead>
          <tr>
            <th>Job ID</th>
            <th>Lote</th>
            <th>Estado</th>
            <th>Iniciado</th>
            <th>Duración</th>
            <th>Detalle</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="j in jobs" :key="j.job_id">
            <td><code style="font-size:.75rem">{{ j.job_id }}</code></td>
            <td>
              <router-link :to="'/lotes/' + j.lot_id">{{ j.lot_nombre }}</router-link>
            </td>
            <td>
              <span :class="['badge', statusClass(j.status)]">
                <i :class="['mr-1', statusIcon(j.status)]"></i>{{ statusLabel(j.status) }}
              </span>
            </td>
            <td class="text-muted small">{{ formatDate(j.created_at) }}</td>
            <td class="text-muted small">
              <span v-if="j.processing_seconds">{{ j.processing_seconds }}s</span>
              <span v-else-if="j.status === 'processing'" class="text-warning">
                <i class="fas fa-spinner fa-spin mr-1"></i>en curso
              </span>
              <span v-else>—</span>
            </td>
            <td>
              <span v-if="j.error_code" class="text-danger" style="font-size:.8rem">
                <i class="fas fa-exclamation-circle mr-1"></i>{{ j.error_code }}
              </span>
              <span v-else-if="j.status === 'completed'" class="text-success small">
                <i class="fas fa-check mr-1"></i>OK
              </span>
              <span v-else>—</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Leyenda de estados -->
    <div class="mt-3 d-flex flex-wrap gap-3">
      <span v-for="s in estados" :key="s.key" :class="['badge', s.cls, 'px-2 py-1']" style="font-size:.78rem">
        <i :class="['mr-1', s.icon]"></i>{{ s.label }}
      </span>
      <small class="text-muted ml-2 align-self-center">Estados posibles de un análisis</small>
    </div>
  </div>
</template>

<script>
import DevBanner from '@/components/DevBanner.vue'
import LoadingSpinner from '@/components/LoadingSpinner.vue'
import { getJobs } from '@/services/api'

const STATUS = {
  pending:    { cls: 'badge-secondary', icon: 'fas fa-clock',         label: 'Pendiente' },
  processing: { cls: 'badge-info',      icon: 'fas fa-spinner fa-spin', label: 'Procesando' },
  completed:  { cls: 'badge-success',   icon: 'fas fa-check-circle',  label: 'Completado' },
  failed:     { cls: 'badge-danger',    icon: 'fas fa-times-circle',  label: 'Fallido' },
}

export default {
  name: 'JobsView',
  components: { DevBanner, LoadingSpinner },
  data() { return { loading: true, jobs: [] } },
  computed: {
    estados() {
      return Object.entries(STATUS).map(([key, v]) => ({ key, ...v }))
    },
  },
  methods: {
    statusClass(s)  { return (STATUS[s] || STATUS.pending).cls },
    statusIcon(s)   { return (STATUS[s] || STATUS.pending).icon },
    statusLabel(s)  { return (STATUS[s] || STATUS.pending).label },
    formatDate(iso) {
      return iso ? new Date(iso).toLocaleString('es-MX', { dateStyle: 'short', timeStyle: 'short' }) : '—'
    },
    async recargar() {
      this.loading = true
      this.jobs = await getJobs()
      this.loading = false
    },
  },
  async created() {
    this.jobs    = await getJobs()
    this.loading = false
  },
}
</script>

<style scoped>
.gap-3 { gap: 10px; }
</style>

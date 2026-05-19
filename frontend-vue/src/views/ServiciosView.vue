<template>
  <div>
    <dev-banner servicio="GET /health → TIF :8001 y IA :8002" sprint="2 (health) · 3 (config)" />

    <div class="as-page-header">
      <div>
        <h1>Estado de Servicios</h1>
        <small>Microservicios TIF e IA en tiempo real</small>
      </div>
      <button class="as-btn as-btn--outline" @click="recargar">
        <i class="fas fa-sync-alt mr-1"></i>Actualizar
      </button>
    </div>

    <loading-spinner v-if="loading" />
    <template v-else>
      <div class="row">
        <!-- TIF -->
        <div class="col-md-6 mb-4">
          <div class="as-card">
            <div class="d-flex justify-content-between align-items-center mb-3">
              <div>
                <div class="as-card__title mb-1">Microservicio TIF</div>
                <code class="text-muted" style="font-size:.8rem">localhost:8001</code>
              </div>
              <service-pill :status="health.tif.status" :label="health.tif.status === 'ok' ? 'Operativo' : 'Degradado'" />
            </div>

            <div class="service-info-grid mb-3">
              <div class="service-info-item">
                <span class="service-info-label">Versión</span>
                <span>{{ health.tif.version }}</span>
              </div>
              <div class="service-info-item">
                <span class="service-info-label">Uptime</span>
                <span>{{ formatUptime(health.tif.uptime_seconds) }}</span>
              </div>
              <div class="service-info-item">
                <span class="service-info-label">Config cargada</span>
                <span :class="health.tif.config.loaded ? 'text-success' : 'text-danger'">
                  <i :class="health.tif.config.loaded ? 'fas fa-check' : 'fas fa-times'"></i>
                  {{ health.tif.config.loaded ? 'Sí' : 'No' }}
                </span>
              </div>
              <div class="service-info-item">
                <span class="service-info-label">Config válida</span>
                <span :class="health.tif.config.valid ? 'text-success' : 'text-warning'">
                  <i :class="health.tif.config.valid ? 'fas fa-check' : 'fas fa-exclamation-triangle'"></i>
                  {{ health.tif.config.valid ? 'Sí' : 'Pendiente (Sprint 3)' }}
                </span>
              </div>
            </div>

            <div class="service-endpoints">
              <div class="as-card__title">Endpoints disponibles</div>
              <div v-for="ep in endpointsTIF" :key="ep.path" class="endpoint-row">
                <span :class="['method-badge', 'method-badge--' + ep.method.toLowerCase()]">{{ ep.method }}</span>
                <code class="endpoint-path">{{ ep.path }}</code>
                <span :class="['badge ml-auto', ep.ready ? 'badge-success' : 'badge-secondary']">
                  {{ ep.ready ? 'Listo' : 'Sprint ' + ep.sprint }}
                </span>
              </div>
            </div>
          </div>
        </div>

        <!-- IA -->
        <div class="col-md-6 mb-4">
          <div class="as-card">
            <div class="d-flex justify-content-between align-items-center mb-3">
              <div>
                <div class="as-card__title mb-1">Microservicio IA</div>
                <code class="text-muted" style="font-size:.8rem">localhost:8002</code>
              </div>
              <service-pill :status="health.ia.status" :label="health.ia.status === 'ok' ? 'Operativo' : 'Degradado'" />
            </div>

            <div class="service-info-grid mb-3">
              <div class="service-info-item">
                <span class="service-info-label">Versión</span>
                <span>{{ health.ia.version }}</span>
              </div>
              <div class="service-info-item">
                <span class="service-info-label">Uptime</span>
                <span>{{ formatUptime(health.ia.uptime_seconds) }}</span>
              </div>
              <div class="service-info-item">
                <span class="service-info-label">Proveedor IA</span>
                <span class="text-muted">{{ health.ia.ai_provider }}</span>
              </div>
              <div class="service-info-item">
                <span class="service-info-label">Config válida</span>
                <span :class="health.ia.config.valid ? 'text-success' : 'text-warning'">
                  <i :class="health.ia.config.valid ? 'fas fa-check' : 'fas fa-exclamation-triangle'"></i>
                  {{ health.ia.config.valid ? 'Sí' : 'Pendiente (Sprint 8)' }}
                </span>
              </div>
            </div>

            <div class="service-endpoints">
              <div class="as-card__title">Endpoints disponibles</div>
              <div v-for="ep in endpointsIA" :key="ep.path" class="endpoint-row">
                <span :class="['method-badge', 'method-badge--' + ep.method.toLowerCase()]">{{ ep.method }}</span>
                <code class="endpoint-path">{{ ep.path }}</code>
                <span :class="['badge ml-auto', ep.ready ? 'badge-success' : 'badge-secondary']">
                  {{ ep.ready ? 'Listo' : 'Sprint ' + ep.sprint }}
                </span>
              </div>
            </div>
          </div>
        </div>

        <!-- Infraestructura -->
        <div class="col-12">
          <div class="as-card">
            <div class="as-card__title">Infraestructura</div>
            <div class="row">
              <div class="col-md-4 mb-3">
                <div class="infra-item">
                  <div class="infra-item__icon" style="background:#fef3c7">
                    <i class="fas fa-database" style="color:#d97706"></i>
                  </div>
                  <div>
                    <div class="infra-item__name">DynamoDB Local</div>
                    <div class="infra-item__detail">localhost:8005 · En memoria</div>
                    <service-pill status="ok" label="Activo (dev)" />
                  </div>
                </div>
              </div>
              <div class="col-md-4 mb-3">
                <div class="infra-item">
                  <div class="infra-item__icon" style="background:#dbeafe">
                    <i class="fas fa-cloud" style="color:#2563eb"></i>
                  </div>
                  <div>
                    <div class="infra-item__name">AWS S3</div>
                    <div class="infra-item__detail">Bucket: agro-sentinel-dev</div>
                    <service-pill status="unknown" label="Pendiente (Sprint 1)" />
                  </div>
                </div>
              </div>
              <div class="col-md-4 mb-3">
                <div class="infra-item">
                  <div class="infra-item__icon" style="background:#f3e8ff">
                    <i class="fas fa-robot" style="color:#7c3aed"></i>
                  </div>
                  <div>
                    <div class="infra-item__name">Anthropic API</div>
                    <div class="infra-item__detail">claude-sonnet-4-5</div>
                    <service-pill status="unknown" label="Pendiente (Sprint 10)" />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script>
import DevBanner from '@/components/DevBanner.vue'
import ServicePill from '@/components/ServicePill.vue'
import LoadingSpinner from '@/components/LoadingSpinner.vue'
import { getHealth } from '@/services/api'

export default {
  name: 'ServiciosView',
  components: { DevBanner, ServicePill, LoadingSpinner },
  data() {
    return {
      loading: true,
      health: { tif: {}, ia: {} },
      endpointsTIF: [
        { method:'GET',  path:'/health',                    ready:true,  sprint:2 },
        { method:'POST', path:'/analyze',                   ready:false, sprint:7 },
        { method:'GET',  path:'/jobs/{id}/status',          ready:false, sprint:7 },
        { method:'GET',  path:'/lots/{id}/results',         ready:false, sprint:7 },
        { method:'GET',  path:'/internal/config/validate',  ready:false, sprint:3 },
        { method:'POST', path:'/internal/config/refresh',   ready:false, sprint:3 },
      ],
      endpointsIA: [
        { method:'GET',  path:'/health',                    ready:true,  sprint:2 },
        { method:'POST', path:'/analyze',                   ready:false, sprint:8 },
        { method:'GET',  path:'/alerts',                    ready:false, sprint:11 },
        { method:'GET',  path:'/jobs/{id}/status',          ready:false, sprint:11 },
        { method:'GET',  path:'/lots/{id}/history',         ready:false, sprint:11 },
        { method:'POST', path:'/webhook/retry/{id}',        ready:false, sprint:11 },
      ],
    }
  },
  methods: {
    formatUptime(s) {
      if (!s) return '—'
      const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60)
      return `${h}h ${m}m`
    },
    async recargar() {
      this.loading = true
      this.health  = await getHealth()
      this.loading = false
    },
  },
  async created() {
    this.health  = await getHealth()
    this.loading = false
  },
}
</script>

<style scoped>
.service-info-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.service-info-item { display: flex; flex-direction: column; gap: 2px; }
.service-info-label { font-size: .72rem; text-transform: uppercase; letter-spacing: .05em; color: #9ca3af; }
.service-endpoints { margin-top: 8px; }
.endpoint-row {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 0; border-bottom: 1px solid #f3f4f6; font-size: .82rem;
}
.endpoint-row:last-child { border-bottom: none; }
.method-badge {
  padding: 2px 6px; border-radius: 4px; font-size: .7rem; font-weight: 700; min-width: 38px; text-align: center;
}
.method-badge--get  { background: #dcfce7; color: #16a34a; }
.method-badge--post { background: #dbeafe; color: #1d4ed8; }
.endpoint-path { font-size: .78rem; flex: 1; color: #374151; }
.infra-item { display: flex; align-items: flex-start; gap: 12px; }
.infra-item__icon { width: 40px; height: 40px; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 1.1rem; flex-shrink: 0; }
.infra-item__name   { font-weight: 600; font-size: .9rem; margin-bottom: 2px; }
.infra-item__detail { font-size: .78rem; color: #9ca3af; margin-bottom: 6px; }
</style>

<template>
  <div>
    <dev-banner servicio="GET /internal/config/validate → TIF :8001 y IA :8002" sprint="3 y 8" />

    <div class="as-page-header">
      <div>
        <h1>Configuración</h1>
        <small>Estado del item de DynamoDB (<code>pk=local, sk=active</code>)</small>
      </div>
      <button class="as-btn as-btn--outline" @click="recargar">
        <i class="fas fa-sync-alt mr-1"></i>Revalidar
      </button>
    </div>

    <loading-spinner v-if="loading" />
    <template v-else>
      <div class="row">
        <!-- Validación TIF -->
        <div class="col-md-6 mb-4">
          <div class="as-card">
            <div class="d-flex justify-content-between align-items-center mb-3">
              <div class="as-card__title mb-0">Microservicio TIF</div>
              <span :class="['badge', cfg.tif.valid ? 'badge-success' : 'badge-danger']">
                <i :class="cfg.tif.valid ? 'fas fa-check mr-1' : 'fas fa-times mr-1'"></i>
                {{ cfg.tif.valid ? 'Válida' : 'Campos faltantes' }}
              </span>
            </div>

            <template v-if="cfg.tif.missing && cfg.tif.missing.length">
              <div class="missing-section">
                <div class="missing-title">
                  <i class="fas fa-exclamation-circle mr-1 text-danger"></i>
                  {{ cfg.tif.missing.length }} campo{{ cfg.tif.missing.length > 1 ? 's' : '' }} faltante{{ cfg.tif.missing.length > 1 ? 's' : '' }}
                </div>
                <div v-for="f in cfg.tif.missing" :key="f" class="missing-field">
                  <i class="fas fa-times-circle mr-2 text-danger"></i>
                  <code>{{ f }}</code>
                </div>
              </div>
            </template>
            <div v-else class="text-success">
              <i class="fas fa-check-circle mr-2"></i>Todos los campos requeridos están presentes.
            </div>

            <div class="mt-3 pt-3 border-top">
              <div class="as-card__title">Campos requeridos (TIF)</div>
              <div v-for="f in requiredTIF" :key="f" class="field-row">
                <i :class="['mr-2', (cfg.tif.missing||[]).includes(f) ? 'fas fa-times-circle text-danger' : 'fas fa-check-circle text-success']"></i>
                <code style="font-size:.8rem">{{ f }}</code>
              </div>
            </div>
          </div>
        </div>

        <!-- Validación IA -->
        <div class="col-md-6 mb-4">
          <div class="as-card">
            <div class="d-flex justify-content-between align-items-center mb-3">
              <div class="as-card__title mb-0">Microservicio IA</div>
              <span :class="['badge', cfg.ia.valid ? 'badge-success' : 'badge-danger']">
                <i :class="cfg.ia.valid ? 'fas fa-check mr-1' : 'fas fa-times mr-1'"></i>
                {{ cfg.ia.valid ? 'Válida' : 'Campos faltantes' }}
              </span>
            </div>

            <template v-if="cfg.ia.missing && cfg.ia.missing.length">
              <div class="missing-section">
                <div class="missing-title">
                  <i class="fas fa-exclamation-circle mr-1 text-danger"></i>
                  {{ cfg.ia.missing.length }} campo{{ cfg.ia.missing.length > 1 ? 's' : '' }} faltante{{ cfg.ia.missing.length > 1 ? 's' : '' }}
                </div>
                <div v-for="f in cfg.ia.missing" :key="f" class="missing-field">
                  <i class="fas fa-times-circle mr-2 text-danger"></i>
                  <code>{{ f }}</code>
                </div>
              </div>
            </template>
            <div v-else class="text-success">
              <i class="fas fa-check-circle mr-2"></i>Todos los campos requeridos están presentes.
            </div>

            <div class="mt-3 pt-3 border-top">
              <div class="as-card__title">Campos requeridos (IA)</div>
              <div v-for="f in requiredIA" :key="f" class="field-row">
                <i :class="['mr-2', (cfg.ia.missing||[]).includes(f) ? 'fas fa-times-circle text-danger' : 'fas fa-check-circle text-success']"></i>
                <code style="font-size:.8rem">{{ f }}</code>
              </div>
            </div>
          </div>
        </div>

        <!-- Referencia del item DynamoDB -->
        <div class="col-12">
          <div class="as-card">
            <div class="as-card__title">
              <i class="fas fa-database mr-2"></i>Item de configuración — estructura esperada
            </div>
            <div class="table-responsive">
              <table class="as-table">
                <thead>
                  <tr>
                    <th>Sección</th>
                    <th>Campo</th>
                    <th>TIF</th>
                    <th>IA</th>
                    <th>Descripción</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="row in configSchema" :key="row.key">
                    <td><code style="font-size:.8rem">{{ row.section }}</code></td>
                    <td><code style="font-size:.8rem">{{ row.field }}</code></td>
                    <td class="text-center">
                      <i v-if="row.tif" class="fas fa-check text-success"></i>
                      <i v-else class="fas fa-minus text-muted"></i>
                    </td>
                    <td class="text-center">
                      <i v-if="row.ia" class="fas fa-check text-success"></i>
                      <i v-else class="fas fa-minus text-muted"></i>
                    </td>
                    <td class="text-muted small">{{ row.desc }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script>
import DevBanner from '@/components/DevBanner.vue'
import LoadingSpinner from '@/components/LoadingSpinner.vue'
import { getConfigValidacion } from '@/services/api'

export default {
  name: 'ConfiguracionView',
  components: { DevBanner, LoadingSpinner },
  data() {
    return {
      loading: true,
      cfg: { tif: {}, ia: {} },
      requiredTIF: [
        'security.api_secret_key','storage.driver','storage.s3_bucket',
        'storage.base_path','copernicus.client_id','copernicus.client_secret',
        'processing.default_indices','processing.min_valid_pixels_percentage',
      ],
      requiredIA: [
        'security.api_secret_key','storage.driver','storage.s3_bucket',
        'storage.base_path','ai.provider','agronomic_rules.ndvi_drop_alert_pct',
        'agronomic_rules.ndmi_drop_alert_pct','laravel.webhook_url','laravel.webhook_secret',
      ],
      configSchema: [
        { section:'security',          field:'api_secret_key',               tif:true,  ia:true,  desc:'Clave compartida con Laravel' },
        { section:'storage',           field:'s3_bucket / base_path',        tif:true,  ia:true,  desc:'Bucket S3 y ruta base' },
        { section:'copernicus',        field:'client_id / client_secret',    tif:true,  ia:false, desc:'Credenciales OAuth2 CDSE' },
        { section:'copernicus',        field:'max_cloud_coverage',           tif:true,  ia:false, desc:'Máximo porcentaje de nubosidad' },
        { section:'processing',        field:'default_indices',              tif:true,  ia:false, desc:'Índices calculados por defecto' },
        { section:'processing',        field:'min_valid_pixels_percentage',  tif:true,  ia:false, desc:'Mínimo de píxeles válidos' },
        { section:'processing',        field:'generate_png',                 tif:true,  ia:false, desc:'Activar generación de PNGs' },
        { section:'ai',                field:'provider',                     tif:false, ia:true,  desc:'anthropic | ollama | openai | …' },
        { section:'ai.providers.*',    field:'api_key / model',              tif:false, ia:true,  desc:'Credenciales del proveedor activo' },
        { section:'agronomic_rules',   field:'ndvi_drop_alert_pct',          tif:false, ia:true,  desc:'% caída NDVI para alerta' },
        { section:'agronomic_rules',   field:'ndmi_drop_alert_pct',          tif:false, ia:true,  desc:'% caída NDMI para alerta' },
        { section:'crops.*',           field:'ndvi_optimal_min / …',         tif:false, ia:true,  desc:'Umbrales por cultivo' },
        { section:'laravel',           field:'webhook_url / webhook_secret', tif:false, ia:true,  desc:'Destino y firma del webhook' },
      ],
    }
  },
  methods: {
    async recargar() {
      this.loading = true
      this.cfg     = await getConfigValidacion()
      this.loading = false
    },
  },
  async created() {
    this.cfg     = await getConfigValidacion()
    this.loading = false
  },
}
</script>

<style scoped>
.missing-section { background: #fff5f5; border: 1px solid #fecaca; border-radius: 6px; padding: 12px; margin-bottom: 14px; }
.missing-title   { font-weight: 600; font-size: .85rem; margin-bottom: 8px; color: #991b1b; }
.missing-field   { font-size: .85rem; padding: 3px 0; }
.field-row       { display: flex; align-items: center; padding: 4px 0; border-bottom: 1px solid #f9fafb; font-size: .83rem; }
.field-row:last-child { border-bottom: none; }
</style>

# AgroSentinel — Catálogo de Errores

Todo error devuelto por cualquier endpoint sigue este formato estándar:

```json
{
  "ok": false,
  "error_code": "CODIGO_ERROR",
  "message": "Descripción legible del error.",
  "missing": [],
  "invalid": [],
  "details": {},
  "trace_id": "req_01JABCDEF123456",
  "timestamp": "2026-05-18T10:30:00Z"
}
```

Los warnings (errores no críticos) siguen el mismo formato pero con `"ok": true` y un campo `warnings[]`.

---

## Errores de configuración (ambos microservicios)

| Código | HTTP | Descripción | Cómo resolverlo |
|---|---|---|---|
| `ENV_CONFIG_MISSING` | 500 | Faltan variables mínimas en `.env` | Verificar que `.env` tenga `CONFIG_TABLE_NAME`, `CONFIG_PARTITION_KEY`, `AWS_REGION` |
| `DYNAMODB_CONFIG_NOT_FOUND` | 503 | No existe item en DynamoDB con el pk/sk configurado | Crear el item o corregir `CONFIG_PARTITION_KEY` / `CONFIG_SORT_KEY` |
| `CONFIG_DISABLED` | 503 | El item existe pero `enabled: false` | Cambiar `enabled` a `true` en DynamoDB |
| `CONFIG_VALIDATION_ERROR` | 422 | El item existe pero faltan campos requeridos | Ver campo `missing[]` en la respuesta para saber qué agregar |
| `SECRET_RESOLUTION_ERROR` | 503 | DynamoDB apunta a Secrets Manager y el secreto no existe o no hay permiso IAM | Verificar que el secreto exista y que el rol tenga `secretsmanager:GetSecretValue` |

---

## Errores del Microservicio TIF

| Código | HTTP | Descripción | Cómo resolverlo |
|---|---|---|---|
| `COPERNICUS_AUTH_ERROR` | 503 | client_id o client_secret inválidos | Verificar credenciales en DynamoDB `copernicus.client_id/secret` |
| `COPERNICUS_TOKEN_EXPIRED` | 503 | Token OAuth2 expirado y renovación falló | Verificar conectividad con `identity.dataspace.copernicus.eu` |
| `NO_SCENE_AVAILABLE` | 404 | No hay imagen Sentinel-2 disponible para el polígono en el rango de fechas con la nubosidad configurada | Ampliar el rango de fechas o aumentar `max_cloud_coverage` en DynamoDB |
| `INSUFFICIENT_VALID_PIXELS` | 422 | El porcentaje de píxeles válidos tras la máscara SCL está por debajo del mínimo | La imagen tiene demasiadas nubes sobre el lote — intentar con otra fecha |
| `STORAGE_PRESSURE` | 503 | El disco temporal `/tmp/` supera 1.5 GB | Esperar a que terminen análisis activos y se limpie el disco |
| `TILE_DOWNLOAD_TIMEOUT` | 504 | Timeout descargando el tile de Copernicus | Reintentar; puede ser problema temporal de la API de Copernicus |
| `TILE_DOWNLOAD_ERROR` | 502 | Error HTTP al descargar el tile | Ver `details.status_code` en la respuesta |
| `RASTERIO_CROP_ERROR` | 500 | rasterio no pudo recortar el tile al polígono | Verificar que el GeoJSON del lote esté en CRS EPSG:4326 y que sea un polígono válido |
| `RASTERIO_INDEX_ERROR` | 500 | Error calculando un índice espectral | Ver `details.index` para saber cuál índice falló |
| `UNSUPPORTED_INDEX` | 200 (warning) | Se solicitó un índice no implementado | El análisis continúa; el índice aparece en `unsupported_indices[]` |
| `S3_UPLOAD_ERROR` | 500 | No se pudo subir el archivo a S3 | Verificar permisos IAM `s3:PutObject` y que el bucket exista |
| `INVALID_POLYGON` | 400 | El GeoJSON enviado no es un polígono válido | Verificar que el polígono esté cerrado (primer y último punto iguales) y sea convexo o simple |
| `LOT_TOO_LARGE` | 400 | El polígono supera el tamaño máximo soportado | El sistema está optimizado para lotes de hasta 10 ha |

---

## Errores del Microservicio IA

| Código | HTTP | Descripción | Cómo resolverlo |
|---|---|---|---|
| `AI_PROVIDER_CONFIG_MISSING` | 422 | El proveedor activo no tiene configuración en DynamoDB | Agregar `ai.providers.{provider}` al item de DynamoDB |
| `AI_PROVIDER_DISABLED` | 422 | El proveedor está configurado pero `enabled: false` | Cambiar `ai.providers.{provider}.enabled` a `true` |
| `AI_PROVIDER_UNAVAILABLE` | 200 (warning) | Anthropic y fallback fallaron — se devuelve resultado de reglas | Verificar API key y conectividad; el análisis de reglas está disponible |
| `AI_RESPONSE_INVALID` | 502 | La IA no devolvió JSON válido tras 2 intentos | Puede ser problema temporal; reintentar el análisis |
| `AI_TIMEOUT` | 504 | La IA no respondió en el tiempo configurado | Aumentar `ai.timeout` en DynamoDB o reintentar |
| `AI_FALLBACK_UNAVAILABLE` | 502 | Proveedor principal y fallback fallaron | Ver `details.fallback_missing[]` para saber qué configurar |
| `INSUFFICIENT_HISTORY` | 200 (warning) | El lote tiene menos de 2 análisis previos | Normal para lotes nuevos; el análisis continúa sin comparación histórica |
| `CROP_CONFIG_MISSING` | 422 | El cultivo solicitado no existe en `crops.*` de DynamoDB y no hay umbrales globales | Agregar el cultivo a DynamoDB o usar uno de los cultivos soportados |
| `CROP_CONFIG_USING_GLOBAL_DEFAULTS` | 200 (warning) | El cultivo no tiene config específica; se usaron umbrales globales | Opcional: agregar config específica del cultivo en DynamoDB |
| `WEBHOOK_DELIVERY_FAILED` | 200 (warning) | Los 3 reintentos del webhook fallaron — resultado guardado en S3 | Llamar a `POST /webhook/retry/{job_id}` cuando Laravel esté disponible |
| `INVALID_STATISTICS_PAYLOAD` | 400 | El payload de estadísticas recibido del TIF no tiene el formato esperado | Verificar que el Microservicio TIF esté en la versión correcta |
| `HISTORY_READ_ERROR` | 500 | No se pudo leer el historial de S3 | Verificar permisos IAM `s3:GetObject` y que el bucket exista |

---

## Errores de autenticación (ambos microservicios)

| Código | HTTP | Descripción |
|---|---|---|
| `UNAUTHORIZED` | 401 | Header `X-API-Key` ausente o incorrecto |
| `FORBIDDEN` | 403 | IP o origen no está en `allowed_origins` |

---

## Excepciones Python internas

Estas son las excepciones tipadas que el código usa internamente. Los handlers de FastAPI las convierten al formato estándar de respuesta.

```python
# Base
class AgroSentinelError(Exception):
    error_code = "AGRO_SENTINEL_ERROR"
    http_status = 500

# Configuración
class EnvConfigMissingError(AgroSentinelError):       error_code = "ENV_CONFIG_MISSING";         http_status = 500
class DynamoConfigNotFoundError(AgroSentinelError):   error_code = "DYNAMODB_CONFIG_NOT_FOUND";  http_status = 503
class ConfigDisabledError(AgroSentinelError):         error_code = "CONFIG_DISABLED";             http_status = 503
class ConfigValidationError(AgroSentinelError):       error_code = "CONFIG_VALIDATION_ERROR";     http_status = 422
class SecretResolutionError(AgroSentinelError):       error_code = "SECRET_RESOLUTION_ERROR";     http_status = 503

# TIF
class CopernicusAuthError(AgroSentinelError):         error_code = "COPERNICUS_AUTH_ERROR";       http_status = 503
class NoSceneAvailableError(AgroSentinelError):       error_code = "NO_SCENE_AVAILABLE";          http_status = 404
class InsufficientValidPixelsError(AgroSentinelError):error_code = "INSUFFICIENT_VALID_PIXELS";   http_status = 422
class StoragePressureError(AgroSentinelError):        error_code = "STORAGE_PRESSURE";            http_status = 503
class TileDownloadTimeoutError(AgroSentinelError):    error_code = "TILE_DOWNLOAD_TIMEOUT";       http_status = 504
class RasterioProcessingError(AgroSentinelError):     error_code = "RASTERIO_PROCESSING_ERROR";   http_status = 500
class InvalidPolygonError(AgroSentinelError):         error_code = "INVALID_POLYGON";             http_status = 400

# IA
class AiProviderConfigMissingError(AgroSentinelError):error_code = "AI_PROVIDER_CONFIG_MISSING";  http_status = 422
class AiProviderDisabledError(AgroSentinelError):     error_code = "AI_PROVIDER_DISABLED";        http_status = 422
class AiProviderRuntimeError(AgroSentinelError):      error_code = "AI_PROVIDER_RUNTIME_ERROR";   http_status = 502
class AiResponseInvalidError(AgroSentinelError):      error_code = "AI_RESPONSE_INVALID";         http_status = 502
class AiTimeoutError(AgroSentinelError):              error_code = "AI_TIMEOUT";                  http_status = 504
class CropConfigMissingError(AgroSentinelError):      error_code = "CROP_CONFIG_MISSING";         http_status = 422
class WebhookDeliveryError(AgroSentinelError):        error_code = "WEBHOOK_DELIVERY_FAILED";     http_status = 200
```

---

## Política de warnings vs errores

**Errores críticos** — detienen el análisis completamente:
- Configuración faltante o inválida
- Credenciales de Copernicus inválidas
- No hay imagen disponible
- Píxeles válidos insuficientes
- Polígono inválido

**Warnings** — el análisis continúa con información parcial:
- Índice no soportado (se omite ese índice)
- Lote sin historial (análisis sin comparación)
- Cultivo sin config específica (usa umbrales globales)
- Proveedor IA no disponible (devuelve resultado de reglas)
- Webhook fallido (resultado guardado en S3)

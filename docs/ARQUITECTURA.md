# AgroSentinel — Arquitectura Técnica

---

## Principios de diseño

1. **Responsabilidad única por microservicio** — el TIF no sabe de IA; la IA no sabe de TIFs.
2. **Configuración centralizada en DynamoDB** — el `.env` solo contiene las 6 variables para encontrar DynamoDB.
3. **Stateless por defecto** — los microservicios no mantienen estado en memoria entre requests, excepto el caché de configuración.
4. **Idempotencia en S3** — si el análisis ya existe, devolver el guardado sin reprocesar.
5. **Fallar explícitamente** — errores con código, ruta y sugerencia. Nunca un `Exception("algo salió mal")`.
6. **El webhook nunca bloquea** — si Laravel no responde, el resultado queda en S3 y se reintenta.

---

## Diagrama de flujo completo

AgroSentinel corre en su **propio servidor** separado del servidor de Laravel. La comunicación es exclusivamente por HTTP.

```
[SERVIDOR LARAVEL]                      [SERVIDOR AGROSENTINEL]
                                        ┌──────────────────────────────────┐
Usuario solicita análisis               │   Microservicio TIF  (:8001)     │
      │                                 │                                  │
      ▼                                 │  1. Carga config DynamoDB        │
Laravel ERP (PHP)                       │  2. Autentica en Copernicus      │
      │                                 │  3. Busca escena disponible      │
      │  HTTPS POST /analyze            │  4. Descarga tile en streaming   │
      │  { lot_id, polygon_geojson,     │  5. Recorta polígono con rasterio│
      │    dates[], indices[] }         │  6. Elimina tile completo        │
      │─────────────────────────────►  │  7. Aplica máscara SCL           │
      │◄─────────────────────────────  │  8. Calcula índices solicitados  │
      │  202 { job_id, status:          │  9. Genera estadísticas + PNGs   │
      │        "processing" }           │  10. Sube resultados a S3        │
      │                                 │  11. Llama al Microservicio IA   │
      │  (espera async 2–10 min)        └──────────────────────────────────┘
      │                                          │
      │                                          │ HTTP interno
      │                                          ▼
      │                                 ┌──────────────────────────────────┐
      │                                 │   Microservicio IA  (:8002)      │
      │                                 │                                  │
      │                                 │  1. Carga config DynamoDB        │
      │                                 │  2. Lee histórico S3             │
      │                                 │  3. Aplica reglas agronómicas    │
      │                                 │  4. Llama a Anthropic API        │
      │                                 │  5. Valida y normaliza respuesta │
      │                                 │  6. Guarda auditoría en S3       │
      │                                 │  7. Envía webhook a Laravel      │
      │                                 └──────────────────────────────────┘
      │                                          │
      │      HTTPS POST /api/sentinel/webhook    │
      │  { job_id, risk_level, summary, ... }    │
      │◄─────────────────────────────────────────┘
      │
      ▼
Laravel guarda en BD y muestra resultado al usuario
```

**Flujo desde el punto de vista de Laravel:**

1. Laravel hace `POST /analyze` → recibe `job_id` en < 1 segundo (202 Accepted)
2. AgroSentinel procesa en background (2–10 minutos)
3. AgroSentinel llama al webhook de Laravel cuando termina
4. Laravel guarda el resultado y lo muestra al usuario

Laravel puede hacer polling en `GET /jobs/{id}/status` para mostrar progreso, pero el resultado definitivo siempre llega por webhook.

---

## Microservicio TIF

### Stack

```
Python 3.11
FastAPI 0.111+
uvicorn (servidor ASGI)
rasterio 1.3+
GDAL 3.8+ (dependencia del sistema)
numpy 1.26+
boto3 (S3 + DynamoDB)
httpx (descarga streaming Copernicus)
pydantic v2
```

### Estructura de carpetas

```
microservicio-tif/
├── app/
│   ├── main.py                        ← FastAPI app, lifespan, routers
│   ├── core/
│   │   ├── config.py                  ← carga variables .env mínimas
│   │   └── exceptions.py              ← todas las excepciones tipadas
│   ├── api/
│   │   └── routes/
│   │       ├── analyze.py             ← POST /analyze
│   │       ├── jobs.py                ← GET /jobs/{id}/status
│   │       ├── lots.py                ← GET /lots/{id}/results
│   │       ├── health.py              ← GET /health
│   │       └── internal.py            ← /internal/config/*
│   ├── services/
│   │   ├── configuration/
│   │   │   ├── config_loader.py       ← DynamoDB loader con caché TTL
│   │   │   ├── config_validator.py    ← validate_tif_config()
│   │   │   └── schemas.py             ← modelos Pydantic de configuración
│   │   ├── copernicus/
│   │   │   ├── auth.py                ← OAuth2 CDSE
│   │   │   ├── scene_search.py        ← búsqueda de escenas disponibles
│   │   │   └── tile_downloader.py     ← descarga streaming con httpx
│   │   ├── processing/
│   │   │   ├── cropper.py             ← recorte rasterio al polígono
│   │   │   ├── cloud_mask.py          ← máscara SCL
│   │   │   ├── index_calculator.py    ← cálculo de todos los índices
│   │   │   ├── statistics.py          ← min/max/mean/std por índice
│   │   │   └── png_renderer.py        ← colormap y exportación PNG
│   │   └── storage/
│   │       ├── s3_client.py           ← upload/download/check S3
│   │       └── temp_manager.py        ← gestión de /tmp/, límite 1.5 GB
│   └── models/
│       ├── requests.py                ← AnalyzeRequest, etc.
│       └── responses.py               ← AnalyzeResponse, StatsResponse, etc.
├── tests/
│   ├── unit/
│   └── integration/
├── .env.example
├── requirements.txt
└── Dockerfile
```

### Reglas de negocio — TIF

**Descarga:**
- Siempre streaming — nunca `response.content` completo en RAM
- Máximo 2 descargas simultáneas — semáforo asyncio con `asyncio.Semaphore(2)`
- Si `/tmp/` supera 1.5 GB → error `STORAGE_PRESSURE`, no iniciar descarga
- Eliminar tile inmediatamente después del recorte, en el mismo bloque `try/finally`

**Calidad:**
- `valid_pixels_percentage < config.processing.min_valid_pixels_percentage` → error `INSUFFICIENT_VALID_PIXELS`
- Nubosidad alta → warning, no error; el campo `confidence` refleja esto
- `image_quality` siempre presente en la respuesta, incluso en error

**Índices:**
- Solo los explícitamente pedidos en `indices[]`
- Índice no soportado → warning en `unsupported_indices[]`, no falla el análisis
- Fórmulas hardcodeadas en `index_calculator.py` — nunca configurables

**S3:**
- Ruta: `{base_path}/lots/{lot_id}/{YYYY-MM-DD}/`
- Si ya existe `statistics.json` en esa ruta y `force_reprocess=false` → devolver existente
- Nunca sobreescribir sin `force_reprocess=true` explícito

### Contrato de entrada

```json
{
  "job_id": "job_01JABCDEF123456",
  "lot_id": 25,
  "polygon_geojson": {
    "type": "Polygon",
    "coordinates": [[[...], [...], [...], [...]]]
  },
  "dates": ["2026-01-01", "2026-01-31"],
  "indices": ["NDVI", "NDMI", "NDRE", "MSAVI2", "BSI"],
  "resolution_meters": 20,
  "force_reprocess": false
}
```

### Contrato de salida exitosa

```json
{
  "ok": true,
  "job_id": "job_01JABCDEF123456",
  "lot_id": 25,
  "analysis_date": "2026-01-15",
  "image_quality": {
    "cloud_percentage": 3.2,
    "shadow_percentage": 1.1,
    "valid_pixels_percentage": 95.7,
    "confidence": "high"
  },
  "indices": {
    "ndvi": { "min": 0.41, "max": 0.78, "mean": 0.61, "std": 0.09, "valid_pixels": 2847 },
    "ndmi": { "min": 0.10, "max": 0.35, "mean": 0.22, "std": 0.06, "valid_pixels": 2847 },
    "ndre": { "min": 0.18, "max": 0.45, "mean": 0.31, "std": 0.07, "valid_pixels": 2847 }
  },
  "s3_paths": {
    "tif": "agro-sentinel/lots/25/2026-01-15/multiband.tif",
    "png_ndvi": "agro-sentinel/lots/25/2026-01-15/ndvi.png",
    "statistics": "agro-sentinel/lots/25/2026-01-15/statistics.json"
  },
  "unsupported_indices": [],
  "from_cache": false,
  "processing_seconds": 12.4
}
```

### Índices implementados

| Índice | Bandas Sentinel-2 | Fórmula |
|---|---|---|
| NDVI | B8, B4 | `(B8 - B4) / (B8 + B4)` |
| EVI | B8, B4, B2 | `2.5 * (B8 - B4) / (B8 + 6*B4 - 7.5*B2 + 1)` |
| SAVI | B8, B4 | `1.5 * (B8 - B4) / (B8 + B4 + 0.5)` |
| MSAVI2 | B8, B4 | `(2*B8 + 1 - sqrt((2*B8+1)^2 - 8*(B8-B4))) / 2` |
| NDWI | B3, B8 | `(B3 - B8) / (B3 + B8)` |
| NDMI | B8, B11 | `(B8 - B11) / (B8 + B11)` |
| MSI | B11, B8 | `B11 / B8` |
| NDRE | B8A, B5 | `(B8A - B5) / (B8A + B5)` |
| GNDVI | B8, B3 | `(B8 - B3) / (B8 + B3)` |
| BSI | B11, B4, B8, B2 | `((B11+B4) - (B8+B2)) / ((B11+B4) + (B8+B2))` |
| NBR | B8, B12 | `(B8 - B12) / (B8 + B12)` |

---

## Microservicio IA

### Stack

```
Python 3.11
FastAPI 0.111+
uvicorn
httpx (Anthropic API + webhook Laravel)
boto3 (S3 + DynamoDB)
pydantic v2
tenacity (reintentos con backoff exponencial)
```

### Estructura de carpetas

```
microservicio-ia/
├── app/
│   ├── main.py
│   ├── core/
│   │   ├── config.py
│   │   └── exceptions.py
│   ├── api/
│   │   └── routes/
│   │       ├── analyze.py             ← POST /analyze
│   │       ├── jobs.py                ← GET /jobs/{id}/status
│   │       ├── lots.py                ← GET /lots/{id}/history
│   │       ├── alerts.py              ← GET /alerts
│   │       ├── webhook.py             ← POST /webhook/retry/{id}
│   │       ├── health.py
│   │       └── internal.py
│   ├── services/
│   │   ├── configuration/
│   │   │   ├── config_loader.py
│   │   │   ├── config_validator.py    ← validate_ia_config()
│   │   │   └── schemas.py
│   │   ├── agronomic/
│   │   │   ├── rules_engine.py        ← aplica umbrales DynamoDB
│   │   │   ├── history_reader.py      ← lee historial desde S3
│   │   │   └── risk_calculator.py     ← low/medium/medium_high/high
│   │   ├── ai/
│   │   │   ├── prompt_builder.py      ← construye payload para Anthropic
│   │   │   ├── anthropic_client.py    ← llamada a API + reintento
│   │   │   ├── response_parser.py     ← valida y normaliza JSON de IA
│   │   │   └── provider_factory.py    ← selecciona proveedor desde config
│   │   ├── webhook/
│   │   │   └── laravel_notifier.py    ← envío con backoff exponencial
│   │   └── storage/
│   │       └── s3_client.py           ← lectura historial + guardado análisis
│   └── models/
│       ├── requests.py
│       └── responses.py
├── prompts/
│   └── system_prompt_agronomico.md    ← system prompt versionado en código
├── tests/
│   ├── unit/
│   └── integration/
├── .env.example
├── requirements.txt
└── Dockerfile
```

### Reglas de negocio — IA

**Reglas agronómicas (siempre antes de llamar a la IA):**

```
NDVI baja > ndvi_drop_alert_pct vs histórico   → alerta pérdida de vigor
NDMI baja > ndmi_drop_alert_pct vs histórico   → alerta estrés hídrico
NDRE baja + NDMI estable                        → posible estrés nutricional
NDRE baja + NDMI baja                           → priorizar hipótesis hídrica
BSI sube significativamente                     → posible suelo expuesto
valid_pixels < 80%                              → marcar baja confiabilidad
```

Todos los umbrales (`_pct`) vienen de `agronomic_rules` en DynamoDB.

**Histórico:**
- Mínimo 2 análisis previos del lote para calcular variación `%`
- Sin historial → `historical_data: null`, la IA recibe esta advertencia
- El histórico se lee de S3 en `{base_path}/lots/{lot_id}/` — todos los `statistics.json`

**Llamada a Anthropic:**
- Temperatura: máximo 0.3
- Max tokens: 2500
- Si la respuesta no es JSON válido → reintentar una vez
- Si el segundo intento falla → error `AI_RESPONSE_INVALID`

**Fallback:**
- Proveedor principal falla → intentar `fallback_provider` de DynamoDB
- Ambos fallan → devolver resultado de reglas sin diagnóstico IA + warning `AI_PROVIDER_UNAVAILABLE`
- Nunca devolver error 5xx si las reglas agronómicas ya calcularon el riesgo

**Webhook:**
- Reintentos: 3 veces con backoff 5s → 15s → 45s
- Si todos fallan → guardar en S3 como `{base_path}/lots/{lot_id}/pending_webhook_{job_id}.json`
- Endpoint de reintento manual: `POST /webhook/retry/{job_id}`

### Contrato de entrada

```json
{
  "job_id": "job_01JABCDEF123456",
  "lot_id": 25,
  "lot_name": "Lote Norte 3",
  "crop": "maiz",
  "phenological_stage": "crecimiento vegetativo",
  "area_ha": 3.5,
  "analysis_date": "2026-01-15",
  "image_quality": {
    "cloud_percentage": 3.2,
    "valid_pixels_percentage": 95.7,
    "confidence": "high"
  },
  "indices": {
    "ndvi": { "mean": 0.61, "std": 0.09 },
    "ndmi": { "mean": 0.22, "std": 0.06 },
    "ndre": { "mean": 0.31, "std": 0.07 }
  },
  "weather_context": {
    "rainfall_7_days_mm": 2.5,
    "avg_temperature_c": 33.2
  }
}
```

### Contrato de salida exitosa (también cuerpo del webhook)

```json
{
  "ok": true,
  "job_id": "job_01JABCDEF123456",
  "lot_id": 25,
  "status": "completed",
  "rules_result": {
    "risk_level": "medium_high",
    "alerts": [
      "NDVI bajo contra histórico (-17.5%)",
      "NDMI bajo: posible estrés hídrico (-42.1%)"
    ]
  },
  "ai_result": {
    "risk_level": "medium_high",
    "summary": "La parcela presenta caída de vigor y humedad vegetal.",
    "probable_causes": ["Estrés hídrico", "Baja humedad disponible"],
    "recommendations": [
      "Verificar humedad de suelo en campo",
      "Revisar sistema de riego"
    ],
    "confidence": "medium",
    "limitations": [
      "El análisis satelital no confirma por sí solo plaga o deficiencia"
    ]
  },
  "meta": {
    "ai_provider": "anthropic",
    "ai_model": "claude-sonnet-4-5",
    "config_version": 7,
    "warnings": [],
    "processing_seconds": 4.2
  }
}
```

---

## Configuración DynamoDB — qué lee cada servicio

| Campo DynamoDB | TIF | IA |
|---|---|---|
| `security.api_secret_key` | ✅ | ✅ |
| `copernicus.client_id/secret` | ✅ | — |
| `copernicus.max_cloud_coverage` | ✅ | — |
| `storage.s3_bucket / base_path` | ✅ | ✅ |
| `processing.default_indices` | ✅ | — |
| `processing.min_valid_pixels_percentage` | ✅ | — |
| `processing.apply_cloud_mask` | ✅ | — |
| `processing.generate_png` | ✅ | — |
| `ai.provider / fallback_provider` | — | ✅ |
| `ai.providers.anthropic.*` | — | ✅ |
| `ai.timeout / temperature / max_tokens` | — | ✅ |
| `agronomic_rules.*` | — | ✅ |
| `crops.{cultivo}.*` | — | ✅ |
| `laravel.webhook_url / secret` | — | ✅ |

---

## Variables `.env` mínimas (idénticas para ambos servicios)

```env
APP_ENV=production
AWS_REGION=us-east-1
CONFIG_TABLE_NAME=agro_sentinel_config
CONFIG_PARTITION_KEY=production
CONFIG_SORT_KEY=active
CONFIG_CACHE_TTL_SECONDS=300
CONFIG_FAIL_FAST=true
```

Para desarrollo local agregar opcionalmente:
```env
DYNAMODB_ENDPOINT_URL=http://localhost:8005
```

---

## Comunicación entre microservicios

AgroSentinel y Laravel corren en **servidores distintos**. Toda comunicación es HTTP.

```
[Servidor Laravel]          [Servidor AgroSentinel]
                            ┌─────────────────────┐
                            │  TIF  :8001          │
 HTTPS POST /analyze  ───► │                     │
 202 { job_id }       ◄─── │  (interno)          │
                            │     ↓               │
                            │  IA   :8002          │
                            │                     │
 HTTPS POST /webhook  ◄─── │  (externo)          │
 200 { ok: true }     ───► │                     │
                            └─────────────────────┘
```

Los dos microservicios se comunican entre sí por HTTP interno en el mismo servidor (o red privada). Solo el Microservicio IA necesita poder alcanzar la URL pública del webhook de Laravel.

Fase 2 (cuando el volumen lo justifique): insertar SQS entre TIF e IA. El contrato de entrada/salida no cambia — solo el canal de comunicación.

**Configuración de red requerida:**
- Laravel debe poder hacer HTTPS hacia los microservicios (puertos 8001 y 8002 públicos o en red privada)
- El Microservicio IA debe poder hacer HTTPS hacia la URL del webhook de Laravel
- La URL del webhook se configura en DynamoDB en `laravel.webhook_url` — no en el código

---

## Lo que cada servicio NO puede hacer

**TIF no puede:**
- Importar `anthropic`, `openai` ni ningún SDK de IA
- Leer `ai.*` de DynamoDB
- Enviar webhooks a Laravel
- Tener lógica de umbrales agronómicos

**IA no puede:**
- Importar `rasterio`, `gdal`, `numpy`
- Descargar de Copernicus
- Calcular índices espectrales
- Escribir TIF o PNG en S3
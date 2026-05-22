# AgroSentinel — Estructura del Proyecto

Este documento describe la organización completa del repositorio, el propósito de cada archivo
y qué sprint lo implementa. Es la referencia definitiva para saber dónde va cada pieza de código.

---

## Árbol completo del repositorio

```
agro-sentinel-scrum/
│
├── README.md                              ← Punto de entrada — estado de sprints
├── PRODUCT_BACKLOG.md                     ← 24 historias de usuario priorizadas
├── DEFINITION_OF_DONE.md                  ← Criterios que debe cumplir todo código
├── PROMPTS_INICIO_SESION.md               ← Prompts para retomar el proyecto con IA
│
├── .gitignore                             ← Excluye .env con secretos y __pycache__
├── docker-compose.yml                     ← Orquestación local completa (Sprint 2)
│
├── docs/
│   ├── ARQUITECTURA.md                    ← Contratos, reglas y flujo completo
│   ├── ESTRUCTURA_PROYECTO.md             ← (este archivo)
│   ├── DYNAMODB_CONFIG.md                 ← Estructura exacta del item de configuración
│   ├── ENTORNO_LOCAL.md                   ← Cómo levantar el entorno desde cero
│   ├── ERRORES.md                         ← Catálogo completo de códigos de error
│   ├── GLOSARIO.md                        ← Términos agrícolas y técnicos
│   ├── DECISIONES_DISENO.md               ← ADRs — por qué se tomaron las decisiones
│   ├── CONVENCIONES.md                    ← Commits, nombres, checklist de despliegue
│   └── SYSTEM_PROMPT_IA.md                ← Prompt exacto enviado a Anthropic
│
├── sprints/
│   ├── infra/
│   │   ├── SPRINT_01_INFRA.md             ← DynamoDB + S3 + IAM (AWS real)
│   │   └── SPRINT_02_INFRA.md             ← Droplets + Docker + estructura base
│   ├── tif/
│   │   ├── SPRINT_03_TIF.md               ← Config loader + caché + /health
│   │   ├── SPRINT_04_TIF.md               ← Copernicus auth + búsqueda de escenas
│   │   ├── SPRINT_05_TIF.md               ← Descarga streaming + recorte + máscara
│   │   ├── SPRINT_06_TIF.md               ← Índices + estadísticas + PNGs
│   │   └── SPRINT_07_TIF.md               ← S3 upload + orchestrator + endpoints
│   ├── ia/
│   │   ├── SPRINT_08_IA.md                ← Esqueleto IA + config loader
│   │   ├── SPRINT_09_IA.md                ← Reglas agronómicas + historial S3
│   │   ├── SPRINT_10_IA.md                ← Anthropic + prompt + response parser
│   │   └── SPRINT_11_IA.md                ← Webhook + fallback + auditoría
│   └── laravel/
│       └── SPRINT_12_LARAVEL.md           ← AgroSentinelService PHP + webhook receiver
│
├── scripts/
│   ├── setup_local_dynamo.sh              ← Crea tabla e inserta config en DynamoDB Local
│   ├── config-local.json                  ← Item DynamoDB para desarrollo (pk=local)
│   └── test_analyze_request.json          ← Payload de prueba para POST /analyze
│
├── microservicio-tif/                     ← Servicio geoespacial (puerto 8001)
│   └── [ver sección "Microservicio TIF"]
│
└── microservicio-ia/                      ← Servicio de análisis IA (puerto 8002)
    └── [ver sección "Microservicio IA"]
```

---

## Microservicio TIF — detalle completo

```
microservicio-tif/
│
├── Dockerfile                             ← python:3.11-slim + GDAL + GDAL_VERSION
├── requirements.txt                       ← fastapi, uvicorn, rasterio, numpy, boto3, httpx
├── .env.example                           ← Plantilla de variables de entorno
├── .env                                   ← Variables reales (en .gitignore)
│
├── app/
│   ├── main.py                            ← FastAPI app, lifespan, registro de routers
│   │
│   ├── core/
│   │   ├── config.py                      ← Lee .env (solo las 6 vars mínimas)
│   │   └── exceptions.py                  ← Todas las excepciones tipadas del servicio
│   │
│   ├── api/
│   │   └── routes/
│   │       ├── health.py                  ← GET /health
│   │       ├── analyze.py                 ← POST /analyze → 202 + job_id   [Sprint 7]
│   │       ├── jobs.py                    ← GET /jobs/{id}/status           [Sprint 7]
│   │       ├── lots.py                    ← GET /lots/{id}/results          [Sprint 7]
│   │       └── internal.py                ← GET+POST /internal/config/*     [Sprint 3]
│   │
│   ├── services/
│   │   ├── configuration/
│   │   │   ├── config_loader.py           ← DynamoDB get-item + caché TTL   [Sprint 3]
│   │   │   ├── config_validator.py        ← validate_tif_config()           [Sprint 3]
│   │   │   └── schemas.py                 ← Modelos Pydantic de configuración
│   │   │
│   │   ├── copernicus/
│   │   │   ├── auth.py                    ← OAuth2 CDSE + renovación auto   [Sprint 4]
│   │   │   ├── scene_search.py            ← Búsqueda por polígono + fechas  [Sprint 4]
│   │   │   └── tile_downloader.py         ← Descarga streaming httpx        [Sprint 5]
│   │   │
│   │   ├── processing/
│   │   │   ├── cropper.py                 ← rasterio.mask al polígono GeoJSON [Sprint 5]
│   │   │   ├── cloud_mask.py              ← Máscara SCL (nube/sombra/agua)  [Sprint 5]
│   │   │   ├── index_calculator.py        ← 11 fórmulas NDVI/NDMI/BSI…     [Sprint 6]
│   │   │   ├── statistics.py              ← min/max/mean/std por índice     [Sprint 6]
│   │   │   └── png_renderer.py            ← Colormap + escala a 256×256 px  [Sprint 6]
│   │   │
│   │   └── storage/
│   │       ├── s3_client.py               ← upload/download/check_exists    [Sprint 7]
│   │       └── temp_manager.py            ← Controla /tmp/ → límite 1.5 GB  [Sprint 5]
│   │
│   └── models/
│       ├── requests.py                    ← AnalyzeRequest (Pydantic)
│       └── responses.py                   ← AnalyzeResponse, ImageQuality, IndexStats
│
└── tests/
    ├── unit/                              ← Tests sin I/O externo (mocks)
    └── integration/                       ← Tests con DynamoDB Local y S3 real
```

### Variables de entorno — Microservicio TIF

| Variable | Descripción | Valor local |
|---|---|---|
| `APP_ENV` | `local` / `production` | `local` |
| `AWS_REGION` | Región AWS | `us-east-1` |
| `CONFIG_TABLE_NAME` | Tabla DynamoDB | `agro_sentinel_config` |
| `CONFIG_PARTITION_KEY` | pk del item activo | `local` |
| `CONFIG_SORT_KEY` | sk del item activo | `active` |
| `CONFIG_CACHE_TTL_SECONDS` | Caché config en memoria | `60` |
| `CONFIG_FAIL_FAST` | Falla si config inválida | `true` |
| `DYNAMODB_ENDPOINT_URL` | Solo local — apunta a DynamoDB Local | `http://dynamodb-local:8000` |
| `IA_SERVICE_URL` | URL interna del Microservicio IA | `http://agro-ia:8002` |

---

## Microservicio IA — detalle completo

```
microservicio-ia/
│
├── Dockerfile                             ← python:3.11-slim (sin GDAL)
├── requirements.txt                       ← fastapi, uvicorn, boto3, httpx, tenacity
├── .env.example                           ← Plantilla de variables de entorno
├── .env                                   ← Variables reales (en .gitignore)
│
├── prompts/
│   └── system_prompt_agronomico.md        ← System prompt versionado en git [Sprint 10]
│
├── app/
│   ├── main.py                            ← FastAPI app, lifespan, registro de routers
│   │
│   ├── core/
│   │   ├── config.py                      ← Lee .env (solo las 6 vars mínimas)
│   │   └── exceptions.py                  ← Excepciones tipadas del servicio IA
│   │
│   ├── api/
│   │   └── routes/
│   │       ├── health.py                  ← GET /health
│   │       ├── analyze.py                 ← POST /analyze (recibe de TIF)  [Sprint 8]
│   │       ├── jobs.py                    ← GET /jobs/{id}/status           [Sprint 11]
│   │       ├── lots.py                    ← GET /lots/{id}/history          [Sprint 11]
│   │       ├── alerts.py                  ← GET /alerts (riesgo medium_high+high) [Sprint 11]
│   │       ├── webhook.py                 ← POST /webhook/retry/{id}        [Sprint 11]
│   │       └── internal.py                ← GET+POST /internal/config/*     [Sprint 8]
│   │
│   ├── services/
│   │   ├── configuration/
│   │   │   ├── config_loader.py           ← DynamoDB get-item + caché TTL   [Sprint 8]
│   │   │   ├── config_validator.py        ← validate_ia_config()            [Sprint 8]
│   │   │   └── schemas.py                 ← Modelos Pydantic de configuración
│   │   │
│   │   ├── agronomic/
│   │   │   ├── rules_engine.py            ← Aplica umbrales DynamoDB        [Sprint 9]
│   │   │   ├── history_reader.py          ← Lee statistics.json de S3       [Sprint 9]
│   │   │   └── risk_calculator.py         ← low/medium/medium_high/high     [Sprint 9]
│   │   │
│   │   ├── ai/
│   │   │   ├── provider_factory.py        ← Selecciona cliente según config [Sprint 10]
│   │   │   ├── anthropic_client.py        ← Llamada a API + 1 reintento     [Sprint 10]
│   │   │   ├── prompt_builder.py          ← Construye payload completo      [Sprint 10]
│   │   │   └── response_parser.py         ← Valida y normaliza JSON de IA   [Sprint 10]
│   │   │
│   │   ├── webhook/
│   │   │   └── laravel_notifier.py        ← HMAC-SHA256 + backoff 5s/15s/45s [Sprint 11]
│   │   │
│   │   └── storage/
│   │       └── s3_client.py               ← Lectura historial + auditoría   [Sprint 9/11]
│   │
│   └── models/
│       ├── requests.py                    ← AnalyzeRequest (recibido de TIF)
│       └── responses.py                   ← AnalyzeResponse, RulesResult, AIResult
│
└── tests/
    ├── unit/                              ← Tests sin I/O externo (mocks)
    └── integration/                       ← Tests con DynamoDB Local y S3 real
```

### Variables de entorno — Microservicio IA

| Variable | Descripción | Valor local |
|---|---|---|
| `APP_ENV` | `local` / `production` | `local` |
| `AWS_REGION` | Región AWS | `us-east-1` |
| `CONFIG_TABLE_NAME` | Tabla DynamoDB | `agro_sentinel_config` |
| `CONFIG_PARTITION_KEY` | pk del item activo | `local` |
| `CONFIG_SORT_KEY` | sk del item activo | `active` |
| `CONFIG_CACHE_TTL_SECONDS` | Caché config en memoria | `60` |
| `CONFIG_FAIL_FAST` | Falla si config inválida | `true` |
| `DYNAMODB_ENDPOINT_URL` | Solo local — apunta a DynamoDB Local | `http://dynamodb-local:8000` |

---

## docker-compose.yml — servicios locales

```
Puerto 8005  →  dynamodb-local    (DynamoDB Local, en memoria)
Puerto 8001  →  agro-tif          (Microservicio TIF)
Puerto 8002  →  agro-ia           (Microservicio IA)
```

`agro-tif` y `agro-ia` reciben `DYNAMODB_ENDPOINT_URL` inyectado automáticamente por compose.
`agro-tif` también recibe `IA_SERVICE_URL=http://agro-ia:8002` para poder llamar internamente al Microservicio IA.

---

## Qué implementa cada sprint

| Sprint | Módulos que se implementan completamente |
|---|---|
| **1** | AWS: tabla DynamoDB, bucket S3, política y rol IAM |
| **2** | Estructura de carpetas, `main.py`, `GET /health`, Dockerfiles, `docker-compose.yml` |
| **3** | `config_loader.py`, `config_validator.py`, `schemas.py` (TIF) · `GET /health` con estado config · `POST /internal/config/refresh` |
| **4** | `copernicus/auth.py` · `copernicus/scene_search.py` |
| **5** | `tile_downloader.py` · `cropper.py` · `cloud_mask.py` · `temp_manager.py` |
| **6** | `index_calculator.py` · `statistics.py` · `png_renderer.py` |
| **7** | `storage/s3_client.py` (TIF) · `routes/analyze.py` (orquestador completo) · `routes/jobs.py` · `routes/lots.py` |
| **8** | `config_loader.py`, `config_validator.py`, `schemas.py` (IA) · `routes/analyze.py` (stub) · `GET /health` con estado AI provider |
| **9** | `agronomic/history_reader.py` · `agronomic/rules_engine.py` · `agronomic/risk_calculator.py` · `storage/s3_client.py` (IA) |
| **10** | `ai/provider_factory.py` · `ai/anthropic_client.py` · `ai/prompt_builder.py` · `ai/response_parser.py` |
| **11** | `webhook/laravel_notifier.py` · `routes/alerts.py` · `routes/webhook.py` · `routes/jobs.py` · `routes/lots.py` · auditoría S3 |
| **12** | `AgroSentinelService.php` · webhook receiver Laravel · vistas de lote |

---

## Regla de separación estricta entre microservicios

```
TIF puede importar:         IA puede importar:
  rasterio ✅                 httpx ✅
  numpy ✅                    tenacity ✅
  boto3 ✅                    boto3 ✅
  httpx ✅                    pydantic ✅
  pydantic ✅
                            
TIF nunca importa:          IA nunca importa:
  anthropic ❌                rasterio ❌
  openai ❌                   numpy ❌
  tenacity ❌                 gdal ❌
```

El Microservicio TIF llama al IA por HTTP (`POST http://agro-ia:8002/analyze`).
El Microservicio IA nunca llama al TIF — solo recibe.

---

## Flujo de datos entre archivos (sprint por sprint)

```
Sprint 3-7 (TIF):

POST /analyze
  └── routes/analyze.py
        ├── services/configuration/config_loader.py  → DynamoDB
        ├── services/copernicus/auth.py               → identity.dataspace.copernicus.eu
        ├── services/copernicus/scene_search.py       → catalogue.dataspace.copernicus.eu
        ├── services/copernicus/tile_downloader.py    → download.dataspace.copernicus.eu
        ├── services/processing/cropper.py            → rasterio
        ├── services/processing/cloud_mask.py         → rasterio (banda SCL)
        ├── services/processing/index_calculator.py   → numpy
        ├── services/processing/statistics.py         → numpy
        ├── services/processing/png_renderer.py       → matplotlib/PIL
        ├── services/storage/s3_client.py             → S3
        └── [HTTP POST] → http://agro-ia:8002/analyze


Sprint 8-11 (IA):

POST /analyze (recibe de TIF)
  └── routes/analyze.py
        ├── services/configuration/config_loader.py  → DynamoDB
        ├── services/storage/s3_client.py            → S3 (historial)
        ├── services/agronomic/history_reader.py     → S3
        ├── services/agronomic/rules_engine.py       → lógica local
        ├── services/agronomic/risk_calculator.py    → lógica local
        ├── services/ai/provider_factory.py          → selecciona cliente
        ├── services/ai/prompt_builder.py            → construye payload
        ├── services/ai/anthropic_client.py          → api.anthropic.com
        ├── services/ai/response_parser.py           → valida JSON
        ├── services/storage/s3_client.py            → S3 (auditoría)
        └── services/webhook/laravel_notifier.py     → Laravel webhook
```

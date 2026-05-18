# AgroSentinel — Guía Maestra del Proyecto

> **Punto de entrada para cualquier IA o desarrollador que tome este proyecto.**
> Lee este archivo completo antes de tocar cualquier sprint.

---

## ¿Qué es este proyecto?

AgroSentinel es un sistema de análisis satelital agrícola compuesto por **dos microservicios Python independientes** que se integran con un ERP Laravel existente. Usa imágenes Sentinel-2 para calcular índices espectrales (NDVI, NDMI, NDRE, etc.) sobre lotes agrícolas de 1–10 hectáreas en México y genera diagnósticos con IA.

**No es una aplicación monolítica.** Son dos servicios con responsabilidades completamente separadas.

---

## Lee estos archivos antes de empezar cualquier sprint

```
README.md                         ← estás aquí
docs/ARQUITECTURA.md              ← contratos exactos, reglas, lo que cada servicio NO puede hacer
docs/DYNAMODB_CONFIG.md           ← estructura del item de configuración
docs/ERRORES.md                   ← todos los códigos de error
docs/GLOSARIO.md                  ← términos agrícolas y técnicos
docs/DECISIONES_DISENO.md         ← por qué se tomaron las decisiones clave (ADRs)
docs/CONVENCIONES.md              ← nombres, commits, checklist de despliegue
docs/ENTORNO_LOCAL.md             ← cómo levantar el entorno de desarrollo
docs/SYSTEM_PROMPT_IA.md          ← prompt exacto que se envía a Anthropic (versionado)
PRODUCT_BACKLOG.md                ← 24 historias de usuario priorizadas
DEFINITION_OF_DONE.md            ← criterios que debe cumplir todo código entregado
PROMPTS_INICIO_SESION.md         ← prompts listos para pegar al inicio de cada sesión
```

---

## Estructura completa del repositorio

```
agro-sentinel-scrum/
│
├── README.md
├── PRODUCT_BACKLOG.md
├── DEFINITION_OF_DONE.md
├── PROMPTS_INICIO_SESION.md
│
├── docs/
│   ├── ARQUITECTURA.md
│   ├── DYNAMODB_CONFIG.md
│   ├── ERRORES.md
│   ├── GLOSARIO.md
│   ├── DECISIONES_DISENO.md
│   ├── CONVENCIONES.md
│   ├── ENTORNO_LOCAL.md
│   └── SYSTEM_PROMPT_IA.md
│
└── sprints/
    ├── infra/
    │   ├── SPRINT_01_INFRA.md    ← DynamoDB + S3 + IAM
    │   └── SPRINT_02_INFRA.md    ← Droplets + Docker
    ├── tif/
    │   ├── SPRINT_03_TIF.md      ← Esqueleto + config loader
    │   ├── SPRINT_04_TIF.md      ← Copernicus auth + escenas
    │   ├── SPRINT_05_TIF.md      ← Descarga streaming + recorte
    │   ├── SPRINT_06_TIF.md      ← Índices + estadísticas + PNGs
    │   └── SPRINT_07_TIF.md      ← S3 + orchestrator + endpoints
    ├── ia/
    │   ├── SPRINT_08_IA.md       ← Esqueleto IA + config
    │   ├── SPRINT_09_IA.md       ← Reglas agronómicas + histórico
    │   ├── SPRINT_10_IA.md       ← Anthropic + prompt + parser
    │   └── SPRINT_11_IA.md       ← Webhook + fallback + auditoría
    └── laravel/
        └── SPRINT_12_LARAVEL.md  ← Integración PHP
```

---

## Dos microservicios, dos droplets

| | Microservicio TIF | Microservicio IA |
|---|---|---|
| **Responsabilidad** | Descargar Sentinel-2, recortar, calcular índices | Reglas agronómicas, Anthropic, webhook |
| **Droplet** | $12/mes — 2 GB RAM | $7/mes — 1 GB RAM |
| **Puerto** | 8001 | 8002 |
| **Dependencias pesadas** | rasterio, GDAL, numpy | httpx, tenacity |
| **Conoce de IA** | ❌ Nunca | ✅ Sí |
| **Conoce de TIF/bandas** | ✅ Sí | ❌ Nunca |

---

## Orden de desarrollo (no cambiar)

```
Sprint 1–2   → Infraestructura AWS y Docker   [BLOQUEANTE para todo]
Sprint 3–7   → Microservicio TIF completo      [BLOQUEANTE para Sprint 8+]
Sprint 8–11  → Microservicio IA completo       [BLOQUEANTE para Sprint 12]
Sprint 12    → Integración Laravel
```

---

## Estado actual de sprints

| Sprint | Área | Descripción | Estado |
|---|---|---|---|
| 1 | Infra | DynamoDB + S3 + IAM | ⬜ |
| 2 | Infra | Droplets + Docker + estructura base | ⬜ |
| 3 | TIF | Esqueleto FastAPI + config loader | ⬜ |
| 4 | TIF | Copernicus auth + búsqueda de escenas | ⬜ |
| 5 | TIF | Descarga streaming + recorte + máscara SCL | ⬜ |
| 6 | TIF | Cálculo de índices + estadísticas + PNGs | ⬜ |
| 7 | TIF | S3 upload + orchestrator + endpoints finales | ⬜ |
| 8 | IA | Esqueleto FastAPI IA + config | ⬜ |
| 9 | IA | Reglas agronómicas + histórico S3 | ⬜ |
| 10 | IA | Prompt builder + Anthropic + response parser | ⬜ |
| 11 | IA | Webhook + fallback + auditoría + endpoints | ⬜ |
| 12 | Laravel | AgroSentinelService + webhook receiver | ⬜ |

---

## Contexto de dominio crítico

- Los lotes miden **1–10 hectáreas** en México
- A 20 m/px Sentinel-2, un lote de 10 ha = **~32×32 píxeles**
- El TIF multibanda pesa **500 KB–2 MB** (no gigabytes)
- El tile de Copernicus pesa **~1 GB** y es **temporal** — se descarga, recorta, elimina
- La configuración operativa vive en **DynamoDB** — el `.env` solo tiene 6 variables
- Costo estimado: **$26–36 USD/mes**

---

## Prompt para retomar con cualquier IA

```
Lee los siguientes archivos en este orden antes de responder nada:
1. README.md
2. docs/ARQUITECTURA.md
3. docs/DYNAMODB_CONFIG.md
4. DEFINITION_OF_DONE.md
5. sprints/[área]/SPRINT_[N].md

Confirma sprint activo y primera tarea pendiente.
No generes código hasta que yo lo confirme.
```

---

## Prerrequisitos antes del Sprint 1

- [ ] Cuenta AWS con permisos DynamoDB + S3 + IAM
- [ ] `client_id` y `client_secret` de Copernicus CDSE (`dataspace.copernicus.eu`)
- [ ] API key de Anthropic (`console.anthropic.com`)
- [ ] Polígono GeoJSON de lote de prueba en EPSG:4326
- [ ] Docker y Docker Compose instalados

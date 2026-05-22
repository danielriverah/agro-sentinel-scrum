# AgroSentinel — Convenciones y Registro de Cambios

---

## Versionado

### Versión de configuración (`config_version` en DynamoDB)

Cada vez que se modifica el item de configuración en DynamoDB, incrementar el campo `version` en 1. Esto permite saber exactamente con qué configuración se generó cada análisis histórico.

```
version 1 → configuración inicial
version 2 → se cambió max_cloud_coverage de 20% a 25%
version 3 → se agregó cultivo "pepino" en crops.*
...
```

El campo `meta.config_version` en cada respuesta de análisis registra esto automáticamente.

### Versión del system prompt (`prompts/system_prompt_agronomico.md`)

El system prompt tiene su propia versión en el encabezado del archivo. Cuando se modifique:
1. Actualizar el campo `version` en el encabezado del archivo
2. Crear un commit de git con el mensaje: `prompt: v{N} - [descripción del cambio]`
3. Documentar el cambio en este archivo bajo "Historial de cambios del prompt"

### Versión de la API

Los microservicios no tienen versión en la URL. Si se hacen cambios que rompen el contrato de entrada/salida, incrementar el campo `version` en el `GET /health` de ambos servicios y documentar aquí.

---

## Convenciones de código

### Nombres de archivos Python
- `snake_case` para todos los archivos y funciones
- Módulos de servicio: `{sustantivo}_{acción}.py` (ej: `tile_downloader.py`, `scene_search.py`)
- Modelos Pydantic: `requests.py` y `responses.py` en `models/`

### Nombres de clases Python
- `PascalCase`
- Los servicios terminan en `Service` o el nombre describe la acción: `TileDownloader`, `SceneSearchService`
- Los clientes de API externa terminan en `Client`: `AnthropicClient`, `S3Client`

### Nombres de excepciones
- Siempre terminan en `Error`
- Siempre extienden `AgroSentinelError`
- Nombre describe la causa, no el componente: `StoragePressureError` (no `TmpDiskError`)

### job_id
- Formato: `job_{ULID}` — ejemplo: `job_01JABCDEF123456`
- Si Laravel no lo proporciona, el Microservicio TIF lo genera
- El mismo `job_id` fluye desde TIF hasta Laravel pasando por IA

### Rutas S3
```
{base_path}/lots/{lot_id}/{YYYY-MM-DD}/multiband.tif
{base_path}/lots/{lot_id}/{YYYY-MM-DD}/ndvi.png
{base_path}/lots/{lot_id}/{YYYY-MM-DD}/statistics.json
{base_path}/lots/{lot_id}/analyses/{job_id}.json      ← auditoría IA
{base_path}/lots/{lot_id}/pending_webhook_{job_id}.json  ← webhook fallido
```

### Headers de autenticación
- Entre Laravel y microservicios: `X-API-Key: {security.api_secret_key}`
- Endpoints internos: `Authorization: Bearer {INTERNAL_TOKEN}`
- Webhook de IA a Laravel: `X-AgroSentinel-Signature: sha256={hmac}`

---

## Convenciones de commits

```
feat(tif): implementar descarga streaming de tiles
feat(ia): agregar motor de reglas agronómicas
fix(tif): corregir máscara SCL para píxeles de cirrus
test(ia): agregar tests para response_parser con JSON malformado
docs: actualizar contrato de salida del Sprint 7
config: incrementar config_version a 3 (nuevo cultivo pepino)
prompt: v2 - mejorar instrucciones para lotes sin historial
infra: actualizar docker-compose con variable IA_SERVICE_URL
```

---

## Historial de cambios

### v0.2.0 — 2026-05-18 (Sprint 2)

- Estructura completa de `microservicio-tif/` y `microservicio-ia/` creada
- `docker-compose.yml` con DynamoDB Local + ambos microservicios
- `GET /health` funcionando en `:8001` y `:8002`
- `scripts/setup_local_dynamo.sh` y `scripts/config-local.json` para dev local
- `scripts/test_analyze_request.json` — payload de prueba
- `docs/ESTRUCTURA_PROYECTO.md` — árbol completo y mapa sprint→módulo
- Corrección: `IA_SERVICE_URL` pertenece al `.env` de TIF (TIF llama a IA, no al revés)

### v0.1.0 — 2026-05-18 (Sprint 0 — documentación)

- Diseño inicial del sistema
- Definición de los dos microservicios
- Estructura Scrum con 12 sprints
- Configuración DynamoDB inicial con 6 cultivos
- System prompt agronómico v1

---

## Historial de cambios del system prompt

| Versión | Fecha | Cambio |
|---|---|---|
| 1.0 | 2026-05-18 | Versión inicial con 6 campos requeridos |

---

## Checklist antes de desplegar a producción

Antes de cada despliegue a producción (no aplica para cambios de configuración en DynamoDB):

- [ ] Todos los tests unitarios pasan: `pytest tests/unit/ -v`
- [ ] `GET /health` devuelve `valid: true` en staging con el item de producción
- [ ] `GET /internal/config/validate` no reporta campos faltantes
- [ ] El Dockerfile construye sin errores en una máquina limpia
- [ ] El `requirements.txt` está actualizado con versiones fijas (no rangos)
- [ ] No hay credenciales hardcodeadas (verificar con `grep -r "sk-ant" .`)
- [ ] El `config_version` en el item de DynamoDB se incrementó si hubo cambios de configuración
- [ ] El `CHANGELOG.md` tiene entrada para esta versión

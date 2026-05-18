# Sprint 3 — TIF: Esqueleto FastAPI + Config Loader

**Duración:** 1 semana  
**Prerequisito:** Sprint 2 completado  
**Objetivo:** El Microservicio TIF carga configuración real desde DynamoDB, valida los campos requeridos y expone los endpoints internos de diagnóstico.  
**Historias:** US-004  
**Entregable:** `/health` muestra estado real de config. `/internal/config/validate` lista campos faltantes.

---

## Contexto para la IA

Este sprint implementa la capa de configuración completa del Microservicio TIF. Es el sprint más crítico porque si la configuración no funciona, nada más puede funcionar. Al terminar, el servicio debe leer de DynamoDB al arrancar, cachear la configuración, exponer endpoints de diagnóstico, y fallar con errores claros si falta configuración.

No se implementa lógica de Copernicus, rasterio ni S3 todavía.

---

## Archivos a implementar

### `app/core/config.py`
Lee las 6 variables mínimas del `.env`. Falla en el arranque si falta alguna.

```python
import os
from pydantic_settings import BaseSettings

class EnvSettings(BaseSettings):
    app_env: str = "local"
    aws_region: str
    config_table_name: str
    config_partition_key: str
    config_sort_key: str = "active"
    config_cache_ttl_seconds: int = 300
    config_fail_fast: bool = True
    dynamodb_endpoint_url: str | None = None

    class Config:
        env_file = ".env"

env = EnvSettings()
```

### `app/core/exceptions.py`
Todas las excepciones tipadas del catálogo `docs/ERRORES.md`. Incluir TODAS aunque aún no se usen — son la base para todos los sprints siguientes.

Estructura base:
```python
class AgroSentinelError(Exception):
    error_code = "AGRO_SENTINEL_ERROR"
    http_status = 500

    def __init__(self, message: str, details: dict = None, missing: list = None, invalid: list = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}
        self.missing = missing or []
        self.invalid = invalid or []
```

Implementar todas las subclases listadas en `docs/ERRORES.md`.

### `app/services/configuration/config_loader.py`
Clase `DynamoConfigLoader` con:
- `get_config(force_refresh=False)` devuelve el item de DynamoDB cacheado
- Caché en memoria con TTL configurable
- Si DynamoDB no está disponible y hay caché, devolver la caché
- Si no hay caché y falla → `DynamoConfigNotFoundError`
- Si `enabled: false` → `ConfigDisabledError`

### `app/services/configuration/config_validator.py`
Función `validate_tif_config(config: dict) -> dict` que valida:
- Campos globales: `security.api_secret_key`, `storage.driver`, `storage.s3_bucket`, `storage.base_path`
- Campos de Copernicus: `copernicus.client_id`, `copernicus.client_secret`
- Campos de processing: `processing.default_indices`, `processing.min_valid_pixels_percentage`
- Si `storage.driver = s3`: también `storage.aws_region`
- Devuelve `{ ok, error_code, missing[], invalid[], config_version }`

### `app/api/routes/health.py`
`GET /health` devuelve estado de configuración sin exponer secretos:
```json
{
  "status": "ok",
  "service": "agro-sentinel-tif",
  "config": {
    "loaded": true,
    "valid": true,
    "version": 1,
    "storage_driver": "s3",
    "last_loaded_at": "2026-05-18T10:00:00Z"
  }
}
```

### `app/api/routes/internal.py`
- `GET /internal/config/validate` — ejecuta `validate_tif_config()`
- `POST /internal/config/refresh` — `force_refresh=True` en config_loader
- Ambos requieren `Authorization: Bearer {INTERNAL_TOKEN}` (token fijo en esta fase)

### `app/main.py`
Conectar routers. Handler global de excepciones que convierte `AgroSentinelError` al formato estándar `{ ok, error_code, message, missing, invalid, details, trace_id, timestamp }`.

---

## Criterios de aceptación

- [ ] `docker-compose up` levanta sin errores
- [ ] `GET /health` devuelve `config.valid: true` con el item de DynamoDB Local
- [ ] `GET /internal/config/validate` devuelve `ok: true` con el item completo
- [ ] Si se elimina un campo del item y se hace refresh, `/validate` lista ese campo en `missing[]`
- [ ] `POST /internal/config/refresh` recarga sin reiniciar el servicio
- [ ] Si DynamoDB no está disponible, devuelve `DYNAMODB_CONFIG_NOT_FOUND` (503)
- [ ] Los errores siguen el formato estándar con `trace_id` y `timestamp`

---

## Estado de tareas

| Archivo | Estado |
|---|---|
| `app/core/config.py` | ⬜ |
| `app/core/exceptions.py` | ⬜ |
| `app/services/configuration/config_loader.py` | ⬜ |
| `app/services/configuration/config_validator.py` | ⬜ |
| `app/api/routes/health.py` | ⬜ |
| `app/api/routes/internal.py` | ⬜ |
| `app/main.py` (routers + handler global) | ⬜ |
| Tests unitarios de config_validator | ⬜ |

**Sprint completado:** ⬜

# Sprint 8 — IA: Esqueleto FastAPI + Config Loader

**Duración:** 1 semana  
**Prerequisito:** Sprint 7 completado  
**Objetivo:** El Microservicio IA tiene su estructura base, carga configuración desde DynamoDB y expone endpoints de diagnóstico.  
**Historias:** US-013  
**Entregable:** `/health` incluye estado de conectividad con Anthropic. `/internal/config/validate` valida secciones `ai.*`, `agronomic_rules`, `laravel`.

---

## Contexto para la IA

Este sprint es análogo al Sprint 3 pero para el Microservicio IA. La estructura de carpetas ya existe desde el Sprint 2. Aquí se implementa la lógica real.

La diferencia clave con el validador del TIF es que este valida secciones distintas: en lugar de `copernicus.*` y `processing.*`, valida `ai.*`, `agronomic_rules.*` y `laravel.*`.

El health check de este servicio debe intentar hacer una llamada mínima al proveedor IA activo para verificar conectividad. Si falla, el servicio reporta `degraded` pero no falla — los análisis que lleguen intentarán igualmente y manejarán el error.

---

## Archivos a implementar

### `app/core/config.py` y `app/core/exceptions.py`
Idénticos al Microservicio TIF. Copiar y ajustar el nombre del servicio.

### `app/services/configuration/config_validator.py`

Función `validate_ia_config(config: dict) -> dict` que valida:

Campos globales requeridos:
- `security.api_secret_key`
- `storage.driver`, `storage.s3_bucket`, `storage.base_path`
- `ai.provider`
- `laravel.webhook_url`, `laravel.webhook_secret`
- `agronomic_rules.ndvi_drop_alert_pct`, `agronomic_rules.ndmi_drop_alert_pct`

Campos según `ai.provider`:
```python
provider_required = {
    "anthropic": ["ai.providers.anthropic.enabled", "ai.providers.anthropic.model"],
    "openai": ["ai.providers.openai.enabled", "ai.providers.openai.base_url", "ai.providers.openai.model"],
    "ollama": ["ai.providers.ollama.enabled", "ai.providers.ollama.base_url", "ai.providers.ollama.model"],
    "vllm": ["ai.providers.vllm.enabled", "ai.providers.vllm.base_url", "ai.providers.vllm.model"],
    "custom": ["ai.providers.custom.enabled", "ai.providers.custom.url"],
}
```

Para `anthropic` y `openai`, verificar que exista `api_key` O `api_key_secret_name`.

### `app/api/routes/health.py`

```json
{
  "status": "ok",
  "service": "agro-sentinel-ia",
  "config": {
    "loaded": true,
    "valid": true,
    "version": 1,
    "ai_provider": "anthropic",
    "ai_connectivity": "ok"
  }
}
```

Para verificar `ai_connectivity`, hacer una llamada mínima al proveedor (Anthropic: `POST /v1/messages` con 1 token). Si falla → `"ai_connectivity": "unavailable"` pero `"status": "degraded"` (no error).

---

## Criterios de aceptación

- [ ] `GET /health` devuelve `ai_connectivity: ok` con Anthropic configurado y con API key válida
- [ ] `GET /health` devuelve `status: degraded` con API key inválida, sin error 500
- [ ] `GET /internal/config/validate` valida correctamente los campos de `ai.*` y `laravel.*`
- [ ] Si `ai.provider = anthropic` pero falta `api_key`, aparece en `missing[]`

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
| `app/main.py` | ⬜ |
| Tests unitarios config_validator sección IA | ⬜ |

**Sprint completado:** ⬜

---
---


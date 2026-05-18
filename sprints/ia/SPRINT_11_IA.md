# Sprint 11 — IA: Webhook Laravel + Fallback + Auditoría + Endpoints Finales

**Duración:** 1 semana  
**Prerequisito:** Sprint 10 completado  
**Objetivo:** El Microservicio IA está completo: envía webhook a Laravel, maneja fallback de proveedor, guarda auditoría en S3 y expone todos los endpoints.  
**Historias:** US-018, US-019, US-020, US-021  
**Entregable:** Un análisis completo de extremo a extremo del Microservicio IA funciona correctamente incluyendo webhook.

---

## Contexto para la IA

Este sprint une todos los servicios del Microservicio IA en un orquestador. El flujo completo: recibir estadísticas del TIF → reglas → IA → webhook → auditoría.

El webhook se firma con HMAC-SHA256:
```python
import hmac, hashlib
signature = hmac.new(
    webhook_secret.encode(),
    json.dumps(payload).encode(),
    hashlib.sha256
).hexdigest()
# Header: X-AgroSentinel-Signature: sha256={signature}
```

---

## Archivos a implementar

### `app/services/webhook/laravel_notifier.py`

```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

class LaravelNotifier:
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=5, max=45),
        retry=retry_if_exception_type(httpx.HTTPError)
    )
    async def _send_with_retry(self, payload: dict, webhook_url: str, secret: str) -> None:
        ...

    async def notify(self, job_id: str, payload: dict, webhook_url: str, secret: str) -> bool:
        """
        Intenta enviar el webhook.
        Si falla tras 3 intentos → guarda pending_webhook en S3 y devuelve False.
        Si tiene éxito → devuelve True.
        """
        ...
```

### `app/services/analysis_orchestrator.py` (Microservicio IA)

Flujo completo:
1. Cargar config DynamoDB
2. Leer historial S3
3. Calcular cambios históricos
4. Aplicar reglas agronómicas
5. Construir prompt
6. Llamar a IA con fallback
7. Parsear respuesta
8. Guardar análisis completo en S3 (auditoría)
9. Enviar webhook a Laravel
10. Devolver resultado

Para el fallback:
```python
try:
    client = provider_factory.get_client(config)
    ai_result = await client.complete(system_prompt, user_message)
except (AiProviderRuntimeError, AiTimeoutError):
    fallback = config["ai"].get("fallback_provider")
    if fallback:
        fallback_client = provider_factory.get_client_for(config, fallback)
        ai_result = await fallback_client.complete(...)
    else:
        # Sin fallback: devolver resultado de reglas con warning
        ai_result = None
```

### `app/api/routes/analyze.py`

```
POST /analyze
```
Acepta el payload del Microservicio TIF. Procesa en background. Devuelve 202 con `job_id`.

### `app/api/routes/alerts.py`

```
GET /alerts
```
Lee los últimos análisis de S3 (o del job_store en memoria) y devuelve los lotes con riesgo `medium_high` o `high`. Ordenados por nivel de riesgo descendente.

### `app/api/routes/webhook.py`

```
POST /webhook/retry/{job_id}
```
Lee el `pending_webhook_{job_id}.json` de S3 y reintenta el envío.

---

## Criterios de aceptación

- [ ] El webhook llega a Laravel con la firma HMAC correcta (verificable en el endpoint receptor)
- [ ] Si el webhook falla 3 veces → `pending_webhook_{job_id}.json` existe en S3
- [ ] `POST /webhook/retry/{job_id}` reintenta y tiene éxito si Laravel está disponible
- [ ] Si Anthropic falla → el fallback toma el relevo automáticamente
- [ ] Si ambos fallan → la respuesta incluye `rules_result` y warning `AI_PROVIDER_UNAVAILABLE`
- [ ] `GET /alerts` devuelve los lotes con riesgo alto ordenados correctamente
- [ ] El archivo de auditoría en S3 incluye `config_version`, `ai_provider`, `input_payload`, `output_payload`
- [ ] `POST /analyze` completo de extremo a extremo funciona con datos del Sprint 7

---

## Estado de tareas

| Archivo | Estado |
|---|---|
| `app/services/webhook/laravel_notifier.py` | ⬜ |
| `app/services/analysis_orchestrator.py` | ⬜ |
| `app/api/routes/analyze.py` | ⬜ |
| `app/api/routes/jobs.py` | ⬜ |
| `app/api/routes/lots.py` | ⬜ |
| `app/api/routes/alerts.py` | ⬜ |
| `app/api/routes/webhook.py` | ⬜ |
| Test integración flujo completo IA | ⬜ |
| Test fallback de proveedor | ⬜ |
| Test webhook con mock de Laravel | ⬜ |

**Sprint completado:** ⬜

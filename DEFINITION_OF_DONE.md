# Definition of Done — AgroSentinel

Una tarea o historia de usuario está **terminada** cuando cumple TODOS los criterios de su nivel.

---

## DoD General (aplica a toda tarea de código)

- [ ] El código corre sin errores en el entorno local
- [ ] Los errores usan las excepciones tipadas de `core/exceptions.py` — nunca `Exception` genérica
- [ ] Las respuestas de error siguen el formato estándar `{ ok, error_code, message, missing, invalid, details }`
- [ ] No hay credenciales, API keys ni secretos hardcodeados en el código
- [ ] Las variables de configuración operativa se leen desde DynamoDB, no desde `.env`
- [ ] El código tiene type hints en todas las funciones públicas
- [ ] Los modelos Pydantic validan todos los datos de entrada y salida
- [ ] El archivo `requirements.txt` está actualizado si se agregó una dependencia nueva

---

## DoD por tipo de tarea

### Endpoint HTTP

- [ ] Cumple el DoD General
- [ ] El contrato de entrada/salida coincide exactamente con el definido en `docs/ARQUITECTURA.md`
- [ ] Devuelve el código HTTP correcto según `docs/ERRORES.md`
- [ ] El endpoint de salud (`/health`) refleja el estado real del servicio
- [ ] Los endpoints internos (`/internal/*`) requieren autenticación Bearer

### Servicio / módulo interno

- [ ] Cumple el DoD General
- [ ] Tiene al menos un test unitario que prueba el caso feliz
- [ ] Tiene al menos un test unitario que prueba el caso de error principal
- [ ] No importa librerías del microservicio opuesto (TIF no importa httpx para IA; IA no importa rasterio)

### Integración con servicio externo (Copernicus, Anthropic, S3, DynamoDB)

- [ ] Cumple el DoD General
- [ ] Maneja timeout explícito — nunca espera indefinidamente
- [ ] Maneja el caso de credenciales inválidas con el error correcto del catálogo
- [ ] Maneja el caso de servicio no disponible (5xx del externo) sin propagar excepción genérica
- [ ] Tiene reintento configurado donde corresponde (webhook: 3 reintentos; descarga tile: 1 reintento)

### Sprint completo

- [ ] Todos los DoD de sus tareas individuales cumplidos
- [ ] El servicio arranca con `uvicorn app.main:app` sin errores
- [ ] `GET /health` devuelve `status: ok` con el estado real de la configuración
- [ ] `GET /internal/config/validate` no reporta campos faltantes con el item de DynamoDB local
- [ ] El entregable del sprint está documentado en el archivo del sprint correspondiente

---

## DoD específico por sprint

### Sprint 1 — Infra DynamoDB + S3 + IAM
- [ ] Tabla `agro_sentinel_config` creada en AWS
- [ ] Item `pk=production, sk=active` insertado con estructura completa (todos los `CAMBIAR` reemplazados)
- [ ] Item `pk=local, sk=active` insertado para desarrollo
- [ ] Bucket S3 creado
- [ ] Rol IAM creado con solo `dynamodb:GetItem` y `s3:PutObject / s3:GetObject`
- [ ] Se puede leer el item desde consola AWS o CLI

### Sprint 2 — Infra Droplets + Docker
- [ ] Dockerfile del Microservicio TIF construye sin errores
- [ ] Dockerfile del Microservicio IA construye sin errores
- [ ] `docker-compose.yml` levanta ambos servicios + DynamoDB Local
- [ ] Ambos servicios responden en sus puertos (8001 y 8002)

### Sprint 3 — TIF: Esqueleto + config loader
- [ ] FastAPI arranca en puerto 8001
- [ ] `GET /health` responde `200`
- [ ] `config_loader.py` lee desde DynamoDB y cachea por TTL
- [ ] `validate_tif_config()` detecta campos faltantes y devuelve lista
- [ ] `GET /internal/config/validate` devuelve resultado correcto
- [ ] `POST /internal/config/refresh` recarga la configuración

### Sprint 4 — TIF: Copernicus auth + búsqueda de escenas
- [ ] `auth.py` obtiene token OAuth2 de CDSE correctamente
- [ ] El token se renueva automáticamente antes de expirar
- [ ] `scene_search.py` devuelve escenas disponibles para un polígono y rango de fechas
- [ ] Filtra correctamente por `max_cloud_coverage` de DynamoDB
- [ ] Maneja `COPERNICUS_AUTH_ERROR` y `NO_SCENE_AVAILABLE` correctamente

### Sprint 5 — TIF: Descarga streaming + recorte rasterio
- [ ] La descarga usa streaming HTTP — nunca carga el tile completo en RAM
- [ ] El semáforo limita a 2 descargas simultáneas
- [ ] El tile se elimina en el bloque `finally` — nunca queda en disco si algo falla
- [ ] `cropper.py` recorta correctamente al polígono GeoJSON en EPSG:4326
- [ ] `cloud_mask.py` aplica la máscara SCL correctamente
- [ ] `StoragePressureError` se lanza si `/tmp/` supera 1.5 GB

### Sprint 6 — TIF: Índices + estadísticas
- [ ] Los 11 índices calculan correctamente con las fórmulas de `docs/ARQUITECTURA.md`
- [ ] Solo se calculan los índices pedidos en el payload
- [ ] Los índices no soportados van a `unsupported_indices[]` sin fallar
- [ ] `statistics.py` calcula min, max, mean, std, valid_pixels por índice
- [ ] `valid_pixels_percentage` se calcula sobre el polígono del lote, no sobre el tile completo

### Sprint 7 — TIF: S3 + endpoints finales
- [ ] TIF, PNGs y `statistics.json` se suben a la ruta correcta en S3
- [ ] Si ya existe el análisis en S3 y `force_reprocess=false`, devuelve el existente
- [ ] `POST /analyze` devuelve el contrato de salida completo de `docs/ARQUITECTURA.md`
- [ ] `GET /jobs/{id}/status` devuelve el estado correcto
- [ ] Después de subir a S3, llama al Microservicio IA con las estadísticas

### Sprint 8 — IA: Esqueleto + config
- [ ] FastAPI arranca en puerto 8002
- [ ] `GET /health` incluye estado de conectividad con Anthropic
- [ ] `config_loader.py` equivalente al del TIF, pero valida sección `ai.*`
- [ ] `validate_ia_config()` detecta campos faltantes en `ai`, `agronomic_rules`, `laravel`

### Sprint 9 — IA: Reglas agronómicas + histórico
- [ ] `history_reader.py` lee todos los `statistics.json` del lote desde S3
- [ ] Calcula variación porcentual de cada índice contra la media histórica
- [ ] `rules_engine.py` aplica los umbrales de DynamoDB y genera la lista de alertas
- [ ] `risk_calculator.py` asigna el nivel de riesgo correcto
- [ ] Sin historial → `historical_data: null`, warning `INSUFFICIENT_HISTORY`
- [ ] Cultivo sin config → usa umbrales globales + warning `CROP_CONFIG_USING_GLOBAL_DEFAULTS`

### Sprint 10 — IA: Anthropic + prompt
- [ ] `prompt_builder.py` construye el payload completo con índices, histórico y alertas
- [ ] El system prompt está en `prompts/system_prompt_agronomico.md` — no hardcodeado
- [ ] `anthropic_client.py` llama a la API con temperatura 0.2 y max_tokens 2500
- [ ] Si la respuesta no es JSON válido, reintenta una vez antes de `AI_RESPONSE_INVALID`
- [ ] `response_parser.py` valida que la respuesta tenga todos los campos esperados
- [ ] `provider_factory.py` selecciona el proveedor correcto según `ai.provider` en DynamoDB

### Sprint 11 — IA: Webhook + fallback + auditoría
- [ ] `laravel_notifier.py` reintenta 3 veces con backoff 5s → 15s → 45s
- [ ] Si los 3 fallan → guarda `pending_webhook_{job_id}.json` en S3
- [ ] `POST /webhook/retry/{job_id}` funciona correctamente
- [ ] El fallback de proveedor funciona cuando el principal falla
- [ ] Cada análisis guarda el input, output y `config_version` en S3
- [ ] `POST /analyze` devuelve el contrato de salida completo de `docs/ARQUITECTURA.md`
- [ ] `GET /alerts` devuelve lotes con riesgo `medium_high` o `high`

### Sprint 12 — Laravel: integración
- [ ] `AgroSentinelService.php` llama correctamente al Microservicio TIF
- [ ] El endpoint webhook receptor en Laravel guarda el resultado en la BD
- [ ] Los errores estructurados del microservicio se muestran correctamente en el panel
- [ ] Las migraciones de `sentinel_escenas`, `parcela_indices`, `ia_analisis` están creadas

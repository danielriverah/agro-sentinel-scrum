# AgroSentinel — Product Backlog

Historias de usuario ordenadas por prioridad. Cada historia tiene criterios de aceptación específicos.
El backlog está organizado por épicas. El sprint asignado indica cuándo se implementa.

---

## Épica 1 — Infraestructura base

### US-001 · Como equipo de desarrollo, necesito la tabla DynamoDB creada con el item de configuración inicial para que los microservicios puedan arrancar.

**Sprint:** 1  
**Prioridad:** Crítica — bloqueante para todo lo demás

Criterios de aceptación:
- La tabla `agro_sentinel_config` existe en AWS con pk y sk como String
- El item `pk=production, sk=active` existe con todos los campos del `docs/DYNAMODB_CONFIG.md`
- El item `pk=local, sk=active` existe para desarrollo
- Se puede leer el item con `aws dynamodb get-item`

---

### US-002 · Como equipo de desarrollo, necesito el bucket S3 y los permisos IAM configurados para que los microservicios puedan guardar y leer archivos.

**Sprint:** 1  
**Prioridad:** Crítica

Criterios de aceptación:
- Bucket S3 creado con el nombre configurado en DynamoDB
- Política IAM con solo `dynamodb:GetItem` + `s3:PutObject` + `s3:GetObject`
- Rol IAM asociado al entorno de ejecución (instancia o task)
- Se puede subir y bajar un archivo de prueba desde el servidor

---

### US-003 · Como equipo de desarrollo, necesito un entorno Docker local con DynamoDB Local para desarrollar sin costos AWS.

**Sprint:** 2  
**Prioridad:** Alta

Criterios de aceptación:
- `docker-compose.yml` levanta DynamoDB Local en puerto 8005
- `docker-compose.yml` levanta ambos microservicios en puertos 8001 y 8002
- Las variables `DYNAMODB_ENDPOINT_URL=http://localhost:8005` se configuran automáticamente en el entorno local
- Un script de setup inserta los items de configuración en DynamoDB Local

---

## Épica 2 — Microservicio TIF

### US-004 · Como sistema, necesito que el Microservicio TIF cargue su configuración desde DynamoDB al arrancar para operar con los parámetros correctos.

**Sprint:** 3  
**Prioridad:** Crítica

Criterios de aceptación:
- El servicio no arranca si faltan campos críticos en DynamoDB (`CONFIG_FAIL_FAST=true`)
- `GET /internal/config/validate` lista los campos faltantes con sus rutas exactas
- La configuración se cachea en memoria por `CONFIG_CACHE_TTL_SECONDS`
- `POST /internal/config/refresh` recarga desde DynamoDB sin reiniciar el servicio
- `GET /health` muestra si la configuración es válida y su versión

---

### US-005 · Como sistema, necesito autenticarme en Copernicus CDSE para poder buscar y descargar imágenes Sentinel-2.

**Sprint:** 4  
**Prioridad:** Crítica

Criterios de aceptación:
- El servicio obtiene un token OAuth2 válido de `identity.dataspace.copernicus.eu`
- El token se renueva automáticamente antes de expirar
- Si las credenciales son inválidas, devuelve `COPERNICUS_AUTH_ERROR` (503)
- Si el servicio de Copernicus no está disponible, devuelve el error correcto

---

### US-006 · Como sistema, necesito buscar escenas Sentinel-2 disponibles para un polígono y rango de fechas para saber qué imágenes puedo analizar.

**Sprint:** 4  
**Prioridad:** Crítica

Criterios de aceptación:
- La búsqueda filtra por polígono (intersección espacial) y rango de fechas
- Solo devuelve escenas con nubosidad < `max_cloud_coverage` de DynamoDB
- Si no hay escenas disponibles, devuelve `NO_SCENE_AVAILABLE` (404) con el rango de fechas intentado
- Devuelve la escena más reciente disponible dentro del rango

---

### US-007 · Como sistema, necesito descargar el tile Sentinel-2 en streaming y recortarlo al polígono del lote para obtener solo los datos necesarios.

**Sprint:** 5  
**Prioridad:** Crítica

Criterios de aceptación:
- La descarga usa streaming HTTP — en ningún momento el tile completo está en RAM
- Máximo 2 descargas simultáneas (semáforo)
- Si `/tmp/` supera 1.5 GB, rechaza la descarga con `STORAGE_PRESSURE`
- El tile se elimina inmediatamente después del recorte (bloque `finally`)
- El TIF recortado está en el CRS correcto y cubre exactamente el polígono del lote
- Si el polígono GeoJSON es inválido, devuelve `INVALID_POLYGON` (400)

---

### US-008 · Como sistema, necesito aplicar la máscara SCL para excluir píxeles de nube y sombra antes de calcular índices.

**Sprint:** 5  
**Prioridad:** Alta

Criterios de aceptación:
- Los píxeles clasificados como nube, sombra de nube, y agua se enmascaran correctamente
- Se calcula `valid_pixels_percentage` sobre el polígono del lote (no del tile completo)
- Si `valid_pixels_percentage < min_valid_pixels_percentage`, devuelve `INSUFFICIENT_VALID_PIXELS`
- Si la nubosidad es alta pero no bloquea, el análisis continúa con `confidence: low`

---

### US-009 · Como sistema, necesito calcular los índices espectrales solicitados y generar estadísticas por lote.

**Sprint:** 6  
**Prioridad:** Crítica

Criterios de aceptación:
- Solo se calculan los índices listados en el payload (no todos por defecto)
- Los 11 índices implementan las fórmulas exactas de `docs/ARQUITECTURA.md`
- Las estadísticas incluyen: min, max, mean, std, valid_pixels por índice
- Un índice no soportado genera warning en `unsupported_indices[]` sin fallar el análisis
- Los valores de los índices están en el rango teórico correcto (NDVI entre -1 y 1, etc.)

---

### US-010 · Como sistema, necesito generar PNGs de visualización de los índices para que los usuarios puedan ver el mapa del lote.

**Sprint:** 6  
**Prioridad:** Media

Criterios de aceptación:
- Solo se generan PNGs si `generate_png: true` en DynamoDB
- Cada índice genera un PNG con colormap apropiado (NDVI: verde, NDMI: azul, BSI: naranja)
- El PNG tiene las dimensiones del lote en píxeles (puede ser muy pequeño: 5×5 a 32×32 px)
- El PNG se escala a mínimo 256×256 px para visualización

---

### US-011 · Como sistema, necesito guardar los archivos del análisis en S3 y devolver las rutas al Microservicio IA.

**Sprint:** 7  
**Prioridad:** Crítica

Criterios de aceptación:
- TIF multibanda, PNGs y `statistics.json` se suben a `{base_path}/lots/{lot_id}/{YYYY-MM-DD}/`
- Si ya existe el análisis y `force_reprocess: false`, devuelve el existente (idempotencia)
- El `statistics.json` en S3 es exactamente el objeto `indices` del contrato de salida
- Las rutas S3 se incluyen en la respuesta final al caller
- Después de subir, llama a `POST :8002/analyze` con las estadísticas

---

### US-012 · Como directivo o ingeniero, necesito consultar el estado de un análisis en curso para saber si ya terminó.

**Sprint:** 7  
**Prioridad:** Alta

Criterios de aceptación:
- `GET /jobs/{job_id}/status` devuelve el estado: `pending`, `processing`, `completed`, `failed`
- `GET /lots/{lot_id}/results` devuelve el último análisis completado del lote
- Si el job no existe, devuelve 404 con mensaje claro

---

## Épica 3 — Microservicio IA

### US-013 · Como sistema, necesito que el Microservicio IA cargue su configuración desde DynamoDB para operar con el proveedor y umbrales correctos.

**Sprint:** 8  
**Prioridad:** Crítica

Criterios de aceptación:
- Mismas reglas que US-004 pero validando secciones `ai.*`, `agronomic_rules`, `laravel`
- `GET /health` incluye el estado de conectividad con el proveedor IA activo
- Si el proveedor IA no responde al health check, el servicio reporta `degraded` pero no falla

---

### US-014 · Como sistema, necesito leer el historial de análisis del lote desde S3 para calcular variaciones contra histórico.

**Sprint:** 9  
**Prioridad:** Alta

Criterios de aceptación:
- Se leen todos los `statistics.json` disponibles del lote en S3
- Se calcula la media histórica de cada índice
- Se calcula el cambio porcentual actual vs histórico
- Si hay menos de 2 análisis previos, `historical_data: null` y warning `INSUFFICIENT_HISTORY`
- El historial se procesa sin afectar el tiempo de respuesta del análisis actual

---

### US-015 · Como sistema, necesito aplicar las reglas agronómicas configuradas en DynamoDB para generar alertas y nivel de riesgo previo a la IA.

**Sprint:** 9  
**Prioridad:** Crítica

Criterios de aceptación:
- Las reglas usan los umbrales de `agronomic_rules.*` en DynamoDB — nunca hardcodeados
- Si existe `crops.{cultivo}`, usa esos umbrales; si no, usa los globales + warning
- Las alertas son textos descriptivos con el porcentaje de cambio (ej: "NDVI bajo -17.5%")
- El nivel de riesgo es uno de: `low`, `medium`, `medium_high`, `high`
- Las reglas producen resultado útil aunque no haya historial (usando solo valores absolutos)

---

### US-016 · Como sistema, necesito construir el prompt para la IA con toda la información relevante del lote y enviarlo a Anthropic.

**Sprint:** 10  
**Prioridad:** Crítica

Criterios de aceptación:
- El system prompt está en `prompts/system_prompt_agronomico.md` — versionado en git
- El payload incluye: índices actuales, histórico (si existe), alertas de reglas, contexto del lote (cultivo, etapa, área, clima)
- La llamada usa temperatura 0.2 y max_tokens 2500
- Si la respuesta no es JSON válido, reintenta una vez
- `provider_factory.py` selecciona el proveedor correcto según `ai.provider` en DynamoDB

---

### US-017 · Como sistema, necesito validar y normalizar la respuesta de la IA al formato estándar del contrato de salida.

**Sprint:** 10  
**Prioridad:** Alta

Criterios de aceptación:
- La respuesta debe tener: `risk_level`, `summary`, `probable_causes[]`, `recommendations[]`, `confidence`, `limitations[]`
- Si falta algún campo, el parser lo completa con valores por defecto razonables
- Si la respuesta es completamente inválida tras 2 intentos, error `AI_RESPONSE_INVALID`
- El `risk_level` de la IA se guarda junto al calculado por las reglas (pueden diferir)

---

### US-018 · Como sistema, necesito enviar el resultado completo a Laravel vía webhook con reintentos automáticos.

**Sprint:** 11  
**Prioridad:** Crítica

Criterios de aceptación:
- El webhook se firma con `HMAC-SHA256` usando `laravel.webhook_secret`
- Se reintenta 3 veces con backoff 5s → 15s → 45s si falla
- Si todos fallan, guarda el resultado en S3 como `pending_webhook_{job_id}.json`
- `POST /webhook/retry/{job_id}` reintenta la entrega manualmente
- El webhook nunca incluye credenciales ni secretos de DynamoDB

---

### US-019 · Como sistema, necesito que si el proveedor IA principal falla, se use el fallback configurado en DynamoDB.

**Sprint:** 11  
**Prioridad:** Alta

Criterios de aceptación:
- Si el proveedor principal devuelve error 5xx o timeout, se intenta el `fallback_provider`
- Si el fallback también falla, se devuelve el resultado de las reglas con warning `AI_PROVIDER_UNAVAILABLE`
- El resultado de las reglas siempre llega a Laravel aunque la IA falle
- Se registra qué proveedor produjo el resultado final (`meta.ai_provider`)

---

### US-020 · Como equipo de desarrollo, necesito que cada análisis guarde el payload completo de entrada y salida en S3 para auditoría.

**Sprint:** 11  
**Prioridad:** Alta

Criterios de aceptación:
- Se guarda en S3: `{base_path}/lots/{lot_id}/analyses/{job_id}.json`
- El archivo contiene: `config_version`, `ai_provider`, `ai_model`, `input_payload`, `rules_result`, `ai_result`, `warnings[]`, `timestamp`
- Se guarda incluso si el webhook falla
- La `config_version` corresponde al campo `version` del item de DynamoDB activo

---

### US-021 · Como directivo, necesito ver las alertas activas de todos los lotes para priorizar atención de campo.

**Sprint:** 11  
**Prioridad:** Media

Criterios de aceptación:
- `GET /alerts` devuelve todos los lotes con nivel de riesgo `medium_high` o `high` en el último análisis
- Ordenados por nivel de riesgo descendente, luego por fecha del análisis descendente
- Incluye: `lot_id`, `lot_name`, `risk_level`, `analysis_date`, `alerts[]`

---

## Épica 4 — Integración Laravel

### US-022 · Como desarrollador Laravel, necesito el servicio PHP para llamar al Microservicio TIF y gestionar el ciclo de vida del análisis.

**Sprint:** 12  
**Prioridad:** Alta

Criterios de aceptación:
- `AgroSentinelService.php` tiene métodos: `requestAnalysis()`, `getJobStatus()`, `getLotResults()`, `getAlerts()`
- Firma cada request con el `api_secret_key` correspondiente
- Maneja los errores estructurados del microservicio y los convierte a excepciones Laravel
- El panel muestra la lista de campos faltantes si el error es `CONFIG_VALIDATION_ERROR`

---

### US-023 · Como sistema Laravel, necesito recibir el webhook del Microservicio IA y guardar el resultado en la base de datos.

**Sprint:** 12  
**Prioridad:** Alta

Criterios de aceptación:
- El endpoint `POST /api/sentinel/webhook` valida la firma HMAC-SHA256
- Guarda el resultado en la tabla `ia_analisis` con todos los campos del dominio
- Devuelve 200 al webhook para que no se reintente innecesariamente
- Si hay un análisis previo del mismo lote y fecha, actualiza en lugar de duplicar

---

### US-024 · Como directivo o ingeniero, necesito ver el historial de análisis de un lote en el ERP con los diagnósticos y recomendaciones.

**Sprint:** 12  
**Prioridad:** Media

Criterios de aceptación:
- La vista del lote muestra los últimos N análisis con fecha, riesgo, summary y recomendaciones
- Se puede iniciar un nuevo análisis desde la misma vista
- Los PNGs de los índices se muestran como imágenes con URL firmada de S3
- Los alertas activas se muestran con badge de color según nivel de riesgo

---

## Backlog futuro (no en scope actual)

Estas historias están identificadas pero no forman parte del desarrollo inicial:

- **US-F01** · Análisis comparativo entre dos fechas del mismo lote (antes/después de riego, helada, etc.)
- **US-F02** · Generación de reportes PDF con todos los índices y el diagnóstico IA
- **US-F03** · Notificaciones automáticas por email/SMS cuando el riesgo sube a `high`
- **US-F04** · API multiempresa (campo `tenant` en la pk de DynamoDB)
- **US-F05** · Migración del Microservicio IA a vLLM cuando el volumen justifique GPU propia
- **US-F06** · Dashboard de estadísticas agregadas por empresa, cultivo y región
- **US-F07** · Integración con estaciones meteorológicas propias para reemplazar `weather_context`
- **US-F08** · Soporte para imágenes de drone de alta resolución como alternativa a Sentinel-2

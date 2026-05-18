# AgroSentinel — Decisiones de Diseño (ADR)

Architecture Decision Records. Cada decisión importante está documentada aquí
para que cualquier IA o desarrollador entienda el razonamiento sin tener que deducirlo.

---

## ADR-001 — Dos microservicios en lugar de uno

**Fecha:** 2026-05-18  
**Estado:** Aceptada

**Contexto:** El sistema necesita procesar imágenes geoespaciales con GDAL/rasterio Y hacer llamadas a LLMs. Estas dos responsabilidades tienen dependencias incompatibles, ciclos de vida distintos y necesidades de memoria muy diferentes.

**Decisión:** Dos microservicios independientes: TIF (geoespacial) e IA (análisis).

**Consecuencias:**
- El TIF necesita GDAL instalado en el sistema; la IA no.
- Cada uno escala independientemente — si el volumen de análisis IA crece, solo se escala ese droplet.
- La comunicación es por HTTP y S3, no memoria compartida.
- Regla inviolable: el TIF no importa `anthropic`; la IA no importa `rasterio`.

---

## ADR-009 — AgroSentinel es un servicio externo independiente de Laravel

**Fecha:** 2026-05-18  
**Estado:** Aceptada

**Contexto:** Necesitamos decidir si AgroSentinel corre en el mismo servidor que Laravel o en su propio servidor.

**Decisión:** AgroSentinel corre en su propio servidor (dos Droplets DigitalOcean). Laravel lo consume como API externa, igual que consumiría Stripe o SendGrid.

**Razonamiento:**
- El Microservicio TIF necesita GDAL y descarga tiles de ~1 GB — contaminaría el servidor de Laravel con dependencias del sistema no relacionadas al ERP.
- Laravel puede quedarse sin memoria o CPU durante una descarga larga si comparten servidor.
- Desplegar AgroSentinel de forma independiente permite actualizarlo sin afectar el ERP.
- La separación es explícita: Laravel no conoce nada interno de AgroSentinel — solo las URLs y las claves.

**Consecuencias:**
- La comunicación es HTTPS sobre internet (o red privada de DO).
- El webhook llega desde una IP externa — Laravel debe tenerlo en su firewall/allowlist.
- Las URLs se configuran en `.env` de Laravel: `AGRO_SENTINEL_TIF_URL` y `AGRO_SENTINEL_IA_URL`.
- Si AgroSentinel no está disponible, Laravel debe manejar el error con un mensaje claro — no propagarlo como 500.

---

## ADR-002 — Configuración en DynamoDB, no en .env

**Fecha:** 2026-05-18  
**Estado:** Aceptada

**Contexto:** La configuración operativa (umbrales agronómicos, proveedor IA, credenciales de Copernicus) necesita poder cambiarse sin redesplegar los servicios.

**Decisión:** El `.env` solo tiene las 6 variables mínimas para encontrar DynamoDB. Todo lo demás vive en un item de DynamoDB con `pk=production, sk=active`.

**Consecuencias:**
- Cambiar el proveedor de IA de Anthropic a Ollama = cambiar `ai.provider` en DynamoDB + esperar TTL.
- Los servicios tienen caché en memoria por `CONFIG_CACHE_TTL_SECONDS` (default 300s).
- `POST /internal/config/refresh` fuerza recarga sin reiniciar el servicio.
- Nunca hay que hacer SSH a los servidores para cambiar parámetros agronómicos.

---

## ADR-003 — Anthropic API en lugar de Ollama para producción

**Fecha:** 2026-05-18  
**Estado:** Aceptada

**Contexto:** Se evaluó Ollama (modelo local) vs API de Anthropic para el análisis IA.

**Decisión:** Anthropic API (`claude-sonnet-4-5`) para producción.

**Razonamiento:**
- Con 2–3 análisis diarios el costo es ~$0.01–0.03/análisis = $5–15 USD/mes total.
- No hay GPU que mantener, no hay servidor que escalar, no hay modelo que actualizar.
- La calidad de diagnóstico agronómico es superior con un modelo de frontera.
- El campo `ai.provider` en DynamoDB permite migrar a vLLM sin tocar código.

**Punto de revisión:** Cuando el volumen supere ~500 análisis/mes, evaluar vLLM con GPU propia (~$150/mes fijo vs ~$15/mes variable).

---

## ADR-004 — Droplet $12 para TIF, $7 para IA

**Fecha:** 2026-05-18  
**Estado:** Aceptada

**Contexto:** El Microservicio TIF descarga tiles de ~1 GB aunque el resultado final sea de 500 KB–2 MB.

**Decisión:** TIF en Droplet de 2 GB RAM ($12/mes); IA en Droplet de 1 GB RAM ($7/mes).

**Razonamiento TIF:** Con 2 descargas simultáneas y el overhead de rasterio, 1 GB no tiene margen. 2 GB da holgura sin necesidad de optimizar desde el día uno.

**Razonamiento IA:** Este servicio solo hace llamadas HTTP y procesa JSON. 1 GB es suficiente para 20+ usuarios simultáneos dado que es completamente stateless.

**Punto de revisión:** Si hay más de 5 solicitudes simultáneas frecuentes en TIF, subir a Droplet de 4 GB ($24).

---

## ADR-005 — Jobs asincrónicos sin base de datos

**Fecha:** 2026-05-18  
**Estado:** Aceptada

**Contexto:** `POST /analyze` puede tardar 2–10 minutos (descarga del tile). No se puede bloquear el cliente esperando.

**Decisión:** `POST /analyze` devuelve 202 inmediatamente con `job_id`. El análisis corre en background con `asyncio.create_task`. El estado se guarda en un dict en memoria.

**Consecuencias:**
- Si el servicio se reinicia, los jobs en progreso se pierden. El cliente debe consultar el estado y reintentar si es necesario.
- No hay base de datos en los microservicios — el estado persiste en S3 (resultado final) y en la memoria del proceso (estado del job).
- Aceptable para el volumen actual (2–3 usuarios, pocos análisis diarios).

**Punto de revisión:** Si se necesita persistencia de estado entre reinicios, agregar Redis o una tabla DynamoDB de jobs.

---

## ADR-006 — Idempotencia basada en S3

**Fecha:** 2026-05-18  
**Estado:** Aceptada

**Contexto:** Si un análisis ya existe para un lote y fecha, no tiene sentido descargar el tile de nuevo.

**Decisión:** Antes de cualquier procesamiento, verificar si `{base_path}/lots/{lot_id}/{date}/statistics.json` existe en S3. Si existe y `force_reprocess=false`, devolver el resultado guardado.

**Consecuencias:**
- Una llamada duplicada cuesta ~100ms (verificar S3) en lugar de 2–10 minutos.
- El cliente puede llamar múltiples veces con el mismo job_id sin efectos negativos.
- `force_reprocess=true` fuerza el reprocesamiento incluso si existe el resultado.

---

## ADR-007 — Webhook con firma HMAC en lugar de autenticación mutua TLS

**Fecha:** 2026-05-18  
**Estado:** Aceptada

**Contexto:** El Microservicio IA necesita notificar a Laravel cuando termina un análisis.

**Decisión:** Webhook HTTP con firma HMAC-SHA256 en el header `X-AgroSentinel-Signature`.

**Razonamiento:** mTLS requiere gestión de certificados. HMAC es simple, battle-tested (usado por GitHub, Stripe) y suficiente para este nivel de seguridad. El secret se configura en DynamoDB y en el `.env` de Laravel.

---

## ADR-008 — Sin base de datos relacional en los microservicios Python

**Fecha:** 2026-05-18  
**Estado:** Aceptada

**Contexto:** Los microservicios necesitan almacenamiento persistente para los resultados.

**Decisión:** S3 como almacenamiento de objetos. No hay PostgreSQL, MySQL ni RDS en los microservicios.

**Razonamiento:**
- Los datos son archivos (TIF, PNG, JSON) — S3 es el almacenamiento natural.
- Evita una dependencia de infraestructura adicional (RDS = ~$25/mes mínimo).
- Laravel ya tiene su propia base de datos. Los microservicios guardan en S3 y notifican a Laravel, que guarda lo relevante en su BD.
- Si en el futuro se necesita búsqueda avanzada sobre el historial, agregar una tabla DynamoDB de análisis — sin cambiar la arquitectura base.

---

## Decisiones pendientes de revisión

| Decisión | Cuándo revisar | Trigger |
|---|---|---|
| ADR-003: Anthropic vs vLLM | Cuando volumen > 500 análisis/mes | Costo mensual IA > $50 |
| ADR-004: Tamaño de Droplets | Cuando hay > 5 solicitudes simultáneas | CPU/RAM > 80% sostenido |
| ADR-005: Jobs en memoria | Cuando se necesiten reintentos automáticos | Job perdido por reinicio > 1 vez/semana |
| ADR-008: S3 sin BD | Cuando se necesite búsqueda histórica compleja | Consultas que tarden > 2s en S3 |
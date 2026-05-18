# AgroSentinel — Guía de Entorno Local

Instrucciones para levantar el entorno de desarrollo completo desde cero.
Tiempo estimado: 30–45 minutos la primera vez.

---

## Requisitos del sistema

| Herramienta | Versión mínima | Para qué |
|---|---|---|
| Docker | 24+ | Contenerización de servicios |
| Docker Compose | 2.20+ | Orquestación local |
| AWS CLI | 2.x | Gestión de DynamoDB Local y S3 |
| Python | 3.11+ | Solo si desarrollas fuera de Docker |
| Git | 2.x | Control de versiones |

Para verificar:
```bash
docker --version
docker compose version
aws --version
python3 --version
```

---

## Paso 1 — Clonar y configurar variables de entorno

```bash
git clone [URL_DEL_REPOSITORIO]
cd agro-sentinel
```

Crear `.env` para cada microservicio copiando los ejemplos:
```bash
cp microservicio-tif/.env.example microservicio-tif/.env
cp microservicio-ia/.env.example microservicio-ia/.env
```

Contenido mínimo de `microservicio-tif/.env`:
```env
APP_ENV=local
AWS_REGION=us-east-1
CONFIG_TABLE_NAME=agro_sentinel_config
CONFIG_PARTITION_KEY=local
CONFIG_SORT_KEY=active
CONFIG_CACHE_TTL_SECONDS=60
CONFIG_FAIL_FAST=true
```

Contenido mínimo de `microservicio-ia/.env`:
```env
APP_ENV=local
AWS_REGION=us-east-1
CONFIG_TABLE_NAME=agro_sentinel_config
CONFIG_PARTITION_KEY=local
CONFIG_SORT_KEY=active
CONFIG_CACHE_TTL_SECONDS=60
CONFIG_FAIL_FAST=true
IA_SERVICE_URL=http://agro-ia:8002
```

Los valores de `DYNAMODB_ENDPOINT_URL` los inyecta `docker-compose.yml` automáticamente.

---

## Paso 2 — Preparar el item de configuración local

Editar `scripts/config-local.json` y completar las credenciales reales de Copernicus:
```json
{
  "pk": {"S": "local"},
  "sk": {"S": "active"},
  "version": {"N": "1"},
  "enabled": {"BOOL": true},
  "copernicus": {
    "M": {
      "client_id": {"S": "TU-CLIENT-ID-REAL"},
      "client_secret": {"S": "TU-CLIENT-SECRET-REAL"},
      ...
    }
  }
}
```

El archivo completo está en `docs/DYNAMODB_CONFIG.md` (sección "Item para desarrollo local"). Las credenciales de Copernicus son reales incluso en local — son las mismas que en producción.

---

## Paso 3 — Levantar los servicios

```bash
# Primera vez: construir las imágenes
docker compose build

# Levantar todo en background
docker compose up -d

# Ver logs en tiempo real
docker compose logs -f

# Solo ver logs de un servicio
docker compose logs -f agro-tif
docker compose logs -f agro-ia
```

---

## Paso 4 — Insertar configuración en DynamoDB Local

```bash
# Esperar 5 segundos para que DynamoDB Local arranque
sleep 5

# Crear tabla e insertar item
bash scripts/setup_local_dynamo.sh
```

Verificar:
```bash
aws dynamodb get-item \
  --endpoint-url http://localhost:8005 \
  --table-name agro_sentinel_config \
  --key '{"pk": {"S": "local"}, "sk": {"S": "active"}}' \
  --region us-east-1
```

---

## Paso 5 — Verificar que todo funciona

```bash
# Health del Microservicio TIF
curl -s http://localhost:8001/health | python3 -m json.tool

# Health del Microservicio IA
curl -s http://localhost:8002/health | python3 -m json.tool

# Validar configuración TIF
curl -s -H "Authorization: Bearer dev-token" \
  http://localhost:8001/internal/config/validate | python3 -m json.tool

# Validar configuración IA
curl -s -H "Authorization: Bearer dev-token" \
  http://localhost:8002/internal/config/validate | python3 -m json.tool
```

Respuesta esperada en cada health:
```json
{
  "status": "ok",
  "config": { "loaded": true, "valid": true }
}
```

---

## Paso 6 — Ejecutar un análisis de prueba

Una vez que el Sprint 7 esté completado, usar el polígono de prueba:

```bash
curl -s -X POST http://localhost:8001/analyze \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-secret-123" \
  -d @scripts/test_analyze_request.json | python3 -m json.tool
```

Contenido de `scripts/test_analyze_request.json`:
```json
{
  "lot_id": 1,
  "polygon_geojson": {
    "type": "Polygon",
    "coordinates": [[
      [-102.2950, 21.8850],
      [-102.2850, 21.8850],
      [-102.2850, 21.8780],
      [-102.2950, 21.8780],
      [-102.2950, 21.8850]
    ]]
  },
  "dates": ["2026-01-01", "2026-01-31"],
  "indices": ["NDVI", "NDMI", "NDRE"],
  "force_reprocess": false
}
```

---

## Comandos frecuentes

```bash
# Reiniciar un servicio específico
docker compose restart agro-tif

# Reconstruir imagen después de cambiar requirements.txt
docker compose build agro-tif && docker compose up -d agro-tif

# Acceder al shell de un contenedor
docker compose exec agro-tif bash
docker compose exec agro-ia bash

# Ver el uso de recursos
docker stats

# Limpiar todo y empezar de cero
docker compose down -v
docker compose build --no-cache
docker compose up -d
sleep 5 && bash scripts/setup_local_dynamo.sh

# Ejecutar tests dentro del contenedor
docker compose exec agro-tif pytest tests/unit/ -v
docker compose exec agro-ia pytest tests/unit/ -v
```

---

## Solución de problemas comunes

**El servicio arranca pero `/health` devuelve `config.valid: false`**
→ DynamoDB Local no tiene el item. Ejecutar `bash scripts/setup_local_dynamo.sh`.

**`COPERNICUS_AUTH_ERROR` en el primer análisis**
→ Verificar que `config-local.json` tiene las credenciales reales de Copernicus, no los valores placeholder.

**El tile no se descarga y el análisis queda en `processing` para siempre**
→ Verificar conectividad con Copernicus: `curl https://identity.dataspace.copernicus.eu` debe responder.

**`RASTERIO_CROP_ERROR` al recortar**
→ Verificar que el polígono GeoJSON está cerrado (primer y último punto iguales) y está en EPSG:4326.

**El Microservicio IA no recibe el webhook del TIF**
→ En Docker, los servicios se comunican por nombre de contenedor. Verificar que `IA_SERVICE_URL=http://agro-ia:8002` (no `localhost`).

**`AI_PROVIDER_UNAVAILABLE` en todos los análisis**
→ Verificar la API key de Anthropic en `config-local.json`. En local se puede cambiar temporalmente `ai.provider` a `ollama` si tienes Ollama corriendo en el host.

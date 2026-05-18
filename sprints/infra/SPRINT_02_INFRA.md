# Sprint 2 — Infraestructura: Droplets + Docker + estructura de proyectos

**Duración:** 1 semana  
**Prerequisito:** Sprint 1 completado (DynamoDB y S3 listos)  
**Objetivo:** Tener ambos proyectos Python con su estructura de carpetas, Dockerfiles y un `docker-compose.yml` local funcional.  
**Historias:** US-003  
**Entregable:** Ambos microservicios levantan en Docker con `GET /health` respondiendo 200.

---

## Contexto para la IA

En este sprint se crean los dos proyectos Python vacíos pero con toda la estructura de carpetas definida en `docs/ARQUITECTURA.md`. Los servicios arrancan pero los endpoints aún no tienen lógica real — solo responden 200 en `/health`. La lógica llega en los sprints siguientes.

El objetivo es tener el andamiaje listo para que cada sprint siguiente solo agregue archivos o modifique los existentes sin reorganizar nada.

---

## Tarea 2.1 — Estructura del Microservicio TIF

Crear la siguiente estructura de carpetas y archivos vacíos/stub:

```
microservicio-tif/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   └── exceptions.py
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes/
│   │       ├── __init__.py
│   │       ├── analyze.py
│   │       ├── jobs.py
│   │       ├── lots.py
│   │       ├── health.py
│   │       └── internal.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── configuration/
│   │   │   ├── __init__.py
│   │   │   ├── config_loader.py
│   │   │   ├── config_validator.py
│   │   │   └── schemas.py
│   │   ├── copernicus/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py
│   │   │   ├── scene_search.py
│   │   │   └── tile_downloader.py
│   │   ├── processing/
│   │   │   ├── __init__.py
│   │   │   ├── cropper.py
│   │   │   ├── cloud_mask.py
│   │   │   ├── index_calculator.py
│   │   │   ├── statistics.py
│   │   │   └── png_renderer.py
│   │   └── storage/
│   │       ├── __init__.py
│   │       ├── s3_client.py
│   │       └── temp_manager.py
│   └── models/
│       ├── __init__.py
│       ├── requests.py
│       └── responses.py
├── tests/
│   ├── __init__.py
│   ├── unit/
│   │   └── __init__.py
│   └── integration/
│       └── __init__.py
├── .env.example
├── requirements.txt
└── Dockerfile
```

Contenido mínimo de `app/main.py`:
```python
from fastapi import FastAPI

app = FastAPI(title="AgroSentinel TIF Service", version="0.1.0")

@app.get("/health")
async def health():
    return {"status": "ok", "service": "agro-sentinel-tif", "version": "0.1.0"}
```

Contenido de `requirements.txt`:
```
fastapi==0.111.0
uvicorn[standard]==0.29.0
pydantic[email]==2.7.0
boto3==1.34.0
httpx==0.27.0
rasterio==1.3.10
numpy==1.26.4
python-dotenv==1.0.1
```

Contenido de `.env.example`:
```env
APP_ENV=local
AWS_REGION=us-east-1
CONFIG_TABLE_NAME=agro_sentinel_config
CONFIG_PARTITION_KEY=local
CONFIG_SORT_KEY=active
CONFIG_CACHE_TTL_SECONDS=60
CONFIG_FAIL_FAST=true
# Solo para desarrollo local:
DYNAMODB_ENDPOINT_URL=http://dynamodb-local:8000
```

Contenido de `Dockerfile`:
```dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    gdal-bin \
    libgdal-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

ENV GDAL_VERSION=3.8.4
ENV CPLUS_INCLUDE_PATH=/usr/include/gdal
ENV C_INCLUDE_PATH=/usr/include/gdal

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
```

DoD: `docker build -t agro-tif .` construye sin errores.

---

## Tarea 2.2 — Estructura del Microservicio IA

```
microservicio-ia/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   └── exceptions.py
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes/
│   │       ├── __init__.py
│   │       ├── analyze.py
│   │       ├── jobs.py
│   │       ├── lots.py
│   │       ├── alerts.py
│   │       ├── webhook.py
│   │       ├── health.py
│   │       └── internal.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── configuration/
│   │   │   ├── __init__.py
│   │   │   ├── config_loader.py
│   │   │   ├── config_validator.py
│   │   │   └── schemas.py
│   │   ├── agronomic/
│   │   │   ├── __init__.py
│   │   │   ├── rules_engine.py
│   │   │   ├── history_reader.py
│   │   │   └── risk_calculator.py
│   │   ├── ai/
│   │   │   ├── __init__.py
│   │   │   ├── prompt_builder.py
│   │   │   ├── anthropic_client.py
│   │   │   ├── response_parser.py
│   │   │   └── provider_factory.py
│   │   ├── webhook/
│   │   │   ├── __init__.py
│   │   │   └── laravel_notifier.py
│   │   └── storage/
│   │       ├── __init__.py
│   │       └── s3_client.py
│   └── models/
│       ├── __init__.py
│       ├── requests.py
│       └── responses.py
├── prompts/
│   └── system_prompt_agronomico.md
├── tests/
│   ├── __init__.py
│   ├── unit/
│   │   └── __init__.py
│   └── integration/
│       └── __init__.py
├── .env.example
├── requirements.txt
└── Dockerfile
```

`requirements.txt` del Microservicio IA:
```
fastapi==0.111.0
uvicorn[standard]==0.29.0
pydantic[email]==2.7.0
boto3==1.34.0
httpx==0.27.0
tenacity==8.3.0
python-dotenv==1.0.1
```

`Dockerfile` del Microservicio IA (sin GDAL):
```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8002
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
```

Contenido inicial de `prompts/system_prompt_agronomico.md`:
```markdown
Eres un sistema experto en análisis de cultivos agrícolas por teledetección satelital.
Recibirás datos de índices espectrales calculados desde imágenes Sentinel-2 para un lote agrícola en México.
Tu tarea es analizar los datos, identificar causas probables de cualquier anomalía detectada y
generar recomendaciones concretas y accionables para el responsable del lote.

Responde ÚNICAMENTE con un objeto JSON válido con esta estructura exacta:
{
  "risk_level": "low|medium|medium_high|high",
  "summary": "Resumen de 1-3 oraciones del estado del lote.",
  "probable_causes": ["causa 1", "causa 2"],
  "recommendations": ["acción 1", "acción 2", "acción 3"],
  "confidence": "low|medium|high",
  "limitations": ["limitación 1"]
}

No incluyas texto fuera del JSON. No uses bloques de código markdown.
```

DoD: `docker build -t agro-ia .` construye sin errores.

---

## Tarea 2.3 — docker-compose.yml local

Crear en la raíz del repositorio:

```yaml
version: "3.9"

services:

  dynamodb-local:
    image: amazon/dynamodb-local:latest
    container_name: agro-dynamodb-local
    ports:
      - "8005:8000"
    command: ["-jar", "DynamoDBLocal.jar", "-inMemory", "-sharedDb"]

  agro-tif:
    build:
      context: ./microservicio-tif
    container_name: agro-tif
    ports:
      - "8001:8001"
    env_file:
      - ./microservicio-tif/.env
    environment:
      - DYNAMODB_ENDPOINT_URL=http://dynamodb-local:8000
    depends_on:
      - dynamodb-local
    volumes:
      - /tmp/agro-tif:/tmp

  agro-ia:
    build:
      context: ./microservicio-ia
    container_name: agro-ia
    ports:
      - "8002:8002"
    env_file:
      - ./microservicio-ia/.env
    environment:
      - DYNAMODB_ENDPOINT_URL=http://dynamodb-local:8000
    depends_on:
      - dynamodb-local
```

---

## Tarea 2.4 — Script de setup local

Crear `scripts/setup_local_dynamo.sh`:

```bash
#!/bin/bash
# Inserta los items de configuración en DynamoDB Local
# Ejecutar después de levantar docker-compose

ENDPOINT="http://localhost:8005"

echo "Creando tabla..."
aws dynamodb create-table \
  --endpoint-url $ENDPOINT \
  --table-name agro_sentinel_config \
  --attribute-definitions \
    AttributeName=pk,AttributeType=S \
    AttributeName=sk,AttributeType=S \
  --key-schema \
    AttributeName=pk,KeyType=HASH \
    AttributeName=sk,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST \
  --region us-east-1

echo "Insertando item local..."
aws dynamodb put-item \
  --endpoint-url $ENDPOINT \
  --table-name agro_sentinel_config \
  --item file://scripts/config-local.json \
  --region us-east-1

echo "Setup completado."
```

DoD: ejecutar el script e insertar el item de desarrollo en DynamoDB Local.

---

## Verificación final del sprint

```bash
# Levantar todo
docker-compose up -d

# Esperar 10 segundos e insertar config
sleep 10 && bash scripts/setup_local_dynamo.sh

# Verificar TIF
curl http://localhost:8001/health
# Esperado: {"status": "ok", "service": "agro-sentinel-tif", ...}

# Verificar IA
curl http://localhost:8002/health
# Esperado: {"status": "ok", "service": "agro-sentinel-ia", ...}
```

---

## Estado de tareas

| Tarea | Descripción | Estado |
|---|---|---|
| 2.1 | Estructura Microservicio TIF | ⬜ |
| 2.2 | Estructura Microservicio IA | ⬜ |
| 2.3 | docker-compose.yml | ⬜ |
| 2.4 | Script setup local DynamoDB | ⬜ |
| — | Verificación final | ⬜ |

**Sprint completado:** ⬜

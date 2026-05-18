# Sprint 7 — TIF: S3 Upload + Orchestrator + Endpoints Finales

**Duración:** 1 semana  
**Prerequisito:** Sprint 6 completado  
**Objetivo:** El Microservicio TIF está completo y funcional de extremo a extremo.  
**Historias:** US-011, US-012  
**Entregable:** `POST /analyze` procesa un lote real, guarda en S3 y llama al Microservicio IA.

---

## Contexto para la IA

Este sprint une todos los servicios anteriores en un orquestador central. El flujo completo debe funcionar en un solo `POST /analyze`. Los jobs se procesan en background con `asyncio.create_task` — el endpoint devuelve 202 inmediatamente.

El estado de los jobs se guarda en memoria con un dict protegido por `asyncio.Lock`. No hay base de datos en este microservicio.

Al terminar el análisis, el orquestador llama a `POST http://agro-ia:8002/analyze`. La URL del Microservicio IA se lee desde la configuración del `.env` (no de DynamoDB):
```env
IA_SERVICE_URL=http://agro-ia:8002
```

---

## Archivos a implementar

### `app/services/storage/s3_client.py`

```python
import boto3
import json
from app.core.config import env

class S3Client:
    def __init__(self, bucket: str, base_path: str, region: str):
        self._s3 = boto3.client("s3", region_name=region)
        self.bucket = bucket
        self.base_path = base_path

    def build_key(self, lot_id: int, date: str, filename: str) -> str:
        return f"{self.base_path}/lots/{lot_id}/{date}/{filename}"

    async def file_exists(self, s3_key: str) -> bool:
        try:
            self._s3.head_object(Bucket=self.bucket, Key=s3_key)
            return True
        except self._s3.exceptions.ClientError:
            return False

    async def upload_file(self, local_path: str, s3_key: str) -> str:
        self._s3.upload_file(local_path, self.bucket, s3_key)
        return f"s3://{self.bucket}/{s3_key}"

    async def upload_json(self, data: dict, s3_key: str) -> str:
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self._s3.put_object(Bucket=self.bucket, Key=s3_key, Body=body, ContentType="application/json")
        return f"s3://{self.bucket}/{s3_key}"

    async def download_json(self, s3_key: str) -> dict:
        response = self._s3.get_object(Bucket=self.bucket, Key=s3_key)
        return json.loads(response["Body"].read().decode("utf-8"))
```

### `app/services/analysis_orchestrator.py`

Orquesta todos los pasos en orden estricto:

```python
class AnalysisOrchestrator:
    async def run(self, request: AnalyzeRequest, job_id: str) -> dict:
        config = await self.config_loader.get_config()

        # 1. Idempotencia
        stats_key = self.s3.build_key(request.lot_id, "...", "statistics.json")
        if not request.force_reprocess and await self.s3.file_exists(stats_key):
            existing = await self.s3.download_json(stats_key)
            return {**existing, "from_cache": True}

        # 2. Verificar presión de disco
        self.temp_manager.check_pressure()

        # 3. Auth Copernicus
        token = await self.auth_service.get_token()

        # 4. Buscar escena
        scene = await self.scene_search.find_best_scene(
            polygon_geojson=request.polygon_geojson,
            date_start=request.dates[0],
            date_end=request.dates[1],
            max_cloud_coverage=config["copernicus"]["max_cloud_coverage"]
        )

        # 5. Descargar tile (con semáforo)
        async with self.download_semaphore:
            tile_path = str(self.temp_manager.job_path(job_id) / "tile.zip")
            try:
                await self.downloader.download_tile(scene["product_id"], token, tile_path)

                # 6. Recortar
                tif_path = str(self.temp_manager.job_path(job_id) / "multiband.tif")
                crop_result = crop_tile_to_polygon(tile_path, request.polygon_geojson, tif_path)

            finally:
                # 7. Eliminar tile SIEMPRE
                if os.path.exists(tile_path):
                    os.remove(tile_path)

        # 8. Máscara SCL
        quality = apply_scl_mask(tif_path, scl_band_index=11)

        # 9. Validar píxeles válidos
        min_valid = config["processing"]["min_valid_pixels_percentage"]
        if quality["valid_percentage"] < min_valid:
            raise InsufficientValidPixelsError(...)

        # 10. Calcular índices
        index_arrays, unsupported = calculate_indices(
            tif_path, request.indices, quality["mask_array"]
        )

        # 11. Estadísticas
        stats = compute_statistics(index_arrays)

        # 12. PNGs (si aplica)
        png_paths = {}
        if config["processing"].get("generate_png"):
            for name, array in index_arrays.items():
                png_path = str(self.temp_manager.job_path(job_id) / f"{name}.png")
                render_index_png(array, name, png_path)
                png_paths[name] = png_path

        # 13. Upload S3
        analysis_date = scene["acquisition_date"]
        s3_paths = {}
        s3_paths["tif"] = await self.s3.upload_file(tif_path, self.s3.build_key(request.lot_id, analysis_date, "multiband.tif"))
        s3_paths["statistics"] = await self.s3.upload_json(stats, self.s3.build_key(request.lot_id, analysis_date, "statistics.json"))
        for name, path in png_paths.items():
            s3_paths[f"png_{name}"] = await self.s3.upload_file(path, self.s3.build_key(request.lot_id, analysis_date, f"{name}.png"))

        # 14. Limpiar temp
        self.temp_manager.cleanup_job(job_id)

        result = {
            "ok": True,
            "job_id": job_id,
            "lot_id": request.lot_id,
            "analysis_date": analysis_date,
            "image_quality": quality,
            "indices": stats,
            "s3_paths": s3_paths,
            "unsupported_indices": unsupported,
            "from_cache": False
        }

        # 15. Llamar al Microservicio IA
        await self._notify_ia_service(result, request)

        return result
```

### `app/api/routes/analyze.py`

```python
@router.post("/analyze", status_code=202)
async def analyze(request: AnalyzeRequest, background_tasks: BackgroundTasks):
    job_id = request.job_id or str(ulid.new())
    job_store.set_status(job_id, "processing")

    async def run_analysis():
        try:
            result = await orchestrator.run(request, job_id)
            job_store.set_result(job_id, result)
        except AgroSentinelError as e:
            job_store.set_error(job_id, e)

    asyncio.create_task(run_analysis())
    return {"job_id": job_id, "status": "processing"}
```

### `app/api/routes/jobs.py`

```
GET /jobs/{job_id}/status
```
Lee del `job_store` en memoria. Devuelve `pending | processing | completed | failed` con el resultado o error si está disponible.

### `app/api/routes/lots.py`

```
GET /lots/{lot_id}/results
```
Lee el `statistics.json` más reciente del lote desde S3 (listando `{base_path}/lots/{lot_id}/` y tomando la fecha más reciente).

---

## Criterios de aceptación

- [ ] `POST /analyze` devuelve 202 en menos de 200ms y procesa en background
- [ ] `GET /jobs/{job_id}/status` devuelve `completed` cuando termina con el resultado completo
- [ ] El `statistics.json` existe en S3 con la ruta correcta después del análisis
- [ ] Si ya existe en S3 y `force_reprocess: false`, devuelve el guardado en < 1 segundo sin descargar nada
- [ ] El tile completo no existe en `/tmp/` al terminar (exitoso o fallido)
- [ ] El Microservicio IA recibe el payload correcto (verificar con mock en puerto 8002)
- [ ] Un análisis completo del lote de prueba termina en menos de 5 minutos

---

## Estado de tareas

| Archivo | Estado |
|---|---|
| `app/services/storage/s3_client.py` | ⬜ |
| `app/services/analysis_orchestrator.py` | ⬜ |
| `app/api/routes/analyze.py` | ⬜ |
| `app/api/routes/jobs.py` | ⬜ |
| `app/api/routes/lots.py` | ⬜ |
| Test integración flujo completo end-to-end | ⬜ |

**Sprint completado:** ⬜

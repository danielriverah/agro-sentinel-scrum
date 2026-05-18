# Sprint 5 — TIF: Descarga Streaming + Recorte rasterio + Máscara SCL

**Duración:** 1–2 semanas  
**Prerequisito:** Sprint 4 completado  
**Objetivo:** Descargar el tile de Copernicus en streaming, recortarlo al polígono del lote y aplicar la máscara SCL.  
**Historias:** US-007, US-008  
**Entregable:** Dado el lote de prueba, genera el TIF multibanda recortado y el porcentaje de píxeles válidos.

---

## Contexto crítico para la IA

Este es el sprint técnicamente más delicado. Puntos que no pueden salir mal:

**Descarga streaming:** Usar `httpx.AsyncClient` con `stream=True` y chunks de 8 MB. El tile completo nunca debe estar en RAM simultaneamente. Endpoint de descarga de Copernicus OData:
```
GET https://catalogue.dataspace.copernicus.eu/odata/v1/Products({product_id})/$value
Authorization: Bearer {token}
```

**Reproyección del polígono:** El polígono llega en EPSG:4326 (lat/lon). El tile Sentinel-2 está en UTM (ej. EPSG:32614 para México central). Antes de recortar con rasterio hay que reprojectar el polígono al CRS del tile usando `pyproj.Transformer` o `rasterio.warp.transform_geom`.

**Máscara SCL:** Valores a enmascarar (píxeles inválidos):
- 0: Sin datos, 1: Defectuosos, 3: Sombras de nubes
- 8: Nubes media prob., 9: Nubes alta prob., 10: Cirrus

**Semáforo global:** Declarar en `app/main.py` como estado compartido:
```python
from app.core.state import AppState
app_state = AppState()
```
Con `download_semaphore = asyncio.Semaphore(2)` dentro de `AppState`.

---

## Archivos a implementar

### `app/services/storage/temp_manager.py`

```python
import shutil
import os
from pathlib import Path
from app.core.exceptions import StoragePressureError

class TempManager:
    def __init__(self, base_path: str = "/tmp/agro-tif"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def job_path(self, job_id: str) -> Path:
        path = self.base_path / job_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_disk_usage_gb(self) -> float:
        total = sum(f.stat().st_size for f in self.base_path.rglob("*") if f.is_file())
        return total / (1024 ** 3)

    def check_pressure(self, limit_gb: float = 1.5) -> None:
        usage = self.get_disk_usage_gb()
        if usage >= limit_gb:
            raise StoragePressureError(
                f"Disco temporal en {usage:.2f} GB — límite es {limit_gb} GB",
                details={"usage_gb": usage, "limit_gb": limit_gb}
            )

    def cleanup_job(self, job_id: str) -> None:
        path = self.base_path / job_id
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
```

### `app/services/copernicus/tile_downloader.py`

```python
class TileDownloader:
    CHUNK_SIZE = 8 * 1024 * 1024  # 8 MB

    async def download_tile(
        self,
        product_id: str,
        token: str,
        destination_path: str,
        timeout_seconds: int = 600
    ) -> str:
        """
        Descarga el tile en streaming a destination_path.
        Si supera timeout_seconds → TileDownloadTimeoutError.
        Si status HTTP != 200 → TileDownloadError con status_code.
        Devuelve la ruta al archivo descargado.
        """
        url = f"https://catalogue.dataspace.copernicus.eu/odata/v1/Products({product_id})/$value"
        headers = {"Authorization": f"Bearer {token}"}

        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            async with client.stream("GET", url, headers=headers, follow_redirects=True) as response:
                if response.status_code != 200:
                    raise TileDownloadError(...)

                with open(destination_path, "wb") as f:
                    async for chunk in response.aiter_bytes(self.CHUNK_SIZE):
                        f.write(chunk)

        return destination_path
```

### `app/services/processing/cropper.py`

```python
import rasterio
from rasterio.mask import mask
from rasterio.warp import transform_geom
from pyproj import CRS

def crop_tile_to_polygon(
    tile_path: str,
    polygon_geojson: dict,
    output_path: str,
    bands: list[int] = None
) -> dict:
    """
    Recorta el tile al polígono.
    - Reprojecta el polígono de EPSG:4326 al CRS del tile
    - Aplica rasterio.mask.mask() con crop=True
    - Guarda el resultado como TIF multibanda en output_path
    - Devuelve: { output_path, crs, bounds, pixel_count, width, height }
    """
    with rasterio.open(tile_path) as src:
        tile_crs = src.crs
        # Reprojectar polígono si el tile no está en EPSG:4326
        if tile_crs.to_epsg() != 4326:
            polygon_reprojected = transform_geom("EPSG:4326", tile_crs, polygon_geojson)
        else:
            polygon_reprojected = polygon_geojson

        out_image, out_transform = mask(src, [polygon_reprojected], crop=True, bands=bands)
        out_meta = src.meta.copy()
        out_meta.update({
            "height": out_image.shape[1],
            "width": out_image.shape[2],
            "transform": out_transform
        })

        with rasterio.open(output_path, "w", **out_meta) as dest:
            dest.write(out_image)

    return {
        "output_path": output_path,
        "crs": str(tile_crs),
        "width": out_image.shape[2],
        "height": out_image.shape[1],
        "pixel_count": out_image.shape[1] * out_image.shape[2]
    }
```

### `app/services/processing/cloud_mask.py`

```python
import numpy as np
import rasterio

INVALID_SCL_VALUES = {0, 1, 3, 8, 9, 10}

def apply_scl_mask(tif_path: str, scl_band_index: int) -> dict:
    """
    Lee la banda SCL y calcula estadísticas de calidad.
    Devuelve: { valid_pixels, total_pixels, valid_percentage, cloud_percentage, shadow_percentage, mask_array }
    """
    with rasterio.open(tif_path) as src:
        scl = src.read(scl_band_index)

    total = scl.size
    cloud_pixels = np.sum(np.isin(scl, [8, 9, 10]))
    shadow_pixels = np.sum(scl == 3)
    invalid_pixels = np.sum(np.isin(scl, list(INVALID_SCL_VALUES)))
    valid_pixels = total - invalid_pixels

    mask_array = ~np.isin(scl, list(INVALID_SCL_VALUES))

    return {
        "valid_pixels": int(valid_pixels),
        "total_pixels": int(total),
        "valid_percentage": round(valid_pixels / total * 100, 2),
        "cloud_percentage": round(cloud_pixels / total * 100, 2),
        "shadow_percentage": round(shadow_pixels / total * 100, 2),
        "mask_array": mask_array
    }
```

---

## Criterios de aceptación

- [ ] `TempManager.check_pressure()` lanza `StoragePressureError` con archivos dummy de 1.6 GB
- [ ] La descarga streaming no supera 200 MB de RAM en ningún momento (medible con `memory_profiler`)
- [ ] El tile se elimina en `finally` aunque falle el recorte (verificar con test que lanza excepción en recorte)
- [ ] `cropper.py` genera TIF válido para el polígono de Aguascalientes
- [ ] El TIF resultante pesa menos de 5 MB
- [ ] `cloud_mask.py` calcula porcentajes correctos con datos de prueba conocidos
- [ ] El semáforo rechaza la tercera descarga simultánea hasta que una de las dos anteriores termine

---

## Estado de tareas

| Archivo | Estado |
|---|---|
| `app/services/storage/temp_manager.py` | ⬜ |
| `app/services/copernicus/tile_downloader.py` | ⬜ |
| `app/services/processing/cropper.py` | ⬜ |
| `app/services/processing/cloud_mask.py` | ⬜ |
| Tests unitarios TempManager | ⬜ |
| Test integración descarga + recorte | ⬜ |

**Sprint completado:** ⬜

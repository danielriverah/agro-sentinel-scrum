# Sprint 4 — TIF: Copernicus Auth + Búsqueda de Escenas

**Duración:** 1 semana  
**Prerequisito:** Sprint 3 completado  
**Objetivo:** El servicio puede autenticarse en Copernicus CDSE y buscar escenas Sentinel-2 disponibles para un polígono y rango de fechas.  
**Historias:** US-005, US-006  
**Entregable:** Dado un polígono y rango de fechas, devuelve la escena más reciente con nubosidad aceptable.

---

## Contexto para la IA

La API de Copernicus CDSE usa OAuth2 con grant type `client_credentials`.

Endpoint de token:
```
POST https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&client_id={client_id}&client_secret={client_secret}
```

Para buscar escenas se usa la API STAC:
```
GET https://catalogue.dataspace.copernicus.eu/stac/collections/SENTINEL-2/items
  ?bbox={lon_min},{lat_min},{lon_max},{lat_max}
  &datetime={date_start}T00:00:00Z/{date_end}T23:59:59Z
  &filter=eo:cloud_cover<{max_cloud_coverage}
  &sortby=-datetime
  &limit=5
```

---

## Archivos a implementar

### `app/services/copernicus/auth.py`

```python
class CopernicusAuthService:
    def __init__(self, client_id: str, client_secret: str):
        self._client_id = client_id
        self._client_secret = client_secret
        self._token: str | None = None
        self._token_expires_at: float = 0

    async def get_token(self) -> str:
        """
        Devuelve el token vigente.
        Si expira en menos de 60 segundos, renueva automáticamente.
        Si falla la renovación → CopernicusAuthError.
        """
        ...

    async def _fetch_token(self) -> dict:
        """Llamada real al endpoint OAuth2 con httpx.AsyncClient."""
        ...
```

Reglas:
- Usar `httpx.AsyncClient` con timeout de 30 segundos
- Si el status HTTP no es 200 → `CopernicusAuthError` con `details.status_code`
- Guardar `expires_in` del response para calcular `_token_expires_at`

### `app/services/copernicus/scene_search.py`

```python
class SceneSearchService:
    def __init__(self, auth_service: CopernicusAuthService):
        ...

    async def find_best_scene(
        self,
        polygon_geojson: dict,
        date_start: str,
        date_end: str,
        max_cloud_coverage: int,
        collection: str = "sentinel-2-l2a"
    ) -> dict:
        """
        Devuelve la escena más reciente con nubosidad <= max_cloud_coverage.
        Si no hay ninguna → NoSceneAvailableError.

        Resultado:
        {
            product_id: str,
            acquisition_date: str,  (YYYY-MM-DD)
            cloud_coverage: float,
            download_url: str,
            tile_id: str,
            bbox: list[float]
        }
        """
        ...

    def _polygon_to_bbox(self, polygon_geojson: dict) -> list[float]:
        """Calcula el bounding box [lon_min, lat_min, lon_max, lat_max] del polígono."""
        ...
```

### `app/models/requests.py`

Modelo Pydantic `AnalyzeRequest`:
```python
from pydantic import BaseModel, field_validator

class AnalyzeRequest(BaseModel):
    job_id: str | None = None
    lot_id: int
    polygon_geojson: dict
    dates: list[str]
    indices: list[str]
    resolution_meters: int = 20
    force_reprocess: bool = False

    @field_validator("dates")
    def validate_dates(cls, v):
        # Debe tener exactamente 2 elementos en formato YYYY-MM-DD
        ...

    @field_validator("polygon_geojson")
    def validate_polygon(cls, v):
        # Debe tener type: Polygon y coordinates no vacías
        ...

    @field_validator("indices")
    def validate_indices(cls, v):
        # Debe tener al menos 1 elemento
        ...
```

---

## Datos de prueba

Crear `tests/fixtures/lote_aguascalientes.json`:
```json
{
  "type": "Polygon",
  "coordinates": [[
    [-102.2950, 21.8850],
    [-102.2850, 21.8850],
    [-102.2850, 21.8780],
    [-102.2950, 21.8780],
    [-102.2950, 21.8850]
  ]]
}
```
Este polígono representa ~1 km² al sur de Aguascalientes en zona de cultivos.

---

## Criterios de aceptación

- [ ] `auth.py` obtiene token real de Copernicus con credenciales del item `pk=local`
- [ ] El token se renueva automáticamente cuando está próximo a expirar
- [ ] Dado el polígono de prueba y un rango de 30 días recientes, devuelve al menos una escena
- [ ] Con `max_cloud_coverage: 0`, devuelve `NoSceneAvailableError` (404)
- [ ] Si las credenciales son incorrectas, devuelve `CopernicusAuthError` (503)
- [ ] `AnalyzeRequest` rechaza `dates` con formato incorrecto o sin 2 elementos
- [ ] `AnalyzeRequest` rechaza `polygon_geojson` sin tipo `Polygon`

---

## Estado de tareas

| Archivo | Estado |
|---|---|
| `app/services/copernicus/auth.py` | ⬜ |
| `app/services/copernicus/scene_search.py` | ⬜ |
| `app/models/requests.py` | ⬜ |
| `tests/fixtures/lote_aguascalientes.json` | ⬜ |
| Test unitario auth (mock OAuth2 endpoint) | ⬜ |
| Test integración scene_search (Copernicus real) | ⬜ |

**Sprint completado:** ⬜

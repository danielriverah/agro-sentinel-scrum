# Sprint 6 — TIF: Cálculo de Índices + Estadísticas + PNGs

**Duración:** 1 semana  
**Prerequisito:** Sprint 5 completado (TIF recortado disponible)  
**Objetivo:** Calcular índices espectrales, generar estadísticas y PNGs de visualización.  
**Historias:** US-009, US-010  
**Entregable:** Dado el TIF recortado, produce el JSON de estadísticas y los PNGs correctos.

---

## Contexto para la IA

Los lotes miden 1–10 ha. A 20 m/px, el TIF tiene entre ~5×5 y ~32×32 píxeles por banda. Las estadísticas son sobre decenas o cientos de píxeles — las operaciones son instantáneas con numpy.

Las fórmulas de los índices están en `docs/ARQUITECTURA.md` sección "Índices implementados".

Colormaps para PNGs:
- NDVI, NDRE, GNDVI, EVI, SAVI, MSAVI2 → `RdYlGn` (rojo=bajo, verde=alto)
- NDMI, NDWI → `RdYlBu` (rojo=seco, azul=húmedo)
- BSI, MSI, NBR → `YlOrRd` (amarillo=bajo, rojo=alto/problemático)

Los PNGs se escalan al rango teórico [-1, 1] para los normalizados, y se redimensionan a mínimo 256×256 con interpolación `nearest` para que los píxeles sean visibles (no interpolados).

---

## Archivos a implementar

### `app/services/processing/index_calculator.py`

```python
import numpy as np
import rasterio

SUPPORTED_INDICES = {
    "NDVI", "EVI", "SAVI", "MSAVI2", "NDWI",
    "NDMI", "MSI", "NDRE", "GNDVI", "BSI", "NBR"
}

# Mapeo de banda Sentinel-2 a índice de banda en el TIF multibanda
BAND_MAP = {
    "B2": 1, "B3": 2, "B4": 3, "B5": 4,
    "B6": 5, "B7": 6, "B8": 7, "B8A": 8,
    "B11": 9, "B12": 10, "SCL": 11
}

def calculate_indices(
    tif_path: str,
    requested_indices: list[str],
    cloud_mask: np.ndarray = None
) -> tuple[dict[str, np.ndarray], list[str]]:
    """
    Calcula los índices solicitados.
    Devuelve: (arrays_por_indice, indices_no_soportados)
    Los píxeles enmascarados se marcan como np.nan.
    """
    supported = [i.upper() for i in requested_indices if i.upper() in SUPPORTED_INDICES]
    unsupported = [i for i in requested_indices if i.upper() not in SUPPORTED_INDICES]

    with rasterio.open(tif_path) as src:
        bands = {name: src.read(idx).astype(float) for name, idx in BAND_MAP.items()}

    if cloud_mask is not None:
        for band in bands.values():
            band[~cloud_mask] = np.nan

    results = {}
    for index_name in supported:
        results[index_name.lower()] = _calculate_single(index_name.upper(), bands)

    return results, unsupported


def _calculate_single(index_name: str, bands: dict) -> np.ndarray:
    b = bands
    with np.errstate(divide="ignore", invalid="ignore"):
        if index_name == "NDVI":
            return (b["B8"] - b["B4"]) / (b["B8"] + b["B4"])
        elif index_name == "EVI":
            return 2.5 * (b["B8"] - b["B4"]) / (b["B8"] + 6*b["B4"] - 7.5*b["B2"] + 1)
        elif index_name == "SAVI":
            return 1.5 * (b["B8"] - b["B4"]) / (b["B8"] + b["B4"] + 0.5)
        elif index_name == "MSAVI2":
            return (2*b["B8"] + 1 - np.sqrt((2*b["B8"] + 1)**2 - 8*(b["B8"] - b["B4"]))) / 2
        elif index_name == "NDWI":
            return (b["B3"] - b["B8"]) / (b["B3"] + b["B8"])
        elif index_name == "NDMI":
            return (b["B8"] - b["B11"]) / (b["B8"] + b["B11"])
        elif index_name == "MSI":
            return b["B11"] / b["B8"]
        elif index_name == "NDRE":
            return (b["B8A"] - b["B5"]) / (b["B8A"] + b["B5"])
        elif index_name == "GNDVI":
            return (b["B8"] - b["B3"]) / (b["B8"] + b["B3"])
        elif index_name == "BSI":
            return ((b["B11"] + b["B4"]) - (b["B8"] + b["B2"])) / ((b["B11"] + b["B4"]) + (b["B8"] + b["B2"]))
        elif index_name == "NBR":
            return (b["B8"] - b["B12"]) / (b["B8"] + b["B12"])
    raise ValueError(f"Índice no implementado: {index_name}")
```

### `app/services/processing/statistics.py`

```python
import numpy as np

def compute_statistics(index_arrays: dict[str, np.ndarray]) -> dict:
    """
    Para cada índice calcula min, max, mean, std, valid_pixels.
    Ignora np.nan (píxeles enmascarados).
    """
    result = {}
    for name, array in index_arrays.items():
        valid = array[~np.isnan(array)]
        if len(valid) == 0:
            result[name] = {
                "min": None, "max": None, "mean": None,
                "std": None, "valid_pixels": 0
            }
        else:
            result[name] = {
                "min": round(float(np.min(valid)), 4),
                "max": round(float(np.max(valid)), 4),
                "mean": round(float(np.mean(valid)), 4),
                "std": round(float(np.std(valid)), 4),
                "valid_pixels": int(len(valid))
            }
    return result
```

### `app/services/processing/png_renderer.py`

```python
import numpy as np
from PIL import Image
import matplotlib.cm as cm

COLORMAPS = {
    "ndvi": "RdYlGn", "ndre": "RdYlGn", "gndvi": "RdYlGn",
    "evi": "RdYlGn", "savi": "RdYlGn", "msavi2": "RdYlGn",
    "ndmi": "RdYlBu", "ndwi": "RdYlBu",
    "bsi": "YlOrRd", "msi": "YlOrRd", "nbr": "YlOrRd"
}

INDEX_RANGES = {
    "ndvi": (-1, 1), "ndmi": (-1, 1), "ndre": (-1, 1),
    "ndwi": (-1, 1), "gndvi": (-1, 1), "nbr": (-1, 1),
    "evi": (-1, 2), "savi": (-1, 1.5), "msavi2": (-1, 1),
    "bsi": (-1, 1), "msi": (0, 3)
}

def render_index_png(
    index_array: np.ndarray,
    index_name: str,
    output_path: str,
    min_size: int = 256
) -> str:
    name = index_name.lower()
    vmin, vmax = INDEX_RANGES.get(name, (-1, 1))
    cmap_name = COLORMAPS.get(name, "RdYlGn")

    normalized = np.clip((index_array - vmin) / (vmax - vmin), 0, 1)
    normalized = np.nan_to_num(normalized, nan=0.5)

    cmap = cm.get_cmap(cmap_name)
    rgba = (cmap(normalized) * 255).astype(np.uint8)
    img = Image.fromarray(rgba, mode="RGBA")

    if img.width < min_size or img.height < min_size:
        scale = max(min_size // max(img.width, img.height), 1)
        img = img.resize((img.width * scale, img.height * scale), Image.NEAREST)

    img.save(output_path)
    return output_path
```

---

## Criterios de aceptación

- [ ] Los 11 índices calculan sin error usando el TIF del lote de prueba (Sprint 5)
- [ ] Los valores de NDVI están en rango [-1, 1] (verificar con `assert np.nanmax(result) <= 1.0`)
- [ ] División por cero produce `nan`, no excepción (verificar con `np.errstate`)
- [ ] `statistics.py` calcula correctamente ignorando NaN — test con array de 10 valores donde 3 son NaN
- [ ] Un índice no soportado no lanza excepción — aparece en la lista `unsupported` devuelta
- [ ] Los PNGs se generan y son imágenes válidas (PIL puede abrirlos)
- [ ] Los PNGs tienen mínimo 256×256 píxeles aunque el lote sea de 5×5 px

---

## Estado de tareas

| Archivo | Estado |
|---|---|
| `app/services/processing/index_calculator.py` | ⬜ |
| `app/services/processing/statistics.py` | ⬜ |
| `app/services/processing/png_renderer.py` | ⬜ |
| Test: cada índice con valores conocidos (verificar fórmula) | ⬜ |
| Test: statistics con NaN | ⬜ |
| Test: PNG generado tiene dimensiones >= 256x256 | ⬜ |

**Sprint completado:** ⬜

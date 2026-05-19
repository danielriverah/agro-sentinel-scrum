from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
import rasterio
import matplotlib.cm as cm
from PIL import Image
from pyproj import Transformer
from rasterio.windows import Window


class SceneTileBuilder:
    def __init__(self, output_root: str = "/tmp/agro-tif/outputs"):
        self.output_root = Path(output_root)
        self.output_root.mkdir(parents=True, exist_ok=True)

    def build(
        self,
        scene_name: str,
        latitude: float,
        longitude: float,
        tile_size: int,
        assets: dict[str, Any],
        bands: list[str],
    ) -> dict[str, str | list[str] | int]:
        run_id = uuid4().hex[:12]
        out_dir = self.output_root / f"{scene_name}_{run_id}"
        out_dir.mkdir(parents=True, exist_ok=True)

        band_arrays: list[np.ndarray] = []
        profile = None

        for band in bands:
            asset = assets.get(band)
            if not asset or "href" not in asset:
                raise ValueError(f"Band not available in scene assets: {band}")
            href = asset["href"]
            with rasterio.open(href) as src:
                transformer = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
                x, y = transformer.transform(longitude, latitude)
                row, col = src.index(x, y)
                half = tile_size // 2
                window = Window(col - half, row - half, tile_size, tile_size)
                arr = src.read(1, window=window, boundless=True, fill_value=0)
                band_arrays.append(arr)
                if profile is None:
                    profile = src.profile
                    profile.update(
                        {
                            "height": tile_size,
                            "width": tile_size,
                            "count": len(bands),
                            "driver": "GTiff",
                            "dtype": arr.dtype,
                            "compress": "lzw",
                        }
                    )

        assert profile is not None
        multiband_path = out_dir / "tile_multiband.tif"
        with rasterio.open(multiband_path, "w", **profile) as dst:
            for idx, arr in enumerate(band_arrays, start=1):
                dst.write(arr, idx)

        pngs = self._render_previews(out_dir, band_arrays, bands)
        indices = self._compute_indices(band_arrays, bands)
        thematic_pngs = self._render_thematic_layers(out_dir, indices)
        decision_summary = self._decision_summary(indices)
        ndvi_mean = self._compute_ndvi_mean(band_arrays, bands)
        return {
            "scene_name": scene_name,
            "tile_size": tile_size,
            "bands": bands,
            "multiband_tif": str(multiband_path),
            "pngs": pngs,
            "output_dir": str(out_dir),
            "indices": {"ndvi": {"mean": ndvi_mean}} if ndvi_mean is not None else {},
            "index_stats": {
                k: {"mean": round(float(np.nanmean(v)), 4)} for k, v in indices.items() if np.isfinite(v).any()
            },
            "thematic_pngs": thematic_pngs,
            "decision_summary": decision_summary,
        }

    def _render_previews(self, out_dir: Path, band_arrays: list[np.ndarray], bands: list[str]) -> list[str]:
        lookup = {band: band_arrays[i] for i, band in enumerate(bands)}
        previews: list[tuple[str, list[str]]] = [
            ("natural.png", ["B04", "B03", "B02"]),
            ("false_color_veg.png", ["B08", "B04", "B03"]),
            ("red_edge.png", ["B07", "B06", "B05"]),
            ("swir.png", ["B12", "B11", "B08"]),
        ]
        saved: list[str] = []
        for filename, combo in previews:
            if not all(c in lookup for c in combo):
                continue
            rgb = np.dstack([self._to_uint8(lookup[c]) for c in combo])
            img = Image.fromarray(rgb, mode="RGB")
            output_path = out_dir / filename
            img.save(output_path)
            saved.append(str(output_path))
        return saved

    @staticmethod
    def _to_uint8(arr: np.ndarray) -> np.ndarray:
        valid = arr[arr > 0]
        if valid.size == 0:
            return np.zeros_like(arr, dtype=np.uint8)
        p2 = np.percentile(valid, 2)
        p98 = np.percentile(valid, 98)
        clipped = np.clip(arr, p2, p98)
        scaled = ((clipped - p2) / max(p98 - p2, 1e-6) * 255.0).astype(np.uint8)
        return scaled

    @staticmethod
    def _compute_ndvi_mean(band_arrays: list[np.ndarray], bands: list[str]) -> float | None:
        lookup = {band: band_arrays[i].astype("float32") for i, band in enumerate(bands)}
        if "B08" not in lookup or "B04" not in lookup:
            return None
        nir = lookup["B08"]
        red = lookup["B04"]
        with np.errstate(divide="ignore", invalid="ignore"):
            ndvi = (nir - red) / (nir + red)
        valid = ndvi[np.isfinite(ndvi)]
        if valid.size == 0:
            return None
        return round(float(np.mean(valid)), 4)

    @staticmethod
    def _compute_indices(band_arrays: list[np.ndarray], bands: list[str]) -> dict[str, np.ndarray]:
        lookup = {band: band_arrays[i].astype("float32") for i, band in enumerate(bands)}

        def ratio(a: str, b: str) -> np.ndarray:
            with np.errstate(divide="ignore", invalid="ignore"):
                return (lookup[a] - lookup[b]) / (lookup[a] + lookup[b])

        out: dict[str, np.ndarray] = {}
        if "B08" in lookup and "B04" in lookup:
            out["ndvi"] = ratio("B08", "B04")
            out["savi"] = 1.5 * (lookup["B08"] - lookup["B04"]) / (lookup["B08"] + lookup["B04"] + 0.5)
            out["evi"] = 2.5 * (lookup["B08"] - lookup["B04"]) / (lookup["B08"] + 6 * lookup["B04"] - 7.5 * lookup.get("B02", lookup["B04"]) + 1)
        if "B8A" in lookup and "B05" in lookup:
            out["ndre"] = ratio("B8A", "B05")
        if "B08" in lookup and "B11" in lookup:
            out["ndmi"] = ratio("B08", "B11")
        if "B08" in lookup and "B03" in lookup:
            out["gndvi"] = ratio("B08", "B03")
        if "B08" in lookup and "B12" in lookup:
            out["nbr"] = ratio("B08", "B12")
        return out

    def _render_thematic_layers(self, out_dir: Path, indices: dict[str, np.ndarray]) -> list[str]:
        cmap_map = {
            "ndvi": "RdYlGn",
            "ndre": "RdYlGn",
            "ndmi": "RdYlBu",
            "savi": "RdYlGn",
            "evi": "RdYlGn",
            "gndvi": "RdYlGn",
            "nbr": "YlOrRd",
        }
        saved: list[str] = []
        for name, arr in indices.items():
            cmap_name = cmap_map.get(name, "viridis")
            norm = np.clip((arr + 1.0) / 2.0, 0, 1)
            norm = np.nan_to_num(norm, nan=0.5)
            rgba = (cm.get_cmap(cmap_name)(norm) * 255).astype(np.uint8)
            img = Image.fromarray(rgba, mode="RGBA")
            out = out_dir / f"{name}.png"
            img.save(out)
            saved.append(str(out))
        return saved

    @staticmethod
    def _decision_summary(indices: dict[str, np.ndarray]) -> dict[str, str]:
        def m(name: str) -> float | None:
            arr = indices.get(name)
            if arr is None:
                return None
            valid = arr[np.isfinite(arr)]
            if valid.size == 0:
                return None
            return float(np.mean(valid))

        ndvi = m("ndvi")
        ndmi = m("ndmi")
        ndre = m("ndre")
        nbr = m("nbr")

        return {
            "vigor_vegetal": "alto" if (ndvi is not None and ndvi >= 0.65) else "medio/bajo",
            "estres_hidrico": "alto" if (ndmi is not None and ndmi < 0.1) else "bajo/medio",
            "humedad": "baja" if (ndmi is not None and ndmi < 0.15) else "aceptable",
            "enfermedades": "posible alerta" if (ndre is not None and ndre < 0.2) else "sin alerta fuerte",
            "suelo_desnudo": "presente" if (ndvi is not None and ndvi < 0.35) else "bajo",
            "malezas": "revisar campo" if (ndvi is not None and ndvi > 0.45 and ndre is not None and ndre < 0.18) else "sin señal fuerte",
            "inundaciones": "riesgo" if (ndmi is not None and ndmi > 0.45) else "sin señal fuerte",
            "salinidad": "posible" if (ndvi is not None and ndvi < 0.3 and ndmi is not None and ndmi < 0.1) else "sin señal fuerte",
            "quemas": "posible" if (nbr is not None and nbr < 0.1) else "sin evidencia",
            "estructura_cultivo": "heterogenea" if (ndvi is not None and 0.35 <= ndvi <= 0.65) else "relativamente uniforme",
        }

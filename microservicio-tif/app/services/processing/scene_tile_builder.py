from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
import rasterio
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
        ndvi_mean = self._compute_ndvi_mean(band_arrays, bands)
        return {
            "scene_name": scene_name,
            "tile_size": tile_size,
            "bands": bands,
            "multiband_tif": str(multiband_path),
            "pngs": pngs,
            "output_dir": str(out_dir),
            "indices": {"ndvi": {"mean": ndvi_mean}} if ndvi_mean is not None else {},
        }

    def _render_previews(self, out_dir: Path, band_arrays: list[np.ndarray], bands: list[str]) -> list[str]:
        lookup = {band: band_arrays[i] for i, band in enumerate(bands)}
        previews: list[tuple[str, list[str]]] = [
            ("true_color.png", ["B04", "B03", "B02"]),
            ("false_color_veg.png", ["B08", "B04", "B03"]),
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

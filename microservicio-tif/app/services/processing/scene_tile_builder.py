from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
import rasterio
import matplotlib.cm as cm
from PIL import Image
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.features import rasterize
from rasterio.warp import transform_geom
from rasterio.windows import Window
from rasterio.windows import from_bounds


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
        polygon_geojson: dict[str, Any] | None = None,
        production_id: int | None = None,
    ) -> dict[str, str | list[str] | int]:
        out_dir = self._create_output_dir(scene_name=scene_name, production_id=production_id)

        if not bands:
            raise ValueError("At least one band is required")
        ref_band = bands[0]
        ref_asset = assets.get(ref_band)
        if not ref_asset or "href" not in ref_asset:
            raise ValueError(f"Reference band not available in scene assets: {ref_band}")

        # Reference grid (usually 10m band like B04) defines final extent and transform.
        with rasterio.open(ref_asset["href"]) as ref_src:
            transformer = Transformer.from_crs("EPSG:4326", ref_src.crs, always_xy=True)
            x, y = transformer.transform(longitude, latitude)
            row, col = ref_src.index(x, y)
            half = tile_size // 2
            ref_window = Window(col - half, row - half, tile_size, tile_size)
            ref_transform = ref_src.window_transform(ref_window)
            left, bottom, right, top = rasterio.windows.bounds(ref_window, ref_src.transform)
            ref_crs = ref_src.crs
            ref_dtype = ref_src.dtypes[0]

        band_arrays: list[np.ndarray] = []
        profile = None
        tile_crs = ref_crs

        for band in bands:
            asset = assets.get(band)
            if not asset or "href" not in asset:
                raise ValueError(f"Band not available in scene assets: {band}")
            href = asset["href"]
            with rasterio.open(href) as src:
                # Reproject reference bounds to each band grid, then resample to reference tile.
                if src.crs != ref_crs:
                    raise ValueError(f"Band CRS mismatch for {band}: {src.crs} != {ref_crs}")
                band_window = from_bounds(left, bottom, right, top, transform=src.transform)
                arr = src.read(
                    1,
                    window=band_window,
                    out_shape=(tile_size, tile_size),
                    resampling=Resampling.bilinear,
                    boundless=True,
                    fill_value=0,
                )
                band_arrays.append(arr)
                if profile is None:
                    profile = src.profile
                    profile.update(
                        {
                            "height": tile_size,
                            "width": tile_size,
                            "count": len(bands),
                            "driver": "GTiff",
                            "dtype": ref_dtype,
                            "compress": "lzw",
                            "transform": ref_transform,
                        }
                    )

        assert profile is not None
        polygon_mask = self._build_polygon_mask(
            polygon_geojson=polygon_geojson,
            tile_crs=tile_crs,
            transform=profile["transform"],
            shape=(tile_size, tile_size),
        )

        multiband_path = out_dir / "tile_multiband.tif"
        with rasterio.open(multiband_path, "w", **profile) as dst:
            for idx, arr in enumerate(band_arrays, start=1):
                dst.write(arr, idx)

        pngs = self._render_previews(out_dir, band_arrays, bands, polygon_mask)
        indices_full = self._compute_indices(band_arrays, bands)
        indices_masked = (
            {k: self._apply_mask(v, polygon_mask) for k, v in indices_full.items()}
            if polygon_mask is not None
            else indices_full
        )
        thematic_pngs = self._render_thematic_layers(out_dir, indices_full, polygon_mask)
        decision_summary = self._decision_summary(indices_masked)
        ndvi_mean = self._compute_ndvi_mean(band_arrays, bands)
        if polygon_mask is not None and "ndvi" in indices_masked:
            ndvi_mean = self._safe_mean(indices_masked["ndvi"])
        return {
            "scene_name": scene_name,
            "tile_size": tile_size,
            "bands": bands,
            "multiband_tif": str(multiband_path),
            "pngs": pngs,
            "output_dir": str(out_dir),
            "indices": {"ndvi": {"mean": ndvi_mean}} if ndvi_mean is not None else {},
            "index_stats": {
                k: {"mean": round(float(np.nanmean(v)), 4)} for k, v in indices_masked.items() if np.isfinite(v).any()
            },
            "thematic_pngs": thematic_pngs,
            "decision_summary": decision_summary,
            "polygon_mask_applied": polygon_mask is not None,
        }

    def build_from_multiband_tif(
        self,
        scene_name: str,
        tile_size: int,
        multiband_tif_path: str,
        bands: list[str],
        polygon_geojson: dict[str, Any] | None = None,
        production_id: int | None = None,
    ) -> dict[str, str | list[str] | int]:
        out_dir = self._create_output_dir(scene_name=scene_name, production_id=production_id)
        with rasterio.open(multiband_tif_path) as src:
            if src.count < len(bands):
                raise ValueError(
                    f"Existing multiband TIF has {src.count} bands but {len(bands)} were requested"
                )
            band_arrays: list[np.ndarray] = [src.read(i + 1) for i in range(len(bands))]
            polygon_mask = self._build_polygon_mask(
                polygon_geojson=polygon_geojson,
                tile_crs=src.crs,
                transform=src.transform,
                shape=(src.height, src.width),
            )
            pngs = self._render_previews(out_dir, band_arrays, bands, polygon_mask)
            indices_full = self._compute_indices(band_arrays, bands)
            indices_masked = (
                {k: self._apply_mask(v, polygon_mask) for k, v in indices_full.items()}
                if polygon_mask is not None
                else indices_full
            )
            thematic_pngs = self._render_thematic_layers(out_dir, indices_full, polygon_mask)
            decision_summary = self._decision_summary(indices_masked)
            ndvi_mean = self._compute_ndvi_mean(band_arrays, bands)
            if polygon_mask is not None and "ndvi" in indices_masked:
                ndvi_mean = self._safe_mean(indices_masked["ndvi"])
            return {
                "scene_name": scene_name,
                "tile_size": tile_size,
                "bands": bands,
                "multiband_tif": str(multiband_tif_path),
                "pngs": pngs,
                "output_dir": str(out_dir),
                "indices": {"ndvi": {"mean": ndvi_mean}} if ndvi_mean is not None else {},
                "index_stats": {
                    k: {"mean": round(float(np.nanmean(v)), 4)} for k, v in indices_masked.items() if np.isfinite(v).any()
                },
                "thematic_pngs": thematic_pngs,
                "decision_summary": decision_summary,
                "polygon_mask_applied": polygon_mask is not None,
            }

    def _create_output_dir(self, scene_name: str, production_id: int | None) -> Path:
        run_id = uuid4().hex[:12]
        if production_id is not None:
            out_dir = self.output_root / f"PROD_{production_id}" / f"{scene_name}_{run_id}"
        else:
            out_dir = self.output_root / f"{scene_name}_{run_id}"
        out_dir.mkdir(parents=True, exist_ok=True)
        return out_dir

    def _render_previews(
        self,
        out_dir: Path,
        band_arrays: list[np.ndarray],
        bands: list[str],
        polygon_mask: np.ndarray | None = None,
    ) -> list[str]:
        lookup = {band: band_arrays[i] for i, band in enumerate(bands)}
        previews: list[tuple[str, list[str]]] = [
            ("natural.png", ["B04", "B03", "B02"]),
            ("false_color_veg.png", ["B08", "B04", "B03"]),
            ("red_edge.png", ["B07", "B06", "B05"]),
            ("swir.png", ["B12", "B11", "B08"]),
        ]
        preview_edge_colors: dict[str, tuple[int, int, int]] = {
            "natural.png": (255, 215, 0),        # gold
            "false_color_veg.png": (255, 215, 0), # gold
            "red_edge.png": (255, 64, 64),        # red
            "swir.png": (255, 64, 64),            # red
        }
        saved: list[str] = []
        for filename, combo in previews:
            if not all(c in lookup for c in combo):
                continue
            rgb = np.dstack([self._to_uint8(lookup[c]) for c in combo])
            if polygon_mask is not None:
                color = preview_edge_colors.get(filename, (255, 215, 0))
                rgb = self._overlay_polygon_edge_rgb(rgb, polygon_mask, color)
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

    def _render_thematic_layers(
        self,
        out_dir: Path,
        indices: dict[str, np.ndarray],
        polygon_mask: np.ndarray | None = None,
    ) -> list[str]:
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
            if polygon_mask is not None:
                edge_color = (64, 128, 255, 255) if name in {"ndmi", "nbr"} else (255, 215, 0, 255)
                rgba = self._overlay_polygon_edge_rgba(rgba, polygon_mask, edge_color)
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

    @staticmethod
    def _safe_mean(arr: np.ndarray) -> float | None:
        valid = arr[np.isfinite(arr)]
        if valid.size == 0:
            return None
        return round(float(np.mean(valid)), 4)

    @staticmethod
    def _apply_mask(arr: np.ndarray, polygon_mask: np.ndarray) -> np.ndarray:
        masked = arr.astype("float32").copy()
        masked[~polygon_mask] = np.nan
        return masked

    def _build_polygon_mask(
        self,
        polygon_geojson: dict[str, Any] | None,
        tile_crs: Any,
        transform: Any,
        shape: tuple[int, int],
    ) -> np.ndarray | None:
        if polygon_geojson is None or tile_crs is None:
            return None
        geom = transform_geom("EPSG:4326", tile_crs, polygon_geojson)
        mask = rasterize(
            [(geom, 1)],
            out_shape=shape,
            transform=transform,
            fill=0,
            dtype="uint8",
        )
        return mask.astype(bool)

    def _overlay_polygon(self, rgb: np.ndarray, polygon_mask: np.ndarray) -> np.ndarray:
        out = rgb.copy()
        out[~polygon_mask] = (out[~polygon_mask] * 0.35).astype(np.uint8)
        edge = self._edge_mask(polygon_mask)
        out[edge] = np.array([255, 215, 0], dtype=np.uint8)
        return out

    @staticmethod
    def _edge_mask(mask: np.ndarray) -> np.ndarray:
        up = np.zeros_like(mask)
        down = np.zeros_like(mask)
        left = np.zeros_like(mask)
        right = np.zeros_like(mask)
        up[1:, :] = mask[:-1, :]
        down[:-1, :] = mask[1:, :]
        left[:, 1:] = mask[:, :-1]
        right[:, :-1] = mask[:, 1:]
        neighbor_all = up & down & left & right
        return mask & (~neighbor_all)

    def _overlay_polygon_edge_rgba(
        self,
        rgba: np.ndarray,
        polygon_mask: np.ndarray,
        color: tuple[int, int, int, int],
    ) -> np.ndarray:
        out = rgba.copy()
        edge = self._edge_mask(polygon_mask)
        out[edge] = np.array([color[0], color[1], color[2], color[3]], dtype=np.uint8)
        return out

    def _overlay_polygon_edge_rgb(
        self,
        rgb: np.ndarray,
        polygon_mask: np.ndarray,
        color: tuple[int, int, int],
    ) -> np.ndarray:
        out = rgb.copy()
        edge = self._edge_mask(polygon_mask)
        out[edge] = np.array([color[0], color[1], color[2]], dtype=np.uint8)
        return out

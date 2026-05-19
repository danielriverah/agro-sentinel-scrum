from __future__ import annotations

from typing import Any

import httpx


class SceneAssetsService:
    STAC_SEARCH_URL = "https://catalogue.dataspace.copernicus.eu/stac/search"

    async def get_scene_assets(self, scene_name: str) -> dict[str, Any]:
        payload = {
            "collections": ["sentinel-2-l2a"],
            "ids": [scene_name],
            "limit": 1,
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(self.STAC_SEARCH_URL, json=payload)

        response.raise_for_status()
        data = response.json()
        features = data.get("features", [])
        if not features:
            raise ValueError(f"Scene not found: {scene_name}")
        return features[0]

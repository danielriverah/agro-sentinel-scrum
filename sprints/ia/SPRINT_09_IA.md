# Sprint 9 — IA: Reglas Agronómicas + Histórico S3

**Duración:** 1 semana  
**Prerequisito:** Sprint 8 completado  
**Objetivo:** El motor de reglas agronómicas calcula alertas y nivel de riesgo. El lector de historial lee análisis previos del lote desde S3.  
**Historias:** US-014, US-015  
**Entregable:** Dado un payload de estadísticas, produce alertas y nivel de riesgo correctos con y sin historial.

---

## Contexto para la IA

Las reglas agronómicas se aplican SIEMPRE antes de llamar a la IA. Son deterministas y trazables. La IA recibe el resultado de las reglas (alertas + nivel de riesgo calculado) como parte de su contexto — no calcula las reglas ella misma.

El historial se lee de S3 buscando todos los archivos `statistics.json` en `{base_path}/lots/{lot_id}/*/statistics.json`. Se ordena por fecha descendente y se toman los últimos N (configurable, default 6).

---

## Archivos a implementar

### `app/services/storage/s3_client.py`

```python
class S3Client:
    async def list_lot_analyses(self, lot_id: int) -> list[dict]:
        """
        Lista todos los statistics.json del lote ordenados por fecha descendente.
        Devuelve: [{ date: str, key: str }, ...]
        """
        prefix = f"{self.base_path}/lots/{lot_id}/"
        response = self._s3.list_objects_v2(Bucket=self.bucket, Prefix=prefix)
        # Filtrar solo statistics.json y ordenar por fecha
        ...

    async def download_json(self, s3_key: str) -> dict:
        response = self._s3.get_object(Bucket=self.bucket, Key=s3_key)
        return json.loads(response["Body"].read())
```

### `app/services/agronomic/history_reader.py`

```python
class HistoryReader:
    async def read_lot_history(self, lot_id: int, max_entries: int = 6) -> list[dict] | None:
        """
        Lee los últimos max_entries análisis del lote desde S3.
        Si hay menos de 2 → devuelve None (sin historial suficiente).
        """
        ...

    def calculate_historical_means(self, history: list[dict]) -> dict[str, float]:
        """
        Calcula la media histórica de cada índice.
        Devuelve: { "ndvi": 0.68, "ndmi": 0.35, ... }
        """
        ...

    def calculate_changes(self, current: dict, historical_means: dict) -> dict[str, float]:
        """
        Calcula el cambio porcentual actual vs histórico.
        Devuelve: { "ndvi": -17.5, "ndmi": -42.1, ... }  (negativo = bajó)
        """
        ...
```

### `app/services/agronomic/rules_engine.py`

```python
class RulesEngine:
    def __init__(self, config: dict):
        self.rules = config["agronomic_rules"]
        self.crops = config.get("crops", {})

    def evaluate(
        self,
        current_indices: dict,
        changes_pct: dict | None,
        crop: str,
        valid_pixels_pct: float
    ) -> dict:
        """
        Aplica todas las reglas y devuelve:
        {
            alerts: list[str],
            risk_level: str,
            crop_config_used: "specific" | "global_defaults",
            warnings: list[str]
        }
        """
        alerts = []
        warnings = []
        crop_config = self.crops.get(crop)
        crop_config_used = "specific"

        if not crop_config:
            crop_config_used = "global_defaults"
            warnings.append("CROP_CONFIG_USING_GLOBAL_DEFAULTS")

        # Regla: píxeles válidos
        if valid_pixels_pct < self.rules["min_valid_pixels_percentage"]:
            alerts.append(f"Porcentaje de píxeles válidos bajo: {valid_pixels_pct:.1f}%")

        # Reglas de cambio histórico (solo si hay historial)
        if changes_pct:
            if changes_pct.get("ndvi", 0) < -self.rules["ndvi_drop_alert_pct"]:
                alerts.append(f"NDVI bajo contra histórico ({changes_pct['ndvi']:.1f}%)")
            if changes_pct.get("ndmi", 0) < -self.rules["ndmi_drop_alert_pct"]:
                alerts.append(f"NDMI bajo: posible estrés hídrico ({changes_pct['ndmi']:.1f}%)")
            # ... demás reglas

        # Calcular nivel de riesgo según cantidad y tipo de alertas
        risk_level = self._calculate_risk_level(alerts, current_indices, crop_config)

        return {
            "alerts": alerts,
            "risk_level": risk_level,
            "crop_config_used": crop_config_used,
            "warnings": warnings
        }

    def _calculate_risk_level(self, alerts: list, current_indices: dict, crop_config: dict | None) -> str:
        # low: sin alertas o NDVI en rango óptimo
        # medium: 1 alerta o NDVI en rango de advertencia
        # medium_high: 2+ alertas o NDVI bajo mínimo de advertencia
        # high: 3+ alertas o múltiples índices críticos simultáneos
        ...
```

---

## Criterios de aceptación

- [ ] Con NDVI bajando 20% vs histórico → alerta `"NDVI bajo contra histórico (-20.0%)"` y riesgo >= `medium`
- [ ] Con NDRE bajando y NDMI estable → alerta de posible estrés nutricional
- [ ] Sin historial → `changes_pct: null`, no hay alertas de cambio histórico, warning `INSUFFICIENT_HISTORY`
- [ ] Cultivo `maiz` con NDVI=0.40 (< `ndvi_warning_min: 0.45`) → genera alerta absoluta aunque no haya historial
- [ ] Cultivo no configurado → usa reglas globales + warning `CROP_CONFIG_USING_GLOBAL_DEFAULTS`
- [ ] `history_reader` devuelve `None` si hay menos de 2 análisis previos en S3

---

## Estado de tareas

| Archivo | Estado |
|---|---|
| `app/services/storage/s3_client.py` | ⬜ |
| `app/services/agronomic/history_reader.py` | ⬜ |
| `app/services/agronomic/rules_engine.py` | ⬜ |
| `app/services/agronomic/risk_calculator.py` | ⬜ |
| Tests unitarios rules_engine con 10+ casos | ⬜ |
| Test integración history_reader con S3 real | ⬜ |

**Sprint completado:** ⬜

---
---


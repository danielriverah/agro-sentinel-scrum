"""
Instancias singleton de los stores en memoria.
Importar desde aquí en lugar de crear instancias locales en cada módulo,
para que analyze.py, configurations.py y el sync service lean/escriban
el mismo objeto en RAM.
"""
from app.services.monitoring_store import MonitoringStore
from app.services.crop_config_store import CropConfigStore

monitoring_store = MonitoringStore()
crop_config_store = CropConfigStore()

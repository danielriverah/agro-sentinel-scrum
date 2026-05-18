# AgroSentinel — Glosario

Términos del dominio agrícola y técnico usados en todo el proyecto.

---

## Dominio agrícola

**Lote / Parcela**
Unidad mínima de análisis. Un área de terreno con un solo cultivo activo. En este sistema mide entre 1 y 10 hectáreas.

**Producción**
Sinónimo de lote en el contexto del ERP. Una producción es un lote con un cultivo, fechas de siembra y cosecha, y un responsable asignado.

**Hectárea (ha)**
Unidad de superficie. 1 ha = 10,000 m². Un lote típico en este sistema tiene entre 1 y 10 ha.

**Etapa fenológica**
Estado de desarrollo de la planta. Ejemplos: germinación, emergencia, crecimiento vegetativo, floración, fructificación, maduración, cosecha.

**Estrés hídrico**
Condición donde la planta no tiene suficiente agua disponible. Se detecta con caída de NDMI y NDWI.

**Estrés nutricional**
Deficiencia de nutrientes (principalmente nitrógeno). Se detecta con caída de NDRE mientras NDMI se mantiene estable.

**Vigor vegetal**
Medida general de salud y densidad de la planta. El índice NDVI es el indicador principal.

**Nivel de riesgo**
Clasificación del estado del lote: `low`, `medium`, `medium_high`, `high`. Lo calcula primero el motor de reglas y luego puede ser ajustado por la IA.

---

## Sentinel-2 y teledetección

**Sentinel-2**
Satélite de la Agencia Espacial Europea (ESA) que captura imágenes multiespectrales de la Tierra. Resolución de 10–60 m/px según la banda. Pasa sobre México cada 5 días aproximadamente.

**Sentinel-2 L2A**
Nivel de procesamiento de los productos Sentinel-2. L2A = reflectancia en superficie (ya corregido por la atmósfera). Es el nivel que usa AgroSentinel.

**Tile / escena**
Unidad de descarga de Sentinel-2. Cada tile cubre ~110×110 km y pesa ~1 GB. AgroSentinel descarga el tile completo, recorta el lote (~500 KB–2 MB), y descarta el tile original.

**Banda espectral**
Canal de longitud de onda capturado por el satélite. Las bandas relevantes para AgroSentinel son:

| Banda | Nombre | Longitud de onda | Resolución |
|---|---|---|---|
| B2 | Blue | 490 nm | 10 m |
| B3 | Green | 560 nm | 10 m |
| B4 | Red | 665 nm | 10 m |
| B5 | Red Edge 1 | 705 nm | 20 m |
| B6 | Red Edge 2 | 740 nm | 20 m |
| B7 | Red Edge 3 | 783 nm | 20 m |
| B8 | NIR | 842 nm | 10 m |
| B8A | Narrow NIR | 865 nm | 20 m |
| B11 | SWIR 1 | 1610 nm | 20 m |
| B12 | SWIR 2 | 2190 nm | 20 m |
| SCL | Clasificación | — | 20 m |

**SCL (Scene Classification Layer)**
Banda de clasificación de píxeles en Sentinel-2 L2A. Cada píxel tiene una categoría: vegetación, suelo desnudo, agua, nube, sombra de nube, etc. AgroSentinel la usa para crear la máscara de nubes.

**Máscara de nubes**
Proceso de excluir los píxeles clasificados como nubes o sombras en la SCL antes de calcular índices. Evita que las nubes distorsionen los valores.

**Píxeles válidos**
Píxeles del lote que no están enmascarados (no son nube, sombra, ni agua). Se expresa como porcentaje del total de píxeles del lote. Si cae por debajo del mínimo configurado, el análisis no es confiable.

**Nubosidad**
Porcentaje del área del lote cubierta por nubes. Diferente a `cloud_percentage` de toda la escena — AgroSentinel calcula la nubosidad específica del polígono del lote.

---

## Índices espectrales

**NDVI** (Normalized Difference Vegetation Index)
Índice de vigor y densidad vegetal. Rango: -1 a 1. Valores saludables para cultivos: 0.5–0.9.

**NDMI** (Normalized Difference Moisture Index)
Humedad del cultivo y estrés hídrico. Valores positivos = buena humedad; negativos = suelo o vegetación seca.

**NDRE** (Normalized Difference Red Edge)
Contenido de clorofila y nitrógeno en plantas densas. Más sensible que NDVI para detectar estrés temprano.

**BSI** (Bare Soil Index)
Detecta suelo desnudo o baja cobertura vegetal. Sube cuando hay cosecha parcial, daño o erosión.

**NDWI** (Normalized Difference Water Index)
Agua superficial, encharcamientos y cuerpos de agua. No confundir con NDMI (que mide humedad en la planta).

**EVI** (Enhanced Vegetation Index)
Versión mejorada de NDVI para vegetación muy densa donde el NDVI satura.

**SAVI** (Soil-Adjusted Vegetation Index)
NDVI corregido por el efecto del suelo visible. Útil en etapas tempranas con cobertura baja.

**MSAVI2** (Modified Soil-Adjusted Vegetation Index 2)
Mejor que SAVI para cultivo joven o suelo expuesto. No requiere factor de ajuste manual.

**MSI** (Moisture Stress Index)
Estrés hídrico. A diferencia de NDMI, valores más altos = más estrés (no normalizado).

**GNDVI** (Green NDVI)
Alternativa al NDVI usando la banda verde. Más sensible a variaciones de clorofila.

**NBR** (Normalized Burn Ratio)
Daño severo, sequía fuerte o vegetación completamente seca.

---

## Técnico

**Copernicus / CDSE**
Copernicus Data Space Ecosystem. Plataforma de la ESA para acceder a imágenes Sentinel-2. URL: `dataspace.copernicus.eu`. Requiere registro gratuito para obtener `client_id` y `client_secret`.

**rasterio**
Librería Python para leer, escribir y manipular archivos raster geoespaciales (GeoTIFF, etc.). Usa GDAL internamente.

**GDAL**
Geospatial Data Abstraction Library. Librería C/C++ base para procesamiento geoespacial. Dependencia del sistema para rasterio.

**GeoTIFF / TIF**
Formato de archivo raster que incluye información geoespacial (proyección, coordenadas). Los archivos del lote se almacenan en este formato.

**TIF multibanda**
Un solo archivo GeoTIFF que contiene múltiples bandas espectrales. AgroSentinel genera uno por lote y fecha con todas las bandas necesarias para calcular los índices solicitados.

**GeoJSON**
Formato JSON estándar para representar geometrías geoespaciales. El polígono del lote se envía en este formato. Debe estar en CRS EPSG:4326 (coordenadas WGS84, latitud/longitud).

**EPSG:4326**
Sistema de referencia de coordenadas estándar usando latitud y longitud en grados decimales (WGS84). Es el formato que espera AgroSentinel para el `polygon_geojson`.

**CRS (Coordinate Reference System)**
Sistema de referencia de coordenadas. Define cómo se mapean las coordenadas a posiciones en la Tierra.

**Resolución espacial**
Tamaño del pixel en metros. AgroSentinel trabaja a 20 m/px, que es la resolución de las bandas más útiles para análisis agrícola (B5, B8A, B11).

**DynamoDB**
Base de datos NoSQL de AWS usada como fuente central de configuración. AgroSentinel nunca escribe en ella — solo lee.

**Caché de configuración**
El resultado de la lectura de DynamoDB se guarda en memoria por `CONFIG_CACHE_TTL_SECONDS` segundos (default 300). Evita consultar DynamoDB en cada request.

**Backoff exponencial**
Estrategia de reintento donde el tiempo de espera entre intentos crece exponencialmente. AgroSentinel usa 5s → 15s → 45s para el webhook a Laravel.

**Webhook**
Llamada HTTP que el Microservicio IA hace a Laravel cuando termina un análisis. Laravel no pregunta — AgroSentinel notifica.

**Idempotencia**
Propiedad de una operación donde ejecutarla múltiples veces produce el mismo resultado. Si el análisis de un lote para una fecha ya existe en S3, devolver el guardado sin reprocesar.

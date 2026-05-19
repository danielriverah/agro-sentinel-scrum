// ─── Datos ficticios centralizados ───────────────────────────────────────────
// Todos los datos de esta aplicación son mock hasta que los microservicios
// estén conectados. Cada función simula la respuesta real de la API.

export const LOTES = [
  {
    id: 1, nombre: 'Lote Norte 1', cultivo: 'maiz', etapa: 'crecimiento vegetativo',
    area_ha: 4.2, municipio: 'Tepatitlán', estado: 'Jalisco',
    ultimo_analisis: '2026-05-10', riesgo: 'low', coordenadas: [-102.2950, 21.8850]
  },
  {
    id: 2, nombre: 'Lote Norte 2', cultivo: 'tomate', etapa: 'floración',
    area_ha: 2.8, municipio: 'Tepatitlán', estado: 'Jalisco',
    ultimo_analisis: '2026-05-12', riesgo: 'medium', coordenadas: [-102.2800, 21.8780]
  },
  {
    id: 3, nombre: 'Lote Sur A', cultivo: 'lechuga', etapa: 'desarrollo foliar',
    area_ha: 1.5, municipio: 'Arandas', estado: 'Jalisco',
    ultimo_analisis: '2026-05-14', riesgo: 'medium_high', coordenadas: [-102.3100, 21.8600]
  },
  {
    id: 4, nombre: 'Lote Sur B', cultivo: 'brocoli', etapa: 'formación cabeza',
    area_ha: 3.1, municipio: 'Arandas', estado: 'Jalisco',
    ultimo_analisis: '2026-05-08', riesgo: 'high', coordenadas: [-102.3200, 21.8550]
  },
  {
    id: 5, nombre: 'Parcela Este 1', cultivo: 'chile', etapa: 'maduración',
    area_ha: 2.0, municipio: 'San Miguel el Alto', estado: 'Jalisco',
    ultimo_analisis: '2026-05-11', riesgo: 'low', coordenadas: [-102.2600, 21.9000]
  },
  {
    id: 6, nombre: 'Parcela Este 2', cultivo: 'cebolla', etapa: 'bulbificación',
    area_ha: 5.7, municipio: 'San Miguel el Alto', estado: 'Jalisco',
    ultimo_analisis: '2026-05-15', riesgo: 'medium', coordenadas: [-102.2500, 21.8950]
  },
]

export const ANALISIS_POR_LOTE = {
  1: [
    {
      job_id: 'job_01TESTA0000001', fecha: '2026-05-10', riesgo: 'low',
      confianza: 'high', nubosidad_pct: 2.1, pixeles_validos_pct: 97.9,
      indices: {
        ndvi: { mean: 0.71, std: 0.08, min: 0.52, max: 0.88 },
        ndmi: { mean: 0.28, std: 0.05, min: 0.18, max: 0.41 },
        ndre: { mean: 0.35, std: 0.06, min: 0.22, max: 0.49 },
      },
      resumen: 'El lote presenta condiciones óptimas de vigor vegetal y humedad.',
      recomendaciones: ['Mantener el programa de riego actual', 'Monitoreo preventivo en 15 días'],
      causas: ['Condiciones climáticas favorables', 'Adecuada disponibilidad hídrica'],
    },
    {
      job_id: 'job_01TESTA0000002', fecha: '2026-04-22', riesgo: 'low',
      confianza: 'high', nubosidad_pct: 5.3, pixeles_validos_pct: 94.7,
      indices: {
        ndvi: { mean: 0.68, std: 0.09, min: 0.48, max: 0.85 },
        ndmi: { mean: 0.25, std: 0.06, min: 0.14, max: 0.39 },
        ndre: { mean: 0.32, std: 0.07, min: 0.20, max: 0.46 },
      },
      resumen: 'Lote con buen desarrollo vegetativo para la etapa fenológica.',
      recomendaciones: ['Continuar con el plan de fertilización', 'Revisión de plagas preventiva'],
      causas: ['Etapa temprana del cultivo'],
    },
  ],
  2: [
    {
      job_id: 'job_01TESTB0000001', fecha: '2026-05-12', riesgo: 'medium',
      confianza: 'medium', nubosidad_pct: 12.4, pixeles_validos_pct: 87.6,
      indices: {
        ndvi: { mean: 0.58, std: 0.11, min: 0.35, max: 0.76 },
        ndmi: { mean: 0.19, std: 0.07, min: 0.08, max: 0.33 },
        ndre: { mean: 0.27, std: 0.08, min: 0.14, max: 0.42 },
      },
      resumen: 'Se detecta leve reducción de humedad vegetal. Monitorear riego.',
      recomendaciones: ['Aumentar frecuencia de riego en 20%', 'Verificar sensores de humedad'],
      causas: ['Posible estrés hídrico leve', 'Temperaturas elevadas recientes'],
    },
  ],
  3: [
    {
      job_id: 'job_01TESTC0000001', fecha: '2026-05-14', riesgo: 'medium_high',
      confianza: 'high', nubosidad_pct: 3.8, pixeles_validos_pct: 96.2,
      indices: {
        ndvi: { mean: 0.42, std: 0.13, min: 0.22, max: 0.61 },
        ndmi: { mean: 0.12, std: 0.09, min: 0.02, max: 0.28 },
        ndre: { mean: 0.21, std: 0.09, min: 0.08, max: 0.36 },
      },
      resumen: 'Caída significativa de vigor e índice de humedad. Requiere atención inmediata.',
      alertas: ['NDVI bajo contra histórico (-18.2%)', 'NDMI bajo: posible estrés hídrico (-38.5%)'],
      recomendaciones: [
        'Inspección de campo en las próximas 48 horas',
        'Revisar sistema de riego por goteo',
        'Verificar salinidad del suelo',
      ],
      causas: ['Estrés hídrico moderado', 'Posible salinización del suelo'],
    },
  ],
  4: [
    {
      job_id: 'job_01TESTD0000001', fecha: '2026-05-08', riesgo: 'high',
      confianza: 'high', nubosidad_pct: 1.5, pixeles_validos_pct: 98.5,
      indices: {
        ndvi: { mean: 0.31, std: 0.16, min: 0.08, max: 0.52 },
        ndmi: { mean: 0.06, std: 0.10, min: -0.04, max: 0.22 },
        ndre: { mean: 0.14, std: 0.10, min: 0.01, max: 0.28 },
      },
      resumen: 'Estado crítico del cultivo. Pérdida severa de vigor y posible daño irreversible.',
      alertas: [
        'NDVI bajo contra histórico (-42.6%)',
        'NDMI crítico: suelo casi seco (-61.3%)',
        'NDRE bajo: déficit nutricional probable',
      ],
      recomendaciones: [
        'URGENTE: Revisión de campo hoy',
        'Riego de emergencia inmediato',
        'Consultar ingeniero agrónomo',
        'Evaluar pérdida parcial de cosecha',
      ],
      causas: ['Fallo en sistema de riego', 'Posible ataque de plaga subterránea', 'Déficit hídrico severo'],
    },
  ],
  5: [
    {
      job_id: 'job_01TESTE0000001', fecha: '2026-05-11', riesgo: 'low',
      confianza: 'high', nubosidad_pct: 4.1, pixeles_validos_pct: 95.9,
      indices: {
        ndvi: { mean: 0.65, std: 0.07, min: 0.50, max: 0.81 },
        ndmi: { mean: 0.24, std: 0.05, min: 0.15, max: 0.38 },
        ndre: { mean: 0.33, std: 0.06, min: 0.22, max: 0.47 },
      },
      resumen: 'Cultivo en etapa de maduración con buenas condiciones generales.',
      recomendaciones: ['Preparar plan de cosecha', 'Reducir gradualmente el riego'],
      causas: ['Progresión normal del ciclo fenológico'],
    },
  ],
  6: [
    {
      job_id: 'job_01TESTF0000001', fecha: '2026-05-15', riesgo: 'medium',
      confianza: 'medium', nubosidad_pct: 18.2, pixeles_validos_pct: 81.8,
      indices: {
        ndvi: { mean: 0.52, std: 0.12, min: 0.31, max: 0.70 },
        ndmi: { mean: 0.17, std: 0.08, min: 0.05, max: 0.31 },
        ndre: { mean: 0.25, std: 0.09, min: 0.11, max: 0.40 },
      },
      resumen: 'Condiciones aceptables con ligera reducción de vigor. Vigilar humedad.',
      recomendaciones: ['Ajustar frecuencia de riego', 'Aplicar fertilización foliar'],
      causas: ['Nubosidad alta redujo calidad del análisis', 'Posible estrés moderado'],
    },
  ],
}

export const ALERTAS = LOTES
  .filter(l => l.riesgo === 'medium_high' || l.riesgo === 'high')
  .map(l => {
    const analisis = (ANALISIS_POR_LOTE[l.id] || [])[0] || {}
    return {
      lot_id: l.id, lot_nombre: l.nombre, cultivo: l.cultivo,
      risk_level: l.riesgo, fecha_analisis: l.ultimo_analisis,
      area_ha: l.area_ha, municipio: l.municipio,
      alertas: analisis.alertas || [],
    }
  })

export const JOBS = [
  {
    job_id: 'job_01JOBS000001', lot_id: 3, lot_nombre: 'Lote Sur A',
    status: 'completed', created_at: '2026-05-14T08:22:00Z',
    updated_at: '2026-05-14T08:29:45Z', processing_seconds: 462,
  },
  {
    job_id: 'job_01JOBS000002', lot_id: 4, lot_nombre: 'Lote Sur B',
    status: 'completed', created_at: '2026-05-08T10:05:00Z',
    updated_at: '2026-05-08T10:13:22Z', processing_seconds: 502,
  },
  {
    job_id: 'job_01JOBS000003', lot_id: 6, lot_nombre: 'Parcela Este 2',
    status: 'processing', created_at: '2026-05-19T07:45:00Z',
    updated_at: '2026-05-19T07:45:00Z', processing_seconds: null,
  },
  {
    job_id: 'job_01JOBS000004', lot_id: 2, lot_nombre: 'Lote Norte 2',
    status: 'failed', created_at: '2026-05-13T14:30:00Z',
    updated_at: '2026-05-13T14:31:10Z', processing_seconds: 70,
    error_code: 'NO_SCENE_AVAILABLE', error_message: 'No hay imagen Sentinel-2 disponible para el rango solicitado',
  },
]

export const SERVICIOS_HEALTH = {
  tif: {
    status: 'ok', service: 'agro-sentinel-tif', version: '0.1.0',
    config: { loaded: false, valid: false, version: null },
    uptime_seconds: 3842,
  },
  ia: {
    status: 'ok', service: 'agro-sentinel-ia', version: '0.1.0',
    config: { loaded: false, valid: false, version: null },
    ai_provider: 'pendiente',
    uptime_seconds: 3841,
  },
}

export const CONFIG_VALIDACION = {
  tif: {
    valid: false,
    missing: [
      'copernicus.client_id',
      'copernicus.client_secret',
      'storage.s3_bucket',
    ],
  },
  ia: {
    valid: false,
    missing: [
      'ai.providers.anthropic.api_key',
      'laravel.webhook_url',
      'laravel.webhook_secret',
    ],
  },
}

export const RESUMEN_DASHBOARD = {
  total_lotes: LOTES.length,
  alertas_activas: ALERTAS.length,
  analisis_mes: 14,
  lotes_riesgo_high: LOTES.filter(l => l.riesgo === 'high').length,
  lotes_riesgo_medium_high: LOTES.filter(l => l.riesgo === 'medium_high').length,
  lotes_riesgo_medium: LOTES.filter(l => l.riesgo === 'medium').length,
  lotes_riesgo_low: LOTES.filter(l => l.riesgo === 'low').length,
}

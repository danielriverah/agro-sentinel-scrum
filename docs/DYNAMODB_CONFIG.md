# AgroSentinel — Configuración DynamoDB

Este archivo define la estructura exacta del item de configuración en DynamoDB.
Es la fuente de verdad para ambos microservicios.

---

## Tabla

```
Nombre:           agro_sentinel_config
Partition key:    pk  (String)
Sort key:         sk  (String)
```

---

## Item completo de producción

```json
{
  "pk": "production",
  "sk": "active",
  "version": 1,
  "enabled": true,
  "updated_at": "2026-05-18T10:00:00Z",
  "updated_by": "setup-inicial",

  "security": {
    "api_secret_key": "CAMBIAR-POR-CLAVE-SEGURA-COMPARTIDA-CON-LARAVEL",
    "allowed_origins": [
      "https://tu-erp.com"
    ]
  },

  "ai": {
    "provider": "anthropic",
    "timeout": 60,
    "max_tokens": 2500,
    "temperature": 0.2,
    "fallback_provider": null,
    "providers": {
      "anthropic": {
        "enabled": true,
        "api_key": "sk-ant-CAMBIAR",
        "model": "claude-sonnet-4-5"
      },
      "openai": {
        "enabled": false,
        "api_key": "",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4.1"
      },
      "ollama": {
        "enabled": false,
        "base_url": "http://localhost:11434",
        "model": "qwen2.5:14b"
      },
      "lmstudio": {
        "enabled": false,
        "base_url": "http://localhost:1234/v1",
        "model": "qwen2.5-14b-instruct"
      },
      "vllm": {
        "enabled": false,
        "base_url": "http://localhost:8001/v1",
        "model": "Qwen/Qwen2.5-14B-Instruct"
      },
      "custom": {
        "enabled": false,
        "url": "",
        "api_key": "",
        "timeout": 60
      }
    }
  },

  "storage": {
    "driver": "s3",
    "aws_region": "us-east-1",
    "s3_bucket": "CAMBIAR-POR-NOMBRE-REAL-DEL-BUCKET",
    "base_path": "agro-sentinel",
    "public_url_ttl_minutes": 60
  },

  "copernicus": {
    "client_id": "CAMBIAR-POR-CLIENT-ID-CDSE",
    "client_secret": "CAMBIAR-POR-CLIENT-SECRET-CDSE",
    "default_collection": "sentinel-2-l2a",
    "max_cloud_coverage": 20
  },

  "laravel": {
    "webhook_url": "https://tu-erp.com/api/sentinel/webhook",
    "webhook_secret": "CAMBIAR-POR-CLAVE-WEBHOOK",
    "timeout": 30
  },

  "processing": {
    "default_indices": ["NDVI", "NDMI", "NDRE", "MSAVI2", "BSI"],
    "resolution_meters": 20,
    "apply_cloud_mask": true,
    "min_valid_pixels_percentage": 80,
    "generate_png": true,
    "generate_geotiff": true,
    "generate_pdf": false
  },

  "agronomic_rules": {
    "ndvi_drop_alert_pct": 15,
    "ndmi_drop_alert_pct": 20,
    "ndre_drop_alert_pct": 15,
    "bsi_rise_alert_pct": 50,
    "min_valid_pixels_percentage": 80,
    "risk_levels": {
      "low": 1,
      "medium": 2,
      "medium_high": 3,
      "high": 4
    }
  },

  "crops": {
    "maiz": {
      "enabled": true,
      "ndvi_optimal_min": 0.65,
      "ndvi_warning_min": 0.45,
      "ndmi_warning_min": 0.20,
      "ndre_warning_min": 0.28
    },
    "lechuga": {
      "enabled": true,
      "ndvi_optimal_min": 0.60,
      "ndvi_warning_min": 0.40,
      "ndmi_warning_min": 0.18,
      "ndre_warning_min": 0.25
    },
    "brocoli": {
      "enabled": true,
      "ndvi_optimal_min": 0.58,
      "ndvi_warning_min": 0.38,
      "ndmi_warning_min": 0.17,
      "ndre_warning_min": 0.24
    },
    "tomate": {
      "enabled": true,
      "ndvi_optimal_min": 0.62,
      "ndvi_warning_min": 0.42,
      "ndmi_warning_min": 0.19,
      "ndre_warning_min": 0.26
    },
    "chile": {
      "enabled": true,
      "ndvi_optimal_min": 0.60,
      "ndvi_warning_min": 0.40,
      "ndmi_warning_min": 0.18,
      "ndre_warning_min": 0.25
    },
    "cebolla": {
      "enabled": true,
      "ndvi_optimal_min": 0.55,
      "ndvi_warning_min": 0.35,
      "ndmi_warning_min": 0.16,
      "ndre_warning_min": 0.22
    }
  }
}
```

---

## Item para desarrollo local

```json
{
  "pk": "local",
  "sk": "active",
  "version": 1,
  "enabled": true,
  "updated_at": "2026-05-18T10:00:00Z",
  "updated_by": "dev-setup",

  "security": {
    "api_secret_key": "dev-secret-123",
    "allowed_origins": ["http://localhost", "http://localhost:8000"]
  },

  "ai": {
    "provider": "ollama",
    "timeout": 120,
    "max_tokens": 2500,
    "temperature": 0.2,
    "fallback_provider": null,
    "providers": {
      "anthropic": {
        "enabled": false,
        "api_key": "",
        "model": "claude-sonnet-4-5"
      },
      "ollama": {
        "enabled": true,
        "base_url": "http://host.docker.internal:11434",
        "model": "qwen2.5:14b"
      }
    }
  },

  "storage": {
    "driver": "s3",
    "aws_region": "us-east-1",
    "s3_bucket": "agro-sentinel-dev",
    "base_path": "dev",
    "public_url_ttl_minutes": 60
  },

  "copernicus": {
    "client_id": "COPERNICUS-CLIENT-ID-REAL",
    "client_secret": "COPERNICUS-CLIENT-SECRET-REAL",
    "default_collection": "sentinel-2-l2a",
    "max_cloud_coverage": 30
  },

  "laravel": {
    "webhook_url": "https://[tu-subdominio].ngrok.io/api/sentinel/webhook",
    // Para desarrollo local: usar ngrok para exponer Laravel al webhook externo
    // Alternativa: http://host.docker.internal:8000/api/sentinel/webhook (si Laravel también está en Docker)
    "webhook_secret": "dev-webhook-secret",
    "timeout": 30
  },

  "processing": {
    "default_indices": ["NDVI", "NDMI", "NDRE"],
    "resolution_meters": 20,
    "apply_cloud_mask": true,
    "min_valid_pixels_percentage": 60,
    "generate_png": true,
    "generate_geotiff": true,
    "generate_pdf": false
  },

  "agronomic_rules": {
    "ndvi_drop_alert_pct": 15,
    "ndmi_drop_alert_pct": 20,
    "ndre_drop_alert_pct": 15,
    "bsi_rise_alert_pct": 50,
    "min_valid_pixels_percentage": 60,
    "risk_levels": {
      "low": 1,
      "medium": 2,
      "medium_high": 3,
      "high": 4
    }
  },

  "crops": {
    "maiz": {
      "enabled": true,
      "ndvi_optimal_min": 0.65,
      "ndvi_warning_min": 0.45,
      "ndmi_warning_min": 0.20,
      "ndre_warning_min": 0.28
    }
  }
}
```

---

## Cómo insertar el item con AWS CLI

```bash
aws dynamodb put-item \
  --table-name agro_sentinel_config \
  --item file://config-item.json \
  --region us-east-1
```

Donde `config-item.json` es el JSON anterior con los valores reales completados.

---

## Campos obligatorios mínimos para que el servicio arranque

Si falta cualquiera de estos, ambos microservicios fallan con `CONFIG_VALIDATION_ERROR`:

```
security.api_secret_key
storage.driver
storage.s3_bucket
storage.base_path
copernicus.client_id              (solo TIF)
copernicus.client_secret          (solo TIF)
processing.default_indices        (solo TIF)
processing.min_valid_pixels_percentage  (solo TIF)
ai.provider                       (solo IA)
ai.providers.{provider}.enabled   (solo IA)
ai.providers.{provider}.model     (solo IA)
agronomic_rules.ndvi_drop_alert_pct  (solo IA)
agronomic_rules.ndmi_drop_alert_pct  (solo IA)
laravel.webhook_url               (solo IA)
laravel.webhook_secret            (solo IA)
```
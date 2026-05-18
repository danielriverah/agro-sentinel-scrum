# Sprint 1 — Infraestructura: DynamoDB + S3 + IAM

**Duración:** 1 semana  
**Objetivo:** Tener la infraestructura AWS base lista para que ambos microservicios puedan arrancar.  
**Historias:** US-001, US-002  
**Entregable:** AWS configurado, item de DynamoDB insertado, S3 listo, IAM restrictivo.

---

## Contexto para la IA

Antes de ejecutar este sprint, la IA debe saber:
- No se escribe código Python en este sprint — es configuración de infraestructura
- El item de DynamoDB es la fuente de verdad de toda la configuración operativa
- Los campos `CAMBIAR` del template deben reemplazarse con valores reales antes de insertar
- El rol IAM debe ser mínimo — solo `dynamodb:GetItem` y los S3 necesarios

---

## Tareas

### Tarea 1.1 — Crear tabla DynamoDB

```bash
aws dynamodb create-table \
  --table-name agro_sentinel_config \
  --attribute-definitions \
    AttributeName=pk,AttributeType=S \
    AttributeName=sk,AttributeType=S \
  --key-schema \
    AttributeName=pk,KeyType=HASH \
    AttributeName=sk,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST \
  --region us-east-1
```

Verificar:
```bash
aws dynamodb describe-table --table-name agro_sentinel_config --region us-east-1
```

DoD: la tabla existe y su status es ACTIVE.

---

### Tarea 1.2 — Insertar item de producción

1. Copiar el JSON completo de `docs/DYNAMODB_CONFIG.md` (sección "Item completo de producción")
2. Reemplazar todos los valores `CAMBIAR-POR-*` con valores reales
3. Guardar como `config-production.json`
4. Insertar:

```bash
aws dynamodb put-item \
  --table-name agro_sentinel_config \
  --item file://config-production.json \
  --region us-east-1
```

Verificar:
```bash
aws dynamodb get-item \
  --table-name agro_sentinel_config \
  --key '{"pk": {"S": "production"}, "sk": {"S": "active"}}' \
  --region us-east-1
```

DoD: el item se puede leer y contiene todos los campos esperados.

---

### Tarea 1.3 — Insertar item de desarrollo local

1. Copiar el JSON de `docs/DYNAMODB_CONFIG.md` (sección "Item para desarrollo local")
2. Completar las credenciales de Copernicus (son reales incluso en dev)
3. Guardar como `config-local.json`
4. Insertar con `pk=local, sk=active`

DoD: el item local existe con credenciales de Copernicus reales y Ollama configurado.

---

### Tarea 1.4 — Crear bucket S3

```bash
aws s3api create-bucket \
  --bucket NOMBRE-DEL-BUCKET \
  --region us-east-1

# Bloquear acceso público
aws s3api put-public-access-block \
  --bucket NOMBRE-DEL-BUCKET \
  --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
```

Verificar subiendo un archivo de prueba:
```bash
echo "test" | aws s3 cp - s3://NOMBRE-DEL-BUCKET/test.txt
aws s3 ls s3://NOMBRE-DEL-BUCKET/
```

DoD: bucket creado con acceso público bloqueado.

---

### Tarea 1.5 — Crear política y rol IAM

Política mínima (guardar como `agro-sentinel-policy.json`):
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DynamoDBReadConfig",
      "Effect": "Allow",
      "Action": ["dynamodb:GetItem"],
      "Resource": "arn:aws:dynamodb:us-east-1:ACCOUNT_ID:table/agro_sentinel_config"
    },
    {
      "Sid": "S3ReadWrite",
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::NOMBRE-DEL-BUCKET",
        "arn:aws:s3:::NOMBRE-DEL-BUCKET/*"
      ]
    }
  ]
}
```

```bash
# Reemplazar ACCOUNT_ID y NOMBRE-DEL-BUCKET antes de ejecutar
aws iam create-policy \
  --policy-name AgroSentinelPolicy \
  --policy-document file://agro-sentinel-policy.json

aws iam create-role \
  --role-name AgroSentinelRole \
  --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ec2.amazonaws.com"},"Action":"sts:AssumeRole"}]}'

aws iam attach-role-policy \
  --role-name AgroSentinelRole \
  --policy-arn arn:aws:iam::ACCOUNT_ID:policy/AgroSentinelPolicy
```

DoD: rol creado con solo los permisos listados — verificar que NO tiene permisos de escritura en DynamoDB.

---

## Verificación final del sprint

Ejecutar este checklist antes de marcar el sprint como completado:

```bash
# 1. Leer item de producción
aws dynamodb get-item \
  --table-name agro_sentinel_config \
  --key '{"pk": {"S": "production"}, "sk": {"S": "active"}}'

# 2. Leer item de desarrollo
aws dynamodb get-item \
  --table-name agro_sentinel_config \
  --key '{"pk": {"S": "local"}, "sk": {"S": "active"}}'

# 3. Verificar S3
aws s3 ls s3://NOMBRE-DEL-BUCKET/

# 4. Verificar que el rol NO tiene dynamodb:PutItem
aws iam simulate-principal-policy \
  --policy-source-arn arn:aws:iam::ACCOUNT_ID:role/AgroSentinelRole \
  --action-names dynamodb:PutItem \
  --resource-arns arn:aws:dynamodb:us-east-1:ACCOUNT_ID:table/agro_sentinel_config
# Debe devolver: IMPLICIT_DENY
```

---

## Estado de tareas

| Tarea | Descripción | Estado |
|---|---|---|
| 1.1 | Crear tabla DynamoDB | ⬜ |
| 1.2 | Insertar item producción | ⬜ |
| 1.3 | Insertar item desarrollo local | ⬜ |
| 1.4 | Crear bucket S3 | ⬜ |
| 1.5 | Crear política y rol IAM | ⬜ |
| — | Verificación final | ⬜ |

**Sprint completado:** ⬜

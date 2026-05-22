#!/bin/bash
# Inserta los items de configuración en DynamoDB Local
# Ejecutar después de levantar docker-compose

ENDPOINT="http://localhost:8005"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Creando tabla agro_sentinel_config..."
aws dynamodb create-table \
  --endpoint-url "$ENDPOINT" \
  --table-name agro_sentinel_config \
  --attribute-definitions \
    AttributeName=pk,AttributeType=S \
    AttributeName=sk,AttributeType=S \
  --key-schema \
    AttributeName=pk,KeyType=HASH \
    AttributeName=sk,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST \
  --region us-east-1

echo "Insertando item local..."
aws dynamodb put-item \
  --endpoint-url "$ENDPOINT" \
  --table-name agro_sentinel_config \
  --item file://"$SCRIPT_DIR/config-local.json" \
  --region us-east-1

echo ""
echo "Verificando item insertado..."
aws dynamodb get-item \
  --endpoint-url "$ENDPOINT" \
  --table-name agro_sentinel_config \
  --key '{"pk": {"S": "local"}, "sk": {"S": "active"}}' \
  --region us-east-1

echo ""
echo "Setup completado."

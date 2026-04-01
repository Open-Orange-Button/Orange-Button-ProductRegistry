#!/bin/bash
set -e

ACCOUNT_ID="545009828484"
REGION="us-east-1"
REPO="ob-product-registry-2026-02-repo"
CLUSTER="ob-product-registry-2026-02-cluster"
SERVICE="ob-product-registry-2026-02-service"
ECR_URL="$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$REPO"

echo "=== ECR Login ==="
aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com

echo "=== Building Docker image ==="
docker build -t ob-product-registry .

echo "=== Tagging and pushing ==="
docker tag ob-product-registry:latest $ECR_URL:latest
docker push $ECR_URL:latest

echo "=== Deploying to ECS ==="
aws ecs update-service --cluster $CLUSTER --service $SERVICE --force-new-deployment \
  --query 'service.deployments[0].rolloutState' --output text

echo "=== Waiting for deployment ==="
while true; do
    sleep 15
    STATUS=$(aws ecs describe-services --cluster $CLUSTER --services $SERVICE \
      --query 'services[0].deployments[0].rolloutState' --output text)
    RUNNING=$(aws ecs describe-services --cluster $CLUSTER --services $SERVICE \
      --query 'services[0].deployments[0].runningCount' --output text)
    echo "  Status: $STATUS | Running: $RUNNING"
    if [ "$STATUS" = "COMPLETED" ]; then
        break
    fi
done

echo "=== Deployment complete ==="
echo "Live at: https://productregistry.oballiance.org/product/"

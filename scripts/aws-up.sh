#!/bin/bash
# Start the EC2 instance and bring the app containers up.
#
# Usage: ./scripts/aws-up.sh
#
# Docker on the instance is enabled at boot and every container has
# `restart: unless-stopped`, so containers will usually resume on their
# own once the instance is running — this script's final step is just a
# safety net that re-runs `docker-compose up -d` explicitly, in case a
# container didn't come back cleanly.

set -euo pipefail

INSTANCE_ID="i-0902c55037d9f9b30"
REGION="ap-south-1"
ELASTIC_IP="13.126.244.219"

echo "==> Starting EC2 instance ($INSTANCE_ID)..."
aws ec2 start-instances --region "$REGION" --instance-ids "$INSTANCE_ID" >/dev/null

echo "==> Waiting for it to reach 'running'..."
aws ec2 wait instance-running --region "$REGION" --instance-ids "$INSTANCE_ID"
echo "    Instance is running."

echo "==> Waiting for the SSM agent to register (can take ~1-2 min after boot)..."
for i in $(seq 1 30); do
  STATUS=$(aws ec2 describe-instance-status --region "$REGION" --instance-ids "$INSTANCE_ID" \
    --query 'InstanceStatuses[0].InstanceStatus.Status' --output text 2>/dev/null || echo "")
  PING=$(aws ssm describe-instance-information --region "$REGION" \
    --filters "Key=InstanceIds,Values=$INSTANCE_ID" \
    --query 'InstanceInformationList[0].PingStatus' --output text 2>/dev/null || echo "")
  if [ "$PING" == "Online" ]; then
    echo "    SSM is online."
    break
  fi
  sleep 5
  if [ "$i" -eq 30 ]; then
    echo "    SSM did not come online in time — check the instance manually." >&2
    exit 1
  fi
done

echo "==> Making sure the app containers are up (docker-compose up -d)..."
COMMAND_ID=$(aws ssm send-command \
  --region "$REGION" \
  --instance-ids "$INSTANCE_ID" \
  --document-name "AWS-RunShellScript" \
  --comment "aws-up.sh: ensure containers are running" \
  --parameters '{"commands":["cd /opt/app","docker-compose -f docker-compose.deploy.yml up -d","docker ps -a --format \"table {{.Names}}\\t{{.Status}}\""]}' \
  --query "Command.CommandId" --output text)

echo "    SSM command: $COMMAND_ID"
until aws ssm get-command-invocation --region "$REGION" --command-id "$COMMAND_ID" \
  --instance-id "$INSTANCE_ID" --query Status --output text 2>/dev/null | grep -qE "Success|Failed"; do
  sleep 3
done

aws ssm get-command-invocation --region "$REGION" --command-id "$COMMAND_ID" \
  --instance-id "$INSTANCE_ID" --query StandardOutputContent --output text

echo ""
echo "==> Done. App should be reachable at:"
echo "    API:     http://$ELASTIC_IP"
echo "    Webapp:  http://$ELASTIC_IP:3000"
echo ""
echo "Verify with: curl http://$ELASTIC_IP/health"

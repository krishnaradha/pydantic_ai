#!/bin/bash
# Phase 2 — Integration. Connects the resources from
# scripts/aws-create-resources.sh together: pushes the AWS-specific deploy
# files onto the instance, sets the GitHub Actions secrets the CI/CD
# pipeline needs, and (optionally) triggers the first deploy.
#
# Full explanation of what this does and why:
#   docs/tutorials/aws/integration/end-to-end-setup.md
#
# Usage:
#   export AWS_REGION=ap-south-1
#   export EC2_INSTANCE_ID=i-xxxxxxxxxxxxxxxxx
#   export ECR_REGISTRY=<account-id>.dkr.ecr.<region>.amazonaws.com
#   export PUBLIC_API_URL=http://<elastic-ip>
#   export AWS_ACCESS_KEY_ID=...        # the gha-deploy user's key
#   export AWS_SECRET_ACCESS_KEY=...    # shown once when it was created
#   export GITHUB_REPO=owner/repo       # e.g. krishnaradha/pydantic_ai
#   ./scripts/aws-integrate.sh
#
# Required env vars:
#   AWS_REGION              Region everything was created in
#   EC2_INSTANCE_ID          From aws-create-resources.sh's summary output
#   ECR_REGISTRY             From aws-create-resources.sh's summary output
#   PUBLIC_API_URL           http://<elastic-ip> — baked into the frontend build
#   AWS_ACCESS_KEY_ID        gha-deploy's access key (for GitHub secrets)
#   AWS_SECRET_ACCESS_KEY    gha-deploy's secret key (for GitHub secrets)
#   GITHUB_REPO              owner/repo, so `gh secret set` targets the right repo
#
# Optional:
#   SKIP_GH_SECRETS=1        Skip setting GitHub Actions secrets (e.g. if
#                             you don't have `gh` authenticated here)
#   SKIP_PUSH_FILES=1        Skip pushing docker-compose.deploy.yml/nginx.conf
#                             (e.g. on a re-run where they're already there)

set -euo pipefail

: "${AWS_REGION:?Set AWS_REGION}"
: "${EC2_INSTANCE_ID:?Set EC2_INSTANCE_ID (from aws-create-resources.sh output)}"
: "${ECR_REGISTRY:?Set ECR_REGISTRY (from aws-create-resources.sh output)}"
: "${PUBLIC_API_URL:?Set PUBLIC_API_URL, e.g. http://<elastic-ip>}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# ---------------------------------------------------------------------------
# 1. Push the AWS-specific deploy files onto the instance
# ---------------------------------------------------------------------------
if [ "${SKIP_PUSH_FILES:-0}" != "1" ]; then
  echo "==> [1/3] Pushing docker-compose.deploy.yml and nginx.conf to /opt/app"

  COMPOSE_B64=$(base64 <"$REPO_ROOT/docker-compose.deploy.yml" | tr -d '\n')
  NGINX_B64=$(base64 <"$REPO_ROOT/nginx/nginx.conf" | tr -d '\n')

  cat >/tmp/aws-integrate-push.json <<EOF
{
  "commands": [
    "mkdir -p /opt/app/nginx /opt/app/docs",
    "echo '$COMPOSE_B64' | base64 -d > /opt/app/docker-compose.deploy.yml",
    "echo '$NGINX_B64' | base64 -d > /opt/app/nginx/nginx.conf",
    "chown -R ec2-user:ec2-user /opt/app"
  ]
}
EOF

  COMMAND_ID=$(aws ssm send-command --region "$AWS_REGION" \
    --instance-ids "$EC2_INSTANCE_ID" \
    --document-name "AWS-RunShellScript" \
    --comment "aws-integrate.sh: push deploy files" \
    --parameters file:///tmp/aws-integrate-push.json \
    --query "Command.CommandId" --output text)

  until aws ssm get-command-invocation --region "$AWS_REGION" --command-id "$COMMAND_ID" \
    --instance-id "$EC2_INSTANCE_ID" --query Status --output text 2>/dev/null | grep -qE "Success|Failed"; do
    sleep 3
  done
  STATUS=$(aws ssm get-command-invocation --region "$AWS_REGION" --command-id "$COMMAND_ID" \
    --instance-id "$EC2_INSTANCE_ID" --query Status --output text)
  if [ "$STATUS" != "Success" ]; then
    echo "    Failed — check with: aws ssm get-command-invocation --command-id $COMMAND_ID --instance-id $EC2_INSTANCE_ID" >&2
    exit 1
  fi
  echo "    Done."
else
  echo "==> [1/3] Skipped (SKIP_PUSH_FILES=1)"
fi

# ---------------------------------------------------------------------------
# 2. GitHub Actions secrets
# ---------------------------------------------------------------------------
if [ "${SKIP_GH_SECRETS:-0}" != "1" ]; then
  echo ""
  echo "==> [2/3] Setting GitHub Actions secrets"
  : "${AWS_ACCESS_KEY_ID:?Set AWS_ACCESS_KEY_ID (gha-deploy's key), or set SKIP_GH_SECRETS=1}"
  : "${AWS_SECRET_ACCESS_KEY:?Set AWS_SECRET_ACCESS_KEY (gha-deploy's secret), or set SKIP_GH_SECRETS=1}"
  : "${GITHUB_REPO:?Set GITHUB_REPO=owner/repo, or set SKIP_GH_SECRETS=1}"

  if ! command -v gh >/dev/null 2>&1; then
    echo "    gh CLI not found. Install it, run 'gh auth login', then re-run this script" >&2
    echo "    (or set SKIP_GH_SECRETS=1 and add the secrets manually)." >&2
    exit 1
  fi

  gh secret set AWS_ACCESS_KEY_ID --repo "$GITHUB_REPO" --body "$AWS_ACCESS_KEY_ID"
  gh secret set AWS_SECRET_ACCESS_KEY --repo "$GITHUB_REPO" --body "$AWS_SECRET_ACCESS_KEY"
  gh secret set AWS_REGION --repo "$GITHUB_REPO" --body "$AWS_REGION"
  gh secret set ECR_REGISTRY --repo "$GITHUB_REPO" --body "$ECR_REGISTRY"
  gh secret set EC2_INSTANCE_ID --repo "$GITHUB_REPO" --body "$EC2_INSTANCE_ID"
  gh secret set PUBLIC_API_URL --repo "$GITHUB_REPO" --body "$PUBLIC_API_URL"
  echo "    Set 6 secrets on $GITHUB_REPO."
else
  echo ""
  echo "==> [2/3] Skipped (SKIP_GH_SECRETS=1)"
fi

# ---------------------------------------------------------------------------
# 3. Summary
# ---------------------------------------------------------------------------
echo ""
echo "================================================================"
echo " Integration complete."
echo "================================================================"
echo "Next steps:"
echo "  1. Make sure application secrets exist in SSM Parameter Store"
echo "     (docs/tutorials/aws/resource-creation/06-ssm-parameters.md)."
echo "  2. Push to main to trigger the first deploy:"
echo "       git push origin main"
echo "     ...or trigger it manually:"
echo "       gh workflow run deploy.yml --repo ${GITHUB_REPO:-<owner/repo>}"
echo "  3. Verify: curl ${PUBLIC_API_URL}/health"

#!/bin/bash
# Phase 1 — Resource creation. Creates every AWS resource the free-tier
# deployment needs, from an empty account: IAM identities, ECR repos, a
# security group, an EC2 instance, an Elastic IP, and an S3 bucket.
#
# Full explanation of what each step does and why:
#   docs/tutorials/aws/resource-creation/
#
# Usage:
#   export AWS_REGION=ap-south-1
#   ./scripts/aws-create-resources.sh
#
# Required env vars:
#   AWS_REGION        AWS region to create everything in (e.g. ap-south-1)
#
# Optional env vars (sane defaults shown):
#   PROJECT_NAME       multi-agentic     Prefix for resource names
#   INSTANCE_TYPE       t3.micro          EC2 instance type (keep this for free tier)
#   EBS_VOLUME_GB       20                Root volume size (free tier covers up to 30GB)
#   VPC_ID              (auto-detected)   Uses the account's default VPC if unset
#   SUBNET_ID           (auto-detected)   Uses the first subnet in that VPC if unset
#
# This script is safe to re-run — it checks whether each resource already
# exists before creating it. It does NOT set application secrets (API
# keys) in SSM Parameter Store — that's a manual step with real values
# only you have; see docs/tutorials/aws/resource-creation/06-ssm-parameters.md.

set -euo pipefail

: "${AWS_REGION:?Set AWS_REGION, e.g. export AWS_REGION=ap-south-1}"
PROJECT_NAME="${PROJECT_NAME:-multi-agentic}"
INSTANCE_TYPE="${INSTANCE_TYPE:-t3.micro}"
EBS_VOLUME_GB="${EBS_VOLUME_GB:-20}"

SSM_PATH="/${PROJECT_NAME}"
SG_NAME="${PROJECT_NAME}-sg"
INSTANCE_NAME="${PROJECT_NAME}-system"

echo "==> Region: $AWS_REGION   Project: $PROJECT_NAME"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "==> Account: $ACCOUNT_ID"

# ---------------------------------------------------------------------------
# 1. IAM
# ---------------------------------------------------------------------------
echo ""
echo "==> [1/7] IAM: gha-deploy user"
if ! aws iam get-user --user-name gha-deploy >/dev/null 2>&1; then
  aws iam create-user --user-name gha-deploy >/dev/null
  aws iam attach-user-policy --user-name gha-deploy \
    --policy-arn arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryPowerUser

  cat >/tmp/gha-deploy-ssm-policy.json <<'EOF'
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["ssm:SendCommand", "ssm:GetCommandInvocation"],
    "Resource": "*"
  }]
}
EOF
  aws iam put-user-policy --user-name gha-deploy \
    --policy-name gha-deploy-ssm --policy-document file:///tmp/gha-deploy-ssm-policy.json

  echo "    Created. Generating access key — SAVE THIS, it's shown once:"
  aws iam create-access-key --user-name gha-deploy
else
  echo "    gha-deploy already exists, skipping (no new access key generated)."
fi

echo "==> [1/7] IAM: ec2-app-role"
if ! aws iam get-role --role-name ec2-app-role >/dev/null 2>&1; then
  aws iam create-role --role-name ec2-app-role --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{"Effect":"Allow","Principal":{"Service":"ec2.amazonaws.com"},"Action":"sts:AssumeRole"}]
  }' >/dev/null

  aws iam attach-role-policy --role-name ec2-app-role \
    --policy-arn arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly
  aws iam attach-role-policy --role-name ec2-app-role \
    --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
  aws iam attach-role-policy --role-name ec2-app-role \
    --policy-arn arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess

  cat >/tmp/ec2-app-ssm-params-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["ssm:GetParameter", "ssm:GetParameters", "ssm:GetParametersByPath"],
      "Resource": [
        "arn:aws:ssm:${AWS_REGION}:${ACCOUNT_ID}:parameter${SSM_PATH}",
        "arn:aws:ssm:${AWS_REGION}:${ACCOUNT_ID}:parameter${SSM_PATH}/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": ["kms:Decrypt"],
      "Resource": "arn:aws:kms:${AWS_REGION}:${ACCOUNT_ID}:alias/aws/ssm"
    }
  ]
}
EOF
  aws iam put-role-policy --role-name ec2-app-role \
    --policy-name ec2-app-ssm-params --policy-document file:///tmp/ec2-app-ssm-params-policy.json

  aws iam create-instance-profile --instance-profile-name ec2-app-profile >/dev/null
  aws iam add-role-to-instance-profile \
    --instance-profile-name ec2-app-profile --role-name ec2-app-role
  # Instance profiles take a few seconds to propagate before EC2 can use them.
  sleep 10
else
  echo "    ec2-app-role already exists, skipping."
fi

# ---------------------------------------------------------------------------
# 2. ECR
# ---------------------------------------------------------------------------
echo ""
echo "==> [2/7] ECR repositories"
for repo in "${PROJECT_NAME}/api" "${PROJECT_NAME}/webapp"; do
  if ! aws ecr describe-repositories --region "$AWS_REGION" --repository-names "$repo" >/dev/null 2>&1; then
    aws ecr create-repository --region "$AWS_REGION" --repository-name "$repo" >/dev/null
    echo "    Created $repo"
  else
    echo "    $repo already exists, skipping."
  fi
done
ECR_REGISTRY="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

# ---------------------------------------------------------------------------
# 3. Security group
# ---------------------------------------------------------------------------
echo ""
echo "==> [3/7] Security group"
if [ -z "${VPC_ID:-}" ]; then
  VPC_ID=$(aws ec2 describe-vpcs --region "$AWS_REGION" --filters Name=is-default,Values=true \
    --query 'Vpcs[0].VpcId' --output text)
  echo "    Using default VPC: $VPC_ID"
fi

SG_ID=$(aws ec2 describe-security-groups --region "$AWS_REGION" \
  --filters Name=group-name,Values="$SG_NAME" Name=vpc-id,Values="$VPC_ID" \
  --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null || echo "None")

if [ "$SG_ID" == "None" ] || [ -z "$SG_ID" ]; then
  SG_ID=$(aws ec2 create-security-group --region "$AWS_REGION" \
    --group-name "$SG_NAME" --description "$PROJECT_NAME EC2" --vpc-id "$VPC_ID" \
    --query 'GroupId' --output text)
  for port in 80 443 3000; do
    aws ec2 authorize-security-group-ingress --region "$AWS_REGION" --group-id "$SG_ID" \
      --protocol tcp --port "$port" --cidr 0.0.0.0/0 >/dev/null
  done
  echo "    Created $SG_ID with 80/443/3000 open"
else
  echo "    $SG_NAME already exists ($SG_ID), skipping."
fi

# ---------------------------------------------------------------------------
# 4. EC2 instance
# ---------------------------------------------------------------------------
echo ""
echo "==> [4/7] EC2 instance"
INSTANCE_ID=$(aws ec2 describe-instances --region "$AWS_REGION" \
  --filters Name=tag:Name,Values="$INSTANCE_NAME" Name=instance-state-name,Values=pending,running,stopped,stopping \
  --query 'Reservations[0].Instances[0].InstanceId' --output text 2>/dev/null || echo "None")

if [ "$INSTANCE_ID" == "None" ] || [ -z "$INSTANCE_ID" ]; then
  if [ -z "${SUBNET_ID:-}" ]; then
    SUBNET_ID=$(aws ec2 describe-subnets --region "$AWS_REGION" --filters Name=vpc-id,Values="$VPC_ID" \
      --query 'Subnets[0].SubnetId' --output text)
    echo "    Using subnet: $SUBNET_ID"
  fi

  AMI_ID=$(aws ssm get-parameters --region "$AWS_REGION" \
    --names /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 \
    --query 'Parameters[0].Value' --output text)

  cat >/tmp/ec2-bootstrap.sh <<'EOF'
#!/bin/bash
dnf install -y docker
systemctl enable --now docker
usermod -aG docker ec2-user

curl -SL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64 \
  -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

mkdir -p /opt/app
chown ec2-user:ec2-user /opt/app
EOF

  INSTANCE_ID=$(aws ec2 run-instances --region "$AWS_REGION" \
    --image-id "$AMI_ID" \
    --instance-type "$INSTANCE_TYPE" \
    --iam-instance-profile Name=ec2-app-profile \
    --security-group-ids "$SG_ID" \
    --subnet-id "$SUBNET_ID" \
    --associate-public-ip-address \
    --block-device-mappings "[{\"DeviceName\":\"/dev/xvda\",\"Ebs\":{\"VolumeSize\":${EBS_VOLUME_GB},\"VolumeType\":\"gp3\"}}]" \
    --user-data file:///tmp/ec2-bootstrap.sh \
    --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$INSTANCE_NAME}]" \
    --query 'Instances[0].InstanceId' --output text)

  echo "    Launched $INSTANCE_ID, waiting for it to start running..."
  aws ec2 wait instance-running --region "$AWS_REGION" --instance-ids "$INSTANCE_ID"
  echo "    Running."
else
  echo "    $INSTANCE_NAME already exists ($INSTANCE_ID), skipping."
fi

# ---------------------------------------------------------------------------
# 5. Elastic IP
# ---------------------------------------------------------------------------
echo ""
echo "==> [5/7] Elastic IP"
EIP=$(aws ec2 describe-addresses --region "$AWS_REGION" --filters Name=instance-id,Values="$INSTANCE_ID" \
  --query 'Addresses[0].PublicIp' --output text 2>/dev/null || echo "None")

if [ "$EIP" == "None" ] || [ -z "$EIP" ]; then
  ALLOCATION_ID=$(aws ec2 allocate-address --region "$AWS_REGION" --domain vpc --query AllocationId --output text)
  aws ec2 associate-address --region "$AWS_REGION" \
    --instance-id "$INSTANCE_ID" --allocation-id "$ALLOCATION_ID" >/dev/null
  EIP=$(aws ec2 describe-addresses --region "$AWS_REGION" --allocation-ids "$ALLOCATION_ID" \
    --query 'Addresses[0].PublicIp' --output text)
  echo "    Allocated and attached: $EIP"
else
  echo "    Already has an Elastic IP: $EIP"
fi

# ---------------------------------------------------------------------------
# 6. SSM Parameter Store — path only; real secret values are a manual step
# ---------------------------------------------------------------------------
echo ""
echo "==> [6/7] SSM Parameter Store"
echo "    This script does not set secret values (it doesn't have them)."
echo "    Set them yourself, e.g.:"
echo "      aws ssm put-parameter --region $AWS_REGION --name ${SSM_PATH}/OPENAI_API_KEY --type SecureString --value \"sk-...\""
echo "      aws ssm put-parameter --region $AWS_REGION --name ${SSM_PATH}/TAVILY_API_KEY --type SecureString --value \"tvly-...\""
echo "      aws ssm put-parameter --region $AWS_REGION --name ${SSM_PATH}/E2B_API_KEY --type SecureString --value \"e2b_...\""
echo "      aws ssm put-parameter --region $AWS_REGION --name ${SSM_PATH}/CORS_ORIGINS --type String --value \"http://${EIP}:3000\""
echo "    Full list: docs/tutorials/aws/resource-creation/06-ssm-parameters.md"

# ---------------------------------------------------------------------------
# 7. S3 bucket
# ---------------------------------------------------------------------------
echo ""
echo "==> [7/7] S3 bucket"
BUCKET="${PROJECT_NAME}-rag-docs-${ACCOUNT_ID}"
if ! aws s3api head-bucket --bucket "$BUCKET" >/dev/null 2>&1; then
  aws s3 mb "s3://$BUCKET" --region "$AWS_REGION" >/dev/null
  aws s3api put-bucket-versioning --bucket "$BUCKET" --versioning-configuration Status=Enabled
  echo "    Created $BUCKET"
else
  echo "    $BUCKET already exists, skipping."
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "================================================================"
echo " Resource creation complete. Save these for the integration step:"
echo "================================================================"
echo "AWS_REGION=$AWS_REGION"
echo "ECR_REGISTRY=$ECR_REGISTRY"
echo "EC2_INSTANCE_ID=$INSTANCE_ID"
echo "ELASTIC_IP=$EIP"
echo "PUBLIC_API_URL=http://$EIP"
echo "S3_BUCKET=$BUCKET"
echo ""
echo "Next steps:"
echo "  1. Set the real application secrets in SSM (see [6/7] above)."
echo "  2. Run scripts/aws-integrate.sh with the values above as env vars."

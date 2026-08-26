# AWS Resource Checklist — Run & Verify

Companion to [aws-setup-guide.md](aws-setup-guide.md) Part 1. Run each step,
then run its verify command before moving to the next. Fill in the
placeholders (`<...>`) as you go — jot down the real values somewhere, later
steps reuse them.

Prereqs: AWS CLI installed and configured (`aws configure`) with an IAM user
that has admin/broad permissions for initial setup (you can lock this down
later — the `gha-deploy` and `ec2-app-role` identities created below are the
narrow, ongoing-use identities).

```bash
aws sts get-caller-identity   # confirms CLI is authenticated; note your Account ID
```

---

## Step 0 — pick your region

```bash
export AWS_REGION=us-east-1   # or whatever region you want everything in
aws configure set region $AWS_REGION
```

Verify:
```bash
aws configure get region
```

---

## Step 1 — `gha-deploy` IAM user (used by GitHub Actions)

```bash
aws iam create-user --user-name gha-deploy
```
Verify:
```bash
aws iam get-user --user-name gha-deploy
```

```bash
aws iam attach-user-policy \
  --user-name gha-deploy \
  --policy-arn arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryPowerUser
```
Verify:
```bash
aws iam list-attached-user-policies --user-name gha-deploy
```

```bash
cat > /tmp/gha-deploy-ssm-policy.json <<'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["ssm:SendCommand", "ssm:GetCommandInvocation"],
      "Resource": "*"
    }
  ]
}
EOF
aws iam put-user-policy \
  --user-name gha-deploy \
  --policy-name gha-deploy-ssm \
  --policy-document file:///tmp/gha-deploy-ssm-policy.json
```
Verify:
```bash
aws iam get-user-policy --user-name gha-deploy --policy-name gha-deploy-ssm
```

```bash
aws iam create-access-key --user-name gha-deploy
```
**Copy `AccessKeyId` and `SecretAccessKey` from the output now — the secret
is never shown again.** Save both somewhere safe; they go into GitHub repo
secrets later (`AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`).

Verify:
```bash
aws iam list-access-keys --user-name gha-deploy
```

---

## Step 2 — `ec2-app-role` IAM role (attached to the EC2 instance)

```bash
aws iam create-role \
  --role-name ec2-app-role \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": {"Service": "ec2.amazonaws.com"},
      "Action": "sts:AssumeRole"
    }]
  }'
```
Verify:
```bash
aws iam get-role --role-name ec2-app-role
```

```bash
aws iam attach-role-policy --role-name ec2-app-role \
  --policy-arn arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly
aws iam attach-role-policy --role-name ec2-app-role \
  --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
aws iam attach-role-policy --role-name ec2-app-role \
  --policy-arn arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess
```
Verify:
```bash
aws iam list-attached-role-policies --role-name ec2-app-role
```

```bash
aws iam create-instance-profile --instance-profile-name ec2-app-profile
aws iam add-role-to-instance-profile \
  --instance-profile-name ec2-app-profile --role-name ec2-app-role
```
Verify:
```bash
aws iam get-instance-profile --instance-profile-name ec2-app-profile
```

---

## Step 3 — ECR: one repo per image

```bash
aws ecr create-repository --repository-name multi-agentic/api
aws ecr create-repository --repository-name multi-agentic/webapp
```
Verify:
```bash
aws ecr describe-repositories --repository-names multi-agentic/api multi-agentic/webapp
```

Note the registry URL for later (GitHub secret `ECR_REGISTRY`):
```bash
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
```

---

## Step 4 — security group

Find your default VPC first if you don't already have one picked out:
```bash
aws ec2 describe-vpcs --filters Name=is-default,Values=true \
  --query 'Vpcs[0].VpcId' --output text
```
Save that as `VPC_ID`:
```bash
export VPC_ID=<paste VPC id here>
```

```bash
aws ec2 create-security-group \
  --group-name multi-agentic-sg \
  --description "multi-agentic-system EC2" \
  --vpc-id $VPC_ID
```
Verify and capture the group id:
```bash
export SG_ID=$(aws ec2 describe-security-groups \
  --filters Name=group-name,Values=multi-agentic-sg \
  --query 'SecurityGroups[0].GroupId' --output text)
echo $SG_ID
```

```bash
# HTTP/HTTPS directly from the internet — this instance is the public entry point
aws ec2 authorize-security-group-ingress --group-id $SG_ID \
  --protocol tcp --port 80 --cidr 0.0.0.0/0
aws ec2 authorize-security-group-ingress --group-id $SG_ID \
  --protocol tcp --port 443 --cidr 0.0.0.0/0
# No inbound SSH rule needed — SSM Session Manager replaces it.
```
Verify:
```bash
aws ec2 describe-security-groups --group-ids $SG_ID \
  --query 'SecurityGroups[0].IpPermissions'
```

---

## Step 5 — launch the EC2 instance

Find a subnet in that VPC:
```bash
aws ec2 describe-subnets --filters Name=vpc-id,Values=$VPC_ID \
  --query 'Subnets[0].SubnetId' --output text
```
```bash
export SUBNET_ID=<paste subnet id here>
```

Find the latest Amazon Linux 2023 AMI for your region:
```bash
export AMI_ID=$(aws ssm get-parameters --names \
  /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 \
  --query 'Parameters[0].Value' --output text)
echo $AMI_ID
```

Create the bootstrap script (installs Docker + Docker Compose only — it does
**not** clone the repo or build images, see [aws-setup-guide.md](aws-setup-guide.md) 1.4):
```bash
cat > /tmp/ec2-bootstrap.sh <<'EOF'
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
```

```bash
aws ec2 run-instances \
  --image-id $AMI_ID \
  --instance-type t3.micro \
  --iam-instance-profile Name=ec2-app-profile \
  --security-group-ids $SG_ID \
  --subnet-id $SUBNET_ID \
  --associate-public-ip-address \
  --block-device-mappings '[{"DeviceName":"/dev/xvda","Ebs":{"VolumeSize":20,"VolumeType":"gp3"}}]' \
  --user-data file:///tmp/ec2-bootstrap.sh \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=multi-agentic-system}]'
```

Capture the instance id and wait for it to boot:
```bash
export INSTANCE_ID=$(aws ec2 describe-instances \
  --filters Name=tag:Name,Values=multi-agentic-system Name=instance-state-name,Values=pending,running \
  --query 'Reservations[0].Instances[0].InstanceId' --output text)
echo $INSTANCE_ID

aws ec2 wait instance-running --instance-ids $INSTANCE_ID
```

Verify it's up and SSM can reach it (takes ~1-2 min after boot for the SSM
agent to register):
```bash
aws ec2 describe-instances --instance-ids $INSTANCE_ID \
  --query 'Reservations[0].Instances[0].[State.Name,PublicIpAddress]'

aws ssm describe-instance-information \
  --filters Key=InstanceIds,Values=$INSTANCE_ID
```

---

## Step 6 — allocate an Elastic IP

```bash
export ALLOC_ID=$(aws ec2 allocate-address --domain vpc --query AllocationId --output text)
aws ec2 associate-address --instance-id $INSTANCE_ID --allocation-id $ALLOC_ID
```
Verify and note the public IP — this is the URL you'll hit the app on:
```bash
aws ec2 describe-addresses --allocation-ids $ALLOC_ID \
  --query 'Addresses[0].PublicIp' --output text
```

---

## Step 7 — SSM Parameter Store: app secrets

Repeat for each variable currently in your local `.env`:
```bash
aws ssm put-parameter --name /multi-agentic/OPENAI_API_KEY --type SecureString --value "sk-..."
aws ssm put-parameter --name /multi-agentic/CORS_ORIGINS --type String --value "http://<ELASTIC_IP>"
```
Verify:
```bash
aws ssm get-parameters-by-path --path /multi-agentic --with-decryption \
  --query 'Parameters[].Name'
```

---

## Step 8 — S3 bucket for RAG source documents

Bucket names are globally unique — this uses your account ID as a suffix so
it won't collide with anyone else's:
```bash
export ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export RAG_BUCKET=multi-agentic-rag-docs-$ACCOUNT_ID
echo $RAG_BUCKET

aws s3 mb s3://$RAG_BUCKET
aws s3api put-bucket-versioning --bucket $RAG_BUCKET \
  --versioning-configuration Status=Enabled
```
Verify:
```bash
aws s3api get-bucket-versioning --bucket $RAG_BUCKET
```

---

## Done — what you should have now

- IAM: `gha-deploy` user (with access key saved) + `ec2-app-role`/`ec2-app-profile`
- ECR: `multi-agentic/api` and `multi-agentic/webapp` repos
- A running EC2 `t3.micro` with an Elastic IP attached, reachable over SSM
- SSM Parameter Store populated under `/multi-agentic/*`
- An S3 bucket for RAG docs

Next: Part 2 of [aws-setup-guide.md](aws-setup-guide.md) (GitHub Actions
CI/CD) — add the repo secrets (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`,
`AWS_REGION`, `ECR_REGISTRY`, `EC2_INSTANCE_ID`) and commit the workflow.

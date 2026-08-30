# 4. EC2 Instance — The Server

Part of the [AWS resource creation](README.md) series. Requires
[1. IAM](01-iam.md) (the instance profile) and
[3. Security Group](03-security-group.md) to exist first.

## What is EC2?

**EC2 (Elastic Compute Cloud)** is AWS's virtual machine service — it's
just a computer you rent by the hour (or, within the free tier, for free),
living in an AWS data center. This is where the actual application
containers run.

## Why one single instance?

This project deliberately runs everything (`api`, `webapp`, `redis`,
`chromadb`, `nginx`, all as Docker containers) on **one** EC2 instance,
rather than AWS's more "proper" managed-container options like ECS Fargate.
The reason is cost: a single `t3.micro` instance is free for 12 months
under AWS's free tier (750 hours/month — enough for one instance running
continuously), while Fargate has no free tier at all. See
[aws-architecture.md](../../../aws-architecture.md) for the full reasoning
and the tradeoffs (single point of failure, no redundancy — acceptable for
a demo, not for production traffic at scale).

## Launching the instance

First, find a subnet to launch into — the same VPC used for the security
group in [3. Security Group](03-security-group.md):

```bash
aws ec2 describe-subnets --filters Name=vpc-id,Values=<VPC_ID> \
  --query 'Subnets[0].SubnetId' --output text
```

Any subnet in that VPC works for this single-instance setup — a default VPC
comes with one subnet per availability zone, all equally fine here since
there's no multi-AZ redundancy to plan around.

Then find an AMI (see below):

```bash
aws ec2 run-instances \
  --image-id <AMI_ID> \
  --instance-type t3.micro \
  --iam-instance-profile Name=ec2-app-profile \
  --security-group-ids <SG_ID> \
  --subnet-id <SUBNET_ID> \
  --associate-public-ip-address \
  --block-device-mappings '[{"DeviceName":"/dev/xvda","Ebs":{"VolumeSize":20,"VolumeType":"gp3"}}]' \
  --user-data file://ec2-bootstrap.sh \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=multi-agentic-system}]'
```

Breaking down each flag:

| Flag | What it means |
|---|---|
| `--image-id` | Which **AMI** (Amazon Machine Image — a template OS + preinstalled software) to boot from. See below for how to find the latest one. |
| `--instance-type t3.micro` | The hardware size — 2 vCPUs (burstable), 1GB RAM. Chosen specifically because it's covered by the free tier. |
| `--iam-instance-profile` | Attaches the `ec2-app-profile` from [1. IAM](01-iam.md), which wraps `ec2-app-role` — this is what lets the instance pull from ECR and use SSM without any stored credentials. |
| `--security-group-ids` | Attaches the firewall rules from [3. Security Group](03-security-group.md). |
| `--subnet-id` | Which network subnet (a subdivision of the VPC) the instance lives in. |
| `--associate-public-ip-address` | Gives the instance a public IP so it's reachable from the internet at all (without this, it'd only be reachable from inside the VPC). |
| `--block-device-mappings` | Configures the instance's disk — 20GB `gp3` (general-purpose SSD), well within the free tier's 30GB EBS allowance. |
| `--user-data` | A script that runs automatically the *first time* the instance boots (see below). |
| `--tag-specifications` | Just a human-readable label (`Name=multi-agentic-system`) so it's identifiable in the AWS console/CLI output. |

### Finding the AMI

```bash
aws ssm get-parameters --names \
  /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 \
  --query 'Parameters[0].Value' --output text
```

Rather than hardcoding an AMI ID (which is region-specific and changes as
AWS ships updates), this queries an AWS-maintained SSM parameter that
always points at the current latest Amazon Linux 2023 image for whichever
region you're in.

### `user-data` — the bootstrap script

```bash
#!/bin/bash
dnf install -y docker
systemctl enable --now docker
usermod -aG docker ec2-user

curl -SL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64 \
  -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

mkdir -p /opt/app
chown ec2-user:ec2-user /opt/app
```

This runs once, automatically, the first time the instance boots — before
you've even had a chance to log in. It installs Docker, starts it, installs
the `docker-compose` binary (see
[docker-fundamentals.md](../../docker/docker-fundamentals.md) for why this
specific binary name matters — it's `docker-compose`, hyphenated, not the
`docker compose` plugin, which isn't preinstalled here), and creates
`/opt/app` — the directory where the actual application files will live.

Deliberately, this script does **not** clone the git repo or build any
images — the instance only ever *pulls* pre-built images from ECR (see
[2. ECR](02-ecr.md)). What it needs beyond Docker itself
(`docker-compose.deploy.yml`, `nginx/nginx.conf`) gets placed there by the
deploy process, covered in the integration phase.

## Verifying it worked

```bash
aws ec2 describe-instances --instance-ids <INSTANCE_ID> \
  --query 'Reservations[0].Instances[0].[State.Name,PublicIpAddress]'
```
Should show `"running"` and a public IP address.

```bash
aws ssm describe-instance-information \
  --filters Key=InstanceIds,Values=<INSTANCE_ID>
```
Confirms the SSM agent registered successfully — this can take 1–2 minutes
after boot. If this returns empty, the instance either isn't fully booted
yet, or `ec2-app-role`'s `AmazonSSMManagedInstanceCore` policy (from
[1. IAM](01-iam.md)) isn't actually attached.

## What's next

[5. Elastic IP](05-elastic-ip.md)

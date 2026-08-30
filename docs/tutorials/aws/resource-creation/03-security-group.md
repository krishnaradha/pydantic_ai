# 3. Security Group — Network Firewall

Part of the [AWS resource creation](README.md) series. Assumes
[1. IAM](01-iam.md) is done. Independent of [2. ECR](02-ecr.md) — can be
done in either order.

## What is a security group?

A **security group** is a virtual firewall attached to AWS resources
(most commonly EC2 instances). It controls what network traffic is allowed
**in** (inbound rules) and **out** (outbound rules). By default, a newly
created security group allows *no* inbound traffic at all — every port has
to be explicitly opened.

This matters because an EC2 instance, once launched, is a real computer
with a real public IP address, reachable from the entire internet unless
something blocks it. The security group is that block.

## Why explicit rules instead of "allow everything"?

Least privilege again — the app only needs to be reachable on specific
ports. Every additional open port is one more thing an attacker could probe.
This project's instance needs exactly:

- **Port 80** — HTTP, for the API (via nginx)
- **Port 443** — HTTPS (open for future use; this deployment doesn't
  currently terminate TLS, see [aws-architecture.md](../../../aws-architecture.md)
  caveats)
- **Port 3000** — the webapp frontend, served directly (not proxied through
  nginx — see the [CI/CD doc](../../ci-cd/ci-cd-pipeline-explained.md) and
  `docker-compose.deploy.yml` for why)

Nothing else — no database ports, no internal service ports — should be
reachable from the public internet.

## Creating the security group

```bash
aws ec2 describe-vpcs --filters Name=is-default,Values=true \
  --query 'Vpcs[0].VpcId' --output text
```

First, find a **VPC** (Virtual Private Cloud — an isolated network within
your AWS account) to create the security group in. Every AWS account gets
a default VPC automatically; using it is the simplest option for a
single-instance setup like this one.

```bash
aws ec2 create-security-group \
  --group-name multi-agentic-sg \
  --description "multi-agentic-system EC2" \
  --vpc-id <VPC_ID>
```

Creates the security group itself — at this point, it exists but allows no
inbound traffic (only default outbound, which is unrestricted).

```bash
aws ec2 authorize-security-group-ingress --group-id <SG_ID> \
  --protocol tcp --port 80 --cidr 0.0.0.0/0
aws ec2 authorize-security-group-ingress --group-id <SG_ID> \
  --protocol tcp --port 443 --cidr 0.0.0.0/0
aws ec2 authorize-security-group-ingress --group-id <SG_ID> \
  --protocol tcp --port 3000 --cidr 0.0.0.0/0
```

Each `authorize-security-group-ingress` call adds one inbound rule.
Breaking down the flags:
- `--protocol tcp` — the network protocol (TCP, used by virtually all web
  traffic, vs. UDP for things like DNS/video streaming).
- `--port` — which port this rule applies to.
- `--cidr 0.0.0.0/0` — which source IPs are allowed to connect.
  `0.0.0.0/0` means "any IP address on the internet." A CIDR block is a way
  of expressing an IP range; `0.0.0.0/0` is the special case meaning "all of
  them."

## No SSH port — on purpose

Notice port 22 (SSH) is deliberately **not** opened. Normally you'd need
that to log into a server. This project instead uses **SSM Session
Manager** (enabled by the `AmazonSSMManagedInstanceCore` policy from
[1. IAM](01-iam.md)) for remote access — it tunnels a shell session through
the AWS API instead of a direct network connection, so there's no need for
an open inbound port at all:

```bash
aws ssm start-session --target <INSTANCE_ID>
```

If you specifically want SSH as well, you'd add a rule scoped to *your* IP
only, never `0.0.0.0/0`:
```bash
aws ec2 authorize-security-group-ingress --group-id <SG_ID> \
  --protocol tcp --port 22 --cidr <YOUR_IP>/32
```

## Verifying it worked

```bash
aws ec2 describe-security-groups --group-ids <SG_ID> \
  --query 'SecurityGroups[0].IpPermissions'
```

Should list three inbound rules (80, 443, 3000), each with
`0.0.0.0/0` as the source.

## What's next

[4. EC2 Instance](04-ec2-instance.md)

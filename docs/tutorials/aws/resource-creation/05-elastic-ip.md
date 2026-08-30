# 5. Elastic IP — A Fixed Public Address

Part of the [AWS resource creation](README.md) series. Requires
[4. EC2 Instance](04-ec2-instance.md) to exist first.

## The problem this solves

An EC2 instance's default public IP address is **not permanent** — every
time the instance stops and starts again (not reboots — stop/start), it
gets assigned a brand new public IP. That's a problem the moment anything
external depends on a fixed address: a DNS record, a hardcoded URL in a
frontend build, a security group rule, GitHub Actions secrets, etc. — all
of these would silently break on every stop/start cycle.

## What is an Elastic IP?

An **Elastic IP (EIP)** is a static public IP address you allocate to your
AWS account, then attach to an instance. It stays the same regardless of
whether the instance is stopped and restarted — you're "reserving" that
specific address for your own use.

## Allocating and attaching

```bash
aws ec2 allocate-address --domain vpc
```
Reserves a new, unused public IP address for your account. `--domain vpc`
specifies it's for use within a VPC (the only option for any modern AWS
account — a legacy `standard`/"EC2-Classic" mode no longer exists for new
accounts).

```bash
aws ec2 associate-address --instance-id <INSTANCE_ID> --allocation-id <ALLOCATION_ID>
```
Attaches the allocated address to the instance. From this point on, that
specific IP is what the instance is reachable at — and it stays that way
across stop/start cycles.

## The cost nuance that trips people up

Elastic IPs are **free while attached to a running instance** — but AWS
charges a small hourly fee (a few cents/hour) for an EIP that's either
**unattached**, or attached to a **stopped** instance. The reasoning is
scarcity: public IPv4 addresses are a limited resource, and AWS discourages
reserving one you're not actively using.

Practically, this means: if you stop the instance to save money (e.g.
between demos), the EIP itself will accrue a small charge for as long as
it's idle — but releasing the EIP to avoid that charge means losing the
fixed address, which then requires updating every place that referenced it
(GitHub secrets, the frontend's baked-in API URL, CORS config). For a
short idle period (a few days), it's almost always cheaper and less
disruptive to just eat the few cents than to release and reallocate.

## Verifying it worked

```bash
aws ec2 describe-addresses --allocation-ids <ALLOCATION_ID> \
  --query 'Addresses[0].[PublicIp,InstanceId,AssociationId]'
```
Should show the IP address, the instance it's associated with, and a
non-empty `AssociationId` (confirming the attachment, not just the
allocation, succeeded).

Then confirm the instance is actually reachable at that address:
```bash
curl -m 5 -o /dev/null -w "%{http_code}\n" http://<ELASTIC_IP>
```
(This will likely fail/timeout at this stage — nothing is listening on port
80 yet, since no application containers are running. That's expected; this
step only confirms the network path, not the application.)

## What's next

[6. SSM Parameters — Application Secrets](06-ssm-parameters.md)

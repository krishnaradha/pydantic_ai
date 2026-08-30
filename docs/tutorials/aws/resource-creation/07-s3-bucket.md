# 7. S3 Bucket — Document Storage

Part of the [AWS resource creation](README.md) series. Independent of the
other steps — can be done any time. Last step of resource creation.

## What is S3?

**S3 (Simple Storage Service)** is AWS's object storage — a place to store
files (of essentially any type/size) accessed by key, organized into named
**buckets**. Unlike EBS (the disk attached to an EC2 instance), S3 storage
exists independently of any server — it doesn't go away if the instance is
stopped, replaced, or terminated.

## What this bucket is for

This project's RAG (retrieval-augmented generation) pipeline needs a
knowledge base of source documents. Rather than uploading files directly to
the EC2 instance (which would mean SSH/SCP access, and ties the documents'
existence to that one instance surviving), documents get uploaded to an S3
bucket instead — durable, independent storage that other AWS services (like
a future Lambda-based auto-reindex pipeline) can also react to.

## Creating the bucket

```bash
aws s3 mb s3://multi-agentic-rag-docs-<unique-suffix>
```

S3 bucket names are **globally unique across all AWS accounts everywhere**
— not just within your account. `multi-agentic-rag-docs` alone would likely
already be taken by someone else's bucket. Appending something unique (this
project uses the AWS account ID, which is guaranteed unique to you) avoids
any collision:

```bash
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
aws s3 mb s3://multi-agentic-rag-docs-$ACCOUNT_ID
```

```bash
aws s3api put-bucket-versioning --bucket multi-agentic-rag-docs-$ACCOUNT_ID \
  --versioning-configuration Status=Enabled
```

Enables **versioning** — every time a file with the same name is uploaded,
S3 keeps the old version instead of silently overwriting it. This means an
accidental bad upload (or deletion) is recoverable — you can list and
restore previous versions of any object, rather than the update being
destructive and irreversible.

## Verifying it worked

```bash
aws s3api get-bucket-versioning --bucket multi-agentic-rag-docs-$ACCOUNT_ID
```
Should return `{"Status": "Enabled"}`.

```bash
aws s3 ls
```
Should list the bucket among your account's buckets.

Test that it actually works end to end:
```bash
echo "test" > /tmp/test.txt
aws s3 cp /tmp/test.txt s3://multi-agentic-rag-docs-$ACCOUNT_ID/test.txt
aws s3 ls s3://multi-agentic-rag-docs-$ACCOUNT_ID/
aws s3 rm s3://multi-agentic-rag-docs-$ACCOUNT_ID/test.txt   # clean up
```

## A note on cost

S3's free tier (5GB storage) is part of AWS's **permanent** Always Free
tier — unlike EC2/ECR, which are free only for the account's first 12
months, this one doesn't expire. For a folder of text/PDF documents, 5GB is
a very high ceiling to hit.

## Resource creation: complete

All seven resources now exist:

1. [IAM](01-iam.md) — identities and permissions
2. [ECR](02-ecr.md) — image storage
3. [Security Group](03-security-group.md) — firewall rules
4. [EC2 Instance](04-ec2-instance.md) — the server
5. [Elastic IP](05-elastic-ip.md) — fixed public address
6. [SSM Parameters](06-ssm-parameters.md) — application secrets
7. [S3 Bucket](07-s3-bucket.md) — document storage

None of this runs the actual application yet — that's the **integration**
phase: connecting these pieces together so code changes actually become a
running, reachable app. See `docs/tutorials/aws/integration/` (once
written) for that next.

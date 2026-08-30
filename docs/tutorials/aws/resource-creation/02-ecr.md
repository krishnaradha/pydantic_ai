# 2. ECR — Container Image Registry

Part of the [AWS resource creation](README.md) series. Assumes
[1. IAM](01-iam.md) is done.

## What is ECR?

**ECR (Elastic Container Registry)** is AWS's storage service for Docker
images — think of it as a private version of Docker Hub, living inside your
AWS account. When CI/CD builds an image, it gets pushed here; when the EC2
instance deploys, it pulls from here. See
[docker-fundamentals.md](../../docker/docker-fundamentals.md) if "image"
and "registry" aren't familiar terms yet.

## Why a registry at all?

The EC2 instance running the app is not the same machine that *builds* the
app (that's GitHub's CI runner). Something has to sit in between, holding
the built image so the instance can fetch it. Without a registry, you'd
have to build directly on the production server — slower, and it means the
server needs build tools/dependencies it otherwise wouldn't.

**Why ECR specifically, not Docker Hub?** Two reasons: it's private by
default (no accidental public exposure of your app's image), and it's
already inside your AWS account's IAM/networking boundary, so permissions
are managed the same way as everything else (see
[1. IAM](01-iam.md) — `gha-deploy` and `ec2-app-role` were already granted
push/pull access to ECR specifically).

## Creating the repositories

```bash
aws ecr create-repository --repository-name multi-agentic/api
aws ecr create-repository --repository-name multi-agentic/webapp
```

Each `create-repository` call creates one **repository** — a named space
that holds every version (tag) of one particular image. We create two,
because this project has two independently-built images: the FastAPI
backend and the Next.js frontend. Each gets pushed and versioned separately.

The naming (`multi-agentic/api`, `multi-agentic/webapp`) is just a
convention — a "namespace/image-name" pattern that keeps related
repositories grouped together and readable in the AWS console.

## Verifying it worked

```bash
aws ecr describe-repositories --repository-names multi-agentic/api multi-agentic/webapp
```

Should return details for both repos, including a `repositoryUri` field —
that URI (e.g. `123456789012.dkr.ecr.ap-south-1.amazonaws.com/multi-agentic/api`)
is what `docker push`/`docker pull` actually target.

Get the registry's base URL (the part before the repository name) for later
use — this becomes the `ECR_REGISTRY` value used throughout CI/CD:

```bash
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
```

## A note on cost

ECR's free tier covers 500MB/month of storage for the first 12 months of
the AWS account's life. Each image tag (e.g. one per commit SHA, plus
`latest`) takes up space — if left unmanaged, old tags accumulate
indefinitely. Not a problem at small scale/early on, but worth knowing:
`aws ecr list-images` and `aws ecr batch-delete-image` exist for cleanup if
storage ever grows unexpectedly.

## What's next

[3. Security Group](03-security-group.md)

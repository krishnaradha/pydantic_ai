# End-to-End Setup

Everything you need to clone this repo, run it locally, and deploy it to
your own AWS account for **$0** (free-tier). This file is the linear,
copy-paste path — for the "why" behind each step, see the linked docs.

## What you'll end up with

One EC2 instance running the full stack (nginx, api, webapp, redis,
chromadb), images built and shipped automatically by GitHub Actions on
every push, secrets pulled fresh from AWS SSM Parameter Store — never
committed to git. Full design rationale: [docs/aws-architecture.md](docs/aws-architecture.md).

---

## 0. Prerequisites

Accounts you need, and what each one is for:

| Account | For | Sign up |
|---|---|---|
| AWS | Hosting everything | [aws.amazon.com](https://aws.amazon.com) — free-tier account works |
| GitHub | Hosting the code + CI/CD | [github.com](https://github.com) |
| OpenAI | The LLM | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
| Tavily | Web search tool | [tavily.com](https://tavily.com) — free tier |
| E2B | Code-sandbox tool | [e2b.dev](https://e2b.dev) — free tier |

Local tools:

```bash
aws --version      # AWS CLI — https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html
git --version
docker --version   # https://docs.docker.com/get-docker/
gh --version        # brew install gh, or https://cli.github.com
```

Authenticate each one:

```bash
aws configure        # needs an access key from an IAM user with admin access (one-time bootstrap)
gh auth login
docker ps            # confirms the daemon is actually running
```

Full detail: [docs/tutorials/aws/resource-creation/00-prerequisites.md](docs/tutorials/aws/resource-creation/00-prerequisites.md)

---

## 1. Clone the repo

```bash
git clone https://github.com/<owner>/<repo>.git
cd <repo>
cp .env.example .env
```

Fill in `.env` with your real `OPENAI_API_KEY`, `TAVILY_API_KEY`, and
`E2B_API_KEY` — required, the app won't start without them.

---

## 2. Run it locally first (recommended)

Confirms your API keys work and the app itself is healthy, before
involving AWS at all:

```bash
docker compose up -d --build
curl http://localhost:8000/health   # every service should report "ok": true
open http://localhost:3000          # or just visit it in a browser
```

Shut it down when done: `docker compose down`.

---

## 3. Create your AWS resources

```bash
export AWS_REGION=ap-south-1   # pick your region
./scripts/aws-create-resources.sh
```

Creates, in order: IAM identities (`gha-deploy`, `ec2-app-role`), two ECR
repos, a security group (ports 80/443/3000 only, no SSH), an EC2
`t3.micro` instance, an Elastic IP, and an S3 bucket. Safe to re-run — it
skips anything that already exists. Takes a few minutes; ends by printing
a summary block like:

```
AWS_REGION=ap-south-1
ECR_REGISTRY=123456789012.dkr.ecr.ap-south-1.amazonaws.com
EC2_INSTANCE_ID=i-0abc123...
ELASTIC_IP=13.xx.xx.xx
PUBLIC_API_URL=http://13.xx.xx.xx
S3_BUCKET=multi-agentic-rag-docs-123456789012
```

**Save this block** — the next two steps need it.

What each resource is and why: [docs/tutorials/aws/resource-creation/](docs/tutorials/aws/resource-creation/README.md)

---

## 4. Set your application secrets

The script above can't do this part — it doesn't have your API keys.
Using the region from step 3's output:

```bash
aws ssm put-parameter --region $AWS_REGION --name /multi-agentic/OPENAI_API_KEY --type SecureString --value "sk-..."
aws ssm put-parameter --region $AWS_REGION --name /multi-agentic/TAVILY_API_KEY --type SecureString --value "tvly-..."
aws ssm put-parameter --region $AWS_REGION --name /multi-agentic/E2B_API_KEY --type SecureString --value "e2b_..."
aws ssm put-parameter --region $AWS_REGION --name /multi-agentic/CORS_ORIGINS --type String --value "http://<ELASTIC_IP>:3000"
```

Use the real `ELASTIC_IP` from step 3's output. Full list (including
optional ones): [06-ssm-parameters.md](docs/tutorials/aws/resource-creation/06-ssm-parameters.md)

---

## 5. Get the `gha-deploy` access key

Created in step 3, but the secret value is only ever shown once, at
creation. If you still have it from the script's output, skip this. If
not, rotate it:

```bash
aws iam create-access-key --user-name gha-deploy   # copy both values shown
```

---

## 6. Wire CI/CD to AWS

```bash
export AWS_REGION=ap-south-1                 # same as step 3
export EC2_INSTANCE_ID=i-0abc123...            # from step 3's output
export ECR_REGISTRY=...                        # from step 3's output
export PUBLIC_API_URL=http://<ELASTIC_IP>       # from step 3's output
export AWS_ACCESS_KEY_ID=...                    # from step 5
export AWS_SECRET_ACCESS_KEY=...                # from step 5
export GITHUB_REPO=<owner>/<repo>               # your repo, e.g. krishnaradha/pydantic_ai
./scripts/aws-integrate.sh
```

Pushes `docker-compose.deploy.yml` and `nginx/nginx.conf` onto the
instance, and sets all 6 GitHub Actions secrets the pipeline needs.

---

## 7. Ship it

```bash
git push origin main
```

This triggers `.github/workflows/deploy.yml`: builds the `api` and
`webapp` images, pushes them to ECR, then tells the EC2 instance (via SSM
— no SSH) to pull and restart. Watch it run:

```bash
gh run watch $(gh run list --limit 1 --json databaseId -q '.[0].databaseId')
```

---

## 8. Validate

```bash
curl http://<ELASTIC_IP>/health          # every service should be "ok": true
open http://<ELASTIC_IP>:3000            # send a real message, confirm it responds
```

If anything's broken, check the troubleshooting table — it documents every
real failure hit building this exact pipeline (IAM permission gaps, a
`docker-compose` binary mismatch, missing secrets, a `crypto.randomUUID`
bug, and more) with root cause and fix for each:
[docs/tutorials/aws/integration/end-to-end-setup.md](docs/tutorials/aws/integration/end-to-end-setup.md#troubleshooting-real-failures-encountered-building-this)

---

## Day to day

| Task | Command |
|---|---|
| Redeploy | `git push origin main` — CI/CD handles the rest |
| Pause billing | `aws ec2 stop-instances --instance-ids <id>` |
| Resume | `./scripts/aws-up.sh` (starts the instance, confirms containers are up) |
| Rotate a secret | `aws ssm put-parameter ... --overwrite`, then redeploy |

---

## Where to go deeper

| Topic | Doc |
|---|---|
| Why this architecture (EC2 vs. Fargate, ECR, no API Gateway) | [docs/aws-architecture.md](docs/aws-architecture.md) |
| Every AWS resource explained, flag by flag | [docs/tutorials/aws/resource-creation/](docs/tutorials/aws/resource-creation/README.md) |
| How the CI/CD pipeline actually works | [docs/tutorials/ci-cd/ci-cd-pipeline-explained.md](docs/tutorials/ci-cd/ci-cd-pipeline-explained.md) |
| Docker / Docker Compose fundamentals | [docs/tutorials/docker/docker-fundamentals.md](docs/tutorials/docker/docker-fundamentals.md) |
| Git fundamentals | [docs/tutorials/git/git-fundamentals.md](docs/tutorials/git/git-fundamentals.md) |
| App architecture (agents, API, frontend) | [README.md](README.md) |

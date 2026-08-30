# 0. Prerequisites

Part of the [AWS resource creation](README.md) series. Read this **before**
[1. IAM](01-iam.md) — everything else in this series assumes these are
already in place.

## Accounts you need

| Account | For | Sign up |
|---|---|---|
| AWS | Hosting everything in this series | [aws.amazon.com](https://aws.amazon.com) — a free-tier account works for this entire setup |
| GitHub | Hosting the code + running CI/CD | [github.com](https://github.com) |
| OpenAI | The LLM the app runs on | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) — requires billing set up, calls are pay-per-use |
| Tavily | Web search tool the agent uses | [tavily.com](https://tavily.com) — has a free tier |
| E2B | Sandboxed code execution for the code agent | [e2b.dev](https://e2b.dev) — has a free tier |

The last three give you the actual API key **values** — you'll store them
in AWS in [6. SSM Parameters](06-ssm-parameters.md), not in this project's
code or git history.

## Local tools you need installed

```bash
aws --version      # AWS CLI — https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html
git --version       # almost always preinstalled; if not, https://git-scm.com
docker --version    # https://docs.docker.com/get-docker/
gh --version         # GitHub CLI — brew install gh (Mac), or https://cli.github.com
```

On a Mac with [Homebrew](https://brew.sh) installed, all of these except
the AWS CLI (which has its own installer) come from `brew install <name>`.

## Authenticating each CLI

**AWS CLI** — needs credentials for *some* identity before it can do
anything, including creating the `gha-deploy`/`ec2-app-role` identities from
[1. IAM](01-iam.md). This is a bootstrapping step: you need an identity with
enough permissions to *create other identities* — typically your AWS
account's root user (only for this one-time setup) or an existing IAM user
with administrator access.

```bash
aws configure
```
Prompts for an Access Key ID, Secret Access Key, default region, and output
format. If you don't have an access key yet: AWS Console → IAM → Users →
your user → Security credentials → Create access key.

Verify it worked:
```bash
aws sts get-caller-identity
```
Should print your account ID and user ARN, not an error.

**GitHub CLI** — needs a one-time interactive login (opens a browser, or
accepts a device code):
```bash
gh auth login
```
Verify:
```bash
gh auth status
```

**Docker** — needs its background service (Docker Desktop, or the `docker`
daemon on Linux) actually running, not just installed:
```bash
docker ps
```
If this hangs or errors with "cannot connect to the Docker daemon," Docker
isn't running yet.

## A GitHub repository to deploy from

This series assumes your application code already lives in a GitHub
repository — either one you `git init`'d and pushed, or one you cloned.
If starting fresh:
```bash
git init
gh repo create <your-repo-name> --private --source=. --push
```
`--private` is a reasonable default for something with API keys and
infrastructure details in its history — see
[git-fundamentals.md](../../git/git-fundamentals.md) if any of this is
unfamiliar.

## What you do *not* need yet

- A domain name — this setup is reachable via a raw IP address (see
  [5. Elastic IP](05-elastic-ip.md)); a custom domain is an optional
  addition, not a requirement.
- Any AWS resources — that's what the rest of this series creates, from
  nothing, starting at [1. IAM](01-iam.md).

## What's next

[1. IAM — Identities and Permissions](01-iam.md)

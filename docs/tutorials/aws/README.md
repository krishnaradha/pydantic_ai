# AWS Tutorials

How this project's AWS deployment works, from an empty account to a running
app — broken into two phases, each broken into small, focused steps.

## Phase 1 — [Resource Creation](resource-creation/)

Starts with [prerequisites](resource-creation/00-prerequisites.md) — the
accounts, local tools, and API keys you need before any AWS command will
work — then provisions every AWS resource the deployment needs: IAM
identities, ECR repositories, a security group, the EC2 instance itself, a
fixed Elastic IP, SSM parameters for secrets (the full list of required vs.
optional application secrets is enumerated there), and an S3 bucket.
Nothing runs yet at the end of this phase — it's the empty scaffolding
everything else attaches to.

→ Start at [resource-creation/README.md](resource-creation/README.md)

## Phase 2 — [Integration](integration/end-to-end-setup.md)

Connects the resources from Phase 1 together: wiring GitHub Actions to AWS,
getting the deploy files onto the instance, running the first deploy, and
validating the whole thing actually works end to end — including a table of
every real failure hit while building this pipeline, and how each was
diagnosed and fixed.

→ Start at [integration/end-to-end-setup.md](integration/end-to-end-setup.md)

## Related reading

- [aws-architecture.md](../../aws-architecture.md) — the overall design and
  why it looks the way it does (free-tier constraints, what's on EC2 vs.
  managed services)
- [aws-setup-guide.md](../../aws-setup-guide.md) — the original condensed
  setup guide (this tutorial series is the expanded, explained version)
- [ci-cd/ci-cd-pipeline-explained.md](../ci-cd/ci-cd-pipeline-explained.md)
  — how the GitHub Actions pipeline that deploys to this infrastructure works

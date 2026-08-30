# Tutorials

Fundamentals and walkthroughs for this project's tooling — start wherever
matches what you already know.

| Tutorial | Covers |
|---|---|
| [git/git-fundamentals.md](git/git-fundamentals.md) | Version control basics: commits, branches, remotes, merge conflicts |
| [docker/docker-fundamentals.md](docker/docker-fundamentals.md) | Containers, images, Dockerfiles, Docker Compose |
| [ci-cd/ci-cd-pipeline-explained.md](ci-cd/ci-cd-pipeline-explained.md) | What CI/CD is, and a step-by-step walkthrough of this repo's GitHub Actions pipeline |
| [aws/](aws/README.md) | This project's AWS deployment, from an empty account to a running app — split into Resource Creation and Integration phases |

## Suggested order

If you're new to all of this: **Git → Docker → CI/CD → AWS**. Each builds
on ideas from the one before it — the CI/CD doc assumes you know what a
container image is, and the AWS docs assume you understand what the CI/CD
pipeline is doing.

If you already know Git/Docker, skip straight to CI/CD and AWS.

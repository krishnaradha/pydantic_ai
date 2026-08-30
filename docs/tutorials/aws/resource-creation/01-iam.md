# 1. IAM — Identities and Permissions

Part of the [AWS resource creation](.) series. This is step 1 — everything
else in this series assumes these identities already exist.

## What is IAM?

**IAM (Identity and Access Management)** is AWS's system for controlling
*who* (or *what*) can do *what* to your AWS resources. Two concepts matter
here:

- **IAM user** — an identity for something *outside* AWS that needs to call
  AWS APIs (a person, or in our case, a CI/CD pipeline). Authenticates with
  an access key ID + secret access key.
- **IAM role** — an identity for something *inside* AWS that needs to call
  other AWS APIs (an EC2 instance, a Lambda function). Instead of a
  long-lived key, AWS automatically hands out short-lived, auto-rotating
  credentials to whatever the role is attached to.

**Policies** are documents that say what a user/role is allowed to do — e.g.
"can push images to ECR" or "can read this specific SSM parameter path."
Nothing is allowed by default; every permission has to be explicitly granted.

## Why two separate identities?

This project creates **two** identities, deliberately never reusing one for
both purposes:

| Identity | Type | Used by | Purpose |
|---|---|---|---|
| `gha-deploy` | IAM user | GitHub Actions | Push images to ECR, trigger deploys via SSM |
| `ec2-app-role` | IAM role | The EC2 instance itself | Pull images from ECR, read secrets from SSM |

**Why not one identity for everything?** Principle of least privilege — if
the EC2 instance were ever compromised, an attacker with its credentials
should *not* be able to do things only CI/CD needs to do (like triggering
new deploys). Keeping them separate limits the blast radius of any single
credential leaking.

**Why a role (not a user) for the EC2 instance?** A role attached via an
"instance profile" means AWS automatically injects temporary, auto-rotating
credentials into the instance — nothing to store on disk, nothing that can
be stolen from a config file, nothing to manually rotate.

## Creating `gha-deploy` (the CI/CD user)

```bash
aws iam create-user --user-name gha-deploy
```
Creates the identity itself — at this point it can authenticate, but can't
do anything yet (no permissions attached).

```bash
aws iam attach-user-policy \
  --user-name gha-deploy \
  --policy-arn arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryPowerUser
```
Attaches an AWS-managed policy that grants push/pull access to ECR
repositories. "Managed policy" means AWS wrote and maintains it — no need
to hand-write the exact list of ECR API actions required.

```bash
cat > gha-deploy-ssm-policy.json <<'EOF'
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
  --policy-document file://gha-deploy-ssm-policy.json
```
This one we write ourselves (a **custom inline policy**), because there's no
AWS-managed policy scoped to exactly "trigger Run Command and check its
result" — the closest managed policies grant much broader SSM access than
needed. `ssm:SendCommand` is what lets the deploy step tell the EC2 instance
to run the deploy script; `ssm:GetCommandInvocation` is what lets it check
whether that command actually succeeded.

```bash
aws iam create-access-key --user-name gha-deploy
```
Generates the actual credentials — an `AccessKeyId` and `SecretAccessKey`.
**The secret is shown exactly once**, in this command's output, and can
never be retrieved again afterward (not even by AWS support). It needs to
be copied immediately into GitHub Actions secrets (covered in the
integration phase). If it's lost, the only fix is generating a new key pair
and deleting the old one — there's no "show me the secret again."

## Creating `ec2-app-role` (the instance role)

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
Creates the role. The `assume-role-policy-document` (sometimes called the
"trust policy") is different from a permissions policy — it doesn't say
what the role *can do*, it says *who's allowed to become this role*. Here,
only the EC2 service itself is trusted to assume it — nothing else can.

```bash
aws iam attach-role-policy --role-name ec2-app-role \
  --policy-arn arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly
aws iam attach-role-policy --role-name ec2-app-role \
  --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
aws iam attach-role-policy --role-name ec2-app-role \
  --policy-arn arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess
```
Three managed policies:
- **`AmazonEC2ContainerRegistryReadOnly`** — lets the instance *pull* images
  from ECR. Deliberately read-only — the instance never needs to push.
- **`AmazonSSMManagedInstanceCore`** — this is what makes the instance
  reachable via SSM Run Command / Session Manager in the first place (the
  agent needs permission to register itself and receive commands). Without
  this, there'd be no remote-management mechanism at all except SSH.
- **`AmazonS3ReadOnlyAccess`** — lets the instance read from S3 (used later
  for pulling RAG documents).

⚠️ Note: none of these three grant `ssm:GetParametersByPath` for reading
**Parameter Store** values (a different SSM capability from Run Command).
That has to be added separately as a custom policy — an easy thing to miss,
covered in the [SSM Parameters](06-ssm-parameters.md) step.

```bash
aws iam create-instance-profile --instance-profile-name ec2-app-profile
aws iam add-role-to-instance-profile \
  --instance-profile-name ec2-app-profile --role-name ec2-app-role
```
A role by itself can't be directly attached to an EC2 instance — it has to
be wrapped in an **instance profile** first (a thin AWS wrapper that exists
purely for this purpose). This is a historical AWS API quirk, not a
meaningful extra concept — just something you attach the role *through*.

## Verifying it worked

```bash
# Confirm the user exists
aws iam get-user --user-name gha-deploy

# Confirm its policies are attached
aws iam list-attached-user-policies --user-name gha-deploy
aws iam get-user-policy --user-name gha-deploy --policy-name gha-deploy-ssm

# Confirm the role exists with the right policies
aws iam get-role --role-name ec2-app-role
aws iam list-attached-role-policies --role-name ec2-app-role

# Confirm the instance profile wraps the role
aws iam get-instance-profile --instance-profile-name ec2-app-profile
```

If all of these return data (not an error), IAM setup is complete.

## What's next

[2. ECR — Container Image Registry](02-ecr.md)

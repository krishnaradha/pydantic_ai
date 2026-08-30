# 6. SSM Parameter Store — Application Secrets

Part of the [AWS resource creation](README.md) series. Independent of the
other steps so far — can be done any time after [1. IAM](01-iam.md).

## What is SSM Parameter Store?

**Parameter Store** is a feature of AWS Systems Manager (the same "SSM"
used for Run Command in the [CI/CD doc](../../ci-cd/ci-cd-pipeline-explained.md))
that stores configuration values and secrets — API keys, connection
strings, feature flags — in a hierarchical, named structure (like a
filesystem: `/multi-agentic/OPENAI_API_KEY`, `/multi-agentic/CORS_ORIGINS`,
etc.), with encryption available for sensitive values.

## Why not just put secrets in the code or a `.env` file in git?

Because anyone with read access to the repository would then have every API
key. Git history is also effectively permanent — even deleting a secret in
a later commit leaves it recoverable from history unless you rewrite it
(painful, and easy to get wrong). Parameter Store keeps secrets **out of
git entirely**: the deploy process fetches them fresh, at deploy time,
directly from AWS — never committed, never visible in a diff, never sitting
in GitHub Actions logs.

## The full list this application needs

This isn't guesswork — it's the exact set defined in
[.env.example](../../../../.env.example) and enforced in
[multi_agentic_system/config.py](../../../../multi_agentic_system/config.py).
Three are hard-required (the app's `Settings` class fails to even start
without them); the rest are optional, with sane defaults baked into the code.

| Parameter | Required? | Type | Get it from |
|---|---|---|---|
| `OPENAI_API_KEY` | **Required** | `SecureString` | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
| `TAVILY_API_KEY` | **Required** | `SecureString` | [tavily.com](https://tavily.com) |
| `E2B_API_KEY` | **Required** | `SecureString` | [e2b.dev](https://e2b.dev) |
| `CORS_ORIGINS` | Optional (defaults to `http://localhost:3000` — wrong for a deployed instance, so set it explicitly) | `String` | Your Elastic IP, e.g. `http://<elastic-ip>:3000` |
| `LOGFIRE_TOKEN` | Optional (observability integration, unused if unset) | `SecureString` | [logfire.pydantic.dev](https://logfire.pydantic.dev) |
| `LLM_MODEL` | Optional (defaults to `openai:gpt-4o`) | `String` | — |

`REDIS_URL`, `CHROMA_HOST`, `CHROMA_PORT` are **not** SSM parameters at all
— in the deployed setup they're hardcoded in `docker-compose.deploy.yml`'s
`environment:` block (pointing at the `redis`/`chromadb` containers by
Docker's internal service-name DNS), not secrets that vary per environment.

## `String` vs. `SecureString`

```bash
aws ssm put-parameter --name /multi-agentic/OPENAI_API_KEY --type SecureString --value "sk-..."
aws ssm put-parameter --name /multi-agentic/TAVILY_API_KEY --type SecureString --value "tvly-..."
aws ssm put-parameter --name /multi-agentic/E2B_API_KEY --type SecureString --value "e2b_..."
aws ssm put-parameter --name /multi-agentic/CORS_ORIGINS --type String --value "http://<your-elastic-ip>:3000"
```

- **`String`** — stored as plain text. Fine for non-sensitive config like
  `CORS_ORIGINS` (an allowed-origins URL — not a secret, just configuration).
- **`SecureString`** — encrypted at rest using AWS KMS (Key Management
  Service), and requires explicit `--with-decryption` to read back in
  plaintext. Used for anything that's an actual credential.

Add any optional ones you want the same way — `LOGFIRE_TOKEN` as
`SecureString`, `LLM_MODEL` as `String`. Everything under `/multi-agentic/`
gets picked up automatically by the deploy script's
`get-parameters-by-path` call (see
[ci-cd-pipeline-explained.md](../../ci-cd/ci-cd-pipeline-explained.md)) —
there's no separate registration step; creating the parameter *is* the only
step.

## Reading secrets back

This is what the deploy script (see the
[CI/CD doc](../../ci-cd/ci-cd-pipeline-explained.md)) does on every deploy:

```bash
aws ssm get-parameters-by-path --path /multi-agentic --with-decryption --output json
```

`get-parameters-by-path` fetches every parameter under that prefix in one
call — this is why they're all namespaced under `/multi-agentic/...`, so
one query retrieves the whole set. `--with-decryption` is required to get
`SecureString` values back as plaintext (without it, they'd come back still
encrypted).

## The permission this needs — and the trap to avoid

Reading Parameter Store requires **explicit IAM permission** —
`ssm:GetParameter`, `ssm:GetParameters`, and/or `ssm:GetParametersByPath` —
which is a **different permission** from `AmazonSSMManagedInstanceCore`
(the policy that enables Run Command, attached back in
[1. IAM](01-iam.md)). It's an easy trap: the instance can *receive commands*
via SSM without being able to *read Parameter Store* via SSM — they're
separate capabilities under the same "SSM" umbrella.

The fix — a custom inline policy on `ec2-app-role`:

```bash
cat > ssm-param-read-policy.json <<'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["ssm:GetParameter", "ssm:GetParameters", "ssm:GetParametersByPath"],
      "Resource": [
        "arn:aws:ssm:<REGION>:<ACCOUNT_ID>:parameter/multi-agentic",
        "arn:aws:ssm:<REGION>:<ACCOUNT_ID>:parameter/multi-agentic/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": ["kms:Decrypt"],
      "Resource": "arn:aws:kms:<REGION>:<ACCOUNT_ID>:alias/aws/ssm"
    }
  ]
}
EOF
aws iam put-role-policy \
  --role-name ec2-app-role \
  --policy-name ec2-app-ssm-params \
  --policy-document file://ssm-param-read-policy.json
```

Two things worth noting:
- **Both** the exact path (`.../parameter/multi-agentic`) and the wildcard
  (`.../parameter/multi-agentic/*`) are included as resources —
  `GetParametersByPath`'s permission check can be picky about matching the
  exact path argument used in the API call, so it's safer to grant both
  forms.
- **`kms:Decrypt`** on the `alias/aws/ssm` key is required *in addition* to
  the SSM actions — `SecureString` values are encrypted with a KMS key
  (AWS's default one, unless you configured a custom one), and IAM
  authorizes read access to the parameter separately from decrypt access to
  the underlying key.

⚠️ IAM policy changes can take up to a minute or two to fully propagate —
if a permission check fails immediately after creating a policy, it's worth
waiting briefly and retrying before assuming something's actually wrong.

## Verifying it worked

```bash
aws ssm get-parameters-by-path --path /multi-agentic --query 'Parameters[].Name' --output text
```
Should list every parameter name you created — a quick sanity check that
they exist, without needing `--with-decryption`.

To confirm a *value* isn't an unfilled placeholder (an easy mistake when
copy-pasting example commands), check its length rather than printing it:
```bash
aws ssm get-parameter --name /multi-agentic/OPENAI_API_KEY --with-decryption \
  --query 'Parameter.Value' --output text | wc -c
```
A real OpenAI key is over 100 characters; a placeholder like `sk-...` is 7.

## What's next

[7. S3 Bucket — Document Storage](07-s3-bucket.md)

# Deploying to AWS (ECS Express Mode)

AWS App Runner stopped accepting new customers on 2026-04-30. AWS's recommended
replacement is **Amazon ECS Express Mode** — same "point at an image, get an
HTTPS URL" simplicity, backed by Fargate + an auto-provisioned Application
Load Balancer (TLS included).

## What gets deployed

One container running everything:

- The Vite production build (`dist/`) served as static files
- The VoiceBot proxy routes `/api/nlu` (Claude) and `/api/stt` (OpenAI
  Whisper), reusing the existing `server/nlu.ts` / `server/stt.ts` handlers
  unchanged — the frontend still calls the same relative paths, so no
  frontend code changes

This is `Dockerfile` + `server/prodServer.ts` (already added and verified
locally: `docker build` succeeds, `/health` returns `ok`, `/` and deep routes
serve the SPA with a 200, and `/api/nlu` reaches the real Anthropic client).

## Prerequisites

- Docker running locally
- AWS CLI v2, **authenticated** — run `aws sts get-caller-identity` to check.
  Your session was expired when this was written; re-authenticate (`aws sso
  login` or however your org logs in) before running anything below.
- A default VPC with public subnets in the target region (Express Mode
  provisions an internet-facing ALB there by default). Most accounts already
  have one; if not, create one or pass `--network-configuration` with your
  own subnets.
- Your Anthropic and OpenAI API keys

Fill in your own values for `<account-id>`, `<region>` (e.g. `ap-northeast-1`),
and `<repo-name>` (e.g. `ym-fleet-ops-frontend`) everywhere below.

## 1. Store the API keys in Secrets Manager

Don't pass API keys as plain container environment variables — Security Hub
flags this (`ECS.8`), and Express Mode's `secrets` field makes it just as easy
to do it properly.

```bash
aws secretsmanager create-secret --name ym-fleet-ops/anthropic-api-key \
    --secret-string "<your-anthropic-key>"
aws secretsmanager create-secret --name ym-fleet-ops/openai-api-key \
    --secret-string "<your-openai-key>"
```

Note the two secret ARNs returned — you'll need them in step 5.

## 2. Create the IAM roles (one-time per account)

```bash
aws iam create-role --role-name ecsTaskExecutionRole \
    --assume-role-policy-document '{
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": { "Service": "ecs-tasks.amazonaws.com" },
            "Action": "sts:AssumeRole"
        }]
    }'

aws iam create-role --role-name ecsInfrastructureRoleForExpressServices \
    --assume-role-policy-document '{
        "Version": "2012-10-17",
        "Statement": [{
            "Sid": "AllowAccessInfrastructureForECSExpressServices",
            "Effect": "Allow",
            "Principal": { "Service": "ecs.amazonaws.com" },
            "Action": "sts:AssumeRole"
        }]
    }'

aws iam attach-role-policy --role-name ecsTaskExecutionRole \
    --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy
aws iam attach-role-policy --role-name ecsInfrastructureRoleForExpressServices \
    --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSInfrastructureRoleforExpressGatewayServices
```

`AmazonECSTaskExecutionRolePolicy` does **not** include Secrets Manager read
access, so add that so the task can pull the two secrets from step 1:

```bash
aws iam put-role-policy --role-name ecsTaskExecutionRole \
    --policy-name ReadVoicebotSecrets \
    --policy-document '{
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Action": "secretsmanager:GetSecretValue",
            "Resource": [
                "arn:aws:secretsmanager:<region>:<account-id>:secret:ym-fleet-ops/anthropic-api-key-*",
                "arn:aws:secretsmanager:<region>:<account-id>:secret:ym-fleet-ops/openai-api-key-*"
            ]
        }]
    }'
```

IAM roles take a little time to propagate. If step 5 fails with an
`assume-role`/`Unable to assume the service linked role` error, wait ~1 minute
and retry.

## 3. Push the image to ECR

**If you're building on Apple Silicon (arm64 Mac): pass `--platform linux/amd64`.**
Express Mode services default to `X86_64` Fargate tasks. A plain `docker build`
on an M-series Mac produces an arm64 image, which ECS silently accepts on push
but then fails every task at container start with `exec format error` (visible
in CloudWatch Logs, log group `/aws/ecs/default/<service-name>-<suffix>`) — the
task just flaps between `Provisioning`/`Deprovisioning` with no build-time
warning. Confirm what you actually pushed with:
`docker image inspect <account-id>.dkr.ecr.<region>.amazonaws.com/<repo-name>:latest --format '{{.Architecture}}'`
— it must say `amd64`.

```bash
aws ecr create-repository --repository-name <repo-name>

aws ecr get-login-password --region <region> \
    | docker login --username AWS --password-stdin <account-id>.dkr.ecr.<region>.amazonaws.com

docker build --platform linux/amd64 -t <repo-name>:latest .
docker tag <repo-name>:latest <account-id>.dkr.ecr.<region>.amazonaws.com/<repo-name>:latest
docker push <account-id>.dkr.ecr.<region>.amazonaws.com/<repo-name>:latest
```

## 4. Create the Express Mode service

```bash
aws ecs create-express-gateway-service \
    --service-name ym-fleet-ops-frontend \
    --execution-role-arn arn:aws:iam::<account-id>:role/ecsTaskExecutionRole \
    --infrastructure-role-arn arn:aws:iam::<account-id>:role/ecsInfrastructureRoleForExpressServices \
    --health-check-path "/health" \
    --primary-container '{
        "image": "<account-id>.dkr.ecr.<region>.amazonaws.com/<repo-name>:latest",
        "containerPort": 8080,
        "environment": [
            { "name": "ANTHROPIC_MODEL", "value": "claude-sonnet-5" },
            { "name": "OPENAI_STT_MODEL", "value": "gpt-4o-transcribe" }
        ],
        "secrets": [
            { "name": "ANTHROPIC_API_KEY", "valueFrom": "arn:aws:secretsmanager:<region>:<account-id>:secret:ym-fleet-ops/anthropic-api-key" },
            { "name": "OPENAI_API_KEY", "valueFrom": "arn:aws:secretsmanager:<region>:<account-id>:secret:ym-fleet-ops/openai-api-key" }
        ]
    }' \
    --monitor-resources
```

`--monitor-resources` streams provisioning status and blocks until the
service is `ACTIVE`. Note the `serviceArn` in the response — you need it for
updates/deletes/lookups.

## 5. Access it

```
https://<service-name>.ecs.<region>.on.aws/
```

Check status any time with:

```bash
aws ecs describe-express-gateway-service --service-arn <service-arn>
```

## 6. Redeploying after a code change

Same `--platform linux/amd64` caveat as step 3 applies here — don't drop it
just because it's a "quick redeploy."

```bash
docker build --platform linux/amd64 -t <repo-name>:latest .
docker tag <repo-name>:latest <account-id>.dkr.ecr.<region>.amazonaws.com/<repo-name>:latest
docker push <account-id>.dkr.ecr.<region>.amazonaws.com/<repo-name>:latest

aws ecs update-express-gateway-service \
    --service-arn <service-arn> \
    --primary-container '{"image":"<account-id>.dkr.ecr.<region>.amazonaws.com/<repo-name>:latest"}' \
    --monitor-resources
```

Express Mode does a rolling deployment — no downtime.

## 7. Tearing it down

This is not reversible — it deletes the ALB, target groups, security groups,
and scaling policies:

```bash
aws ecs delete-express-gateway-service --service-arn <service-arn> --monitor-resources
aws ecr delete-repository --repository-name <repo-name> --force
```

## Known tradeoffs

- Runs one always-on Fargate task + ALB — this does not scale to zero the way
  a pure static-site + Lambda split would, so there's a small constant cost.
- The image includes full `node_modules` (including build-time tools like
  `vite`/`vue-tsc`) rather than a slimmed multi-stage runtime layer — traded
  away for a one-file Dockerfile. Worth revisiting if image size/cold-start
  becomes a problem.

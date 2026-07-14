#!/usr/bin/env python3
"""
gen_frontend_taskdef.py  <ecr-image>  <region>  <account-id>  <output-json>

Generates the ECS Fargate task definition JSON for the frontend and writes it.
Called by Makefile prod-frontend target.
"""
import json
import sys

if len(sys.argv) < 5:
    print(f"Usage: {sys.argv[0]} <ecr-image> <region> <account-id> <output-json>", file=sys.stderr)
    sys.exit(1)

image      = sys.argv[1]
region     = sys.argv[2]
account_id = sys.argv[3]
output     = sys.argv[4]

td = {
    "family": "ym-fleet-ops-frontend",
    "executionRoleArn": f"arn:aws:iam::{account_id}:role/ecsTaskExecRole-ship",
    "networkMode": "awsvpc",
    "requiresCompatibilities": ["FARGATE"],
    "cpu": "512",
    "memory": "1024",
    "containerDefinitions": [
        {
            "name": "frontend",
            "image": image,
            "portMappings": [
                {"containerPort": 8080, "protocol": "tcp"}
            ],
            "essential": True,
            "environment": [
                {"name": "PORT", "value": "8080"},
                {"name": "ANTHROPIC_MODEL",   "value": "claude-sonnet-5"},
                {"name": "OPENAI_STT_MODEL",  "value": "gpt-4o-transcribe"},
            ],
            "logConfiguration": {
                "logDriver": "awslogs",
                "options": {
                    "awslogs-group":         "/ecs/ym-fleet-ops-frontend",
                    "awslogs-create-group":  "true",
                    "awslogs-region":        region,
                    "awslogs-stream-prefix": "ecs",
                },
            },
        }
    ],
}

with open(output, "w") as f:
    json.dump(td, f, indent=2)

print(f"Wrote {output}")

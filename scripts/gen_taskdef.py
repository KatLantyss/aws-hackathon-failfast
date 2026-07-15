#!/usr/bin/env python3
"""
gen_taskdef.py  <ecr-image>  <region>  <account-id>  <output-json>

Generates the ECS task definition JSON for ship-api and writes it to output-json.
Called by Makefile prod-backend target.
"""
import json
import sys

if len(sys.argv) < 5:
    print(f"Usage: {sys.argv[0]} <ecr-image> <region> <account-id> <output-json>", file=sys.stderr)
    sys.exit(1)

image      = sys.argv[1]  # e.g. 151274905459.dkr.ecr.us-east-1.amazonaws.com/ship-analysis-api:latest
region     = sys.argv[2]  # e.g. us-east-1
account_id = sys.argv[3]  # e.g. 151274905459
output     = sys.argv[4]  # e.g. /tmp/ship-api-taskdef.json

td = {
    "family": "ship-api",
    "taskRoleArn": f"arn:aws:iam::{account_id}:role/ecsTaskRole-ship",
    "executionRoleArn": f"arn:aws:iam::{account_id}:role/ecsTaskExecRole-ship",
    "networkMode": "host",
    "containerDefinitions": [
        {
            "name": "ship-api",
            "image": image,
            "cpu": 2048,
            "memoryReservation": 3584,
            "portMappings": [
                {"containerPort": 8000, "hostPort": 8000, "protocol": "tcp"}
            ],
            "essential": True,
            "environment": [
                {"name": "AWS_REGION",         "value": region},
                {"name": "VESSEL_TABLE",        "value": "ship-analysis-dev-vessel-data"},
                {"name": "MAINT_TABLE",         "value": "ship-analysis-dev-maintenance-events"},
                {"name": "FLEET_SUMMARY_TABLE", "value": "ship-analysis-dev-fleet-summary"},
            ],
            "logConfiguration": {
                "logDriver": "awslogs",
                "options": {
                    "awslogs-group":         "/ecs/ship-api",
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

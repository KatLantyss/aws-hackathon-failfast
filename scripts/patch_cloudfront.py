#!/usr/bin/env python3
"""
patch_cloudfront.py  <cf-config.json>  <frontend-ecs-url>

Patches an existing CloudFront distribution config to add:
  - A second origin pointing at the ECS Express Mode frontend service
  - A default cache behavior that routes /* → frontend
  - A path-pattern cache behavior that routes /api/* and /health → backend EC2

Usage (from Makefile):
    python3 scripts/patch_cloudfront.py /tmp/cf-config.json \
        https://ym-fleet-ops-frontend-svc.ecs.us-east-1.on.aws \
        > /tmp/cf-config-patched.json
"""

import json
import re
import sys
from urllib.parse import urlparse


def main():
    if len(sys.argv) < 3:
        print("Usage: patch_cloudfront.py <config.json> <frontend-ecs-https-url>", file=sys.stderr)
        sys.exit(1)

    config_path   = sys.argv[1]
    frontend_url  = sys.argv[2].rstrip('/')

    with open(config_path) as f:
        cfg = json.load(f)

    parsed       = urlparse(frontend_url)
    frontend_host = parsed.netloc  # e.g. ym-fleet-ops-frontend-svc.ecs.us-east-1.on.aws
    frontend_id  = "ym-fleet-ops-frontend"
    backend_id   = "ship-api-ec2"    # existing origin id

    # ── 1. Add frontend origin if not already present ────────────────────────
    origins = cfg['Origins']['Items']
    if not any(o['Id'] == frontend_id for o in origins):
        origins.append({
            "Id": frontend_id,
            "DomainName": frontend_host,
            "OriginPath": "",
            "CustomHeaders": {"Quantity": 0},
            "CustomOriginConfig": {
                "HTTPPort": 80,
                "HTTPSPort": 443,
                "OriginProtocolPolicy": "https-only",
                "OriginSslProtocols": {
                    "Quantity": 3,
                    "Items": ["TLSv1", "TLSv1.1", "TLSv1.2"]
                },
                "OriginReadTimeout": 30,
                "OriginKeepaliveTimeout": 5
            },
            "ConnectionAttempts": 3,
            "ConnectionTimeout": 10,
            "OriginShield": {"Enabled": False}
        })
        cfg['Origins']['Quantity'] = len(origins)

    # ── 2. Default cache behavior → frontend ─────────────────────────────────
    dcb = cfg['DefaultCacheBehavior']
    dcb['TargetOriginId'] = frontend_id
    # Allow all HTTP methods so the frontend's /api/nlu POST works
    dcb['AllowedMethods'] = {
        "Quantity": 7,
        "Items": ["HEAD", "DELETE", "POST", "GET", "OPTIONS", "PUT", "PATCH"],
        "CachedMethods": {"Quantity": 2, "Items": ["HEAD", "GET"]}
    }
    # Forward all headers/query strings to frontend (needed for SPA routing)
    dcb['CachePolicyId']          = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"  # CachingDisabled
    dcb['OriginRequestPolicyId']  = "b689b0a8-53d0-40ab-baf2-68738e2966ac"  # AllViewerExceptHostHeader

    # ── 3. Path-pattern behavior: /api/* and /health → backend EC2 ───────────
    api_behavior = {
        "PathPattern": "/api/*",
        "TargetOriginId": backend_id,
        "ViewerProtocolPolicy": "redirect-to-https",
        "AllowedMethods": {
            "Quantity": 7,
            "Items": ["HEAD", "DELETE", "POST", "GET", "OPTIONS", "PUT", "PATCH"],
            "CachedMethods": {"Quantity": 2, "Items": ["HEAD", "GET"]}
        },
        "Compress": True,
        "CachePolicyId": "4135ea2d-6df8-44a3-9df3-4b5a84be39ad",           # CachingDisabled
        "OriginRequestPolicyId": "b689b0a8-53d0-40ab-baf2-68738e2966ac",    # AllViewerExceptHostHeader
        "TrustedSigners": {"Enabled": False, "Quantity": 0},
        "TrustedKeyGroups": {"Enabled": False, "Quantity": 0},
        "ForwardedValues": {
            "QueryString": True,
            "Cookies": {"Forward": "none"},
            "Headers": {"Quantity": 0},
            "QueryStringCacheKeys": {"Quantity": 0}
        },
        "MinTTL": 0,
        "DefaultTTL": 0,
        "MaxTTL": 0
    }
    health_behavior = dict(api_behavior)
    health_behavior['PathPattern'] = '/health'

    existing_items = cfg.get('CacheBehaviors', {}).get('Items', [])
    # Replace or append
    keep = [cb for cb in existing_items if cb['PathPattern'] not in ('/api/*', '/health')]
    keep = [api_behavior, health_behavior] + keep

    cfg['CacheBehaviors'] = {
        "Quantity": len(keep),
        "Items": keep
    }

    print(json.dumps(cfg, indent=2))


if __name__ == '__main__':
    main()

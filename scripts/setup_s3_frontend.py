#!/usr/bin/env python3
"""
setup_s3_frontend.py

Idempotent setup for S3 + CloudFront static frontend hosting.
Run once (or re-run safely on every deploy).

Steps:
  1. Create S3 bucket if it doesn't exist (block all public access)
  2. Create CloudFront Origin Access Control (OAC) if needed
  3. Update CloudFront distribution:
       - Add S3 origin with OAC
       - Default behavior /* → S3 (SPA with 403/404 → index.html)
       - Keep /api/* and /health → existing EC2 backend origin
  4. Update S3 bucket policy to allow CloudFront OAC reads
  5. Print the bucket name for use by sync step

Usage:
    python3 scripts/setup_s3_frontend.py \
        --profile hackathon \
        --region us-east-1 \
        --account-id 151274905459 \
        --distribution-id EYQC35Y9OSEQD \
        --backend-origin-id ship-api-ec2

Outputs (to stdout, last line):
    BUCKET=<bucket-name>
"""

import argparse
import json
import time
import sys
import boto3
from botocore.exceptions import ClientError


def get_or_create_bucket(s3, s3_ctrl, region, bucket_name):
    try:
        s3.head_bucket(Bucket=bucket_name)
        print(f"  S3 bucket '{bucket_name}' already exists", flush=True)
    except ClientError as e:
        if e.response['Error']['Code'] in ('404', 'NoSuchBucket'):
            print(f"  Creating S3 bucket '{bucket_name}'...", flush=True)
            if region == 'us-east-1':
                s3.create_bucket(Bucket=bucket_name)
            else:
                s3.create_bucket(
                    Bucket=bucket_name,
                    CreateBucketConfiguration={'LocationConstraint': region}
                )
        else:
            raise

    # Block all public access
    s3_ctrl.put_public_access_block(
        Bucket=bucket_name,
        PublicAccessBlockConfiguration={
            'BlockPublicAcls': True,
            'IgnorePublicAcls': True,
            'BlockPublicPolicy': True,
            'RestrictPublicBuckets': True,
        }
    )
    return bucket_name


def get_or_create_oac(cf, oac_name):
    """Return OAC id, creating it if needed."""
    # List existing OACs
    paginator = cf.get_paginator('list_origin_access_controls') if hasattr(cf, 'get_paginator') else None
    try:
        resp = cf.list_origin_access_controls(MaxItems='100')
        for item in resp.get('OriginAccessControlList', {}).get('Items', []):
            if item['Name'] == oac_name:
                print(f"  OAC '{oac_name}' already exists: {item['Id']}", flush=True)
                return item['Id']
    except Exception:
        pass

    print(f"  Creating OAC '{oac_name}'...", flush=True)
    resp = cf.create_origin_access_control(
        OriginAccessControlConfig={
            'Name': oac_name,
            'Description': 'OAC for ship-fleet-ops frontend S3 bucket',
            'SigningProtocol': 'sigv4',
            'SigningBehavior': 'always',
            'OriginAccessControlOriginType': 's3',
        }
    )
    oac_id = resp['OriginAccessControl']['Id']
    print(f"  Created OAC: {oac_id}", flush=True)
    return oac_id


def update_cloudfront(cf, distribution_id, bucket_name, oac_id, backend_origin_id, region, account_id):
    """Patch the CloudFront distribution config idempotently."""
    resp = cf.get_distribution_config(Id=distribution_id)
    etag = resp['ETag']
    cfg  = resp['DistributionConfig']

    bucket_domain  = f"{bucket_name}.s3.{region}.amazonaws.com"
    s3_origin_id   = "ym-fleet-ops-frontend-s3"

    # ── 1. Add / update S3 origin ────────────────────────────────────────────
    origins = cfg['Origins']['Items']
    existing_s3 = next((o for o in origins if o['Id'] == s3_origin_id), None)
    if existing_s3:
        existing_s3['DomainName'] = bucket_domain
        existing_s3['OriginAccessControlId'] = oac_id
        existing_s3['S3OriginConfig'] = {'OriginAccessIdentity': ''}
    else:
        origins.append({
            'Id': s3_origin_id,
            'DomainName': bucket_domain,
            'OriginPath': '',
            'CustomHeaders': {'Quantity': 0},
            'S3OriginConfig': {'OriginAccessIdentity': ''},
            'OriginAccessControlId': oac_id,
            'ConnectionAttempts': 3,
            'ConnectionTimeout': 10,
            'OriginShield': {'Enabled': False},
        })
    cfg['Origins']['Items']    = origins
    cfg['Origins']['Quantity'] = len(origins)

    # ── 2. Use existing default behavior as template, only swap origin/policy ─
    # This avoids missing-field errors — we keep all fields CF already expects.
    dcb = cfg['DefaultCacheBehavior']
    dcb['TargetOriginId']       = s3_origin_id
    dcb['ViewerProtocolPolicy'] = 'redirect-to-https'
    dcb['AllowedMethods'] = {
        'Quantity': 2,
        'Items': ['GET', 'HEAD'],
        'CachedMethods': {'Quantity': 2, 'Items': ['GET', 'HEAD']},
    }
    dcb['Compress']        = True
    dcb['SmoothStreaming']  = False
    # Managed-CachingOptimized for S3 static assets
    dcb['CachePolicyId']   = '658327ea-f89d-4fab-a63d-7e88639e58f6'
    # Remove fields that conflict with CachePolicyId
    for key in ('ForwardedValues', 'MinTTL', 'DefaultTTL', 'MaxTTL',
                'OriginRequestPolicyId'):
        dcb.pop(key, None)

    # ── 3. Path behaviors: /api/* and /health → backend EC2 ──────────────────
    # Clone the existing default behavior for the backend path behaviors,
    # then override only the fields we care about.
    import copy
    def make_backend_behavior(path_pattern, allowed_methods_count, allowed_methods):
        b = copy.deepcopy(dcb)
        b['PathPattern']           = path_pattern
        b['TargetOriginId']        = backend_origin_id
        b['ViewerProtocolPolicy']  = 'redirect-to-https'
        b['AllowedMethods'] = {
            'Quantity': allowed_methods_count,
            'Items': allowed_methods,
            'CachedMethods': {'Quantity': 2, 'Items': ['HEAD', 'GET']},
        }
        b['Compress']        = True
        b['SmoothStreaming']  = False
        # CachingDisabled policy for backend (no caching)
        b['CachePolicyId']   = '4135ea2d-6df8-44a3-9df3-4b5a84be39ad'
        b['OriginRequestPolicyId'] = 'b689b0a8-53d0-40ab-baf2-68738e2966ac'
        b.pop('ForwardedValues', None)
        b.pop('MinTTL', None)
        b.pop('DefaultTTL', None)
        b.pop('MaxTTL', None)
        return b

    api_behavior    = make_backend_behavior(
        '/api/*', 7, ['HEAD','DELETE','POST','GET','OPTIONS','PUT','PATCH'])
    health_behavior = make_backend_behavior(
        '/health', 2, ['GET', 'HEAD'])

    existing = cfg.get('CacheBehaviors', {}).get('Items', [])
    keep = [cb for cb in existing if cb['PathPattern'] not in ('/api/*', '/health')]
    new_behaviors = [api_behavior, health_behavior] + keep
    cfg['CacheBehaviors'] = {
        'Quantity': len(new_behaviors),
        'Items': new_behaviors,
    }

    # ── 4. SPA error pages: 403/404 from S3 → serve index.html ──────────────
    existing_errors = cfg.get('CustomErrorResponses', {}).get('Items', [])
    error_codes_done = {e['ErrorCode'] for e in existing_errors}
    for code in [403, 404]:
        if code not in error_codes_done:
            existing_errors.append({
                'ErrorCode': code,
                'ResponsePagePath': '/index.html',
                'ResponseCode': '200',
                'ErrorCachingMinTTL': 0,
            })
    cfg['CustomErrorResponses'] = {
        'Quantity': len(existing_errors),
        'Items': existing_errors,
    }

    print(f"  Updating CloudFront distribution {distribution_id}...", flush=True)
    cf.update_distribution(
        Id=distribution_id,
        IfMatch=etag,
        DistributionConfig=cfg,
    )
    print("  CloudFront update submitted (InProgress → ~5 min to Deployed)", flush=True)


def set_bucket_policy(s3, bucket_name, distribution_arn, account_id):
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "AllowCloudFrontOAC",
                "Effect": "Allow",
                "Principal": {"Service": "cloudfront.amazonaws.com"},
                "Action": "s3:GetObject",
                "Resource": f"arn:aws:s3:::{bucket_name}/*",
                "Condition": {
                    "StringEquals": {
                        "AWS:SourceArn": distribution_arn
                    }
                }
            }
        ]
    }
    s3.put_bucket_policy(
        Bucket=bucket_name,
        Policy=json.dumps(policy)
    )
    print(f"  Bucket policy updated for CloudFront OAC access", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile',          default='hackathon')
    parser.add_argument('--region',           default='us-east-1')
    parser.add_argument('--account-id',       required=True)
    parser.add_argument('--distribution-id',  required=True)
    parser.add_argument('--backend-origin-id', default='ship-api-ec2')
    args = parser.parse_args()

    bucket_name    = f"ym-fleet-ops-frontend-{args.account_id}"
    oac_name       = "ym-fleet-ops-frontend-oac"
    distribution_arn = f"arn:aws:cloudfront::{args.account_id}:distribution/{args.distribution_id}"

    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    s3      = session.client('s3')
    s3_ctrl = session.client('s3', region_name=args.region)
    cf      = session.client('cloudfront')

    print(f"▶  Setting up S3 bucket...", flush=True)
    get_or_create_bucket(s3, s3_ctrl, args.region, bucket_name)

    print(f"▶  Setting up CloudFront OAC...", flush=True)
    oac_id = get_or_create_oac(cf, oac_name)

    print(f"▶  Updating CloudFront distribution...", flush=True)
    update_cloudfront(cf, args.distribution_id, bucket_name, oac_id,
                      args.backend_origin_id, args.region, args.account_id)

    print(f"▶  Setting S3 bucket policy...", flush=True)
    set_bucket_policy(s3, bucket_name, distribution_arn, args.account_id)

    # Output bucket name for Makefile to consume
    print(f"BUCKET={bucket_name}")


if __name__ == '__main__':
    main()

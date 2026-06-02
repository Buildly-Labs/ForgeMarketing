---
title: Brand Management System Migration Guide
date: 2026-05-31
author: GitHub Copilot
category: Architecture
---

# Brand Management System Migration Guide

## Overview

This guide describes the database-driven brand model used by the dashboard.

Key principles:
- No hardcoded brand lists in production paths
- Brands are created and managed through onboarding/admin APIs
- Automation should read active brands from the database

## Recommended APIs

Use the shared loader utilities instead of embedding static arrays.

```python
from config.brand_loader import get_all_brands, get_brand_details

brands = get_all_brands(active_only=True)
brand = get_brand_details(brands[0]) if brands else None
```

## Data Model Summary

The `Brand` table is the source of truth for available brands.

```python
class Brand(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), unique=True, nullable=False)
    display_name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, default='')
    website_url = db.Column(db.String(500), default='')
    is_active = db.Column(db.Boolean, default=True, index=True)
```

Related tables:
- `BrandEmailConfig`
- `BrandSettings`
- `BrandAPICredential`

## Migration Pattern

### 1. Replace hardcoded lists

Before:

```python
brands = ['brand_a', 'brand_b', 'brand_c']
```

After:

```python
from config.brand_loader import get_all_brands
brands = get_all_brands(active_only=True)
```

### 2. Replace hardcoded per-brand branching

Before:

```python
if brand == 'brand_a':
    from_email = 'team@brand-a.example'
```

After:

```python
from config.brand_loader import get_brand_loader

loader = get_brand_loader()
config = loader.get_brand_config(brand, config_type='email')
from_email = (config.get('email') or [{}])[0].get('from_email', '')
```

### 3. Use safe fallbacks

When no brands are configured yet (fresh install), avoid crashing and provide a clear message.

```python
brands = get_all_brands(active_only=True)
if not brands:
    logger.warning('No active brands configured; complete onboarding first')
    return
```

## Practical Examples

### Iterate active brands in an automation job

```python
from config.brand_loader import get_all_brands

for brand in get_all_brands(active_only=True):
    run_for_brand(brand)
```

### Fetch one brand for targeted task

```python
from config.brand_loader import get_brand_details

brand = get_brand_details('washokuplus')
if brand:
    print(brand['display_name'])
```

## Validation Checklist

- `ops/brand_audit.py` reports no high-priority hardcoded brand issues in active runtime paths.
- New brand can be added in admin UI and appears in automation flows without code changes.
- Core endpoints continue to return valid data when 0, 1, or many brands are configured.

## Known Scope Boundaries

This guide focuses on active runtime code paths. Historical archive docs and legacy backups may still contain older product names for recordkeeping.

## Quick Commands

```bash
# Initialize / refresh schema
python dashboard/init_db.py

# Check active brands through API
curl -sS http://localhost:8002/api/admin/brands

# Run hardcoded-brand audit
python ops/brand_audit.py
```

#!/usr/bin/env python3
"""Quick smoke test for the auth flow."""
import sys
sys.path.insert(0, '.')
from dashboard.app import app

with app.test_client() as c:
    # Unauth -> redirect
    r = c.get('/', follow_redirects=False)
    print(f'GET / (unauth): {r.status_code} -> {r.headers.get("Location", "")}')

    # Login page loads
    r = c.get('/login')
    print(f'GET /login: {r.status_code}')

    # Login with correct creds
    r = c.post('/login', json={'email': 'greg@open.build', 'password': 'changeme'})
    print(f'POST /login: {r.status_code} {r.get_json()}')

    # Authed requests work
    r = c.get('/')
    print(f'GET / (authed): {r.status_code}')

    r = c.get('/api/admin/brands')
    d = r.get_json()
    brands = [b['name'] for b in d.get('brands', [])] if d else 'error'
    print(f'GET /api/admin/brands: {r.status_code} brands={brands}')

    # Switch brand
    r = c.post('/switch-brand/2', follow_redirects=False)
    print(f'POST /switch-brand/2: {r.status_code}')

    # Logout
    r = c.get('/logout', follow_redirects=False)
    print(f'GET /logout: {r.status_code} -> {r.headers.get("Location", "")}')

    # After logout
    r = c.get('/', follow_redirects=False)
    print(f'GET / (after logout): {r.status_code} -> {r.headers.get("Location", "")}')

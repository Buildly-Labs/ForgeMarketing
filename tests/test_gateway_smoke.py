#!/usr/bin/env python3
"""Smoke test for the Buildly gateway app."""
import sys, os
PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)
os.environ.setdefault('ADMIN_EMAIL', 'greg@open.build')
os.environ.setdefault('ADMIN_PASSWORD', 'changeme')

from gateway_app import app, db
from dashboard.database import DatabaseManager

with app.app_context():
    db.create_all()
    mgr = DatabaseManager(app)
    mgr.init_db()
    print('DB initialized')

    client = app.test_client()

    # 1. Unauthenticated → redirect to login
    r = client.get('/', follow_redirects=False)
    assert r.status_code == 302, f'Expected 302, got {r.status_code}'
    assert '/login' in r.headers['Location']
    print('1. Unauth redirect OK')

    # 2. GET /login → 200 with Buildly branding
    r = client.get('/login')
    assert r.status_code == 200
    assert b'Buildly' in r.data
    print('2. Login page renders OK (Buildly-branded)')

    # 3. POST /login with valid creds
    r = client.post('/login', data={'email': 'greg@open.build', 'password': 'changeme'}, follow_redirects=False)
    assert r.status_code == 302
    assert r.headers['Location'] == '/'
    print('3. Login POST redirect OK')

    # 4. Landing page renders both app cards
    r = client.get('/')
    assert r.status_code == 200
    assert b'Marketing Hub' in r.data
    assert b'Podcast Studio' in r.data
    print('4. Landing page renders (Marketing Hub + Podcast Studio)')

    # 5. Logout
    r = client.get('/logout', follow_redirects=False)
    assert r.status_code == 302
    assert '/login' in r.headers['Location']
    print('5. Logout redirect OK')

    print('\nAll gateway tests PASSED')

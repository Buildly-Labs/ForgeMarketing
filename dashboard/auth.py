"""
Authentication blueprint — login, logout, brand switching.
"""

from flask import Blueprint, request, jsonify, render_template, redirect, url_for, session, flash
from flask_login import login_user, logout_user, login_required, current_user
from datetime import datetime
import logging

from dashboard.models import db, User, UserBrand, Brand

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__)


# ── HTML routes ──────────────────────────────────────────────

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect('/')

    if request.method == 'GET':
        return render_template('login.html')

    # POST — either JSON or form
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form

    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''

    if not email or not password:
        msg = 'Email and password are required.'
        if request.is_json:
            return jsonify({'success': False, 'error': msg}), 400
        flash(msg, 'error')
        return render_template('login.html'), 400

    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        msg = 'Invalid email or password.'
        if request.is_json:
            return jsonify({'success': False, 'error': msg}), 401
        flash(msg, 'error')
        return render_template('login.html'), 401

    if not user.is_active:
        msg = 'Account is disabled.'
        if request.is_json:
            return jsonify({'success': False, 'error': msg}), 403
        flash(msg, 'error')
        return render_template('login.html'), 403

    login_user(user)
    user.last_login_at = datetime.utcnow()
    db.session.commit()

    # Set default active brand
    brands = user.get_brands()
    if brands:
        session['active_brand_id'] = brands[0].id
    elif user.is_admin:
        first = Brand.query.filter_by(is_active=True).first()
        if first:
            session['active_brand_id'] = first.id

    if request.is_json:
        return jsonify({'success': True, 'redirect': '/'})
    return redirect('/')


@auth_bp.route('/logout')
@login_required
def logout():
    session.pop('active_brand_id', None)
    logout_user()
    return redirect('/login')


# ── Force password change ────────────────────────────────────

@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'GET':
        return render_template('change_password.html')

    if request.is_json:
        data = request.get_json()
    else:
        data = request.form

    new_password = (data.get('new_password') or '').strip()
    confirm_password = (data.get('confirm_password') or '').strip()

    if not new_password or len(new_password) < 8:
        msg = 'Password must be at least 8 characters.'
        if request.is_json:
            return jsonify({'success': False, 'error': msg}), 400
        flash(msg, 'error')
        return render_template('change_password.html'), 400

    if new_password != confirm_password:
        msg = 'Passwords do not match.'
        if request.is_json:
            return jsonify({'success': False, 'error': msg}), 400
        flash(msg, 'error')
        return render_template('change_password.html'), 400

    current_user.set_password(new_password)
    current_user.must_change_password = False
    db.session.commit()

    if request.is_json:
        return jsonify({'success': True, 'redirect': '/'})
    flash('Password updated successfully.', 'success')
    return redirect('/')


# ── Brand switching ──────────────────────────────────────────

@auth_bp.route('/switch-brand/<int:brand_id>', methods=['POST'])
@login_required
def switch_brand(brand_id):
    brand = Brand.query.get(brand_id)
    if not brand or not brand.is_active:
        if request.is_json:
            return jsonify({'success': False, 'error': 'Brand not found'}), 404
        flash('Brand not found', 'error')
        return redirect('/')

    if not current_user.has_brand_access(brand_id):
        if request.is_json:
            return jsonify({'success': False, 'error': 'Access denied'}), 403
        flash('You do not have access to that brand', 'error')
        return redirect('/')

    session['active_brand_id'] = brand_id

    if request.is_json:
        return jsonify({'success': True, 'brand': brand.to_dict()})

    return redirect(request.referrer or '/')


# ── User management API (admin only) ────────────────────────

@auth_bp.route('/api/users', methods=['GET'])
@login_required
def list_users():
    if not current_user.is_admin:
        return jsonify({'success': False, 'error': 'Admin required'}), 403

    users = User.query.all()
    return jsonify({'success': True, 'users': [u.to_dict() for u in users]})


@auth_bp.route('/api/users', methods=['POST'])
@login_required
def create_user():
    if not current_user.is_admin:
        return jsonify({'success': False, 'error': 'Admin required'}), 403

    data = request.get_json() or {}
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''
    display_name = data.get('display_name', '')
    brand_ids = data.get('brand_ids', [])

    if not email or not password:
        return jsonify({'success': False, 'error': 'email and password required'}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({'success': False, 'error': 'Email already exists'}), 409

    user = User(email=email, display_name=display_name)
    user.set_password(password)
    db.session.add(user)
    db.session.flush()

    for bid in brand_ids:
        brand = Brand.query.get(bid)
        if brand:
            db.session.add(UserBrand(user_id=user.id, brand_id=brand.id, role='editor'))

    db.session.commit()
    return jsonify({'success': True, 'user': user.to_dict()}), 201

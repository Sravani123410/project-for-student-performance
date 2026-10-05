import jwt
from datetime import datetime, timedelta
from functools import wraps
from flask import request, redirect, url_for, flash, jsonify, g, current_app
from models import User, db

def generate_jwt(user):
    payload = {
        'sub': str(user.id),
        'name': user.name,
        'email': user.email,
        'role': user.role,
        'exp': datetime.utcnow() + timedelta(hours=24),
        'iat': datetime.utcnow()
    }
    token = jwt.encode(payload, current_app.config['JWT_SECRET_KEY'], algorithm='HS256')
    return token

def decode_jwt(token):
    try:
        payload = jwt.decode(token, current_app.config['JWT_SECRET_KEY'], algorithms=['HS256'])
        return payload
    except Exception as e:
        return None

def get_current_user_from_request():
    token = None
    # Check Authorization header first (Bearer <token>)
    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        token = auth_header.split(' ')[1]
    
    # Check cookie if header not found
    if not token:
        token = request.cookies.get('jwt_token')

    if token:
        payload = decode_jwt(token)
        if payload:
            user_id = int(payload.get('sub')) if payload.get('sub') and str(payload.get('sub')).isdigit() else None
            user = db.session.get(User, user_id) if user_id else None
            if not user and payload.get('email'):
                user = User.query.filter_by(email=payload.get('email')).first()
            return user
    return None

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user_from_request()
        if not user:
            if request.path.startswith('/api/'):
                return jsonify({'error': 'Authentication required', 'message': 'Invalid or expired token'}), 401
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login_page', next=request.url))
        g.current_user = user
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user_from_request()
        if not user:
            if request.path.startswith('/api/'):
                return jsonify({'error': 'Authentication required'}), 401
            flash('Please log in as Administrator.', 'warning')
            return redirect(url_for('login_page'))
        if user.role != 'admin':
            if request.path.startswith('/api/'):
                return jsonify({'error': 'Forbidden', 'message': 'Admin access required'}), 403
            flash('Access denied. Administrator rights required.', 'danger')
            return redirect(url_for('dashboard'))
        g.current_user = user
        return f(*args, **kwargs)
    return decorated_function

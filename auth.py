"""
用户认证模块
处理用户登录、注册、会话管理等功能
"""

import functools
import jwt
from datetime import datetime, timedelta
from flask import request, jsonify, current_app
from models import get_db, User


def generate_token(user_id, expires_in=24*60*60):
    """生成JWT token"""
    payload = {
        'user_id': user_id,
        'exp': datetime.utcnow() + timedelta(seconds=expires_in),
        'iat': datetime.utcnow()
    }
    return jwt.encode(payload, current_app.config['SECRET_KEY'], algorithm='HS256')


def verify_token(token):
    """验证JWT token"""
    try:
        payload = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=['HS256'])
        return payload['user_id']
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def get_current_user():
    """获取当前登录用户"""
    token = request.headers.get('Authorization')
    if not token:
        return None

    # 去掉Bearer前缀
    if token.startswith('Bearer '):
        token = token[7:]

    user_id = verify_token(token)
    if not user_id:
        return None

    with get_db() as db:
        user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
        return user


def login_required(f):
    """登录验证装饰器"""
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({'error': '需要登录或登录已过期'}), 401
        # 将用户信息添加到请求上下文
        request.current_user = user
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """管理员权限验证装饰器"""
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({'error': '需要登录或登录已过期'}), 401
        if not user.is_admin:
            return jsonify({'error': '需要管理员权限'}), 403
        request.current_user = user
        return f(*args, **kwargs)
    return decorated_function


def user_login(username, password):
    """用户登录"""
    with get_db() as db:
        user = db.query(User).filter(
            (User.username == username) | (User.email == username),
            User.is_active == True
        ).first()

        if not user or not user.check_password(password):
            return None, '用户名或密码错误'

        # 更新最后登录时间
        user.last_login = datetime.now()
        db.commit()

        # 生成token
        token = generate_token(user.id)

        return {
            'token': token,
            'user': user.to_dict()
        }, None


def user_register(username, email, password):
    """用户注册"""
    with get_db() as db:
        # 检查用户名是否已存在
        if db.query(User).filter(User.username == username).first():
            return None, '用户名已存在'

        # 检查邮箱是否已存在
        if db.query(User).filter(User.email == email).first():
            return None, '邮箱已存在'

        # 创建新用户
        user = User(
            username=username,
            email=email
        )
        user.set_password(password)

        db.add(user)
        db.commit()
        db.refresh(user)

        return {
            'user': user.to_dict()
        }, None


def update_user_profile(user_id, data):
    """更新用户资料"""
    with get_db() as db:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return None, '用户不存在'

        password_changed = False

        # 更新用户名
        if 'username' in data and data['username'] != user.username:
            # 检查用户名是否已被其他用户使用
            existing_user = db.query(User).filter(
                User.username == data['username'],
                User.id != user_id
            ).first()
            if existing_user:
                return None, '用户名已存在'
            user.username = data['username']

        # 更新邮箱
        if 'email' in data and data['email'] != user.email:
            # 检查邮箱是否已被其他用户使用
            existing_user = db.query(User).filter(
                User.email == data['email'],
                User.id != user_id
            ).first()
            if existing_user:
                return None, '邮箱已存在'
            user.email = data['email']

        # 更新密码（需要验证旧密码）
        if 'new_password' in data and data['new_password']:
            # 验证新密码长度
            if len(data['new_password']) < 8:
                return None, '新密码长度至少8位'
            
            # 验证旧密码
            old_password = data.get('old_password', '')
            if not old_password:
                return None, '修改密码需要提供旧密码'
            
            if not user.check_password(old_password):
                return None, '旧密码错误'
            
            # 更新密码
            user.set_password(data['new_password'])
            password_changed = True

        db.commit()

        result = {
            'user': user.to_dict()
        }
        
        # 如果修改了密码，返回标识
        if password_changed:
            result['password_changed'] = True

        return result, None
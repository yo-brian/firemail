#  -*- coding: utf-8 -*-
import os
import sys
import logging
from logging.handlers import RotatingFileHandler
import threading
import argparse
import datetime
import time
import uuid
import jwt
from functools import wraps
from flask import Flask, send_from_directory, jsonify, request, Response, make_response
from flask_cors import CORS
from database.db import Database
from utils.email import EmailBatchProcessor, OutlookMailHandler
import requests
import msal
from ws_server.handler import WebSocketHandler
import asyncio
import concurrent.futures

# 配置日志
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
os.makedirs(log_dir, exist_ok=True)
app_log_file = os.path.join(log_dir, "FireMail.log")
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        RotatingFileHandler(
            app_log_file,
            maxBytes=1 * 1024 * 1024,
            backupCount=3,
            encoding='utf-8'
        ),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('FireMail')

# 确保数据目录存在
data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
os.makedirs(data_dir, exist_ok=True)

# 初始化Flask应用
app = Flask(__name__)
CORS(app, supports_credentials=True, resources={r"/api/*": {"origins": "*"}})  # 允许跨域请求和凭据


# 增加捕获所有OPTIONS请求的处理方法，支持预检请求
@app.route('/', defaults={'path': ''}, methods=['OPTIONS'])
@app.route('/<path:path>', methods=['OPTIONS'])
def handle_options(path):
    """处理所有OPTIONS请求"""
    response = make_response()
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,POST,PUT,DELETE,OPTIONS')
    response.headers.add('Access-Control-Allow-Credentials', 'true')
    return response

# JWT密钥
JWT_SECRET = os.environ.get('JWT_SECRET_KEY', 'huohuo_email_secret_key')
OUTLOOK_DEVICE_AUTHORITY = os.environ.get(
    'OUTLOOK_DEVICE_AUTHORITY',
    'https://login.microsoftonline.com/consumers/'
)
_OUTLOOK_DEFAULT_SCOPES = ['User.Read', 'Mail.Read', 'Mail.ReadWrite', 'Mail.Send']
_OUTLOOK_RESERVED_SCOPES = {'openid', 'profile', 'offline_access'}
_raw_outlook_scopes = os.environ.get(
    'OUTLOOK_DEVICE_SCOPES',
    'offline_access User.Read Mail.Read Mail.ReadWrite Mail.Send'
)
_raw_outlook_scopes = _raw_outlook_scopes.replace(',', ' ')
OUTLOOK_DEVICE_SCOPES = []
for _scope in _raw_outlook_scopes.split():
    _scope = _scope.strip()
    if not _scope:
        continue
    if _scope.lower() in _OUTLOOK_RESERVED_SCOPES:
        continue
    OUTLOOK_DEVICE_SCOPES.append(_scope)
if not OUTLOOK_DEVICE_SCOPES:
    OUTLOOK_DEVICE_SCOPES = list(_OUTLOOK_DEFAULT_SCOPES)
elif set(s.lower() for s in OUTLOOK_DEVICE_SCOPES) != set(s.lower() for s in _raw_outlook_scopes.split()):
    logger.info(f"Outlook device flow: filtered reserved scopes, effective scopes={OUTLOOK_DEVICE_SCOPES}")
OUTLOOK_DEVICE_FLOW_CACHE_TTL = int(os.environ.get('OUTLOOK_DEVICE_FLOW_CACHE_TTL', '1800'))
_OUTLOOK_DEVICE_FLOW_LOCK = threading.Lock()
_OUTLOOK_DEVICE_FLOWS = {}

# 打印所有环境变量，帮助调试
print("\n========= 环境变量 =========")
for key, value in os.environ.items():
    if key in ['JWT_SECRET_KEY', 'HOST', 'FLASK_PORT', 'WS_PORT', 'API_URL', 'WS_URL']:
        print(f"{key}: {value}")
print("===========================\n")

# 初始化数据库
db = Database()

# 确保注册功能默认开启，只通过数据库控制
allow_register = db.is_registration_allowed()
logger.info(f"系统启动: 注册功能状态 = {allow_register}")

# 初始化邮件处理器
email_processor = EmailBatchProcessor(db)

# 初始化WebSocket处理器
ws_handler = WebSocketHandler()
ws_handler.set_dependencies(db, email_processor)


def _purge_expired_outlook_device_flows():
    now = time.time()
    with _OUTLOOK_DEVICE_FLOW_LOCK:
        expired_keys = []
        for flow_id, item in _OUTLOOK_DEVICE_FLOWS.items():
            expires_at = float(item.get('expires_at') or 0)
            if expires_at and expires_at < now:
                expired_keys.append(flow_id)
                continue
            created_at = float(item.get('created_at') or 0)
            if created_at and (now - created_at) > OUTLOOK_DEVICE_FLOW_CACHE_TTL:
                expired_keys.append(flow_id)
        for flow_id in expired_keys:
            _OUTLOOK_DEVICE_FLOWS.pop(flow_id, None)

# 用户认证装饰器
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None

        # 从请求头或Cookie获取token
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            if auth_header.startswith('Bearer '):
                token = auth_header.split(" ")[1]
        elif request.cookies.get('token'):
            token = request.cookies.get('token')

        if not token:
            return jsonify({'error': '未认证，请先登录'}), 401

        try:
            data = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
            current_user = db.get_user_by_id(data['user_id'])
            if not current_user:
                return jsonify({'error': '无效的用户令牌'}), 401
        except jwt.ExpiredSignatureError:
            return jsonify({'error': '令牌已过期，请重新登录'}), 401
        except Exception as e:
            logger.error(f"令牌验证失败: {str(e)}")
            return jsonify({'error': '无效的令牌'}), 401

        # 将当前用户信息添加到kwargs
        kwargs['current_user'] = current_user
        return f(*args, **kwargs)

    return decorated

# 管理员权限装饰器
def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        current_user = kwargs.get('current_user')
        if not current_user or not current_user['is_admin']:
            return jsonify({'error': '需要管理员权限'}), 403
        return f(*args, **kwargs)

    return decorated

# 认证相关API
@app.route('/api/auth/login', methods=['POST'])
def login():
    """用户登录"""
    try:
        data = request.json
        if not data:
            logger.error("登录请求没有JSON数据")
            return jsonify({'error': '无效的请求数据格式'}), 400

        username = data.get('username')
        password = data.get('password')

        logger.info(f"收到登录请求: 用户名={username}")

        if not username or not password:
            logger.warning("登录失败: 用户名或密码为空")
            return jsonify({'error': '用户名和密码不能为空'}), 400

        user = db.authenticate_user(username, password)
        if not user:
            logger.warning(f"登录失败: 用户名或密码错误, 用户名={username}")
            return jsonify({'error': '用户名或密码错误'}), 401

        # 确保user对象包含所有必要属性
        if 'id' not in user or 'username' not in user or 'is_admin' not in user:
            logger.error(f"用户对象缺少必要字段: {user}")
            return jsonify({'error': '内部服务器错误'}), 500

        # 生成JWT令牌
        token = jwt.encode({
            'user_id': user['id'],
            'username': user['username'],
            'is_admin': user['is_admin'],
            'exp': datetime.datetime.utcnow() + datetime.timedelta(days=7)
        }, JWT_SECRET, algorithm="HS256")

        # 创建响应
        response_data = {
            'token': token,
            'user': {
                'id': user['id'],
                'username': user['username'],
                'is_admin': user['is_admin']
            }
        }

        logger.info(f"登录成功: 用户名={username}, 用户ID={user['id']}")

        # 创建JSON响应并设置CORS头
        response = make_response(jsonify(response_data))
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'POST')

        # 设置Cookie
        response.set_cookie(
            'token',
            token,
            httponly=True,
            max_age=7*24*60*60,  # 7天
            secure=False,  # 开发环境设为False，生产环境设为True
            samesite='Lax'
        )

        logger.info(f"用户 {username} 登录成功")
        return response
    except Exception as e:
        logger.error(f"登录过程中发生错误: {str(e)}")
        return jsonify({'error': f'服务器错误: {str(e)}'}), 500

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    """用户登出"""
    response = make_response(jsonify({'message': '已成功登出'}))
    response.delete_cookie('token')
    return response

@app.route('/api/auth/register', methods=['POST'])
def register():
    """用户注册"""
    # 检查系统是否允许注册
    allow_register = db.is_registration_allowed()
    logger.info(f"收到注册请求，当前注册功能状态: {allow_register}")

    if not allow_register:
        logger.warning("注册功能已禁用，拒绝注册请求")
        return jsonify({'error': '注册功能已禁用'}), 403

    data = request.json
    username = data.get('username')
    password = data.get('password')

    logger.info(f"注册用户名: {username}")

    if not username or not password:
        logger.warning("注册失败: 用户名或密码为空")
        return jsonify({'error': '用户名和密码不能为空'}), 400

    # 用户名格式验证
    if len(username) < 3 or len(username) > 20:
        logger.warning("注册失败: 用户名长度不符合要求")
        return jsonify({'error': '用户名长度必须在3-20个字符之间'}), 400

    # 密码强度验证
    if len(password) < 6:
        logger.warning("注册失败: 密码长度不符合要求")
        return jsonify({'error': '密码长度必须至少为6个字符'}), 400

    try:
        # 创建用户
        success, is_admin = db.create_user(username, password)
        if not success:
            logger.warning(f"注册失败: 用户名 {username} 已存在")
            return jsonify({'error': '用户名已存在'}), 409

        logger.info(f"注册成功: 用户名 {username}, 是否管理员: {is_admin}")
        return jsonify({
            'message': '注册成功',
            'username': username,
            'is_admin': is_admin,
            'note': '您是第一个注册的用户，已被自动设置为管理员' if is_admin else ''
        })
    except Exception as e:
        logger.error(f"注册过程出错: {str(e)}")
        return jsonify({'error': f'注册失败: {str(e)}'}), 500

@app.route('/api/auth/user', methods=['GET'])
@token_required
def get_current_user(current_user):
    """获取当前用户信息"""
    return jsonify({
        'id': current_user['id'],
        'username': current_user['username'],
        'is_admin': current_user['is_admin']
    })

@app.route('/api/auth/change-password', methods=['POST'])
@token_required
def change_password(current_user):
    """更改当前用户密码"""
    data = request.json
    old_password = data.get('old_password')
    new_password = data.get('new_password')

    if not old_password or not new_password:
        return jsonify({'error': '旧密码和新密码不能为空'}), 400

    # 验证旧密码
    user = db.authenticate_user(current_user['username'], old_password)
    if not user:
        return jsonify({'error': '旧密码不正确'}), 401

    # 密码强度验证
    if len(new_password) < 6:
        return jsonify({'error': '新密码长度必须至少为6个字符'}), 400

    # 更新密码
    success = db.update_user_password(current_user['id'], new_password)
    if not success:
        return jsonify({'error': '密码更新失败'}), 500

    return jsonify({'message': '密码已成功更新'})

# 用户管理API
@app.route('/api/users', methods=['GET'])
@token_required
@admin_required
def get_all_users(current_user):
    """获取所有用户 (仅管理员)"""
    users = db.get_all_users()
    return jsonify([dict(user) for user in users])

@app.route('/api/users', methods=['POST'])
@token_required
@admin_required
def create_user(current_user):
    """创建新用户 (仅管理员)"""
    data = request.json
    username = data.get('username')
    password = data.get('password')
    is_admin = data.get('is_admin', False)

    if not username or not password:
        return jsonify({'error': '用户名和密码不能为空'}), 400

    # 用户名格式验证
    if len(username) < 3 or len(username) > 20:
        return jsonify({'error': '用户名长度必须在3-20个字符之间'}), 400

    # 密码强度验证
    if len(password) < 6:
        return jsonify({'error': '密码长度必须至少为6个字符'}), 400

    # 创建用户
    success, _ = db.create_user(username, password, is_admin)
    if not success:
        return jsonify({'error': '用户名已存在'}), 409

    return jsonify({
        'message': '用户创建成功',
        'username': username,
        'is_admin': is_admin
    })

@app.route('/api/users/<int:user_id>', methods=['DELETE'])
@token_required
@admin_required
def delete_user(current_user, user_id):
    """删除用户 (仅管理员)"""
    # 检查是否是当前用户
    if user_id == current_user['id']:
        return jsonify({'error': '不能删除自己的账户'}), 400

    # 删除用户
    success = db.delete_user(user_id)
    if not success:
        return jsonify({'error': '删除用户失败'}), 500

    return jsonify({'message': f'用户ID {user_id} 已删除'})

@app.route('/api/users/<int:user_id>/reset-password', methods=['POST'])
@token_required
@admin_required
def reset_user_password(current_user, user_id):
    """重置用户密码 (仅管理员)"""
    data = request.json
    new_password = data.get('new_password')

    if not new_password:
        return jsonify({'error': '新密码不能为空'}), 400

    # 密码强度验证
    if len(new_password) < 6:
        return jsonify({'error': '新密码长度必须至少为6个字符'}), 400

    # 更新密码
    success = db.update_user_password(user_id, new_password)
    if not success:
        return jsonify({'error': '密码重置失败'}), 500

    return jsonify({'message': f'用户ID {user_id} 的密码已重置'})

# 修改现有API以加入用户认证和授权
@app.route('/api/health', methods=['GET'])
def health_check():
    """健康检查接口"""
    return jsonify({'status': 'ok', 'message': '学在华邮件助手服务正在运行'})

@app.route('/api/config', methods=['GET'])
def get_config():
    """获取系统配置"""
    try:
        # 确保从数据库获取最新的注册状态
        allow_register = db.is_registration_allowed()
        logger.info(f"获取系统配置: 注册功能状态 = {allow_register}")

        config = {
            'allow_register': allow_register,
            'server_time': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        # 设置CORS头，确保前端可以正常访问
        response = jsonify(config)
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'GET')

        logger.info(f"返回系统配置: {config}")
        return response
    except Exception as e:
        logger.error(f"获取系统配置出错: {str(e)}")
        # 返回默认配置，确保注册功能默认开启
        default_config = {
            'allow_register': True,
            'server_time': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'error': f"配置获取错误: {str(e)}"
        }
        response = jsonify(default_config)
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response

@app.route('/api/emails', methods=['GET'])
@token_required
def get_all_emails(current_user):
    """获取当前用户的所有邮箱"""
    # 普通用户只能获取自己的邮箱，管理员可以获取所有邮箱
    if current_user['is_admin']:
        emails = db.get_all_emails()
    else:
        emails = db.get_all_emails(current_user['id'])

    emails_list = []
    for email in emails:
        email_dict = dict(email)
        email_dict['unread_count'] = db.get_unread_count(email_dict['id'])
        emails_list.append(email_dict)

    return jsonify(emails_list)

@app.route('/api/emails', methods=['POST'])
@token_required
def add_email(current_user):
    """添加新邮箱"""
    data = request.json or {}
    email = (data.get('email') or '').strip()
    password = data.get('password') or ''
    mail_type = data.get('mail_type', 'outlook')

    if mail_type != 'outlook' and (not email or not password):
        return jsonify({'error': '邮箱地址和密码是必需的'}), 400

    # 根据不同邮箱类型验证参数并添加
    if mail_type == 'outlook':
        client_id = data.get('client_id')
        refresh_token = data.get('refresh_token')

        if not client_id or not refresh_token:
            return jsonify({'error': 'Outlook邮箱需要提供Client ID和Refresh Token'}), 400

        resolved = OutlookMailHandler.resolve_graph_mailbox(
            refresh_token=refresh_token,
            client_id=client_id,
            expected_email=email or None
        )
        if not resolved.get('success'):
            return jsonify({'error': resolved.get('error') or 'Graph 身份校验失败'}), 400

        # 始终以 Graph /me 返回的邮箱为准，避免手填邮箱与令牌身份不一致
        email = resolved.get('email') or ''
        if not email:
            return jsonify({'error': '无法解析邮箱地址，请检查授权后重试'}), 400

        success = db.add_email(
            current_user['id'],
            email,
            password,
            client_id,
            refresh_token,
            mail_type
        )
    elif mail_type in ['imap', 'gmail', 'qq']:
        # Gmail和QQ邮箱使用IMAP协议，服务器和端口是固定的
        if mail_type == 'gmail':
            server = 'imap.gmail.com'
            port = 993
        elif mail_type == 'qq':
            server = 'imap.qq.com'
            port = 993
        else:
            server = data.get('server', 'imap.gmail.com')
            port = data.get('port', 993)

        success = db.add_email(
            current_user['id'],
            email,
            password,
            mail_type=mail_type,
            server=server,
            port=port,
            use_ssl=True
        )
    else:
        return jsonify({'error': f'不支持的邮箱类型: {mail_type}'}), 400

    if success:
        return jsonify({'message': f'邮箱 {email} 添加成功'})
    else:
        return jsonify({'error': f'邮箱 {email} 已存在或添加失败'}), 409

@app.route('/api/emails/<int:email_id>', methods=['DELETE'])
@token_required
def delete_email(current_user, email_id):
    """删除邮箱"""
    # 获取邮箱信息
    email_info = db.get_email_by_id(email_id, None if current_user['is_admin'] else current_user['id'])
    if not email_info:
        return jsonify({'error': f'邮箱ID {email_id} 不存在或您没有权限'}), 404

    # 停止正在处理的邮箱
    if email_processor.is_email_being_processed(email_id):
        email_processor.stop_processing(email_id)

    # 管理员可以删除任何邮箱，普通用户只能删除自己的邮箱
    db.delete_email(email_id, None if current_user['is_admin'] else current_user['id'])
    return jsonify({'message': f'邮箱 ID {email_id} 已删除'})

@app.route('/api/emails/batch_delete', methods=['POST'])
@token_required
def batch_delete_emails(current_user):
    """批量删除邮箱"""
    data = request.json
    email_ids = data.get('email_ids', [])

    if not email_ids:
        return jsonify({'error': '未提供邮箱ID'}), 400

    # 停止正在处理的邮箱
    for email_id in email_ids:
        if email_processor.is_email_being_processed(email_id):
            email_processor.stop_processing(email_id)

    # 管理员可以删除任何邮箱，普通用户只能删除自己的邮箱
    db.delete_emails(email_ids, None if current_user['is_admin'] else current_user['id'])
    return jsonify({'message': f'已删除 {len(email_ids)} 个邮箱'})

@app.route('/api/emails/<int:email_id>/check', methods=['POST'])
@token_required
def check_email(current_user, email_id):
    """检查指定邮箱的新邮件"""
    try:
        # 获取邮箱信息
        email_info = db.get_email_by_id(email_id)
        if not email_info:
            return jsonify({'error': '邮箱不存在'}), 404

        # 检查邮箱是否属于当前用户
        if email_info['user_id'] != current_user['id']:
            return jsonify({'error': '无权操作此邮箱'}), 403

        # 检查邮箱是否正在处理中
        if email_processor.is_email_being_processed(email_id):
            logger.info(f"邮箱 ID {email_id} 正在处理中，拒绝重复请求")
            return jsonify({
                'success': False,
                'message': '邮箱正在处理中，请稍后再试',
                'status': 'processing'
            }), 409

        # 创建进度回调
        def progress_callback(progress, message):
            logger.info(f"邮箱 ID {email_id} 处理进度: {progress}%, 消息: {message}")
            # 通过WebSocket发送进度更新
            try:
                # 使用日志记录进度，不尝试调用异步方法
                logger.info(f"向用户 {current_user['id']} 发送邮箱检查进度: {progress}%, {message}")
                # 这里应使用同步方式发送消息，但WSHandler.broadcast_to_user是异步方法
            except Exception as e:
                logger.error(f"发送进度更新失败: {str(e)}")

        # 提交任务到线程池
        future = email_processor.manual_thread_pool.submit(
            email_processor._check_email_task,
            email_info,
            progress_callback
        )

        # 等待任务完成
        result = future.result(timeout=300)  # 设置超时时间为5分钟

        # 记录任务完成
        logger.info(f"任务完成: {result}")

        return jsonify(result)

    except concurrent.futures.TimeoutError:
        logger.error(f"检查邮箱超时: {email_id}")
        return jsonify({
            'success': False,
            'message': '检查邮箱超时，请稍后再试'
        }), 408

    except Exception as e:
        logger.error(f"检查邮箱失败: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'检查邮箱失败: {str(e)}'
        }), 500

@app.route('/api/emails/batch_check', methods=['POST'])
@token_required
def batch_check_emails(current_user):
    """批量检查邮箱邮件"""
    data = request.json
    email_ids = data.get('email_ids', [])

    if not email_ids:
        # 如果没有提供 ID，则获取当前用户拥有的所有邮箱
        if current_user['is_admin']:
            emails = db.get_all_emails()
        else:
            emails = db.get_all_emails(current_user['id'])

        email_ids = [email['id'] for email in emails]
    else:
        # 如果提供了ID，验证用户权限
        if not current_user['is_admin']:
            # 获取该用户拥有的邮箱
            owned_emails = db.get_all_emails(current_user['id'])
            owned_ids = [email['id'] for email in owned_emails]
            # 过滤出用户有权限的邮箱ID
            email_ids = [id for id in email_ids if id in owned_ids]

    if not email_ids:
        logger.warning(f"批量检查邮件：未找到邮箱 (用户ID: {current_user['id']})")
        return jsonify({'error': '没有找到邮箱或您没有权限'}), 404

    # 过滤掉已经在处理的邮箱ID
    processing_ids = []
    valid_ids = []
    for email_id in email_ids:
        if email_processor.is_email_being_processed(email_id):
            processing_ids.append(email_id)
        else:
            valid_ids.append(email_id)

    if processing_ids:
        logger.info(f"批量检查：跳过正在处理的邮箱IDs: {processing_ids}")

    if not valid_ids:
        logger.warning("批量检查邮件：所有选择的邮箱都在处理中")
        return jsonify({
            'message': '所有选择的邮箱都在处理中',
            'processing_ids': processing_ids
        }), 409

    # 记录有效的邮箱ID
    valid_emails = [db.get_email_by_id(email_id)['email'] for email_id in valid_ids if db.get_email_by_id(email_id)]
    logger.info(f"批量检查开始处理 {len(valid_ids)} 个邮箱: {valid_emails} (用户ID: {current_user['id']})")

    # 自定义进度回调
    def progress_callback(email_id, progress, message):
        logger.info(f"邮箱 ID {email_id} 处理进度: {progress}%, 消息: {message}")

    # 启动邮件检查线程
    email_processor.check_emails(valid_ids, progress_callback)

    return jsonify({
        'message': f'开始检查 {len(valid_ids)} 个邮箱',
        'skipped': len(processing_ids),
        'total': len(email_ids)
    })

@app.route('/api/emails/<int:email_id>/mail_records', methods=['GET'])
@token_required
def get_mail_records(current_user, email_id):
    """获取指定邮箱的邮件记录"""
    # 获取邮箱信息
    email_info = db.get_email_by_id(email_id, None if current_user['is_admin'] else current_user['id'])
    if not email_info:
        return jsonify({'error': f'邮箱 ID {email_id} 不存在或您没有权限'}), 404

    page = request.args.get('page', type=int)
    page_size = request.args.get('page_size', type=int)

    if page is not None or page_size is not None:
        page = page or 1
        page_size = page_size or 20
        page_size = min(max(page_size, 1), 200)
        records, total = db.get_mail_records_paginated(
            page=page,
            page_size=page_size,
            user_id=None if current_user['is_admin'] else current_user['id'],
            email_id=email_id
        )
        total_pages = (total + page_size - 1) // page_size if total > 0 else 0
        return jsonify({
            'records': records,
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total': total,
                'total_pages': total_pages
            }
        })

    mail_records = db.get_mail_records(email_id)
    return jsonify([dict(record) for record in mail_records])

@app.route('/api/mail_records', methods=['GET'])
@token_required
def list_mail_records(current_user):
    """分页获取邮件记录，可按邮箱筛选。"""
    page = request.args.get('page', default=1, type=int)
    page_size = request.args.get('page_size', default=20, type=int)
    email_id = request.args.get('email_id', type=int)

    if page <= 0:
        page = 1
    if page_size <= 0:
        page_size = 20
    page_size = min(page_size, 200)

    # 如果指定了邮箱，先校验权限
    if email_id is not None:
        email_info = db.get_email_by_id(email_id, None if current_user['is_admin'] else current_user['id'])
        if not email_info:
            return jsonify({'error': f'邮箱 ID {email_id} 不存在或您没有权限'}), 404

    records, total = db.get_mail_records_paginated(
        page=page,
        page_size=page_size,
        user_id=None if current_user['is_admin'] else current_user['id'],
        email_id=email_id
    )
    total_pages = (total + page_size - 1) // page_size if total > 0 else 0

    return jsonify({
        'records': records,
        'pagination': {
            'page': page,
            'page_size': page_size,
            'total': total,
            'total_pages': total_pages
        }
    })

@app.route('/api/mail_records/<int:mail_id>/attachments', methods=['GET'])
@token_required
def get_mail_attachments(current_user, mail_id):
    """获取指定邮件的附件列表"""
    try:
        # 先获取邮件信息，验证权限
        mail_record = db.get_mail_record_by_id(mail_id)
        if not mail_record:
            return jsonify({'error': '邮件不存在'}), 404

        # 验证用户是否有权限访问该邮件
        email_id = mail_record['email_id']
        email_info = db.get_email_by_id(email_id, None if current_user['is_admin'] else current_user['id'])
        if not email_info:
            return jsonify({'error': '无权访问此邮件'}), 403

        # 获取附件列表
        attachments = db.get_attachments(mail_id)
        return jsonify([dict(attachment) for attachment in attachments])
    except Exception as e:
        logger.error(f"获取附件列表失败: {str(e)}")
        return jsonify({'error': f'服务器错误: {str(e)}'}), 500

@app.route('/api/mail_records/<int:mail_id>/mark-read', methods=['POST'])
@token_required
def mark_mail_read(current_user, mail_id):
    """将邮件记录标记为已读，并同步到原邮箱"""
    try:
        mail_record = db.get_mail_record_by_id(mail_id)
        if not mail_record:
            return jsonify({'error': '邮件不存在'}), 404

        email_id = mail_record['email_id']
        email_info = db.get_email_by_id(email_id, None if current_user['is_admin'] else current_user['id'])
        if not email_info:
            return jsonify({'error': '无权访问此邮件'}), 403

        if email_info.get('mail_type') != 'outlook':
            return jsonify({'error': '仅支持Outlook/Graph邮箱的已读同步'}), 400

        graph_message_id = mail_record.get('graph_message_id')
        if not graph_message_id:
            return jsonify({'error': '缺少Graph消息ID，无法同步已读'}), 400

        refresh_token = email_info.get('refresh_token')
        client_id = email_info.get('client_id')
        if not refresh_token or not client_id:
            return jsonify({'error': '缺少Refresh Token或Client ID，无法同步已读'}), 400

        access_token = OutlookMailHandler.get_new_access_token(refresh_token, client_id)
        if not access_token:
            return jsonify({'error': '获取Access Token失败'}), 500

        OutlookMailHandler.mark_message_read(access_token, graph_message_id, True)
        db.set_mail_read_status(mail_id, 1)

        return jsonify({'success': True, 'message': '已同步已读'}), 200
    except Exception as e:
        logger.error(f"同步邮件已读状态失败: {str(e)}")
        return jsonify({'error': f'服务端错误: {str(e)}'}), 500

@app.route('/api/emails/<int:email_id>/send_mail', methods=['POST'])
@token_required
def send_mail(current_user, email_id):
    """发送邮件（Graph）"""
    try:
        email_info = db.get_email_by_id(email_id, None if current_user['is_admin'] else current_user['id'])
        if not email_info:
            return jsonify({'error': '邮箱不存在或无权限'}), 404

        if email_info.get('mail_type') != 'outlook':
            return jsonify({'error': '当前仅支持Outlook/Graph发信'}), 400

        data = request.json or {}
        to_list = data.get('to') or []
        if isinstance(to_list, str):
            to_list = [x.strip() for x in to_list.split(',') if x.strip()]
        subject = data.get('subject') or ''
        content = data.get('content') or ''
        cc_list = data.get('cc') or []
        bcc_list = data.get('bcc') or []
        attachments = _normalize_attachments(data.get('attachments'))

        if not to_list:
            return jsonify({'error': '收件人不能为空'}), 400

        access_token = OutlookMailHandler.get_new_access_token(email_info.get('refresh_token'), email_info.get('client_id'))
        if not access_token:
            return jsonify({'error': '获取Access Token失败'}), 500

        OutlookMailHandler.send_mail(
            access_token,
            to_list,
            subject,
            content,
            cc_list=cc_list,
            bcc_list=bcc_list,
            attachments=attachments
        )
        return jsonify({'success': True, 'message': '发送成功'}), 200
    except Exception as e:
        logger.error(f"发送邮件失败: {str(e)}")
        return jsonify({'error': f'服务端错误: {str(e)}'}), 500

def _normalize_recipients(value):
    if value is None:
        return None
    if isinstance(value, str):
        return [x.strip() for x in value.split(',') if x.strip()]
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    return None

def _normalize_attachments(value):
    if value is None:
        return []
    if not isinstance(value, list):
        return []
    normalized = []
    for item in value:
        if not isinstance(item, dict):
            continue
        content_base64 = (item.get('content_base64') or '').strip()
        if not content_base64:
            continue
        normalized.append({
            'name': (item.get('name') or 'attachment.bin').strip(),
            'content_type': (item.get('content_type') or 'application/octet-stream').strip(),
            'content_base64': content_base64
        })
    return normalized

@app.route('/api/mail_records/<int:mail_id>/reply', methods=['POST'])
@token_required
def reply_mail(current_user, mail_id):
    """Graph 原生 reply/replyAll（支持编辑收件人/主题/正文）"""
    try:
        mail_record = db.get_mail_record_by_id(mail_id)
        if not mail_record:
            return jsonify({'error': '邮件不存在'}), 404

        email_info = db.get_email_by_id(mail_record['email_id'], None if current_user['is_admin'] else current_user['id'])
        if not email_info:
            return jsonify({'error': '无权限访问此邮件'}), 403

        if email_info.get('mail_type') != 'outlook':
            return jsonify({'error': '当前仅支持Outlook/Graph回复'}), 400

        data = request.json or {}
        action = (data.get('action') or 'reply').strip().lower()
        if action not in ('reply', 'replyall'):
            return jsonify({'error': 'action 仅支持 reply 或 replyAll'}), 400
        reply_all = action == 'replyall'

        graph_message_id = (mail_record.get('graph_message_id') or '').strip()
        if not graph_message_id:
            return jsonify({'error': '缺少Graph消息ID，无法执行原生回复'}), 400

        access_token = OutlookMailHandler.get_new_access_token(email_info.get('refresh_token'), email_info.get('client_id'))
        if not access_token:
            return jsonify({'error': '获取Access Token失败'}), 500

        draft = OutlookMailHandler.create_reply_draft(access_token, graph_message_id, reply_all=reply_all)
        draft_id = draft.get('id')
        if not draft_id:
            return jsonify({'error': '创建回复草稿失败'}), 500

        subject = data.get('subject') if 'subject' in data else None
        content = data.get('content') if 'content' in data else None
        quote_body = (draft.get('body') or {}).get('content') or ''
        if content is not None:
            trimmed = content.strip()
            if quote_body:
                content = f"{trimmed}<br><br>{quote_body}" if trimmed else quote_body
        to_list = _normalize_recipients(data.get('to')) if 'to' in data else None
        cc_list = _normalize_recipients(data.get('cc')) if 'cc' in data else None
        bcc_list = _normalize_recipients(data.get('bcc')) if 'bcc' in data else None
        attachments = _normalize_attachments(data.get('attachments'))

        OutlookMailHandler.update_draft_message(
            access_token,
            draft_id,
            subject=subject,
            body_content=content,
            to_list=to_list,
            cc_list=cc_list,
            bcc_list=bcc_list,
            attachments=attachments,
        )
        OutlookMailHandler.send_draft_message(access_token, draft_id)
        return jsonify({'success': True, 'message': '回复发送成功', 'action': 'replyAll' if reply_all else 'reply'}), 200
    except Exception as e:
        logger.error(f"回复邮件失败: {str(e)}")
        return jsonify({'error': f'服务端错误: {str(e)}'}), 500

@app.route('/api/mail_records/<int:mail_id>', methods=['DELETE'])
@token_required
def delete_mail_record(current_user, mail_id):
    """删除邮件（Graph + 本地记录）"""
    try:
        mail_record = db.get_mail_record_by_id(mail_id)
        if not mail_record:
            return jsonify({'error': '邮件不存在'}), 404

        email_info = db.get_email_by_id(mail_record['email_id'], None if current_user['is_admin'] else current_user['id'])
        if not email_info:
            return jsonify({'error': '无权限访问此邮件'}), 403

        remote_delete_warning = None
        # Outlook/Graph: 先尝试删除远端，再删除本地
        if email_info.get('mail_type') == 'outlook' and mail_record.get('graph_message_id'):
            access_token = OutlookMailHandler.get_new_access_token(email_info.get('refresh_token'), email_info.get('client_id'))
            if not access_token:
                return jsonify({'error': '获取Access Token失败'}), 500
            try:
                OutlookMailHandler.delete_message(access_token, mail_record['graph_message_id'])
            except requests.exceptions.HTTPError as http_err:
                status = getattr(http_err.response, 'status_code', None)
                # 常见场景：缺少 Mail.ReadWrite，远端无删除权限。此时允许仅删除本地记录。
                if status in (401, 403):
                    remote_delete_warning = '远端删除失败（权限不足），已仅删除本地记录。请给应用补充 Mail.ReadWrite 权限。'
                    logger.warning(f"远端删除邮件失败(HTTP {status})，降级为仅本地删除: mail_id={mail_id}")
                else:
                    raise

        if not db.delete_mail_record(mail_id):
            return jsonify({'error': '删除本地邮件记录失败'}), 500

        if remote_delete_warning:
            return jsonify({'success': True, 'message': remote_delete_warning, 'remote_deleted': False}), 200
        return jsonify({'success': True, 'message': '删除成功', 'remote_deleted': True}), 200
    except Exception as e:
        logger.error(f"删除邮件失败: {str(e)}")
        return jsonify({'error': f'服务端错误: {str(e)}'}), 500

@app.route('/api/mail_records/batch_delete', methods=['POST'])
@token_required
def batch_delete_mail_records(current_user):
    """批量删除邮件（Graph + 本地记录）"""
    try:
        data = request.json or {}
        mail_ids = data.get('mail_ids') or []
        if not isinstance(mail_ids, list) or not mail_ids:
            return jsonify({'error': 'mail_ids不能为空'}), 400

        # 去重且保证为int
        normalized_ids = []
        seen = set()
        for item in mail_ids:
            try:
                mid = int(item)
            except Exception:
                continue
            if mid > 0 and mid not in seen:
                seen.add(mid)
                normalized_ids.append(mid)

        if not normalized_ids:
            return jsonify({'error': 'mail_ids无有效ID'}), 400

        success_ids = []
        failed = []
        token_cache = {}

        for mail_id in normalized_ids:
            try:
                mail_record = db.get_mail_record_by_id(mail_id)
                if not mail_record:
                    failed.append({'id': mail_id, 'error': '邮件不存在'})
                    continue

                email_info = db.get_email_by_id(
                    mail_record['email_id'],
                    None if current_user['is_admin'] else current_user['id']
                )
                if not email_info:
                    failed.append({'id': mail_id, 'error': '无权限访问此邮件'})
                    continue

                if email_info.get('mail_type') == 'outlook' and mail_record.get('graph_message_id'):
                    email_id = int(email_info['id'])
                    access_token = token_cache.get(email_id)
                    if not access_token:
                        access_token = OutlookMailHandler.get_new_access_token(
                            email_info.get('refresh_token'),
                            email_info.get('client_id')
                        )
                        if not access_token:
                            failed.append({'id': mail_id, 'error': '获取Access Token失败'})
                            continue
                        token_cache[email_id] = access_token
                    try:
                        OutlookMailHandler.delete_message(access_token, mail_record['graph_message_id'])
                    except requests.exceptions.HTTPError as http_err:
                        status = getattr(http_err.response, 'status_code', None)
                        if status not in (401, 403):
                            raise

                if not db.delete_mail_record(mail_id):
                    failed.append({'id': mail_id, 'error': '删除本地邮件记录失败'})
                    continue

                success_ids.append(mail_id)
            except Exception as inner_e:
                failed.append({'id': mail_id, 'error': str(inner_e)})

        return jsonify({
            'success': True,
            'message': f'已删除 {len(success_ids)} 封邮件',
            'success_ids': success_ids,
            'failed': failed
        }), 200
    except Exception as e:
        logger.error(f"批量删除邮件失败: {str(e)}")
        return jsonify({'error': f'服务端错误: {str(e)}'}), 500

@app.route('/api/attachments/<int:attachment_id>/download', methods=['GET'])
@token_required
def download_attachment(current_user, attachment_id):
    """下载附件"""
    try:
        # 获取附件信息
        attachment = db.get_attachment(attachment_id)
        if not attachment:
            return jsonify({'error': '附件不存在'}), 404

        # 验证用户是否有权限下载该附件
        mail_id = attachment['mail_id']
        mail_record = db.get_mail_record_by_id(mail_id)
        if not mail_record:
            return jsonify({'error': '邮件不存在'}), 404

        email_id = mail_record['email_id']
        email_info = db.get_email_by_id(email_id, None if current_user['is_admin'] else current_user['id'])
        if not email_info:
            return jsonify({'error': '无权下载此附件'}), 403

        # 准备下载响应
        filename = attachment['filename']
        content_type = attachment['content_type']
        content = attachment['content']

        response = make_response(content)
        response.headers['Content-Type'] = content_type
        response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'

        return response
    except Exception as e:
        logger.error(f"下载附件失败: {str(e)}")
        return jsonify({'error': f'服务器错误: {str(e)}'}), 500

@app.route('/api/emails/<int:email_id>/upload_email_file', methods=['POST'])
@token_required
def upload_email_file(current_user, email_id):
    """上传邮件文件并解析"""
    try:
        # 验证用户是否有权限操作该邮箱
        email_info = db.get_email_by_id(email_id, None if current_user['is_admin'] else current_user['id'])
        if not email_info:
            return jsonify({'error': f'邮箱 ID {email_id} 不存在或您没有权限'}), 404

        # 检查是否有文件上传
        if 'file' not in request.files:
            return jsonify({'error': '没有上传文件'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': '没有选择文件'}), 400

        # 检查文件扩展名
        allowed_extensions = ['.eml', '.txt', '.msg', '.mbox', '.emlx']
        file_ext = os.path.splitext(file.filename)[1].lower()
        if file_ext not in allowed_extensions:
            return jsonify({'error': f'不支持的文件格式，仅支持 {", ".join(allowed_extensions)}'}), 400

        # 保存文件到临时目录
        temp_dir = os.path.join(os.getcwd(), 'temp')
        os.makedirs(temp_dir, exist_ok=True)
        temp_file_path = os.path.join(temp_dir, f"{int(time.time())}_{file.filename}")
        file.save(temp_file_path)

        try:
            # 导入邮件处理模块
            from utils.email import EmailFileParser

            # 解析邮件文件
            mail_record = EmailFileParser.parse_email_file(temp_file_path)

            if not mail_record:
                return jsonify({'error': '解析邮件文件失败'}), 400

            # 保存邮件记录到数据库
            success, mail_id = db.add_mail_record(
                email_id=email_id,
                subject=mail_record.get('subject', '(无主题)'),
                sender=mail_record.get('sender', '(未知发件人)'),
                content=mail_record.get('content', '(无内容)'),
                received_time=mail_record.get('received_time', datetime.now()),
                folder='IMPORTED',
                is_read=1,
                has_attachments=1 if mail_record.get('has_attachments', False) else 0
            )

            if success and mail_id and mail_record.get('has_attachments', False):
                # 保存附件
                attachments = mail_record.get('full_attachments', [])
                for attachment in attachments:
                    db.add_attachment(
                        mail_id=mail_id,
                        filename=attachment.get('filename', '未命名'),
                        content_type=attachment.get('content_type', 'application/octet-stream'),
                        size=attachment.get('size', 0),
                        content=attachment.get('content', b'')
                    )

            # 删除临时文件
            os.remove(temp_file_path)

            return jsonify({
                'success': True,
                'message': '邮件文件解析成功',
                'mail_id': mail_id
            })

        finally:
            # 确保临时文件被删除
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)

    except Exception as e:
        logger.error(f"上传邮件文件失败: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': f'服务器错误: {str(e)}'}), 500

@app.route('/api/emails/import', methods=['POST'])
@token_required
def import_emails(current_user):
    """批量导入邮箱"""
    data = request.json.get('data')
    mail_type = request.json.get('mail_type', 'outlook')

    if not data:
        return jsonify({'error': '导入数据不能为空'}), 400

    # 解析导入的数据
    lines = data.strip().split('\n')
    total = len(lines)
    success_count = 0
    failed_details = []

    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue

        try:
            parts = line.split('----')
            if mail_type == 'outlook':
                if len(parts) == 3:
                    email, client_id, refresh_token = parts
                    password = ''
                elif len(parts) == 4:
                    email, password, client_id, refresh_token = parts
                else:
                    failed_details.append({
                        'line': i + 1,
                        'content': line,
                        'reason': '格式错误，需要3个字段'
                    })
                    continue

                if not all([email, client_id, refresh_token]):
                    failed_details.append({
                        'line': i + 1,
                        'content': line,
                        'reason': '有空白字段'
                    })
                    continue

                success = db.add_email(current_user['id'], email, password, client_id, refresh_token, mail_type)
            else:
                if len(parts) != 2:
                    failed_details.append({
                        'line': i + 1,
                        'content': line,
                        'reason': '格式错误，需要2个字段'
                    })
                    continue

                email, password = parts
                if not all([email, password]):
                    failed_details.append({
                        'line': i + 1,
                        'content': line,
                        'reason': '有空白字段'
                    })
                    continue

                if mail_type == 'gmail':
                    server = 'imap.gmail.com'
                    port = 993
                elif mail_type == 'qq':
                    server = 'imap.qq.com'
                    port = 993
                elif mail_type == 'imap':
                    failed_details.append({
                        'line': i + 1,
                        'content': line,
                        'reason': 'IMAP类型请使用单个添加并填写服务器参数'
                    })
                    continue
                else:
                    failed_details.append({
                        'line': i + 1,
                        'content': line,
                        'reason': f'不支持的邮箱类型: {mail_type}'
                    })
                    continue

                success = db.add_email(
                    current_user['id'],
                    email,
                    password,
                    mail_type=mail_type,
                    server=server,
                    port=port,
                    use_ssl=True
                )

            if success:
                success_count += 1
            else:
                failed_details.append({
                    'line': i + 1,
                    'content': line,
                    'reason': '邮箱地址已存在'
                })
        except Exception as e:
            logger.error(f"导入邮箱出错: {str(e)}")
            failed_details.append({
                'line': i + 1,
                'content': line,
                'reason': f'导入异常: {str(e)}'
            })

    # 返回导入结果
    return jsonify({
        'total': total,
        'success': success_count,
        'failed': len(failed_details),
        'failed_details': failed_details
    })

@app.route('/api/emails/<int:email_id>/recheck_all', methods=['POST'])
@token_required
def recheck_email_all(current_user, email_id):
    """清空检查时间并重新全量拉取"""
    try:
        email_info = db.get_email_by_id(email_id)
        if not email_info:
            return jsonify({'error': '邮箱不存在'}), 404

        if email_info['user_id'] != current_user['id'] and not current_user['is_admin']:
            return jsonify({'error': '无权操作此邮箱'}), 403

        db.reset_check_time(email_id)
        email_processor.check_emails([email_id])

        return jsonify({'success': True, 'message': '已触发重新全量拉取'}), 200
    except Exception as e:
        logger.error(f"重新全量拉取失败: {str(e)}")
        return jsonify({'error': f'服务端错误: {str(e)}'}), 500

@app.route('/api/oauth/outlook/device_code', methods=['POST'])
@token_required
def outlook_device_code(current_user):
    """获取Outlook设备码（MSAL flow_id 模式）"""
    data = request.json or {}
    client_id = data.get('client_id')
    if not client_id:
        return jsonify({'error': 'client_id required'}), 400

    try:
        _purge_expired_outlook_device_flows()

        token_cache = msal.SerializableTokenCache()
        msal_app = msal.PublicClientApplication(
            client_id=client_id,
            authority=OUTLOOK_DEVICE_AUTHORITY,
            token_cache=token_cache
        )
        flow = msal_app.initiate_device_flow(scopes=OUTLOOK_DEVICE_SCOPES)
        if 'user_code' not in flow:
            logger.error(f"MSAL initiate_device_flow failed: {flow}")
            return jsonify({'error': flow.get('error_description') or flow.get('error') or 'initiate_device_flow failed'}), 400

        flow_id = str(uuid.uuid4())
        created_at = time.time()
        expires_in = int(flow.get('expires_in') or 900)
        expires_at = float(flow.get('expires_at') or (created_at + expires_in))

        with _OUTLOOK_DEVICE_FLOW_LOCK:
            _OUTLOOK_DEVICE_FLOWS[flow_id] = {
                'flow': flow,
                'cache': token_cache,
                'user_id': int(current_user['id']),
                'client_id': client_id,
                'created_at': created_at,
                'expires_at': expires_at,
            }

        return jsonify({
            'flow_id': flow_id,
            'user_code': flow.get('user_code'),
            'verification_uri': flow.get('verification_uri'),
            'verification_uri_complete': flow.get('verification_uri_complete'),
            'expires_in': expires_in,
            'interval': int(flow.get('interval') or 5),
            'message': flow.get('message'),
        }), 200
    except Exception as e:
        logger.error(f"获取设备码失败: {str(e)}")
        return jsonify({'error': f'服务端错误: {str(e)}'}), 500

@app.route('/api/oauth/outlook/device_token', methods=['POST'])
@token_required
def outlook_device_token(current_user):
    """使用设备码换取Token（优先 flow_id，其次兼容 device_code）"""
    data = request.json or {}
    client_id = data.get('client_id')
    device_code = data.get('device_code')
    flow_id = data.get('flow_id')

    try:
        _purge_expired_outlook_device_flows()

        if flow_id:
            with _OUTLOOK_DEVICE_FLOW_LOCK:
                flow_item = _OUTLOOK_DEVICE_FLOWS.get(flow_id)

            if not flow_item:
                return jsonify({'error': 'expired_token', 'error_description': 'Flow not found or expired'}), 400

            if int(flow_item.get('user_id')) != int(current_user['id']):
                return jsonify({'error': 'forbidden', 'error_description': 'Flow does not belong to current user'}), 403

            flow = flow_item['flow']
            if float(flow_item.get('expires_at') or 0) < time.time():
                with _OUTLOOK_DEVICE_FLOW_LOCK:
                    _OUTLOOK_DEVICE_FLOWS.pop(flow_id, None)
                return jsonify({'error': 'expired_token', 'error_description': 'Device flow expired'}), 400

            msal_app = msal.PublicClientApplication(
                client_id=flow_item['client_id'],
                authority=OUTLOOK_DEVICE_AUTHORITY,
                token_cache=flow_item['cache']
            )
            # 非阻塞单次轮询，和前端轮询配合
            result = msal_app.acquire_token_by_device_flow(
                flow,
                exit_condition=lambda _flow: True
            )

            if 'access_token' in result:
                with _OUTLOOK_DEVICE_FLOW_LOCK:
                    _OUTLOOK_DEVICE_FLOWS.pop(flow_id, None)
                return jsonify(result), 200

            error_code = result.get('error')
            if error_code in ('expired_token', 'authorization_declined', 'bad_verification_code'):
                with _OUTLOOK_DEVICE_FLOW_LOCK:
                    _OUTLOOK_DEVICE_FLOWS.pop(flow_id, None)
            return jsonify(result), 400

        # 兼容旧版本：没有 flow_id 时，退回直接 device_code 换 token
        if not client_id or not device_code:
            return jsonify({'error': 'flow_id required (or client_id + device_code for legacy mode)'}), 400

        url = 'https://login.microsoftonline.com/common/oauth2/v2.0/token'
        payload = {
            'client_id': client_id,
            'device_code': device_code,
            'grant_type': 'urn:ietf:params:oauth:grant-type:device_code'
        }
        response = requests.post(url, data=payload, timeout=30)
        return jsonify(response.json()), response.status_code
    except Exception as e:
        logger.error(f"获取Token失败: {str(e)}")
        return jsonify({'error': f'服务端错误: {str(e)}'}), 500

# 系统配置管理
@app.route('/api/admin/config/registration', methods=['POST'])
@token_required
@admin_required
def toggle_registration(current_user):
    """管理员开启/关闭注册功能"""
    data = request.json
    allow = data.get('allow', False)

    if db.toggle_registration(allow):
        action = "开启" if allow else "关闭"
        logger.info(f"管理员 {current_user['username']} 已{action}注册功能")
        return jsonify({'message': f'已成功{action}注册功能', 'allow_register': allow})
    else:
        return jsonify({'error': '更新注册配置失败'}), 500

# 前端静态文件服务
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_frontend(path):
    """提供前端静态文件"""
    # 确定前端构建目录的路径
    frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'frontend', 'dist')

    # 如果路径为空或者是根路径，则返回 index.html
    if not path or path == '/':
        return send_from_directory(frontend_dir, 'index.html')

    # 检查请求的文件是否存在
    file_path = os.path.join(frontend_dir, path)
    if os.path.isfile(file_path):
        return send_from_directory(frontend_dir, path)
    else:
        # 如果文件不存在，返回 index.html 让前端路由处理
        return send_from_directory(frontend_dir, 'index.html')

@app.route('/api/emails/<int:email_id>/password', methods=['GET'])
@token_required
def get_email_password(current_user, email_id):
    """获取指定邮箱的密码"""
    try:
        email = db.get_email_by_id(email_id)
        if not email:
            return jsonify({'error': '邮箱不存在'}), 404

        # 验证是否为当前用户的邮箱或管理员
        if email['user_id'] != current_user['id'] and not current_user['is_admin']:
            return jsonify({'error': '无权访问此邮箱'}), 403

        return jsonify({'password': email['password']})
    except Exception as e:
        logger.error(f"获取邮箱密码失败: {str(e)}")
        return jsonify({'error': f'服务器错误: {str(e)}'}), 500

@app.route('/api/search', methods=['POST'])
@token_required
def search_emails(current_user):
    """搜索邮件内容"""
    try:
        data = request.json
        if not data:
            return jsonify({'error': '无效的请求数据格式'}), 400

        query = data.get('query', '').strip()
        search_in = data.get('search_in', [])  # 可以包含 'subject', 'sender', 'recipient', 'content'

        if not query:
            return jsonify({'error': '搜索关键词不能为空'}), 400

        if not search_in:
            search_in = ['subject', 'sender', 'recipient', 'content']  # 默认搜索所有字段

        logger.info(f"用户 {current_user['username']} 执行搜索: {query}, 搜索范围: {search_in}")

        # 获取用户的所有邮箱
        user_emails = db.get_emails_by_user_id(current_user['id'])
        user_email_ids = [email['id'] for email in user_emails]

        # 根据搜索条件查询邮件
        results = db.search_mail_records(
            user_email_ids,
            query,
            search_in_subject='subject' in search_in,
            search_in_sender='sender' in search_in,
            search_in_recipient='recipient' in search_in,
            search_in_content='content' in search_in
        )

        # 增加邮箱信息到结果中
        emails_map = {email['id']: email for email in user_emails}
        for record in results:
            email_id = record.get('email_id')
            if email_id in emails_map:
                record['email_address'] = emails_map[email_id]['email']

        return jsonify({'results': results})
    except Exception as e:
        logger.error(f"搜索邮件失败: {str(e)}")
        return jsonify({'error': f'服务器错误: {str(e)}'}), 500

@app.route('/api/emails/<int:email_id>', methods=['PUT'])
@token_required
def update_email(current_user, email_id):
    """更新邮箱信息"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': '无效的请求数据'}), 400

        # 获取当前邮箱信息，用于保留不允许修改的字段
        current_email = db.get_email_by_id(email_id, current_user['id'])
        if not current_email:
            return jsonify({'error': '邮箱不存在或您没有权限修改'}), 404

        # 验证邮箱信息
        required_fields = ['email', 'password']
        for field in required_fields:
            if field not in data and field != 'password':  # 密码可以不修改
                return jsonify({'error': f'缺少必要字段: {field}'}), 400

        # 准备更新数据，保持邮箱类型不变
        update_data = {
            'email': data.get('email'),
            'mail_type': current_email['mail_type']  # 使用已有数据，不允许修改
        }

        # 仅当提供了非空密码时才更新密码
        if data.get('password') and data.get('password') != '******':
            update_data['password'] = data.get('password')

        # 根据不同邮箱类型更新特定字段
        if current_email['mail_type'] == 'outlook':
            if data.get('client_id'):
                update_data['client_id'] = data.get('client_id')
            if data.get('refresh_token'):
                update_data['refresh_token'] = data.get('refresh_token')
        elif current_email['mail_type'] in ['imap', 'gmail', 'qq']:
            if data.get('server'):
                update_data['server'] = data.get('server')
            if data.get('port') is not None:
                update_data['port'] = data.get('port')
            if data.get('use_ssl') is not None:
                update_data['use_ssl'] = data.get('use_ssl')

        # 更新邮箱信息
        success = db.update_email(
            email_id,
            user_id=current_user['id'],
            **update_data
        )

        if not success:
            return jsonify({'error': '更新邮箱信息失败'}), 500

        logger.info(f"用户 {current_user['username']} 更新了邮箱 ID: {email_id}")

        return jsonify({
            'message': '邮箱信息更新成功',
            'data': {
                'email_id': email_id,
                'email': update_data['email'],
                'mail_type': update_data['mail_type']
            }
        }), 200

    except Exception as e:
        logger.error(f"更新邮箱信息失败: {str(e)}")
        return jsonify({'error': '更新邮箱信息失败'}), 500

@app.route('/api/email/start_real_time_check', methods=['POST'])
@token_required
def start_real_time_check():
    """启动实时邮件检查"""
    try:
        check_interval = request.json.get('check_interval', 300)
        if check_interval < 30:  # 最小检查间隔为30秒
            check_interval = 30

        success = email_processor.start_real_time_check(check_interval)
        if success:
            return jsonify({
                'success': True,
                'message': f'实时邮件检查已启动，检查间隔: {check_interval}秒'
            })
        else:
            return jsonify({
                'success': False,
                'message': '实时邮件检查已在运行中'
            })
    except Exception as e:
        logger.error(f"启动实时邮件检查失败: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'启动实时邮件检查失败: {str(e)}'
        })

@app.route('/api/email/stop_real_time_check', methods=['POST'])
@token_required
def stop_real_time_check():
    """停止实时邮件检查"""
    try:
        success = email_processor.stop_real_time_check()
        if success:
            return jsonify({
                'success': True,
                'message': '实时邮件检查已停止'
            })
        else:
            return jsonify({
                'success': False,
                'message': '实时邮件检查未在运行'
            })
    except Exception as e:
        logger.error(f"停止实时邮件检查失败: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'停止实时邮件检查失败: {str(e)}'
        })

@app.route('/api/email/add_to_real_time_queue', methods=['POST'])
@token_required
def add_to_real_time_queue():
    """将邮箱添加到实时检查队列"""
    try:
        email_id = request.json.get('email_id')
        if not email_id:
            return jsonify({
                'success': False,
                'message': '缺少邮箱ID'
            })

        email_processor.add_to_real_time_queue(email_id)
        return jsonify({
            'success': True,
            'message': f'邮箱ID: {email_id} 已添加到实时检查队列'
        })
    except Exception as e:
        logger.error(f"添加邮箱到实时检查队列失败: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'添加邮箱到实时检查队列失败: {str(e)}'
        })

@app.route('/api/emails/<int:email_id>/realtime', methods=['POST'])
@token_required
def toggle_email_realtime_check(current_user, email_id):
    """开启/关闭指定邮箱的实时检查"""
    try:
        data = request.json
        enable = data.get('enable', False)

        # 获取当前邮箱信息
        email_info = db.get_email_by_id(email_id, current_user['id'])
        if not email_info:
            return jsonify({'error': '邮箱不存在或您没有权限'}), 404

        # 更新实时检查状态
        success = db.set_email_realtime_check(email_id, enable)
        if not success:
            return jsonify({'error': '更新实时检查状态失败'}), 500

        action = "开启" if enable else "关闭"
        logger.info(f"用户 {current_user['username']} {action}了邮箱 {email_info['email']} 的实时检查")

        return jsonify({
            'success': True,
            'message': f'已{action}邮箱的实时检查',
            'data': {
                'email_id': email_id,
                'email': email_info['email'],
                'enable_realtime_check': enable
            }
        })
    except Exception as e:
        logger.error(f"切换邮箱实时检查状态失败: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'切换邮箱实时检查状态失败: {str(e)}'
        }), 500

def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='学在华邮件助手')
    parser.add_argument('--host', default='0.0.0.0', help='主机地址')
    parser.add_argument('--port', type=int, default=5000, help='HTTP端口')
    parser.add_argument('--ws-port', type=int, default=8765, help='WebSocket端口')
    parser.add_argument('--debug', action='store_true', help='启用调试模式')
    return parser.parse_args()

def start_websocket_server():
    """启动WebSocket服务器"""
    try:
        logger.info("启动WebSocket服务器")
        ws_handler.run()
    except Exception as e:
        logger.error(f"WebSocket服务器异常: {e}")
        sys.exit(1)

if __name__ == '__main__':
    try:
        args = parse_args()

        # 设置WebSocket端口
        ws_handler.port = args.ws_port

        # 启动WebSocket服务器
        ws_thread = threading.Thread(target=start_websocket_server)
        ws_thread.daemon = True
        ws_thread.start()

        # 启动实时邮件检查
        email_processor.start_real_time_check(check_interval=300)
        logger.info("实时邮件检查已启动")

        # 启动Flask应用
        logger.info(f"学在华邮件助手启动于 http://{args.host}:{args.port}")
        app.run(host=args.host, port=args.port, debug=args.debug)
    except KeyboardInterrupt:
        logger.info("程序被用户中断，正在关闭...")
    except Exception as e:
        logger.error(f"程序启动异常: {e}")
    finally:
        # 清理资源
        if db:
            db.close()
        logger.info("程序已关闭")


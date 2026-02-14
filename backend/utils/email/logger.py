"""
邮件处理模块日志配置。
- 日志目录：backend/logs
- 单个日志文件超过 1MB 自动轮转
- 最多保留 3 个备份文件
"""

import logging
from logging.handlers import RotatingFileHandler
import sys
import os
import time
from datetime import datetime

# 日志级别
DEBUG = logging.DEBUG
INFO = logging.INFO
WARNING = logging.WARNING
ERROR = logging.ERROR
CRITICAL = logging.CRITICAL


def ensure_log_dir():
    """确保日志目录存在。"""
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    log_dir = os.path.join(project_root, 'logs')
    os.makedirs(log_dir, exist_ok=True)
    return log_dir


def configure_logger():
    """配置邮件处理模块日志。"""
    log_dir = ensure_log_dir()
    logger = logging.getLogger('email_utils')

    # 避免重复添加 handler
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    current_date = datetime.now().strftime('%Y%m%d')

    main_log_file = os.path.join(log_dir, f'email_assistant_{current_date}.log')
    file_handler = RotatingFileHandler(
        main_log_file,
        maxBytes=1 * 1024 * 1024,
        backupCount=3,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.INFO)

    error_log_file = os.path.join(log_dir, f'email_assistant_error_{current_date}.log')
    error_handler = RotatingFileHandler(
        error_log_file,
        maxBytes=1 * 1024 * 1024,
        backupCount=3,
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)

    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')

    console_handler = logging.StreamHandler(stream=sys.stdout)
    console_handler.setLevel(logging.INFO)

    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    detail_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - [%(threadName)s] - %(message)s')

    file_handler.setFormatter(detail_formatter)
    error_handler.setFormatter(detail_formatter)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(error_handler)
    logger.addHandler(console_handler)
    logger.propagate = False

    return logger


logger = configure_logger()


def log_email_start(email_address, email_id):
    """记录开始处理邮箱。"""
    logger.info(f'===== 开始处理邮箱 {email_address} (ID:{email_id}) =====')


def log_email_complete(email_address, email_id, total_emails, processed, saved):
    """记录邮箱处理完成。"""
    logger.info(f'===== 邮箱处理完成: {email_address} (ID:{email_id}) =====')
    logger.info(f'总邮件数: {total_emails}, 成功处理: {processed}, 新增: {saved}')


def log_email_error(email_address, email_id, error):
    """记录邮箱处理错误。"""
    logger.error(f'===== 邮箱处理错误: {email_address} (ID:{email_id}) =====')
    logger.error(f'错误详情: {str(error)}')


def log_message_processing(message_id, index, total, subject):
    """记录单封邮件处理过程。"""
    logger.debug(f'处理邮件 {index}/{total} (ID:{message_id}) - 主题: {subject[:50]}')


def log_message_error(message_id, error):
    """记录单封邮件处理错误。"""
    logger.error(f'处理邮件 (ID:{message_id}) 失败: {str(error)}')


def log_progress(email_id, progress, message):
    """记录关键进度信息。"""
    if progress in [0, 25, 50, 75, 100]:
        logger.info(f'邮箱 (ID:{email_id}) 进度: {progress}% - {message}')


def timing_decorator(func):
    """用于测量函数执行时间。"""

    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        execution_time = end_time - start_time
        logger.debug(f'函数 {func.__name__} 执行时间: {execution_time:.2f}秒')
        return result

    return wrapper

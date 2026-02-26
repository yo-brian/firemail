# -*- coding: utf-8 -*-
# Email mail processor

from datetime import datetime
from email.message import Message
from typing import Dict, List, Optional, Callable, Any, Tuple, Union
import threading
import logging
import time
import traceback
import concurrent.futures
import queue

from .common import (
    decode_mime_words,
    strip_html,
    safe_decode,
    remove_extra_blank_lines,
    parse_email_date,
    decode_email_content,
    parse_email_message,
    extract_email_content,
    normalize_check_time
)
from .logger import (
    logger,
    log_email_start,
    log_email_complete,
    log_email_error,
    log_message_processing,
    log_message_error,
    log_progress,
    timing_decorator
)
from .outlook import OutlookMailHandler
from .imap import IMAPMailHandler
from .gmail import GmailHandler
from .qq import QQMailHandler
from ._real_time_check import RealTimeChecker

class MailProcessor:

    @staticmethod
    @timing_decorator
    def parse_email_message(msg: Dict, folder: str = "INBOX") -> Dict:
        try:
            # 濡傛灉msg宸茬粡鏄瓧鍏哥被鍨嬶紝鐩存帴杩斿洖
            if isinstance(msg, dict):
                return msg

            # 鍚﹀垯浣跨敤common妯″潡鐨刾arse_email_message澶勭悊Message瀵硅薄
            return parse_email_message(msg, folder)
        except Exception as e:
            logger.error(f"瑙ｆ瀽閭欢娑堟伅澶辫触: {str(e)}")
            traceback.print_exc()
            return None

    @staticmethod
    def _extract_email_content(msg: Message) -> str:
        return extract_email_content(msg)

    @staticmethod
    @timing_decorator
    def save_mail_records(db, email_id: int, mail_records: List[Dict], progress_callback: Optional[Callable] = None) -> int:
        saved_count = 0
        total = len(mail_records)

        logger.info(f"开始保存 {total} 封邮件记录，邮箱ID: {email_id}")

        if not progress_callback:
            progress_callback = lambda progress, message: None

        def _store_attachments(mail_id: int, attachments: List[Dict]):
            for attachment in attachments or []:
                try:
                    filename = attachment.get("filename", "")
                    content_type = attachment.get("content_type", "")
                    size = attachment.get("size", 0)
                    content = attachment.get("content", b"")
                    if not filename or not content:
                        continue
                    db.add_attachment(
                        mail_id=mail_id,
                        filename=filename,
                        content_type=content_type,
                        size=size,
                        content=content,
                    )
                except Exception as att_error:
                    logger.error(f"保存附件失败: {str(att_error)}")

        for i, record in enumerate(mail_records):
            try:
                progress = int((i + 1) / total * 100) if total else 100
                progress_message = f"正在处理邮件 ({i + 1}/{total})"
                progress_callback(progress, progress_message)

                if i % 10 == 0 or i == total - 1:
                    log_progress(email_id, progress, progress_message)

                subject = record.get("subject", "(无主题)")
                sender = record.get("sender", "(未知发件人)")
                has_attachments = bool(record.get("has_attachments", False))
                incoming_attachments = record.get("full_attachments", []) if has_attachments else []

                graph_message_id = (record.get("graph_message_id") or "").strip()
                received_time = record.get("received_time", datetime.now())

                existing = None
                # Prefer Graph message id for dedup; this avoids dropping multiple
                # same-subject mails from the same sender on the same day.
                if graph_message_id:
                    try:
                        existing = db.conn.execute(
                            "SELECT * FROM mail_records WHERE email_id = ? AND graph_message_id = ?",
                            (email_id, graph_message_id)
                        ).fetchone()
                    except Exception as query_error:
                        logger.error(f"按graph_message_id查重失败: {str(query_error)}")

                if not existing:
                    existing = db.conn.execute(
                        "SELECT * FROM mail_records WHERE email_id = ? AND subject = ? AND sender = ? AND received_time = ?",
                        (
                            email_id,
                            subject,
                            sender,
                            db._normalize_to_utc_timestamp(received_time)
                        )
                    ).fetchone()

                if not existing:
                    success, mail_id = db.add_mail_record(
                        email_id=email_id,
                        subject=subject,
                        sender=sender,
                        recipient=record.get("recipient"),
                        content=record.get("content", "(无内容)"),
                        received_time=received_time,
                        folder=record.get("folder", "INBOX"),
                        is_read=1 if record.get("is_read", True) else 0,
                        graph_message_id=graph_message_id,
                        has_attachments=1 if has_attachments else 0,
                    )

                    if success and mail_id:
                        if incoming_attachments:
                            _store_attachments(mail_id, incoming_attachments)
                        saved_count += 1
                    else:
                        logger.warning(f"保存邮件记录失败: {subject[:30]}...")
                else:
                    # 已存在记录但无本地附件时，回填一次附件
                    try:
                        existing_id = existing["id"]
                        if incoming_attachments:
                            existing_atts = db.get_attachments(existing_id) or []
                            if not existing_atts:
                                logger.info(
                                    f"检测到历史邮件缺少附件，开始回填: mail_id={existing_id}, count={len(incoming_attachments)}"
                                )
                                _store_attachments(existing_id, incoming_attachments)
                    except Exception as backfill_error:
                        logger.error(f"附件回填失败: {str(backfill_error)}")

            except Exception as e:
                logger.error(f"保存邮件记录失败: {str(e)}")
                traceback.print_exc()
                continue

        logger.info(f"邮件保存完成: 共 {total} 封, 新增 {saved_count} 封")
        return saved_count

    @staticmethod
    def update_check_time(db, email_id: int) -> bool:
        try:
            logger.info(f"更新邮箱 ID:{email_id} 的检查时间")
            db.update_check_time(email_id)
            return True
        except Exception as e:
            logger.error(f"更新检查时间失败: {str(e)}")
            return False

class EmailBatchProcessor:

    def __init__(self, db, max_workers=5):
        self.db = db
        self.processing_emails = {}
        self.lock = threading.Lock()
        # 鍒涘缓涓や釜鐙珛鐨勭嚎绋嬫睜
        self.manual_thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        self.realtime_thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        self.real_time_running = False
        self.real_time_thread = None

        # 鍒涘缓瀹炴椂妫€鏌ュ櫒
        self.real_time_checker = RealTimeChecker(db, self)

        # 閭绫诲瀷澶勭悊鍣ㄦ槧灏?
        self.handlers = {
            'outlook': OutlookMailHandler,
            'imap': IMAPMailHandler,
            'gmail': GmailHandler,
            'qq': QQMailHandler
        }

    def __del__(self):
        self.stop_real_time_check()
        self.manual_thread_pool.shutdown(wait=True)
        self.realtime_thread_pool.shutdown(wait=True)

    def is_email_being_processed(self, email_id: int) -> bool:
        with self.lock:
            return email_id in self.processing_emails

    def stop_processing(self, email_id: int) -> bool:
        with self.lock:
            if email_id in self.processing_emails:
                self.processing_emails[email_id] = False
                return True
            return False

    def parse_email_message(self, msg: Dict, folder: str = "INBOX") -> Dict:
        return MailProcessor.parse_email_message(msg, folder)

    def update_check_time(self, db, email_id: int) -> bool:
        return MailProcessor.update_check_time(db, email_id)

    def save_mail_records(self, db, email_id: int, mail_records: List[Dict], progress_callback: Optional[Callable] = None) -> int:
        return MailProcessor.save_mail_records(db, email_id, mail_records, progress_callback)

    def check_emails(self, email_ids: List[int], progress_callback: Optional[Callable] = None, is_realtime: bool = False) -> bool:
        if not email_ids:
            logger.warning("娌℃湁鎻愪緵閭ID")
            return False

        # 鑾峰彇閭淇℃伅
        emails = self.db.get_emails_by_ids(email_ids)
        if not emails:
            logger.warning("鏈壘鍒版寚瀹氱殑閭")
            return False

        # 鍒涘缓杩涘害鍥炶皟
        def create_email_progress_callback(email_id):
            def callback(progress, message):
                if progress_callback:
                    progress_callback(email_id, progress, message)
            return callback

        # 閫夋嫨瀵瑰簲鐨勭嚎绋嬫睜
        thread_pool = self.realtime_thread_pool if is_realtime else self.manual_thread_pool

        # 鎻愪氦浠诲姟鍒扮嚎绋嬫睜
        futures = []
        for email_info in emails:
            if self.is_email_being_processed(email_info['id']):
                logger.warning(f"閭 {email_info['email']} 姝ｅ湪澶勭悊涓紝璺宠繃")
                continue

            # 鑾峰彇瀵瑰簲鐨勫鐞嗗櫒
            mail_type = email_info.get('mail_type', 'outlook')
            handler = self.handlers.get(mail_type)

            if not handler:
                logger.error(f"涓嶆敮鎸佺殑閭绫诲瀷: {mail_type}")
                continue

            # 鏍囪涓烘鍦ㄥ鐞?
            with self.lock:
                self.processing_emails[email_info['id']] = True

            # 鎻愪氦浠诲姟鍒扮嚎绋嬫睜
            future = thread_pool.submit(
                self._check_email_task,
                email_info,
                create_email_progress_callback(email_info['id'])
            )
            futures.append(future)

        # 鍚姩鐩戞帶绾跨▼锛屽鐞嗗畬鎴愮殑浠诲姟
        threading.Thread(target=self._monitor_futures, args=(futures,), daemon=True).start()

        return True

    def _monitor_futures(self, futures):
        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result()
                logger.info(f"浠诲姟瀹屾垚: {result}")
            except Exception as e:
                logger.error(f"浠诲姟鎵ц澶辫触: {str(e)}")

    def _check_email_task(self, email_info, callback=None):
        email_id = email_info['id']
        try:
            # 鏍囪涓烘鍦ㄥ鐞?
            with self.lock:
                self.processing_emails[email_id] = True

            # 鑾峰彇涓婃妫€鏌ユ椂闂达紝鐢ㄤ簬浠呰幏鍙栨柊閭欢
            last_check_time = email_info.get('last_check_time')

            # 鏍囧噯鍖栧鐞唋ast_check_time
            last_check_time = normalize_check_time(last_check_time)

            mail_type = email_info.get('mail_type', '')

            if mail_type == 'outlook':
                # 澶勭悊Outlook閭
                refresh_token = email_info.get('refresh_token')
                client_id = email_info.get('client_id')

                if not refresh_token or not client_id:
                    error_msg = "缂哄皯OAuth2.0璁よ瘉淇℃伅"
                    if callback:
                        callback(0, error_msg)
                    return {'success': False, 'message': error_msg}

                # 鑾峰彇鏂扮殑璁块棶浠ょ墝
                try:
                    access_token = OutlookMailHandler.get_new_access_token(refresh_token, client_id)
                    if not access_token:
                        error_msg = "鑾峰彇璁块棶浠ょ墝澶辫触"
                        if callback:
                            callback(0, error_msg)
                        return {'success': False, 'message': error_msg}

                    # 鏇存柊閭鐨勮闂护鐗?
                    self.db.update_email_token(email_id, access_token)
                    email_info['access_token'] = access_token

                    # 璁板綍寮€濮嬪鐞?
                    log_email_start(email_info['email'], email_id)

                    # 浣跨敤 Microsoft Graph 鎷夊彇閭欢
                    try:
                        mail_records = OutlookMailHandler.fetch_emails_graph(
                            email_info['email'],
                            access_token,
                            callback=callback,
                            last_check_time=last_check_time
                        )
                    except Exception as e:
                        error_msg = f"Graph 鎷夊彇澶辫触: {str(e)}"
                        if hasattr(e, "response") and e.response is not None:
                            if e.response.status_code in (401, 403):
                                error_msg = "Graph 授权失败，请重新获取 Refresh Token（权限需包含 offline_access + Mail.Read）"
                        log_email_error(email_info['email'], email_id, error_msg)
                        if callback:
                            callback(0, error_msg)
                        return {'success': False, 'message': error_msg}

                    if not mail_records:
                        if callback:
                            callback(100, "没有找到新邮件")

                        # 娌℃湁鎵惧埌鏂伴偖浠朵篃绠楁垚鍔燂紝鏇存柊妫€鏌ユ椂闂?
                        self.update_check_time(self.db, email_id)

                        return {'success': True, 'message': '没有找到新邮件'}

                    # 淇濆瓨閭欢璁板綍锛屼紶閫掗偖浠堕敭鍒楄〃鐢ㄤ簬楂樻晥鍘婚噸
                    mail_keys = [record.get('mail_key', '') for record in mail_records if 'mail_key' in record]
                    saved_count = self.save_mail_records(self.db, email_id, mail_records, callback)

                    # 鏇存柊鏈€鍚庢鏌ユ椂闂?
                    self.update_check_time(self.db, email_id)

                    # 璁板綍瀹屾垚
                    log_email_complete(email_info['email'], email_id, len(mail_records), len(mail_records), saved_count)

                    return {
                        'success': True,
                        'message': f'成功获取{len(mail_records)}封邮件，新增{saved_count}封'
                    }

                except Exception as e:
                    error_msg = f"澶勭悊Outlook閭澶辫触: {str(e)}"
                    log_email_error(email_info['email'], email_id, error_msg)
                    if callback:
                        callback(0, error_msg)
                    return {'success': False, 'message': error_msg}

            elif mail_type == 'gmail':
                # 澶勭悊Gmail閭
                result = GmailHandler.check_mail(email_info, self.db, callback)
                # 鍙湁鍦ㄦ垚鍔熸椂鏇存柊妫€鏌ユ椂闂?
                if result.get('success', False):
                    self.update_check_time(self.db, email_id)
                return result

            elif mail_type == 'qq':
                # 澶勭悊QQ閭
                result = QQMailHandler.check_mail(email_info, self.db, callback)
                # 鍙湁鍦ㄦ垚鍔熸椂鏇存柊妫€鏌ユ椂闂?
                if result.get('success', False):
                    self.update_check_time(self.db, email_id)
                return result

            else:
                # 澶勭悊IMAP閭
                try:
                    # 璁板綍寮€濮嬪鐞?
                    log_email_start(email_info['email'], email_id)

                    # 鑾峰彇閭欢锛屽鍔爈ast_check_time鍙傛暟
                    mail_records = IMAPMailHandler.fetch_emails(
                        email_info['email'],
                        email_info['password'],
                        server=email_info.get('server'),
                        port=email_info.get('port'),
                        use_ssl=email_info.get('use_ssl', True),
                        callback=callback,
                        last_check_time=last_check_time
                    )

                    if not mail_records:
                        if callback:
                            callback(100, "没有找到新邮件")

                        # 娌℃湁鎵惧埌鏂伴偖浠朵篃绠楁垚鍔燂紝鏇存柊妫€鏌ユ椂闂?
                        self.update_check_time(self.db, email_id)

                        return {'success': True, 'message': '没有找到新邮件'}

                    # 淇濆瓨閭欢璁板綍
                    saved_count = self.save_mail_records(self.db, email_id, mail_records, callback)

                    # 鏇存柊鏈€鍚庢鏌ユ椂闂?
                    self.update_check_time(self.db, email_id)

                    # 璁板綍瀹屾垚
                    log_email_complete(email_info['email'], email_id, len(mail_records), len(mail_records), saved_count)

                    return {
                        'success': True,
                        'message': f'成功获取 {len(mail_records)} 封邮件，新增 {saved_count} 封'
                    }

                except Exception as e:
                    error_msg = f"澶勭悊IMAP閭澶辫触: {str(e)}"
                    log_email_error(email_info['email'], email_id, error_msg)
                    if callback:
                        callback(0, error_msg)
                    return {'success': False, 'message': error_msg}

        except Exception as e:
            error_msg = f"澶勭悊閭澶辫触: {str(e)}"
            log_email_error(email_info['email'], email_id, error_msg)
            if callback:
                callback(0, error_msg)
            return {'success': False, 'message': error_msg}

        finally:
            # 标记处理完成并释放资源
            try:
                with self.lock:
                    if email_id in self.processing_emails:
                        del self.processing_emails[email_id]
                        logger.info(f"邮箱 ID {email_id} 处理完成，已从处理队列中移除")
            except Exception as e:
                logger.error(f"释放邮箱处理资源失败: {str(e)}")

    def start_real_time_check(self, check_interval=60):
        return self.real_time_checker.start(check_interval)

    def stop_real_time_check(self):
        return self.real_time_checker.stop()

    # 灏嗘棫鐨刜real_time_check_loop鏂规硶淇濈暀浣嗘爣璁颁负宸插純鐢?
    def _real_time_check_loop(self, check_interval):
        logger.warning("浣跨敤宸插純鐢ㄧ殑_real_time_check_loop鏂规硶锛屽缓璁娇鐢≧ealTimeChecker")
        batch_size = 10  # 姣忔壒澶勭悊鐨勯偖绠辨暟閲?
        while self.real_time_running:
            try:
                # 鑾峰彇鎵€鏈夋椿璺冮偖绠盜D
                all_email_ids = self.db.get_all_email_ids()
                if not all_email_ids:
                    logger.info("娌℃湁闇€瑕佹鏌ョ殑閭")
                    time.sleep(check_interval)
                    continue

                # 灏嗛偖绠盜D鍒楄〃鍒嗘垚澶氫釜鎵规
                for i in range(0, len(all_email_ids), batch_size):
                    if not self.real_time_running:
                        break

                    batch_ids = all_email_ids[i:i + batch_size]
                    logger.info(f"开始处理第 {i // batch_size + 1} 批邮箱，共 {len(batch_ids)} 个")

                    # 妫€鏌ュ綋鍓嶆壒娆＄殑閭锛屼娇鐢ㄥ疄鏃剁嚎绋嬫睜
                    self.check_emails(batch_ids, is_realtime=True)

                    # 姣忔壒澶勭悊瀹屽悗绛夊緟涓€娈垫椂闂达紝閬垮厤鏈嶅姟鍣ㄥ帇鍔涜繃澶?
                    time.sleep(5)

                # 澶勭悊瀹屾墍鏈夋壒娆″悗锛岀瓑寰呬笅涓€娆℃鏌ュ懆鏈?
                logger.info(f"完成一轮检查，等待 {check_interval} 秒后开始下一轮")
                for _ in range(check_interval):
                    if not self.real_time_running:
                        break
                    time.sleep(1)

            except Exception as e:
                logger.error(f"瀹炴椂閭欢妫€鏌ュ嚭閿? {str(e)}")
                time.sleep(check_interval)


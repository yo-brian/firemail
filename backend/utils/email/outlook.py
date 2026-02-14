"""
Outlook邮件处理模块
"""

import imaplib
import email
import requests
import time
import datetime
from datetime import timezone

from .common import (
    decode_mime_words,
    normalize_check_time,
    format_date_for_imap_search,
)
from .logger import logger

class OutlookMailHandler:
    """Outlook邮箱处理类"""

    IMAP_HOSTS = [
        'outlook.office365.com',
        'imap-mail.outlook.com',
        'outlook.live.com'
    ]

    # Outlook常用文件夹映射
    DEFAULT_FOLDERS = {
        'INBOX': ['inbox', 'Inbox', 'INBOX'],
        'SENT': ['sentitems', 'Sent Items', 'Sent', '已发送'],
        'DRAFTS': ['drafts', 'Drafts', '草稿箱'],
        'TRASH': ['deleteditems', 'Deleted Items', 'Trash', '已删除'],
        'SPAM': ['junkemail', 'Junk E-mail', 'Spam', '垃圾邮件'],
        'ARCHIVE': ['archive', 'Archive', '归档']
    }

    GRAPH_BASE_URL = 'https://graph.microsoft.com/v1.0'
    GRAPH_RETRY_STATUS = {429, 502, 503, 504}

    def __init__(self, email_address, access_token):
        """初始化Outlook处理器"""
        self.email_address = email_address
        self.access_token = access_token
        self.mail = None
        self.error = None

    def connect(self):
        """Connect to Outlook server"""
        try:
            mail = OutlookMailHandler._connect_imap(self.email_address, self.access_token)
            if not mail:
                raise Exception('Unable to connect to Outlook IMAP')
            self.mail = mail
            return True
        except Exception as e:
            self.error = str(e)
            logger.error(f"Outlook connection failed: {e}")
            return False

    @staticmethod
    def _connect_imap(email_address, access_token):
        """Try multiple IMAP hosts and authenticate"""
        auth_string = OutlookMailHandler.generate_auth_string(email_address, access_token)
        for host in OutlookMailHandler.IMAP_HOSTS:
            try:
                mail = imaplib.IMAP4_SSL(host)
                mail.authenticate('XOAUTH2', lambda x: auth_string)
                mail.noop()
                logger.info(f"Outlook IMAP connected: {host}")
                return mail
            except Exception as e:
                logger.error(f"Outlook IMAP connect failed {host}: {e}")
                try:
                    mail.logout()
                except Exception:
                    pass
                continue
        return None

    def get_folders(self):
        """获取文件夹列表"""
        if not self.mail:
            return []

        try:
            _, folders = self.mail.list()
            folder_list = []

            for folder in folders:
                if isinstance(folder, bytes):
                    folder = folder.decode('utf-8', errors='ignore')

                # 解析文件夹名称
                parts = folder.split('"')
                if len(parts) >= 3:
                    folder_name = parts[-2]
                else:
                    folder_name = folder.split()[-1]

                if folder_name and folder_name not in ['.', '..']:
                    folder_list.append(folder_name)

            # 确保常用文件夹在列表中
            default_folders = ['inbox', 'sentitems', 'drafts', 'deleteditems', 'junkemail']
            for df in default_folders:
                if df not in folder_list:
                    folder_list.append(df)

            return sorted(folder_list)
        except Exception as e:
            logger.error(f"获取Outlook文件夹列表失败: {e}")
            return ['inbox']

    def get_messages(self, folder="inbox", limit=100):
        """获取指定文件夹的邮件"""
        if not self.mail:
            return []

        try:
            self.mail.select(folder)
            _, messages = self.mail.search(None, 'ALL')
            message_numbers = messages[0].split()

            # 限制数量并倒序（最新的在前）
            message_numbers = message_numbers[-limit:] if len(message_numbers) > limit else message_numbers
            message_numbers.reverse()

            mail_list = []
            for num in message_numbers:
                try:
                    _, msg_data = self.mail.fetch(num, '(RFC822)')
                    email_body = msg_data[0][1]
                    msg = email.message_from_bytes(email_body)

                    # 简化的邮件解析
                    subject = decode_mime_words(msg.get('Subject', ''))
                    sender = decode_mime_words(msg.get('From', ''))
                    received_time = email.utils.parsedate_to_datetime(msg.get('Date', ''))

                    # 获取邮件内容
                    content = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            content_type = part.get_content_type()
                            if content_type in ['text/plain', 'text/html']:
                                try:
                                    part_content = part.get_payload(decode=True).decode()
                                    content += part_content
                                except:
                                    pass
                    else:
                        try:
                            content = msg.get_payload(decode=True).decode()
                        except:
                            content = str(msg.get_payload())

                    mail_list.append({
                        'subject': subject,
                        'sender': sender,
                        'received_time': received_time,
                        'content': content,
                        'folder': folder
                    })
                except Exception as e:
                    logger.warning(f"解析Outlook邮件失败: {e}")
                    continue

            return mail_list
        except Exception as e:
            logger.error(f"获取Outlook邮件失败: {e}")
            return []

    def close(self):
        """关闭连接"""
        if self.mail:
            try:
                self.mail.logout()
            except:
                pass
            self.mail = None

    @staticmethod
    def get_new_access_token(refresh_token, client_id):
        """刷新获取新的access_token"""
        url = 'https://login.microsoftonline.com/common/oauth2/v2.0/token'
        data = {
            'client_id': client_id,
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token,
        }
        try:
            response = requests.post(url, data=data)
            result_status = response.json().get('error')
            if result_status is not None:
                logger.error(f"获取访问令牌失败: {result_status}")
                return None
            else:
                new_access_token = response.json()['access_token']
                logger.info("成功获取新的访问令牌")
                return new_access_token
        except Exception as e:
            logger.error(f"刷新令牌过程中发生异常: {str(e)}")
            return None

    @staticmethod
    def generate_auth_string(user, token):
        """生成 OAuth2 授权字符串"""
        return f"user={user}\1auth=Bearer {token}\1\1"

    @staticmethod
    def fetch_emails(email_address, access_token, folder="inbox", callback=None, last_check_time=None):
        """
        Fetch Outlook/Hotmail emails via IMAP

        Args:
            email_address: mailbox address
            access_token: OAuth2 access token
            folder: mailbox folder
            callback: progress callback
            last_check_time: only fetch emails after this time

        Returns:
            list: mail records
        """
        mail_records = []

        # Ensure callback exists
        if callback is None:
            callback = lambda progress, folder: None

        # Normalize last_check_time
        last_check_time = normalize_check_time(last_check_time)
        if not last_check_time:
            # Default to last 60 days on first sync
            last_check_time = datetime.datetime.utcnow() - datetime.timedelta(days=60)

        # Parse email
        if last_check_time:
            logger.info(f"Fetching Outlook mailbox {email_address} folder {folder} since {last_check_time.isoformat()}")
        else:
            logger.info(f"Fetching Outlook mailbox {email_address} folder {folder} (all emails)")

        # Parse email??
        max_retries = 3

        for retry in range(max_retries):
            try:
                logger.info(f"Connecting to Outlook IMAP (attempt {retry+1}/{max_retries})")
                callback(10, folder)

                # Connect IMAP
                mail = OutlookMailHandler._connect_imap(email_address, access_token)
                if not mail:
                    logger.error('Outlook IMAP connection failed, skipping')
                    continue

                # Parse email?
                mail.select(folder)
                callback(20, folder)

                # Parse email??
                # Ensure callback exists??IMAP???? (DD-MMM-YYYY)
                search_date = format_date_for_imap_search(last_check_time)
                search_cmd = f'(SINCE "{search_date}")'
                logger.info(f"Searching emails since {search_date}")
                status, data = mail.search(None, search_cmd)

                if status != 'OK':
                    logger.error(f"Search emails failed: {status}")
                    continue

                # Parse email??ID
                mail_ids = data[0].split()


                total_mails = len(mail_ids)
                logger.info(f"Found {total_mails} emails")

                # Parse email??
                for i, mail_id in enumerate(mail_ids):
                    # Parse email
                    progress = int(20 + (i / total_mails) * 70) if total_mails > 0 else 90
                    callback(progress, folder)

                    try:
                        # Parse email
                        status, mail_data = mail.fetch(mail_id, '(RFC822)')

                        if status != 'OK':
                            logger.error(f"Fetch mail ID {mail_id} failed: {status}")
                            continue

                        # Parse email
                        msg = email.message_from_bytes(mail_data[0][1])

                        subject = decode_mime_words(msg.get('Subject', ''))
                        sender = decode_mime_words(msg.get('From', ''))
                        received_time = email.utils.parsedate_to_datetime(msg.get('Date', ''))

                        # Parse email??
                        content = ""
                        if msg.is_multipart():
                            for part in msg.walk():
                                content_type = part.get_content_type()
                                if content_type in ['text/plain', 'text/html']:
                                    try:
                                        part_content = part.get_payload(decode=True).decode()
                                        content += part_content
                                    except Exception:
                                        pass
                        else:
                            try:
                                content = msg.get_payload(decode=True).decode()
                            except Exception:
                                content = str(msg.get_payload())

                        mail_records.append({
                            'subject': subject,
                            'sender': sender,
                            'received_time': received_time,
                            'content': content,
                            'folder': folder
                        })
                    except Exception as e:
                        logger.warning(f"Parse Outlook mail failed: {e}")
                        continue

                try:
                    mail.logout()
                except Exception:
                    pass

                break
            except Exception as e:
                logger.error(f"Fetch Outlook mail failed: {e}")
                if retry < max_retries - 1:
                    time.sleep(1)
                else:
                    break

        return mail_records

    @staticmethod
    def _graph_request(token, url, params=None):
        backoff = 1
        for _ in range(5):
            resp = requests.get(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                },
                params=params,
                timeout=30,
            )
            if resp.status_code < 400:
                return resp.json()
            if resp.status_code in OutlookMailHandler.GRAPH_RETRY_STATUS:
                retry_after = resp.headers.get("Retry-After")
                if retry_after:
                    sleep_seconds = int(retry_after)
                else:
                    sleep_seconds = min(backoff, 30)
                    backoff *= 2
                time.sleep(sleep_seconds)
                continue
            resp.raise_for_status()
        resp.raise_for_status()

    @staticmethod
    def _graph_request_json(method, token, url, payload=None):
        backoff = 1
        for _ in range(5):
            resp = requests.request(
                method,
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json=payload,
                timeout=30,
            )
            if resp.status_code < 400:
                return resp.json() if resp.content else {}
            if resp.status_code in OutlookMailHandler.GRAPH_RETRY_STATUS:
                retry_after = resp.headers.get("Retry-After")
                if retry_after:
                    sleep_seconds = int(retry_after)
                else:
                    sleep_seconds = min(backoff, 30)
                    backoff *= 2
                time.sleep(sleep_seconds)
                continue
            resp.raise_for_status()
        resp.raise_for_status()

    @staticmethod
    def _graph_list_folders(token):
        url = f"{OutlookMailHandler.GRAPH_BASE_URL}/me/mailFolders"
        # Some Microsoft tenants reject selecting wellKnownName on this endpoint.
        # Keep the query minimal for compatibility.
        params = {"$top": 200}
        payload = OutlookMailHandler._graph_request(token, url, params=params)
        return payload.get("value", [])

    @staticmethod
    def _graph_list_messages(token, folder_id, since_iso):
        url = f"{OutlookMailHandler.GRAPH_BASE_URL}/me/mailFolders/{folder_id}/messages"
        params = {
            "$top": 50,
            "$orderby": "receivedDateTime desc",
            "$select": "id,subject,from,receivedDateTime,body,hasAttachments,isRead",
        }
        if since_iso:
            params["$filter"] = f"receivedDateTime ge {since_iso}"

        items = []
        payload = OutlookMailHandler._graph_request(token, url, params=params)
        items.extend(payload.get("value", []))
        next_link = payload.get("@odata.nextLink")
        while next_link:
            payload = OutlookMailHandler._graph_request(token, next_link, params=None)
            items.extend(payload.get("value", []))
            next_link = payload.get("@odata.nextLink")
        return items

    @staticmethod
    def get_profile_email(access_token):
        """Get user's primary email address via Graph /me."""
        try:
            url = f"{OutlookMailHandler.GRAPH_BASE_URL}/me"
            payload = OutlookMailHandler._graph_request(access_token, url, params={"$select": "mail,userPrincipalName"})
            if not payload:
                return None
            profile_email = payload.get("mail") or payload.get("userPrincipalName")
            if profile_email and "@" in profile_email:
                return profile_email
            logger.error(f"Graph /me response has no usable email field: {payload}")
            return None
        except Exception as e:
            logger.error(f"Get profile email via Graph /me failed: {e}")
            return None

    @staticmethod
    def resolve_graph_mailbox(refresh_token, client_id, expected_email=None):
        """
        Resolve mailbox identity from refresh_token/client_id via Graph.

        Returns:
            dict: {success: bool, email: str|None, access_token: str|None, error: str|None}
        """
        try:
            normalized_expected = (expected_email or "").strip().lower()
            access_token = OutlookMailHandler.get_new_access_token(refresh_token, client_id)
            if not access_token:
                return {
                    "success": False,
                    "email": None,
                    "access_token": None,
                    "error": "Refresh Token 或 Client ID 无效，无法获取 Access Token"
                }

            resolved_email = OutlookMailHandler.get_profile_email(access_token)
            if not resolved_email:
                return {
                    "success": False,
                    "email": None,
                    "access_token": access_token,
                    "error": "无法通过 Graph /me 获取邮箱地址（请确认包含 User.Read 权限）"
                }

            normalized_resolved = resolved_email.strip().lower()
            if normalized_expected and normalized_expected != normalized_resolved:
                return {
                    "success": False,
                    "email": None,
                    "access_token": access_token,
                    "error": f"输入邮箱与 Graph 账号不一致：{normalized_expected} != {normalized_resolved}"
                }

            return {
                "success": True,
                "email": normalized_resolved,
                "access_token": access_token,
                "error": None
            }
        except Exception as e:
            logger.error(f"Resolve Graph mailbox failed: {e}")
            return {
                "success": False,
                "email": None,
                "access_token": None,
                "error": f"Graph 身份解析失败: {e}"
            }

    @staticmethod
    def mark_message_read(access_token, message_id, is_read=True):
        url = f"{OutlookMailHandler.GRAPH_BASE_URL}/me/messages/{message_id}"
        payload = {"isRead": bool(is_read)}
        OutlookMailHandler._graph_request_json("PATCH", access_token, url, payload=payload)
        return True

    @staticmethod
    def delete_message(access_token, message_id):
        url = f"{OutlookMailHandler.GRAPH_BASE_URL}/me/messages/{message_id}"
        OutlookMailHandler._graph_request_json("DELETE", access_token, url, payload=None)
        return True

    @staticmethod
    def _to_graph_recipients(items):
        recipients = []
        for item in items or []:
            addr = (item or "").strip()
            if addr:
                recipients.append({"emailAddress": {"address": addr}})
        return recipients

    @staticmethod
    def _to_graph_attachments(items):
        attachments = []
        for item in items or []:
            if not isinstance(item, dict):
                continue
            content_bytes = (item.get("content_base64") or "").strip()
            name = (item.get("name") or "attachment.bin").strip()
            content_type = (item.get("content_type") or "application/octet-stream").strip()
            if not content_bytes:
                continue
            attachments.append({
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": name,
                "contentType": content_type,
                "contentBytes": content_bytes,
            })
        return attachments

    @staticmethod
    def send_mail(access_token, to_list, subject, body_content, cc_list=None, bcc_list=None, attachments=None):
        url = f"{OutlookMailHandler.GRAPH_BASE_URL}/me/sendMail"

        message_payload = {
            "subject": subject or "(No Subject)",
            "body": {
                "contentType": "HTML",
                "content": body_content or "",
            },
            "toRecipients": OutlookMailHandler._to_graph_recipients(to_list),
            "ccRecipients": OutlookMailHandler._to_graph_recipients(cc_list),
            "bccRecipients": OutlookMailHandler._to_graph_recipients(bcc_list),
        }
        graph_attachments = OutlookMailHandler._to_graph_attachments(attachments)
        if graph_attachments:
            message_payload["attachments"] = graph_attachments

        payload = {"message": message_payload, "saveToSentItems": True}

        OutlookMailHandler._graph_request_json("POST", access_token, url, payload=payload)
        return True

    @staticmethod
    def create_reply_draft(access_token, message_id, reply_all=False):
        action = "createReplyAll" if reply_all else "createReply"
        url = f"{OutlookMailHandler.GRAPH_BASE_URL}/me/messages/{message_id}/{action}"
        payload = OutlookMailHandler._graph_request_json("POST", access_token, url, payload={})
        draft_id = payload.get("id")
        if not draft_id:
            raise RuntimeError("Failed to create Graph reply draft")
        return payload

    @staticmethod
    def update_draft_message(access_token, draft_id, subject=None, body_content=None, to_list=None, cc_list=None, bcc_list=None, attachments=None):
        url = f"{OutlookMailHandler.GRAPH_BASE_URL}/me/messages/{draft_id}"
        patch = {}
        if subject is not None:
            patch["subject"] = subject
        if body_content is not None:
            patch["body"] = {
                "contentType": "HTML",
                "content": body_content,
            }
        if to_list is not None:
            patch["toRecipients"] = OutlookMailHandler._to_graph_recipients(to_list)
        if cc_list is not None:
            patch["ccRecipients"] = OutlookMailHandler._to_graph_recipients(cc_list)
        if bcc_list is not None:
            patch["bccRecipients"] = OutlookMailHandler._to_graph_recipients(bcc_list)
        if attachments is not None:
            patch["attachments"] = OutlookMailHandler._to_graph_attachments(attachments)
        if patch:
            OutlookMailHandler._graph_request_json("PATCH", access_token, url, payload=patch)
        return True

    @staticmethod
    def send_draft_message(access_token, draft_id):
        url = f"{OutlookMailHandler.GRAPH_BASE_URL}/me/messages/{draft_id}/send"
        OutlookMailHandler._graph_request_json("POST", access_token, url, payload={})
        return True

    @staticmethod
    def fetch_emails_graph(email_address, access_token, callback=None, last_check_time=None):
        """Fetch Outlook/Hotmail emails via Microsoft Graph."""
        mail_records = []
        if callback is None:
            callback = lambda progress, folder: None

        last_check_time = normalize_check_time(last_check_time)
        if not last_check_time:
            last_check_time = datetime.datetime.utcnow() - datetime.timedelta(days=60)
        since_iso = last_check_time.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")

        folders = OutlookMailHandler._graph_list_folders(access_token)
        if not folders:
            folders = [{"id": "inbox", "displayName": "Inbox"}]

        allowed_names = {"inbox", "junkemail", "junk email", "spam", "收件箱", "垃圾邮件"}
        def _folder_allowed(f):
            well_known = (f.get("wellKnownName") or "").strip().lower()
            if well_known in ("inbox", "junkemail"):
                return True
            name = (f.get("displayName") or f.get("id") or "").strip().lower()
            if name in allowed_names:
                return True
            return f.get("id") in ("inbox", "junkemail")

        folders = [f for f in folders if _folder_allowed(f)]
        logger.info(f"Graph folders selected: {[(f.get('displayName'), f.get('wellKnownName')) for f in folders]}")

        total_folders = len(folders)
        for idx, folder in enumerate(folders):
            folder_id = folder.get("id")
            folder_name = folder.get("displayName", folder_id)
            if not folder_id:
                continue
            callback(10, folder_name)
            messages = OutlookMailHandler._graph_list_messages(access_token, folder_id, since_iso)

            for msg in messages:
                sender = ""
                sender_obj = msg.get("from") or {}
                sender_addr = (sender_obj.get("emailAddress") or {}).get("address")
                if sender_addr:
                    sender = sender_addr

                received_time = msg.get("receivedDateTime")
                try:
                    received_dt = datetime.datetime.fromisoformat(received_time.replace("Z", "+00:00"))
                except Exception:
                    received_dt = datetime.datetime.utcnow()

                body = (msg.get("body") or {}).get("content") or ""
                is_read = bool(msg.get("isRead", True))
                mail_records.append({
                    "subject": msg.get("subject") or "(无主题)",
                    "sender": sender or "(未知发件人)",
                    "received_time": received_dt,
                    "content": body,
                    "folder": folder_name,
                    "is_read": is_read,
                    "graph_message_id": msg.get("id"),
                    "has_attachments": bool(msg.get("hasAttachments")),
                })

            progress = int(10 + ((idx + 1) / max(total_folders, 1)) * 80)
            callback(progress, folder_name)

        return mail_records

    def check_mail(email_info, db, progress_callback=None):
        """检查Outlook/Hotmail邮箱中的邮件并存储到数据库"""
        email_id = email_info['id']
        email_address = email_info['email']
        refresh_token = email_info['refresh_token']
        client_id = email_info['client_id']

        logger.info(f"开始检查Outlook邮箱: ID={email_id}, 邮箱={email_address}")

        # 确保回调函数存在
        if progress_callback is None:
            progress_callback = lambda progress, message: None

        # 报告初始进度
        progress_callback(0, "正在获取访问令牌...")

        try:
            # 获取新的访问令牌
            access_token = OutlookMailHandler.get_new_access_token(refresh_token, client_id)
            if not access_token:
                error_msg = f"邮箱{email_address}(ID={email_id})获取访问令牌失败"
                logger.error(error_msg)
                progress_callback(0, error_msg)
                return {
                    'success': False,
                    'message': error_msg
                }

            # 更新令牌到数据库
            db.update_email_token(email_id, access_token)

            # 报告进度
            progress_callback(10, "开始获取邮件...")

            # 获取邮件
            def folder_progress_callback(progress, folder):
                msg = f"正在处理{folder}文件夹，进度{progress}%"
                # 将各文件夹的进度映射到总进度10-90%
                total_progress = 10 + int(progress * 0.8)
                progress_callback(total_progress, msg)

            try:
                mail_records = OutlookMailHandler.fetch_emails(
                    email_address,
                    access_token,
                    "inbox",
                    folder_progress_callback
                )

                # 报告进度
                count = len(mail_records)
                progress_callback(90, f"获取到{count}封邮件，正在保存...")

                # 将邮件记录保存到数据库
                saved_count = 0
                for record in mail_records:
                    try:
                        success = db.add_mail_record(
                            email_id,
                            record['subject'],
                            record['sender'],
                            record['received_time'],
                            record['content'],
                            is_read=1,
                            has_attachments=1 if record.get('has_attachments', False) else 0
                        )
                        if success:
                            saved_count += 1
                    except Exception as e:
                        logger.error(f"保存邮件记录失败: {str(e)}")

                # 更新最后检查时间（只有在成功获取到邮件或没有新邮件时才更新）
                try:
                    if count >= 0:  # 确保邮件获取成功
                        db.update_check_time(email_id)
                        logger.info(f"已更新邮箱{email_address}(ID={email_id})的最后检查时间")
                    else:
                        logger.warning(f"邮件获取失败，不更新邮箱{email_address}(ID={email_id})的最后检查时间")
                except Exception as e:
                    logger.error(f"更新检查时间失败: {str(e)}")

                # 报告完成
                success_msg = f"完成，共处理{count}封邮件，新增{saved_count}封"
                progress_callback(100, success_msg)

                logger.info(f"邮箱{email_address}(ID={email_id})检查完成，获取到{count}封邮件，新增{saved_count}封")
                return {
                    'success': True,
                    'message': success_msg,
                    'total': count,
                    'saved': saved_count
                }

            except Exception as e:
                error_msg = f"检查邮件失败: {str(e)}"
                logger.error(f"邮箱{email_address}(ID={email_id}){error_msg}")
                progress_callback(0, error_msg)
                return {
                    'success': False,
                    'message': error_msg
                }

        except Exception as e:
            error_msg = f"处理邮箱过程中出错: {str(e)}"
            logger.error(f"邮箱{email_address}(ID={email_id}){error_msg}")
            progress_callback(0, error_msg)
            return {
                'success': False,
                'message': error_msg
            }

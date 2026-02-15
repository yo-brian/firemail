"""
Outlook閭欢澶勭悊妯″潡
"""

import imaplib
import email
import requests
import time
import datetime
import base64
from urllib.parse import quote
from datetime import timezone

from .common import (
    decode_mime_words,
    normalize_check_time,
    format_date_for_imap_search,
)
from .logger import logger

class OutlookMailHandler:
    """Outlook閭澶勭悊鍣?"""

    IMAP_HOSTS = [
        'outlook.office365.com',
        'imap-mail.outlook.com',
        'outlook.live.com'
    ]

    # Outlook甯哥敤鏂囦欢澶瑰埆鍚?
    DEFAULT_FOLDERS = {
        'INBOX': ['inbox', 'Inbox', 'INBOX'],
        'SENT': ['sentitems', 'Sent Items', 'Sent', '宸插彂閫?'],
        'DRAFTS': ['drafts', 'Drafts', '鑽夌绠?'],
        'TRASH': ['deleteditems', 'Deleted Items', 'Trash', '宸插垹闄?'],
        'SPAM': ['junkemail', 'Junk E-mail', 'Spam', '鍨冨溇閭欢'],
        'ARCHIVE': ['archive', 'Archive', '褰掓。']
    }

    GRAPH_BASE_URL = 'https://graph.microsoft.com/v1.0'
    GRAPH_RETRY_STATUS = {429, 502, 503, 504}

    @staticmethod
    def _graph_path_id(value):
        """Encode Graph path identifiers to avoid 400 on special chars."""
        return quote(str(value), safe='')

    def __init__(self, email_address, access_token):
        """鍒濆鍖朞utlook澶勭悊鍣?"""
        self.email_address = email_address
        self.access_token = access_token
        self.mail = None
        self.error = None

    def connect(self):
        """杩炴帴鍒癘utlook鏈嶅姟鍣?"""
        try:
            mail = OutlookMailHandler._connect_imap(self.email_address, self.access_token)
            if not mail:
                raise Exception('鏃犳硶杩炴帴鍒癘utlook IMAP')
            self.mail = mail
            return True
        except Exception as e:
            self.error = str(e)
            logger.error(f"Outlook杩炴帴澶辫触: {e}")
            return False

    @staticmethod
    def _connect_imap(email_address, access_token):
        """灏濊瘯澶氫釜IMAP涓绘満骞惰璇?"""
        auth_string = OutlookMailHandler.generate_auth_string(email_address, access_token)
        for host in OutlookMailHandler.IMAP_HOSTS:
            try:
                mail = imaplib.IMAP4_SSL(host)
                mail.authenticate('XOAUTH2', lambda x: auth_string)
                mail.noop()
                logger.info(f"Outlook IMAP杩炴帴鎴愬姛: {host}")
                return mail
            except Exception as e:
                logger.error(f"Outlook IMAP杩炴帴澶辫触 {host}: {e}")
                try:
                    mail.logout()
                except Exception:
                    pass
                continue
        return None

    def get_folders(self):
        """鑾峰彇閭鏂囦欢澶瑰垪琛?"""
        if not self.mail:
            return []

        try:
            _, folders = self.mail.list()
            folder_list = []

            for folder in folders:
                if isinstance(folder, bytes):
                    folder = folder.decode('utf-8', errors='ignore')

                # 浠嶭IST鍝嶅簲涓В鏋愭枃浠跺す鍚?
                parts = folder.split('"')
                if len(parts) >= 3:
                    folder_name = parts[-2]
                else:
                    folder_name = folder.split()[-1]

                if folder_name and folder_name not in ['.', '..']:
                    folder_list.append(folder_name)

            # 纭繚甯哥敤鏂囦欢澶归兘瀛樺湪
            default_folders = ['inbox', 'sentitems', 'drafts', 'deleteditems', 'junkemail']
            for df in default_folders:
                if df not in folder_list:
                    folder_list.append(df)

            return sorted(folder_list)
        except Exception as e:
            logger.error(f"鑾峰彇Outlook鏂囦欢澶瑰垪琛ㄥけ璐? {e}")
            return ['inbox']

    def get_messages(self, folder="inbox", limit=100):
        """鑾峰彇鎸囧畾鏂囦欢澶逛腑鐨勯偖浠?"""
        if not self.mail:
            return []

        try:
            self.mail.select(folder)
            _, messages = self.mail.search(None, 'ALL')
            message_numbers = messages[0].split()

            # 浠呬繚鐣欐渶杩?`limit` 灏侀偖浠?
            message_numbers = message_numbers[-limit:] if len(message_numbers) > limit else message_numbers
            message_numbers.reverse()

            mail_list = []
            for num in message_numbers:
                try:
                    _, msg_data = self.mail.fetch(num, '(RFC822)')
                    email_body = msg_data[0][1]
                    msg = email.message_from_bytes(email_body)

                    # 瑙ｆ瀽閭欢鍩虹瀛楁
                    subject = decode_mime_words(msg.get('Subject', ''))
                    sender = decode_mime_words(msg.get('From', ''))
                    received_time = email.utils.parsedate_to_datetime(msg.get('Date', ''))

                    # 鎻愬彇閭欢鍐呭
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
                    logger.warning(f"瑙ｆ瀽Outlook閭欢澶辫触: {e}")
                    continue

            return mail_list
        except Exception as e:
            logger.error(f"鑾峰彇Outlook閭欢澶辫触: {e}")
            return []

    def close(self):
        """鍏抽棴IMAP杩炴帴"""
        if self.mail:
            try:
                self.mail.logout()
            except:
                pass
            self.mail = None

    @staticmethod
    def get_new_access_token(refresh_token, client_id):
        """鍒锋柊骞惰繑鍥炴柊鐨勮闂护鐗?"""
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
                logger.error(f"鑾峰彇璁块棶浠ょ墝澶辫触: {result_status}")
                return None
            else:
                new_access_token = response.json()['access_token']
                logger.info("鎴愬姛鍒锋柊璁块棶浠ょ墝")
                return new_access_token
        except Exception as e:
            logger.error(f"鍒锋柊璁块棶浠ょ墝寮傚父: {str(e)}")
            return None

    @staticmethod
    def generate_auth_string(user, token):
        """鐢熸垚OAuth2璁よ瘉瀛楃涓?"""
        return f"user={user}\1auth=Bearer {token}\1\1"

    @staticmethod
    def fetch_emails(email_address, access_token, folder="inbox", callback=None, last_check_time=None):
        """
        閫氳繃IMAP鎷夊彇Outlook/Hotmail閭欢

        Args:
            email_address: 閭鍦板潃
            access_token: OAuth2璁块棶浠ょ墝
            folder: 閭鏂囦欢澶?
            callback: 杩涘害鍥炶皟
            last_check_time: 浠呮媺鍙栬鏃堕棿涔嬪悗鐨勯偖浠?

        Returns:
            list: 閭欢璁板綍
        """
        mail_records = []

        # 纭繚鍥炶皟瀛樺湪
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

        # 鎷夊彇閭欢閲嶈瘯绛栫暐
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

                # 閫夋嫨鐩爣鏂囦欢澶?
                mail.select(folder)
                callback(20, folder)

                # 鏋勯€犳悳绱㈡潯浠?
                # 浣跨敤IMAP SINCE锛圖D-MMM-YYYY锛?
                search_date = format_date_for_imap_search(last_check_time)
                search_cmd = f'(SINCE "{search_date}")'
                logger.info(f"Searching emails since {search_date}")
                status, data = mail.search(None, search_cmd)

                if status != 'OK':
                    logger.error(f"Search emails failed: {status}")
                    continue

                # 瑙ｆ瀽閭欢ID鍒楄〃
                mail_ids = data[0].split()


                total_mails = len(mail_ids)
                logger.info(f"Found {total_mails} emails")

                # 閬嶅巻閭欢ID骞舵媺鍙栬鎯?
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

                        # 瑙ｆ瀽閭欢姝ｆ枃
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
            if resp.status_code >= 400:
                try:
                    logger.error(f"Graph request failed: status={resp.status_code}, url={url}, body={resp.text[:500]}")
                except Exception:
                    pass
            resp.raise_for_status()
        resp.raise_for_status()

    @staticmethod
    def _graph_request_json(method, token, url, payload=None):
        backoff = 1
        for _ in range(5):
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            }
            request_kwargs = {
                "method": method,
                "url": url,
                "headers": headers,
                "timeout": 30,
            }
            if payload is not None:
                headers["Content-Type"] = "application/json"
                request_kwargs["json"] = payload
            resp = requests.request(**request_kwargs)
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
            if resp.status_code >= 400:
                try:
                    logger.error(f"Graph JSON request failed: method={method}, status={resp.status_code}, url={url}, body={resp.text[:800]}")
                except Exception:
                    pass
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
        encoded_folder_id = OutlookMailHandler._graph_path_id(folder_id)
        url = f"{OutlookMailHandler.GRAPH_BASE_URL}/me/mailFolders/{encoded_folder_id}/messages"
        params = {
            "$top": 50,
            "$orderby": "receivedDateTime desc",
            "$select": "id,subject,from,toRecipients,receivedDateTime,body,hasAttachments,isRead",
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
    def _graph_list_attachments(token, message_id):
        encoded_message_id = OutlookMailHandler._graph_path_id(message_id)
        url = f"{OutlookMailHandler.GRAPH_BASE_URL}/me/messages/{encoded_message_id}/attachments"
        params = {"$top": 50}
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
    def _graph_get_attachment(token, message_id, attachment_id):
        encoded_message_id = OutlookMailHandler._graph_path_id(message_id)
        encoded_attachment_id = OutlookMailHandler._graph_path_id(attachment_id)
        url = f"{OutlookMailHandler.GRAPH_BASE_URL}/me/messages/{encoded_message_id}/attachments/{encoded_attachment_id}"
        return OutlookMailHandler._graph_request(token, url, params=None)

    @staticmethod
    def get_profile_email(access_token):
        """閫氳繃 Graph /me 鑾峰彇涓婚偖绠卞湴鍧€"""
        try:
            url = f"{OutlookMailHandler.GRAPH_BASE_URL}/me"
            payload = OutlookMailHandler._graph_request(access_token, url, params={"$select": "mail,userPrincipalName"})
            if not payload:
                return None
            profile_email = payload.get("mail") or payload.get("userPrincipalName")
            if profile_email and "@" in profile_email:
                return profile_email
            logger.error(f"Graph /me 鍝嶅簲涓棤鍙敤閭瀛楁: {payload}")
            return None
        except Exception as e:
            logger.error(f"閫氳繃 Graph /me 鑾峰彇閭澶辫触: {e}")
            return None

    @staticmethod
    @staticmethod
    def resolve_graph_mailbox(refresh_token, client_id, expected_email=None):
        """通过 Graph 使用 refresh_token/client_id 解析邮箱身份。"""
        try:
            normalized_expected = (expected_email or "").strip().lower()
            access_token = OutlookMailHandler.get_new_access_token(refresh_token, client_id)
            if not access_token:
                return {
                    "success": False,
                    "email": None,
                    "access_token": None,
                    "error": "通过 Refresh Token / Client ID 获取访问令牌失败"
                }

            resolved_email = OutlookMailHandler.get_profile_email(access_token)
            if not resolved_email:
                return {
                    "success": False,
                    "email": None,
                    "access_token": access_token,
                    "error": "无法通过 Graph /me 解析邮箱地址（请确认已授予 User.Read 权限）"
                }

            normalized_resolved = resolved_email.strip().lower()
            if normalized_expected and normalized_expected != normalized_resolved:
                return {
                    "success": False,
                    "email": None,
                    "access_token": access_token,
                    "error": f"输入邮箱与 Graph 解析邮箱不一致：{normalized_expected} != {normalized_resolved}"
                }

            return {
                "success": True,
                "email": normalized_resolved,
                "access_token": access_token,
                "error": None
            }
        except Exception as e:
            logger.error(f"Graph邮箱身份解析失败: {e}")
            return {
                "success": False,
                "email": None,
                "access_token": None,
                "error": f"Graph邮箱身份解析失败: {e}"
            }
    def mark_message_read(access_token, message_id, is_read=True):
        encoded_message_id = OutlookMailHandler._graph_path_id(message_id)
        url = f"{OutlookMailHandler.GRAPH_BASE_URL}/me/messages/{encoded_message_id}"
        payload = {"isRead": bool(is_read)}
        OutlookMailHandler._graph_request_json("PATCH", access_token, url, payload=payload)
        return True

    @staticmethod
    def delete_message(access_token, message_id):
        encoded_message_id = OutlookMailHandler._graph_path_id(message_id)
        url = f"{OutlookMailHandler.GRAPH_BASE_URL}/me/messages/{encoded_message_id}"
        OutlookMailHandler._graph_request_json("DELETE", access_token, url, payload=None)
        return True

    @staticmethod
    def delete_messages_batch(access_token, message_ids):
        """Use Microsoft Graph $batch to delete multiple messages.
        Returns dict: {deleted: [message_id], failed: [{message_id, status, body}]}
        """
        normalized = []
        seen = set()
        for mid in message_ids or []:
            value = str(mid or "").strip()
            if value and value not in seen:
                seen.add(value)
                normalized.append(value)

        if not normalized:
            return {"deleted": [], "failed": []}

        batch_url = f"{OutlookMailHandler.GRAPH_BASE_URL}/$batch"
        deleted = []
        failed = []

        # Graph $batch usually limits to 20 requests per batch.
        chunk_size = 20
        for i in range(0, len(normalized), chunk_size):
            chunk = normalized[i:i + chunk_size]
            requests_payload = []
            reqid_to_mid = {}
            for idx, mid in enumerate(chunk):
                req_id = str(idx + 1)
                reqid_to_mid[req_id] = mid
                encoded_mid = OutlookMailHandler._graph_path_id(mid)
                requests_payload.append({
                    "id": req_id,
                    "method": "DELETE",
                    "url": f"/me/messages/{encoded_mid}",
                })

            payload = {"requests": requests_payload}
            response = OutlookMailHandler._graph_request_json("POST", access_token, batch_url, payload=payload)
            for item in response.get("responses", []):
                req_id = str(item.get("id", ""))
                mid = reqid_to_mid.get(req_id)
                if not mid:
                    continue
                status = int(item.get("status") or 0)
                # 404 means already deleted remotely, treat as success for idempotency.
                if 200 <= status < 300 or status == 404:
                    deleted.append(mid)
                else:
                    failed.append({
                        "message_id": mid,
                        "status": status,
                        "body": item.get("body"),
                    })

        return {"deleted": deleted, "failed": failed}

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
            is_inline = bool(item.get("is_inline", False))
            content_id = (item.get("content_id") or "").strip()
            if not content_bytes:
                continue
            attachment_payload = {
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": name,
                "contentType": content_type,
                "contentBytes": content_bytes,
            }
            if is_inline and content_id:
                attachment_payload["isInline"] = True
                attachment_payload["contentId"] = content_id
            attachments.append(attachment_payload)
        return attachments

    @staticmethod
    def send_mail(access_token, to_list, subject, body_content, cc_list=None, bcc_list=None, attachments=None):
        url = f"{OutlookMailHandler.GRAPH_BASE_URL}/me/sendMail"

        message_payload = {
            "subject": subject or "(无主题)",
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
        encoded_message_id = OutlookMailHandler._graph_path_id(message_id)
        url = f"{OutlookMailHandler.GRAPH_BASE_URL}/me/messages/{encoded_message_id}/{action}"
        payload = OutlookMailHandler._graph_request_json("POST", access_token, url, payload=None)
        draft_id = payload.get("id")
        if not draft_id:
            raise RuntimeError("鍒涘缓Graph鍥炲鑽夌澶辫触")
        return payload

    @staticmethod
    def update_draft_message(access_token, draft_id, subject=None, body_content=None, to_list=None, cc_list=None, bcc_list=None, attachments=None):
        encoded_draft_id = OutlookMailHandler._graph_path_id(draft_id)
        url = f"{OutlookMailHandler.GRAPH_BASE_URL}/me/messages/{encoded_draft_id}"
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
        if patch:
            OutlookMailHandler._graph_request_json("PATCH", access_token, url, payload=patch)
        return True

    @staticmethod
    def add_draft_attachments(access_token, draft_id, attachments=None):
        encoded_draft_id = OutlookMailHandler._graph_path_id(draft_id)
        url = f"{OutlookMailHandler.GRAPH_BASE_URL}/me/messages/{encoded_draft_id}/attachments"
        graph_attachments = OutlookMailHandler._to_graph_attachments(attachments)
        for attachment in graph_attachments:
            OutlookMailHandler._graph_request_json("POST", access_token, url, payload=attachment)
        return True

    @staticmethod
    def send_draft_message(access_token, draft_id):
        encoded_draft_id = OutlookMailHandler._graph_path_id(draft_id)
        url = f"{OutlookMailHandler.GRAPH_BASE_URL}/me/messages/{encoded_draft_id}/send"
        try:
            OutlookMailHandler._graph_request_json("POST", access_token, url, payload=None)
        except requests.exceptions.HTTPError as err:
            status = getattr(err.response, "status_code", None)
            if status not in (400, 404):
                raise
            fallback_url = f"{OutlookMailHandler.GRAPH_BASE_URL}/me/messages/{draft_id}/send"
            logger.warning(f"send_draft fallback to raw draft id: status={status}, draft_id={draft_id}")
            OutlookMailHandler._graph_request_json("POST", access_token, fallback_url, payload=None)
        return True

    @staticmethod
    def fetch_emails_graph(email_address, access_token, callback=None, last_check_time=None):
        """閫氳繃 Microsoft Graph 鎷夊彇 Outlook/Hotmail 閭欢"""
        mail_records = []
        if callback is None:
            callback = lambda progress, folder: None

        last_check_time = normalize_check_time(last_check_time)
        if not last_check_time:
            last_check_time = datetime.datetime.utcnow() - datetime.timedelta(days=60)
        since_iso = last_check_time.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")

        folders = OutlookMailHandler._graph_list_folders(access_token)
        if not folders:
            folders = [
                {"id": "inbox", "displayName": "Inbox", "wellKnownName": "inbox"},
                {"id": "sentitems", "displayName": "Sent Items", "wellKnownName": "sentitems"},
            ]
        else:
            # Always ensure key well-known folders are included even if tenant folder listing omits them.
            existing_keys = set()
            for f in folders:
                fid = str(f.get("id") or "").strip().lower()
                wk = str(f.get("wellKnownName") or "").strip().lower()
                name = str(f.get("displayName") or "").strip().lower()
                if fid:
                    existing_keys.add(fid)
                if wk:
                    existing_keys.add(wk)
                if name:
                    existing_keys.add(name)
            for fid, dname in (
                ("inbox", "Inbox"),
                ("junkemail", "Junk Email"),
                ("sentitems", "Sent Items"),
            ):
                if fid not in existing_keys:
                    folders.append({"id": fid, "displayName": dname, "wellKnownName": fid})

        allowed_names = {
            "inbox", "junkemail", "junk email", "spam",
            "sentitems", "sent items", "sent",
            "收件箱", "垃圾邮件", "已发送", "已发送邮件"
        }
        def _folder_allowed(f):
            well_known = (f.get("wellKnownName") or "").strip().lower()
            if well_known in ("inbox", "junkemail", "sentitems"):
                return True
            name = (f.get("displayName") or f.get("id") or "").strip().lower()
            if name in allowed_names:
                return True
            folder_id = (f.get("id") or "").strip().lower()
            return folder_id in ("inbox", "junkemail", "sentitems")

        folders = [f for f in folders if _folder_allowed(f)]
        logger.info(f"Graph已选择文件夹: {[(f.get('displayName'), f.get('wellKnownName')) for f in folders]}")

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
                recipient = ", ".join(
                    (r.get("emailAddress") or {}).get("address", "").strip()
                    for r in (msg.get("toRecipients") or [])
                    if (r.get("emailAddress") or {}).get("address")
                )

                received_time = msg.get("receivedDateTime")
                try:
                    received_dt = datetime.datetime.fromisoformat(received_time.replace("Z", "+00:00"))
                except Exception:
                    received_dt = datetime.datetime.utcnow()

                body = (msg.get("body") or {}).get("content") or ""
                is_read = bool(msg.get("isRead", True))
                graph_message_id = msg.get("id")
                has_attachments = bool(msg.get("hasAttachments"))
                full_attachments = []
                if has_attachments and graph_message_id:
                    try:
                        attachments = OutlookMailHandler._graph_list_attachments(access_token, graph_message_id)
                        for att in attachments:
                            # 浠呭鐞?fileAttachment锛堟殏涓嶅鐞?item/reference 闄勪欢锛?
                            if att.get("@odata.type") != "#microsoft.graph.fileAttachment":
                                continue
                            content_b64 = att.get("contentBytes")
                            if not content_b64 and att.get("id"):
                                try:
                                    detail = OutlookMailHandler._graph_get_attachment(
                                        access_token, graph_message_id, att.get("id")
                                    )
                                    if detail:
                                        content_b64 = detail.get("contentBytes") or content_b64
                                        att = {
                                            **att,
                                            "name": detail.get("name") or att.get("name"),
                                            "contentType": detail.get("contentType") or att.get("contentType"),
                                            "size": detail.get("size") or att.get("size"),
                                        }
                                except Exception as detail_error:
                                    logger.warning(
                                        "Fetch Graph attachment detail failed, message=%s attachment=%s err=%s",
                                        graph_message_id,
                                        att.get("id"),
                                        detail_error,
                                    )
                            if not content_b64:
                                continue
                            try:
                                content_bytes = base64.b64decode(content_b64)
                            except Exception:
                                logger.warning("瑙ｆ瀽Graph闄勪欢鍐呭澶辫触锛宮essage=%s", graph_message_id)
                                continue
                            full_attachments.append({
                                "filename": att.get("name") or "attachment.bin",
                                "content_type": att.get("contentType") or "application/octet-stream",
                                "size": int(att.get("size") or len(content_bytes)),
                                "content": content_bytes,
                            })
                    except Exception as e:
                        logger.warning(f"鑾峰彇Graph闄勪欢澶辫触锛宮essage={graph_message_id}: {e}")
                mail_records.append({
                    "subject": msg.get("subject") or "(无主题)",
                    "sender": sender or "(未知发件人)",
                    "recipient": recipient,
                    "received_time": received_dt,
                    "content": body,
                    "folder": folder_name,
                    "is_read": is_read,
                    "graph_message_id": graph_message_id,
                    "has_attachments": bool(full_attachments) or has_attachments,
                    "full_attachments": full_attachments,
                })

            progress = int(10 + ((idx + 1) / max(total_folders, 1)) * 80)
            callback(progress, folder_name)

        return mail_records
    @staticmethod
    def check_mail(email_info, db, progress_callback=None):
        """检查 Outlook/Hotmail 邮件并保存到数据库。"""
        email_id = email_info['id']
        email_address = email_info['email']
        refresh_token = email_info['refresh_token']
        client_id = email_info['client_id']

        logger.info(f"开始检查 Outlook 邮箱: ID={email_id}, 邮箱={email_address}")

        if progress_callback is None:
            progress_callback = lambda progress, message: None

        progress_callback(0, "正在获取访问令牌...")

        try:
            access_token = OutlookMailHandler.get_new_access_token(refresh_token, client_id)
            if not access_token:
                error_msg = f"邮箱 {email_address}(ID={email_id}) 刷新访问令牌失败"
                logger.error(error_msg)
                progress_callback(0, error_msg)
                return {'success': False, 'message': error_msg}

            db.update_email_token(email_id, access_token)
            progress_callback(10, "开始获取邮件...")

            def folder_progress_callback(progress, folder):
                msg = f"正在处理文件夹 {folder}，进度 {progress}%"
                total_progress = 10 + int(progress * 0.8)
                progress_callback(total_progress, msg)

            try:
                mail_records = OutlookMailHandler.fetch_emails_graph(
                    email_address,
                    access_token,
                    callback=folder_progress_callback,
                    last_check_time=normalize_check_time(email_info.get('last_check_time'))
                )

                count = len(mail_records)
                progress_callback(90, f"已获取 {count} 封邮件，正在保存...")

                saved_count = 0
                for record in mail_records:
                    try:
                        success, mail_id = db.add_mail_record(
                            email_id,
                            record['subject'],
                            record['sender'],
                            record['received_time'],
                            record['content'],
                            recipient=record.get('recipient'),
                            is_read=1,
                            graph_message_id=record.get('graph_message_id'),
                            has_attachments=1 if record.get('has_attachments', False) else 0
                        )
                        if success and mail_id and record.get('has_attachments') and record.get('full_attachments'):
                            for attachment in record.get('full_attachments', []):
                                filename = attachment.get('filename')
                                content = attachment.get('content')
                                if not filename or not content:
                                    continue
                                db.add_attachment(
                                    mail_id=mail_id,
                                    filename=filename,
                                    content_type=attachment.get('content_type') or 'application/octet-stream',
                                    size=attachment.get('size') or len(content),
                                    content=content
                                )
                        if success and mail_id:
                            saved_count += 1
                    except Exception as e:
                        logger.error(f"保存邮件记录失败: {str(e)}")

                try:
                    db.update_check_time(email_id)
                    logger.info(f"已更新最后检查时间: {email_address}(ID={email_id})")
                except Exception as e:
                    logger.error(f"更新最后检查时间失败: {str(e)}")

                success_msg = f"邮件同步完成：获取 {count} 封，保存 {saved_count} 封"
                progress_callback(100, success_msg)
                logger.info(f"邮箱 {email_address}(ID={email_id}) 检查完成，获取 {count} 封，保存 {saved_count} 封")
                return {
                    'success': True,
                    'message': success_msg,
                    'total': count,
                    'saved': saved_count
                }

            except Exception as e:
                error_msg = f"获取/保存邮件失败: {str(e)}"
                logger.error(f"邮箱 {email_address}(ID={email_id}) {error_msg}")
                progress_callback(0, error_msg)
                return {'success': False, 'message': error_msg}

        except Exception as e:
            error_msg = f"邮箱检查过程异常: {str(e)}"
            logger.error(f"邮箱 {email_address}(ID={email_id}) {error_msg}")
            progress_callback(0, error_msg)
            return {'success': False, 'message': error_msg}


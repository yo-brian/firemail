"""Realtime email checking scheduler."""

import logging
import threading
import time
from datetime import datetime

logger = logging.getLogger(__name__)


class RealTimeChecker:
    """Run realtime sync in fixed-size rotating batches."""

    def __init__(self, db, email_processor, batch_size=5):
        self.db = db
        self.email_processor = email_processor
        self.running = False
        self.thread = None
        self.check_interval = 300
        self.batch_size = max(1, int(batch_size))

        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._cursor = 0
        self._eligible_accounts = []
        self._last_round_started_at = None
        self._last_round_selected = []

    def start(self, check_interval=60):
        if self.running:
            logger.warning("Realtime checker already running")
            return False

        self.check_interval = max(int(check_interval), 30)
        self.running = True
        self._stop_event.clear()
        self.thread = threading.Thread(target=self._check_loop, daemon=True)
        self.thread.start()
        logger.info(
            "Realtime checker started: interval=%ss, batch_size=%s",
            self.check_interval,
            self.batch_size,
        )
        return True

    def stop(self):
        if not self.running:
            logger.warning("Realtime checker not running")
            return False

        self.running = False
        self._stop_event.set()
        if self.thread:
            self.thread.join(timeout=5)
        logger.info("Realtime checker stopped")
        return True

    def get_runtime_status(self):
        with self._lock:
            return {
                "running": self.running,
                "check_interval": self.check_interval,
                "batch_size": self.batch_size,
                "eligible_count": len(self._eligible_accounts),
                "next_cursor": self._cursor,
                "last_round_started_at": self._last_round_started_at,
                "last_round_selected": list(self._last_round_selected),
            }

    def _collect_enabled_accounts(self):
        accounts = []
        users = self.db.get_users_with_realtime_check() or []
        for user in users:
            user_accounts = self.db.get_user_emails(user["id"]) or []
            for acc in user_accounts:
                accounts.append(acc)

        accounts.sort(key=lambda x: (x.get("user_id", 0), x.get("id", 0)))
        return accounts

    def _select_next_batch(self, accounts):
        if not accounts:
            return []

        total = len(accounts)
        if self._cursor >= total:
            self._cursor = 0

        start = self._cursor
        count = min(self.batch_size, total)
        indices = [(start + i) % total for i in range(count)]
        selected = [accounts[i] for i in indices]
        self._cursor = (start + count) % total
        return selected

    def _wait_next_round(self):
        # Wait in small steps so stop() can break promptly.
        for _ in range(self.check_interval):
            if not self.running or self._stop_event.is_set():
                break
            self._stop_event.wait(1)

    def _check_loop(self):
        while self.running and not self._stop_event.is_set():
            try:
                accounts = self._collect_enabled_accounts()
                with self._lock:
                    self._eligible_accounts = accounts

                if not accounts:
                    logger.info("No realtime-enabled email accounts")
                    self._wait_next_round()
                    continue

                selected = self._select_next_batch(accounts)
                round_started = datetime.now().isoformat()

                selected_info = [
                    {
                        "id": acc.get("id"),
                        "email": acc.get("email"),
                        "user_id": acc.get("user_id"),
                        "mail_type": acc.get("mail_type"),
                    }
                    for acc in selected
                ]
                with self._lock:
                    self._last_round_started_at = round_started
                    self._last_round_selected = selected_info

                logger.info(
                    "Realtime round started: selected=%s/%s, next_cursor=%s",
                    len(selected),
                    len(accounts),
                    self._cursor,
                )

                for account in selected:
                    if not self.running or self._stop_event.is_set():
                        break

                    account_id = account.get("id")
                    if not account_id:
                        continue

                    if self.email_processor.is_email_being_processed(account_id):
                        logger.info("Skip busy account id=%s email=%s", account_id, account.get("email"))
                        continue

                    self._submit_check_task(account)

                self._wait_next_round()
            except Exception as exc:
                logger.error("Realtime check loop error: %s", exc)
                self._wait_next_round()

    def _submit_check_task(self, account):
        account_id = account.get("id")

        def progress_callback(progress, message):
            logger.info("Realtime progress id=%s %s%% %s", account_id, progress, message)

        self.email_processor.realtime_thread_pool.submit(
            self.email_processor._check_email_task,
            account,
            progress_callback,
        )
        logger.info("Submitted realtime task: id=%s email=%s", account_id, account.get("email"))

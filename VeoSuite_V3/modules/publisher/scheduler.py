"""
VEO SUITE V3 — PublishScheduler
================================
Hàng đợi đăng tự động, lưu bền vững trong SQLite (bảng `publish_queue`).

Khác bản cũ:
- Queue lưu trong DB → không mất khi restart app.
- Tự retry tối đa 3 lần khi upload fail.
- Hỗ trợ nhiều platform qua dispatcher dict (chỉ cần khai báo callable).
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import datetime
from typing import Any

logger = logging.getLogger("VeoSuite.Publisher.Scheduler")

# Số lần retry tối đa cho 1 task trước khi mark 'failed'
MAX_ATTEMPTS = 3

# Khoảng thời gian giữa 2 lần quét queue (giây)
DEFAULT_POLL_SECONDS = 60


class PublishScheduler:
    """Quét bảng `publish_queue` và gọi uploader tương ứng theo platform."""

    def __init__(
        self,
        db_manager: Any,
        uploaders: dict[str, Callable[..., Any]] | None = None,
        poll_seconds: int = DEFAULT_POLL_SECONDS,
    ):
        """
        Args:
            db_manager: instance của DatabaseManager (cần các method
                ``list_publish_queue`` / ``update_publish_task``).
            uploaders:  dict {platform: uploader_obj}. Mỗi uploader_obj
                phải có method ``upload_video(channel_id, video_path,
                title, description, tags, privacy_status) -> (bool, str)``.
            poll_seconds: chu kỳ quét queue.
        """
        self.db = db_manager
        self.uploaders: dict[str, Any] = uploaders or {}
        self.poll_seconds = max(1, int(poll_seconds))
        self._running = False
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    # =====================================================================
    # Public API
    # =====================================================================

    def register_uploader(self, platform: str, uploader: Any) -> None:
        """Gắn uploader cho 1 platform (vd 'youtube', 'tiktok')."""
        self.uploaders[platform] = uploader
        logger.info("Registered uploader: %s", platform)

    def add_to_queue(
        self,
        platform: str,
        channel_id: str,
        video_path: str,
        title: str = "",
        description: str = "",
        tags: list | None = None,
        privacy_status: str = "private",
        schedule_time: str | None = None,
    ) -> int:
        """Thêm 1 task vào queue (bền vững trong SQLite)."""
        task_id = self.db.enqueue_publish(
            platform=platform,
            channel_id=channel_id,
            video_path=video_path,
            title=title,
            description=description,
            tags=tags,
            privacy_status=privacy_status,
            schedule_time=schedule_time,
        )
        logger.info(
            "Enqueued task #%d (%s -> %s) at %s",
            task_id,
            platform,
            channel_id,
            schedule_time or "now",
        )
        return task_id

    def list_queue(self, status: str | None = None) -> list:
        """Liệt kê queue (forward sang DB)."""
        return self.db.list_publish_queue(status=status)

    def start(self) -> None:
        """Khởi động worker thread."""
        if self._running:
            return
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, name="PublishScheduler", daemon=True)
        self._thread.start()
        logger.info("Scheduler started.")

    def stop(self, wait: bool = True, timeout: float = 5.0) -> None:
        """Dừng worker thread."""
        self._running = False
        self._stop_event.set()
        if wait and self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        logger.info("Scheduler stopped.")

    # =====================================================================
    # Internal worker
    # =====================================================================

    def _loop(self) -> None:
        """Vòng lặp chính: tick-poll queue và xử lý task tới hạn."""
        while self._running:
            try:
                self._tick()
            except Exception as e:
                logger.exception("Scheduler tick error: %s", e)
            # Chờ poll_seconds nhưng có thể bị stop_event đánh thức sớm
            self._stop_event.wait(self.poll_seconds)

    def _tick(self) -> None:
        """Một lần quét queue."""
        now = datetime.now()
        pending = self.db.list_publish_queue(status="pending")
        for task in pending:
            sched_str = task.get("schedule_time")
            if sched_str:
                try:
                    sched = datetime.fromisoformat(sched_str)
                except (ValueError, TypeError):
                    sched = now
            else:
                sched = now
            if sched > now:
                continue
            self._run_task(task)

    def _run_task(self, task: dict[str, Any]) -> None:
        """Chạy 1 task: gọi uploader, cập nhật DB."""
        task_id = int(task["id"])
        platform = task["platform"]
        uploader = self.uploaders.get(platform)
        if uploader is None:
            self.db.update_publish_task(
                task_id,
                status="failed",
                last_error=f"No uploader for platform '{platform}'",
            )
            logger.error("No uploader for platform=%s (task #%d)", platform, task_id)
            return

        attempts = int(task.get("attempts") or 0)
        if attempts >= MAX_ATTEMPTS:
            self.db.update_publish_task(
                task_id,
                status="failed",
                last_error=f"Exceeded MAX_ATTEMPTS ({MAX_ATTEMPTS})",
            )
            return

        self.db.update_publish_task(task_id, status="running")
        logger.info("Executing task #%d (%s)", task_id, task.get("title"))

        tags_csv = task.get("tags") or ""
        tags = [t.strip() for t in tags_csv.split(",") if t.strip()]

        ok, msg = False, "(no result)"
        try:
            ok, msg = uploader.upload_video(
                channel_id=task["channel_id"],
                video_path=task["video_path"],
                title=task.get("title") or "",
                description=task.get("description") or "",
                tags=tags,
                privacy_status=task.get("privacy_status") or "private",
            )
        except Exception as e:
            logger.exception("Upload exception (task #%d): %s", task_id, e)
            ok, msg = False, str(e)

        if ok:
            self.db.update_publish_task(
                task_id,
                status="done",
                result_url=msg,
                increment_attempts=True,
            )
            logger.info("Task #%d done -> %s", task_id, msg)
        else:
            new_status = "failed" if attempts + 1 >= MAX_ATTEMPTS else "pending"
            self.db.update_publish_task(
                task_id,
                status=new_status,
                last_error=msg,
                increment_attempts=True,
            )
            logger.warning(
                "Task #%d %s (attempt %d/%d): %s",
                task_id,
                new_status,
                attempts + 1,
                MAX_ATTEMPTS,
                msg,
            )

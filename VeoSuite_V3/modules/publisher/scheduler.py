
import os
import sys
import time
import json
import random
import requests
from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import *
from PyQt6.QtMultimedia import *

import threading
import time
import logging
from datetime import datetime

logger = logging.getLogger('VeoSuite.Publisher')

class PublishScheduler:
    """Module quản lý lịch phát hành tự động."""
    def __init__(self):
        self.queue = []
        self._running = False
        self._thread = None
        
    def add_to_queue(self, task):
        """Thêm task upload vào hàng đợi."""
        task['status'] = 'pending'
        self.queue.append(task)
        logger.info(f"Added task to queue. Total: {len(self.queue)}")
        
    def start(self):
        if self._running: return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("Scheduler started.")
        
    def stop(self):
        self._running = False
        
    def _loop(self):
        while self._running:
            now = datetime.now()
            for task in self.queue:
                if task['status'] == 'pending' and task['schedule_time'] <= now:
                    task['status'] = 'running'
                    logger.info(f"Executing scheduled task: {task['title']}")
                    # (Gọi YouTubeUploader ở đây)
                    time.sleep(1)
                    task['status'] = 'completed'
            time.sleep(60) # Check mỗi phút

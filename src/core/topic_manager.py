import os
import sqlite3
import logging
import datetime
from typing import Optional

from config import TOPIC_POOL_DB

logger = logging.getLogger(__name__)

class TopicManager:
    """
    轻量级 SQLite 主题库管理器，负责保存解析出的推文主题和随机抽取
    """
    def __init__(self, db_path: str = TOPIC_POOL_DB):
        self.db_path = db_path
        # Ensure the data directory exists
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        self._init_db()

    def _init_db(self):
        """初始化数据表"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS topics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic TEXT UNIQUE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_used TIMESTAMP
                )
            """)
            conn.commit()

    def add_topic(self, topic: str) -> bool:
        """
        向主题库中添加一个新主题。如果重复则忽略。
        返回 True 表示成功插入，False 表示已存在或其他错误。
        """
        topic = topic.strip()
        if not topic:
            return False

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                # 使用 INSERT OR IGNORE 防止重复插入
                cursor.execute(
                    "INSERT OR IGNORE INTO topics (topic) VALUES (?)",
                    (topic,)
                )
                conn.commit()
                # 如果 rowcount > 0 说明是真的插入了新条目
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"无法保存主题 '{topic}' 到数据库: {e}")
            return False

    def get_random_topic(self) -> Optional[str]:
        """
        从数据库中随机抽取一个主题，并更新其最后使用时间。
        避免总是选最近用过的主题。
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                # 随机抽取1条数据，偏好较少使用或未曾使用的主题
                # Order by random() for simple random extraction
                cursor.execute("""
                    SELECT id, topic FROM topics 
                    ORDER BY RANDOM() 
                    LIMIT 1
                """)
                row = cursor.fetchone()

                if not row:
                    return None

                topic_id, topic = row
                
                # 更新使用时间
                now = datetime.datetime.now().isoformat()
                cursor.execute(
                    "UPDATE topics SET last_used = ? WHERE id = ?",
                    (now, topic_id)
                )
                conn.commit()

                return topic
        except Exception as e:
            logger.error(f"从主题库随机读取主题失败: {e}")
            return None

    def get_stats(self) -> dict:
        """获取统计信息"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM topics")
                total = cursor.fetchone()[0]
                return {"total_topics": total}
        except Exception:
            return {"total_topics": 0}

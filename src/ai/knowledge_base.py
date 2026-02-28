"""
知识库模块

使用 ChromaDB 向量数据库 + sentence-transformers 嵌入模型，
将高质量推文存为"灵感素材"，支持语义检索用于原创内容生成。
"""

import json
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)


class KnowledgeBase:
    """推文灵感知识库（ChromaDB 向量存储）"""

    def __init__(self, db_path: str = None, embedding_model: str = None):
        from config import KB_PATH, KB_EMBEDDING_MODEL

        self._db_path = db_path or KB_PATH
        self._model_name = embedding_model or KB_EMBEDDING_MODEL
        self._client = None
        self._collection = None
        self._embedder = None

    def _ensure_initialized(self):
        """懒加载：首次调用时才初始化（避免 import 时就加载模型）"""
        if self._client is not None:
            return

        import chromadb
        from sentence_transformers import SentenceTransformer

        os.makedirs(self._db_path, exist_ok=True)

        logger.info(f"初始化知识库: {self._db_path}")
        self._client = chromadb.PersistentClient(path=self._db_path)
        self._collection = self._client.get_or_create_collection(
            name="xhs_inspirations",
            metadata={"hnsw:space": "cosine"},
        )

        logger.info(f"加载嵌入模型: {self._model_name}")
        self._embedder = SentenceTransformer(self._model_name)
        logger.info(f"知识库就绪，当前共 {self._collection.count()} 条素材")

    def add_tweet(self, tweet_data) -> bool:
        """
        将推文存入知识库。

        Args:
            tweet_data: scraper 返回的 TweetData 对象

        Returns:
            True 如果成功入库，False 如果已存在或失败
        """
        self._ensure_initialized()

        doc_id = f"tweet_{tweet_data.tweet_id}"

        # 检查是否已存在
        existing = self._collection.get(ids=[doc_id])
        if existing and existing["ids"]:
            logger.debug(f"推文 {tweet_data.tweet_id} 已在知识库中，跳过")
            return False

        # 构造文档文本（用于 embedding）
        text = tweet_data.text.strip()
        if not text:
            logger.debug(f"推文 {tweet_data.tweet_id} 无文本内容，跳过入库")
            return False

        doc = f"{text}"
        embedding = self._embedder.encode(doc).tolist()

        # 元数据
        metadata = {
            "author": tweet_data.author or "",
            "author_name": tweet_data.author_name or "",
            "tweet_id": tweet_data.tweet_id,
            "url": f"https://x.com/{tweet_data.author}/status/{tweet_data.tweet_id}",
            "image_count": len(tweet_data.image_urls),
            "video_count": len(tweet_data.video_urls),
            "favorite_count": tweet_data.favorite_count,
            "retweet_count": tweet_data.retweet_count,
            "reply_count": tweet_data.reply_count,
            "created_at": tweet_data.created_at or "",
            "ingested_at": datetime.now().isoformat(),
        }

        try:
            self._collection.add(
                documents=[doc],
                embeddings=[embedding],
                metadatas=[metadata],
                ids=[doc_id],
            )
            logger.info(
                f"📥 入库成功: @{tweet_data.author} — "
                f"{text[:50]}{'...' if len(text) > 50 else ''}"
            )
            return True
        except Exception as e:
            logger.warning(f"入库失败: {e}")
            return False

    def retrieve(self, query: str, n_results: int = 8) -> list[dict]:
        """
        语义检索最相关的 N 条素材。

        Args:
            query: 搜索主题（自然语言）
            n_results: 返回数量

        Returns:
            [{"text": ..., "author": ..., "url": ..., "favorite_count": ..., ...}, ...]
        """
        self._ensure_initialized()

        if self._collection.count() == 0:
            logger.warning("知识库为空，请先入库推文")
            return []

        # 限制检索数量不超过库存
        n_results = min(n_results, self._collection.count())

        embedding = self._embedder.encode(query).tolist()
        results = self._collection.query(
            query_embeddings=[embedding],
            n_results=n_results,
            include=["documents", "metadatas", "distances"],
        )

        inspirations = []
        for i in range(len(results["ids"][0])):
            item = {
                "text": results["documents"][0][i],
                "distance": results["distances"][0][i],
                **results["metadatas"][0][i],
            }
            inspirations.append(item)

        logger.info(f"检索到 {len(inspirations)} 条相关素材 (query: {query[:30]}...)")
        return inspirations

    def stats(self) -> dict:
        """返回知识库统计信息"""
        self._ensure_initialized()

        count = self._collection.count()
        info = {
            "total_items": count,
            "db_path": self._db_path,
            "embedding_model": self._model_name,
        }

        # 获取一些样本来统计作者分布
        if count > 0:
            sample_size = min(count, 1000)
            sample = self._collection.get(
                limit=sample_size,
                include=["metadatas"],
            )
            authors = {}
            for meta in sample["metadatas"]:
                author = meta.get("author", "unknown")
                authors[author] = authors.get(author, 0) + 1

            info["unique_authors"] = len(authors)
            info["top_authors"] = sorted(
                authors.items(), key=lambda x: x[1], reverse=True
            )[:10]

        return info


# --- 快速测试 ---
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
    )

    kb = KnowledgeBase()
    s = kb.stats()
    print(f"\n知识库统计:")
    print(f"  总条目: {s['total_items']}")
    print(f"  数据库路径: {s['db_path']}")
    print(f"  嵌入模型: {s['embedding_model']}")
    if s.get("top_authors"):
        print(f"  作者数: {s['unique_authors']}")
        print(f"  Top 作者:")
        for author, cnt in s["top_authors"]:
            print(f"    @{author}: {cnt} 条")

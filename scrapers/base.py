"""
需求驱动家纺生态系统 · 基础爬虫类

所有平台爬虫继承 BaseScraper，统一接口：
  - fetch() → list[dict]  归一化后的帖子数据
  - save(conn) → int      批量写入数据库
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Optional
import time
import json
from loguru import logger


@dataclass
class RawPost:
    """归一化帖子数据结构"""
    source: str              # reddit / pinterest / twitter / tiktok
    source_id: str           # 平台原始 ID
    title: str = ""
    content: str = ""
    url: str = ""
    author: str = ""
    score: int = 0
    num_comments: int = 0
    created_utc: int = 0
    tags: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    image_url: str = ""
    batch_id: str = ""
    search_keyword: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["created_utc"] = self.created_utc or int(time.time())
        return d


class BaseScraper(ABC):
    """爬虫基类"""

    def __init__(self, config: dict):
        self.config = config
        self.source_name = ""  # 子类覆写

    @abstractmethod
    def fetch(self) -> list[RawPost]:
        """抓取并返回归一化的帖子列表"""
        ...

    def save(self, conn) -> int:
        """批量写入数据库，返回写入数"""
        from db.database import insert_raw_post
        posts = []  # 子类应该在 fetch 中填充
        count = 0
        for post in posts:
            if insert_raw_post(conn, post.to_dict()):
                count += 1
        return count

    def canonicalize(self, raw: dict) -> RawPost:
        """子类覆写，将平台原始数据转为 RawPost"""
        raise NotImplementedError

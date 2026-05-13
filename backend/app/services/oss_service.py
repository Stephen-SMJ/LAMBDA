"""阿里云 OSS 存储服务"""

import oss2
import io
from typing import Optional, BinaryIO
from pathlib import Path
from datetime import datetime, timedelta
from app.core.config import settings
import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from urllib.parse import unquote, urlparse


class OSSService:
    """阿里云 OSS 存储服务"""
    
    def __init__(self):
        self.access_key_id = settings.ALIYUN_OSS_ACCESS_KEY_ID
        self.access_key_secret = settings.ALIYUN_OSS_ACCESS_KEY_SECRET
        self.bucket_name = settings.ALIYUN_OSS_BUCKET_NAME
        self.endpoint = settings.ALIYUN_OSS_ENDPOINT
        self.base_url = settings.ALIYUN_OSS_BASE_URL
        
        # 初始化 OSS 客户端
        self.auth = oss2.Auth(self.access_key_id, self.access_key_secret)
        self.bucket = oss2.Bucket(self.auth, self.endpoint, self.bucket_name)
        
        # 线程池用于异步操作
        self.executor = ThreadPoolExecutor(max_workers=10)
    
    async def upload_file(
        self, 
        file_data: bytes, 
        object_name: str, 
        content_type: Optional[str] = None
    ) -> str:
        """
        上传文件到 OSS
        
        Args:
            file_data: 文件二进制数据
            object_name: OSS 对象名称（路径）
            content_type: 文件 MIME 类型
            
        Returns:
            文件的 OSS URL
        """
        headers = None
        if content_type:
            headers = {'Content-Type': content_type}
        
        loop = asyncio.get_event_loop()
        
        # 使用 partial 来传递 kwargs
        if headers:
            func = partial(self.bucket.put_object, object_name, file_data, headers=headers)
        else:
            func = partial(self.bucket.put_object, object_name, file_data)
        
        await loop.run_in_executor(self.executor, func)
        
        return f"{self.base_url}/{object_name}"
    
    async def upload_file_from_path(
        self, 
        file_path: str, 
        object_name: Optional[str] = None
    ) -> str:
        """
        从本地路径上传文件到 OSS
        
        Args:
            file_path: 本地文件路径
            object_name: OSS 对象名称，默认使用文件名
            
        Returns:
            文件的 OSS URL
        """
        path = Path(file_path)
        if not object_name:
            object_name = f"uploads/{path.name}"
        
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            self.executor,
            partial(self.bucket.put_object_from_file, object_name, str(file_path))
        )
        
        return f"{self.base_url}/{object_name}"
    
    async def download_file(self, object_name: str) -> bytes:
        """
        从 OSS 下载文件
        
        Args:
            object_name: OSS 对象名称
            
        Returns:
            文件二进制数据
        """
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            self.executor,
            partial(self.bucket.get_object, object_name)
        )
        return result.read()
    
    async def delete_file(self, object_name: str) -> bool:
        """
        从 OSS 删除文件
        
        Args:
            object_name: OSS 对象名称
            
        Returns:
            是否删除成功
        """
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            self.executor,
            partial(self.bucket.delete_object, object_name)
        )
        return True
    
    async def file_exists(self, object_name: str) -> bool:
        """
        检查文件是否存在
        
        Args:
            object_name: OSS 对象名称
            
        Returns:
            文件是否存在
        """
        loop = asyncio.get_event_loop()
        exists = await loop.run_in_executor(
            self.executor,
            partial(self.bucket.object_exists, object_name)
        )
        return exists
    
    def get_object_name_from_url(self, url: str) -> str:
        """
        从 URL 中提取 OSS 对象名称
        
        Args:
            url: OSS URL
            
        Returns:
            对象名称
        """
        clean_url = (url or "").split("?", 1)[0]
        base_url = (self.base_url or "").rstrip("/")

        if clean_url.startswith(base_url + "/"):
            return unquote(clean_url[len(base_url) + 1:])

        parsed = urlparse(clean_url)
        if parsed.scheme in {"http", "https"}:
            bucket_host = f"{self.bucket_name}."
            if parsed.netloc.startswith(bucket_host) or parsed.netloc == urlparse(base_url).netloc:
                return unquote(parsed.path.lstrip("/"))

        return unquote(clean_url)
    
    async def generate_upload_url(
        self, 
        object_name: str, 
        expires: int = 3600,
        content_type: Optional[str] = None
    ) -> str:
        """
        生成临时上传 URL（用于前端直传）
        
        Args:
            object_name: OSS 对象名称
            expires: URL 过期时间（秒）
            content_type: 限制上传的文件类型
            
        Returns:
            临时上传 URL
        """
        headers = None
        if content_type:
            headers = {'Content-Type': content_type}
        
        loop = asyncio.get_event_loop()
        
        # 使用 lambda 来传递 kwargs
        if headers:
            func = partial(self.bucket.sign_url, 'PUT', object_name, expires, headers=headers)
        else:
            func = partial(self.bucket.sign_url, 'PUT', object_name, expires)
        
        url = await loop.run_in_executor(self.executor, func)
        return url
    
    async def generate_download_url(self, object_name: str, expires: int = 3600) -> str:
        """
        生成临时下载 URL
        
        Args:
            object_name: OSS 对象名称
            expires: URL 过期时间（秒）
            
        Returns:
            临时下载 URL (HTTPS)
        """
        loop = asyncio.get_event_loop()
        url = await loop.run_in_executor(
            self.executor,
            partial(self.bucket.sign_url, 'GET', object_name, expires)
        )
        # 强制使用 HTTPS 避免 Mixed Content 问题
        if url.startswith('http://'):
            url = 'https://' + url[7:]
        return url


# 全局 OSS 服务实例
_oss_service: Optional[OSSService] = None


def get_oss_service() -> OSSService:
    """获取 OSS 服务实例"""
    global _oss_service
    if _oss_service is None:
        _oss_service = OSSService()
    return _oss_service

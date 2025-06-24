import re
import asyncio
import subprocess
import json
import os
import tempfile
import logging
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse
from abc import ABC, abstractmethod

from models import Platform, VideoInfo, VideoQuality, CreatorInfo, CreatorVideoItem, CreatorVideosResponse

logger = logging.getLogger(__name__)

# 简单配置
TEMP_DIR = "./temp"
DOWNLOAD_TIMEOUT = 300  # 5分钟


def safe_decode(data, encoding='utf-8'):
    """安全解码字节数据"""
    if isinstance(data, bytes):
        return data.decode(encoding, errors='ignore')
    return str(data)


class VideoDownloader(ABC):
    """视频下载器基类"""
    
    @abstractmethod
    async def get_video_info(self, url: str) -> VideoInfo:
        """获取视频信息"""
        pass
    
    @abstractmethod
    async def download_video(self, url: str, quality: VideoQuality = VideoQuality.WORST) -> str:
        """下载视频，返回文件路径"""
        pass
    
    @abstractmethod
    def supports_url(self, url: str) -> bool:
        """检查是否支持该URL"""
        pass


class BilibiliDownloader(VideoDownloader):
    """Bilibili视频下载器 (仅支持单视频下载)"""
    
    def supports_url(self, url: str) -> bool:
        bilibili_patterns = [
            r'bilibili\.com/video/',  # 只支持单个视频链接
            r'b23\.tv',
            r'acg\.tv'
        ]
        return any(re.search(pattern, url) for pattern in bilibili_patterns)
    
    async def get_video_info(self, url: str) -> VideoInfo:
        """使用you-get获取单个视频信息"""
        try:
            cmd = ["you-get", "--json", url]
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                error_msg = safe_decode(stderr)
                raise Exception(f"you-get failed: {error_msg}")
            
            info = json.loads(safe_decode(stdout))
            
            return VideoInfo(
                title=info.get("title", "Unknown"),
                platform=Platform.BILIBILI,
                url=url,
                thumbnail=info.get("thumbnail"),
                uploader=info.get("uploader"),
                duration=info.get("duration"),
                formats=info.get("streams", {})
            )
        except Exception as e:
            logger.error(f"Failed to get Bilibili video info: {e}")
            raise
    
    async def download_video(self, url: str, quality: VideoQuality = VideoQuality.WORST) -> str:
        """下载单个Bilibili视频"""
        try:
            # 创建临时目录
            temp_dir = tempfile.mkdtemp(dir=TEMP_DIR)
            
            # 简化下载命令，不指定格式，让you-get自动选择最佳可用格式
            cmd = ["you-get", "-o", temp_dir, url]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), 
                timeout=DOWNLOAD_TIMEOUT
            )
            
            if process.returncode != 0:
                error_msg = safe_decode(stderr)
                raise Exception(f"Download failed: {error_msg}")
            
            # 查找下载的文件
            files = os.listdir(temp_dir)
            video_files = [f for f in files if f.endswith(('.mp4', '.flv', '.mkv'))]
            
            if not video_files:
                raise Exception("No video file found after download")
            
            return os.path.join(temp_dir, video_files[0])
            
        except asyncio.TimeoutError:
            raise Exception("Download timeout")
        except Exception as e:
            logger.error(f"Failed to download Bilibili video: {e}")
            raise


class TikTokDownloader(VideoDownloader):
    """TikTok视频下载器 (使用yt-dlp)"""
    
    def supports_url(self, url: str) -> bool:
        tiktok_patterns = [
            r'tiktok\.com',
            r'vm\.tiktok\.com',
            r'vt\.tiktok\.com',
            r'm\.tiktok\.com'
        ]
        return any(re.search(pattern, url, re.IGNORECASE) for pattern in tiktok_patterns)
    
    async def get_video_info(self, url: str) -> VideoInfo:
        """使用yt-dlp获取视频信息"""
        try:
            # TikTok需要特殊处理，添加user-agent和其他参数，尝试多种配置
            configs = [
                {
                    "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15",
                    "extra_args": ["--extractor-args", "tiktok:api_hostname=api.tiktokv.com"]
                },
                {
                    "user_agent": "Mozilla/5.0 (Linux; Android 10; SM-G973F) AppleWebKit/537.36",
                    "extra_args": ["--no-check-certificate"]
                },
                {
                    "user_agent": "TikTok/1.0",
                    "extra_args": ["--extractor-args", "tiktok:webpage_download=false"]
                }
            ]
            
            for i, config in enumerate(configs, 1):
                try:
                    logger.info(f"尝试配置 {i} 获取TikTok视频信息")
                    cmd = [
                        "yt-dlp", 
                        "--dump-json", 
                        "--no-download",
                        "--socket-timeout", "30",
                        "--retries", "3",
                        "--user-agent", config["user_agent"]
                    ] + config["extra_args"] + [url]
                    
                    process = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    
                    try:
                        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=60)
                    except asyncio.TimeoutError:
                        process.kill()
                        logger.warning(f"配置 {i} 超时")
                        continue
                    
                    if process.returncode == 0:
                        info = json.loads(safe_decode(stdout))
                        logger.info(f"配置 {i} 成功获取视频信息")
                        
                        return VideoInfo(
                            title=info.get("title", "Unknown"),
                            platform=Platform.TIKTOK,
                            url=url,
                            thumbnail=info.get("thumbnail"),
                            uploader=info.get("uploader"),
                            duration=info.get("duration"),
                            view_count=info.get("view_count"),
                            upload_date=info.get("upload_date"),
                            formats=info.get("formats", [])
                        )
                    else:
                        error_msg = safe_decode(stderr)
                        logger.warning(f"配置 {i} 失败: {error_msg}")
                        
                except Exception as e:
                    logger.warning(f"配置 {i} 异常: {e}")
                    continue
            
            # 所有配置都失败
            raise Exception("所有配置都无法获取TikTok视频信息")
            
        except Exception as e:
            logger.error(f"Failed to get TikTok video info: {e}")
            raise
    
    async def download_video(self, url: str, quality: VideoQuality = VideoQuality.WORST) -> str:
        """下载TikTok视频"""
        logger.info(f"开始下载TikTok视频: {url}, 质量: {quality}")
        
        try:
            # 创建临时目录
            temp_dir = tempfile.mkdtemp(dir=TEMP_DIR)
            logger.info(f"创建临时目录: {temp_dir}")
            
            # 优化的下载配置，减少超时时间和重试次数
            cmd = [
                "yt-dlp", 
                "-o", f"{temp_dir}/%(title).50s.%(ext)s",  # 限制文件名长度
                "-f", "worst[ext=mp4]/worst",  # 优先选择mp4格式的最低质量
                "--socket-timeout", "20",  # 缩短socket超时
                "--retries", "2",  # 减少重试次数
                "--fragment-retries", "2",  # 减少片段重试
                "--no-warnings",  # 减少输出
                "--no-playlist",  # 确保只下载单个视频
                "--user-agent", "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15",
                url
            ]
            
            logger.info(f"执行下载命令: {' '.join(cmd[:8])}...")  # 只记录部分命令
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            try:
                # 设置更短的总超时时间
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), 
                    timeout=180  # 3分钟超时
                )
            except asyncio.TimeoutError:
                process.kill()
                logger.error(f"TikTok视频下载超时: {url}")
                raise Exception("下载超时，请稍后重试或选择其他视频")
            
            stdout_str = safe_decode(stdout)
            stderr_str = safe_decode(stderr)
            
            if process.returncode != 0:
                logger.error(f"yt-dlp下载失败，返回码: {process.returncode}")
                logger.error(f"错误输出: {stderr_str[:200]}")
                raise Exception(f"视频下载失败: {stderr_str[:100]}")
            
            # 查找下载的文件
            try:
                files = os.listdir(temp_dir)
                video_files = [f for f in files if f.lower().endswith(('.mp4', '.webm', '.mkv', '.m4v', '.flv'))]
                
                if not video_files:
                    logger.error(f"下载完成但未找到视频文件，目录内容: {files}")
                    raise Exception("下载完成但未找到视频文件")
                
                file_path = os.path.join(temp_dir, video_files[0])
                file_size = os.path.getsize(file_path)
                logger.info(f"成功下载视频: {video_files[0]}, 大小: {file_size} bytes")
                
                return file_path
                
            except Exception as e:
                logger.error(f"处理下载文件时出错: {e}")
                raise Exception(f"文件处理失败: {str(e)}")
            
        except Exception as e:
            logger.error(f"TikTok视频下载失败: {url}, 错误: {str(e)}")
            # 清理可能创建的临时目录
            try:
                if 'temp_dir' in locals() and os.path.exists(temp_dir):
                    import shutil
                    shutil.rmtree(temp_dir)
            except:
                pass
            raise
    
    async def get_creator_videos(self, creator_url: str, max_count: int = 20) -> CreatorVideosResponse:
        """获取TikTok博主视频列表"""
        logger.info(f"处理TikTok用户链接: {creator_url}")
        
        # 尝试从URL中提取用户名
        username = self._extract_username_from_url(creator_url)
        if not username:
            logger.warning(f"无法从URL中提取用户名: {creator_url}")
            return self._create_empty_response(creator_url)
        
        logger.info(f"处理TikTok用户: {username}, 最大获取数量: {max_count}")
        
        try:
            cmd = [
                "yt-dlp",
                "--flat-playlist",
                "--dump-json",
                "--playlist-end", str(max_count),
                "--user-agent", "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15",
                "--socket-timeout", "15",  # 缩短超时时间
                "--retries", "1",  # 减少重试次数
                "--no-warnings",  # 减少输出
                creator_url
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            try:
                # 缩短总超时时间，避免长时间阻塞
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=60)
            except asyncio.TimeoutError:
                process.kill()
                logger.warning(f"yt-dlp执行超时: {creator_url}")
                return self._create_error_response(creator_url, "请求超时，请稍后重试")
            
            if process.returncode != 0:
                error_msg = safe_decode(stderr)
                logger.warning(f"yt-dlp执行失败: {error_msg}")
                return self._create_error_response(creator_url, f"无法获取视频列表: {error_msg[:50]}")
            
            # 解析输出
            output = safe_decode(stdout).strip()
            if not output:
                return self._create_empty_response(creator_url)
            
            lines = output.split('\n')
            videos = []
            creator_info = None
            
            for line in lines:
                if line.strip():
                    try:
                        info = json.loads(line)
                        
                        # 创建者信息
                        if creator_info is None:
                            creator_info = CreatorInfo(
                                name=info.get("uploader", "Unknown"),
                                platform=Platform.TIKTOK,
                                profile_url=creator_url,
                                avatar=info.get("uploader_avatar"),
                                follower_count=info.get("uploader_follower_count")
                            )
                        
                        video_item = CreatorVideoItem(
                            title=info.get("title", "Unknown"),
                            url=info.get("url", f"https://www.tiktok.com/@{info.get('uploader', '')}/video/{info.get('id', '')}"),
                            thumbnail=info.get("thumbnail"),
                            duration=info.get("duration"),
                            view_count=info.get("view_count"),
                            upload_date=info.get("upload_date")
                        )
                        videos.append(video_item)
                    except json.JSONDecodeError as e:
                        logger.debug(f"JSON解析失败: {e}, 内容: {line[:100]}")
                        continue
            
            # 如果没有获取到创建者信息，使用默认值
            if creator_info is None:
                creator_info = CreatorInfo(
                    name="Unknown Creator",
                    platform=Platform.TIKTOK,
                    profile_url=creator_url
                )
            
            logger.info(f"成功获取到 {len(videos)} 个视频,creator_info: {creator_info}")
            return CreatorVideosResponse(
                creator_info=creator_info,
                videos=videos,
                total_count=len(videos),
                has_more=False
            )
            
        except Exception as e:
            logger.error(f"获取TikTok用户视频失败: {e}")
            return self._create_error_response(creator_url, f"服务暂不可用: {str(e)[:50]}")
    
    def _extract_username_from_url(self, url: str) -> Optional[str]:
        """从TikTok URL中提取用户名"""
        import re
        patterns = [
            r'tiktok\.com/@([^/?]+)',
            r'tiktok\.com/([^/@?]+)',
            r'vm\.tiktok\.com/([^/?]+)',
            r'vt\.tiktok\.com/([^/?]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None
    
    def _create_empty_response(self, creator_url: str) -> CreatorVideosResponse:
        """创建空的响应"""
        return CreatorVideosResponse(
            creator_info=CreatorInfo(
                name="Unknown Creator",
                platform=Platform.TIKTOK,
                profile_url=creator_url
            ),
            videos=[],
            total_count=0,
            has_more=False
        )
    
    def _create_error_response(self, creator_url: str, error_msg: str) -> CreatorVideosResponse:
        """创建错误响应"""
        return CreatorVideosResponse(
            creator_info=CreatorInfo(
                name="服务暂不可用",
                platform=Platform.TIKTOK,
                profile_url=creator_url,
                description=error_msg
            ),
            videos=[],
            total_count=0,
            has_more=False
        )


class VideoService:
    """视频服务主类"""
    
    def __init__(self):
        self.downloaders = [
            BilibiliDownloader(),
            TikTokDownloader()
        ]
    
    def detect_platform(self, url: str) -> Platform:
        """检测视频平台"""
        for downloader in self.downloaders:
            if downloader.supports_url(url):
                if isinstance(downloader, BilibiliDownloader):
                    return Platform.BILIBILI
                elif isinstance(downloader, TikTokDownloader):
                    return Platform.TIKTOK
        return Platform.UNKNOWN
    
    def _get_downloader(self, url: str) -> Optional[VideoDownloader]:
        """获取对应的下载器"""
        for downloader in self.downloaders:
            if downloader.supports_url(url):
                return downloader
        return None
    
    async def get_video_info(self, url: str) -> VideoInfo:
        """获取视频信息"""
        downloader = self._get_downloader(url)
        if not downloader:
            raise Exception(f"Unsupported platform for URL: {url}")
        
        return await downloader.get_video_info(url)
    
    async def download_video(self, url: str, quality: VideoQuality = VideoQuality.WORST) -> str:
        """下载视频"""
        downloader = self._get_downloader(url)
        if not downloader:
            raise Exception(f"Unsupported platform for URL: {url}")
        
        return await downloader.download_video(url, quality)
    
    async def get_creator_videos(self, creator_url: str, max_count: int = 20) -> CreatorVideosResponse:
        """获取博主视频列表 - 仅支持TikTok"""
        # 检查是否是B站博主页面
        if re.search(r'space\.bilibili\.com|bilibili\.com/(?:v/|u/)', creator_url):
            # B站不支持批量获取，返回提示信息
            return CreatorVideosResponse(
                creator_info=CreatorInfo(
                    name="B站用户",
                    platform=Platform.BILIBILI,
                    profile_url=creator_url,
                    description="抱歉，B站由于反爬虫机制限制，不支持自动批量获取视频列表。建议手动复制视频链接使用单个下载功能。"
                ),
                videos=[
                    CreatorVideoItem(
                        title="💡 建议使用单个视频下载功能",
                        url="例如: https://www.bilibili.com/video/BV1xx411c7mu",
                        description="复制单个视频链接，使用 /api/v1/video/download 接口下载"
                    )
                ],
                total_count=1,
                has_more=False
            )
        
        # 检查是否是TikTok博主页面
        if re.search(r'tiktok\.com/@', creator_url):
            downloader = next((d for d in self.downloaders if isinstance(d, TikTokDownloader)), None)
            if downloader:
                return await downloader.get_creator_videos(creator_url, max_count)
        
        # 不支持的平台
        raise Exception(f"不支持的平台或URL格式: {creator_url}")
    
    def _get_downloader_by_creator_url(self, creator_url: str) -> Optional[VideoDownloader]:
        """根据博主URL获取对应的下载器 - 仅支持TikTok"""
        # 只支持TikTok博主页面
        if re.search(r'tiktok\.com/@', creator_url):
            return next((d for d in self.downloaders if isinstance(d, TikTokDownloader)), None)
        
        return None


# 全局实例
video_service = VideoService()

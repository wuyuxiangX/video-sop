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

# 使用命令行 yt-dlp 进行视频处理
from concurrent.futures import ThreadPoolExecutor

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
    async def download_video(self, url: str, quality: VideoQuality = VideoQuality.WORST) -> str:
        """下载视频，返回文件路径"""
        pass
    
    @abstractmethod
    def supports_url(self, url: str) -> bool:
        """检查是否支持该URL"""
        pass


class BilibiliDownloader(VideoDownloader):
    """Bilibili视频下载器 (使用yt-dlp)"""
    
    def supports_url(self, url: str) -> bool:
        bilibili_patterns = [
            r'bilibili\.com/video/',  # 单个视频链接
            r'space\.bilibili\.com',  # 用户空间
            r'bilibili\.com/(?:v/|u/)',  # 其他格式
            r'b23\.tv',
            r'acg\.tv'
        ]
        return any(re.search(pattern, url) for pattern in bilibili_patterns)
    

    
    async def download_video(self, url: str, quality: VideoQuality = VideoQuality.WORST) -> str:
        """使用yt-dlp命令行下载Bilibili视频"""
        logger.info(f"开始下载Bilibili视频: {url}, 质量: {quality}")
        
        try:
            # 创建临时目录
            temp_dir = tempfile.mkdtemp(dir=TEMP_DIR)
            logger.info(f"创建临时目录: {temp_dir}")
            
            # 构建命令行参数
            cmd = [
                'yt-dlp',
                '-f', 'worstvideo+worstaudio',  # 直接使用最低质量
                '-o', f'{temp_dir}/%(title).50s.%(ext)s',  # 输出文件名模板
                '--no-warnings',  # 不显示警告
                '--merge-output-format', 'mp4',  # 合并为mp4格式
                url
            ]
            
            logger.info(f"执行命令: {' '.join(cmd)}")
            
            # 使用线程池执行命令行下载
            def run_download():
                try:
                    result = subprocess.run(
                        cmd, 
                        capture_output=True, 
                        text=True, 
                        timeout=DOWNLOAD_TIMEOUT,
                        encoding='utf-8'
                    )
                    
                    if result.returncode != 0:
                        logger.error(f"yt-dlp命令失败: {result.stderr}")
                        raise Exception(f"Bilibili下载失败: {result.stderr}")
                    
                    logger.info("yt-dlp命令执行成功")
                    
                    # 查找下载的文件
                    files = os.listdir(temp_dir)
                    video_files = [f for f in files if f.lower().endswith(('.mp4', '.flv', '.mkv', '.webm'))]
                    
                    if not video_files:
                        logger.error(f"下载完成但未找到视频文件，目录内容: {files}")
                        raise Exception("下载完成但未找到视频文件")
                    
                    file_path = os.path.join(temp_dir, video_files[0])
                    file_size = os.path.getsize(file_path)
                    
                    if file_size == 0:
                        logger.error(f"下载的文件为空: {video_files[0]}")
                        raise Exception("下载的文件为空")
                    
                    logger.info(f"成功下载Bilibili视频: {video_files[0]}, 大小: {file_size} bytes")
                    return file_path
                    
                except subprocess.TimeoutExpired:
                    logger.error("yt-dlp命令执行超时")
                    raise Exception("下载超时，请稍后重试或选择其他视频")
                except Exception as e:
                    logger.error(f"命令执行异常: {e}")
                    raise
            
            # 使用线程池异步执行下载
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(run_download)
                file_path = await asyncio.wrap_future(future)
                return file_path
                    
        except Exception as e:
            logger.error(f"Bilibili视频下载失败: {url}, 错误: {str(e)}")
            # 清理可能创建的临时目录
            try:
                if 'temp_dir' in locals() and os.path.exists(temp_dir):
                    import shutil
                    shutil.rmtree(temp_dir)
            except:
                pass
            raise
    
    async def get_creator_videos(self, creator_url: str, max_count: int = 20) -> CreatorVideosResponse:
        """获取Bilibili博主视频列表 - 使用命令行版本"""
        logger.info(f"处理Bilibili用户链接: {creator_url}")
        
        try:
            import subprocess
            import json
            
            # 🎯 使用命令行版本 - 基于用户提供的工作示例
            cmd = [
                'yt-dlp', 
                '-J',  # 输出JSON
                '--flat-playlist',  # 扁平化播放列表
                '-I', f'1-{max_count}',  # 限制数量
                creator_url
            ]
            
            logger.info(f"执行命令: {' '.join(cmd)}")
            
            # 使用线程池执行命令行
            def run_command():
                try:
                    result = subprocess.run(
                        cmd, 
                        capture_output=True, 
                        text=True, 
                        timeout=60,  # 60秒超时
                        encoding='utf-8'
                    )
                    if result.returncode == 0:
                        return json.loads(result.stdout)
                    else:
                        logger.error(f"yt-dlp命令失败: {result.stderr}")
                        return None
                except Exception as e:
                    logger.error(f"命令执行异常: {e}")
                    return None
            
            # 异步执行
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(run_command)
                try:
                    info = await asyncio.wait_for(
                        asyncio.wrap_future(future), 
                        timeout=90  # 总超时90秒
                    )
                except asyncio.TimeoutError:
                    logger.warning(f"命令执行超时: {creator_url}")
                    return self._create_error_response(creator_url, "请求超时，请稍后重试", Platform.BILIBILI)
            
            if not info:
                logger.warning(f"无法获取Bilibili播放列表信息: {creator_url}")
                return self._create_error_response(creator_url, "无法获取视频列表", Platform.BILIBILI)
            
            # 解析结果 - Bilibili返回简单的URL列表
            videos = []
            entries = info.get('entries', [])
            
            if not entries:
                logger.warning("entries为空")
                return self._create_empty_response(creator_url, Platform.BILIBILI)
            
            # 创建者信息
            creator_info = CreatorInfo(
                name="Bilibili用户",  # Bilibili命令行版本通常不返回详细信息
                platform=Platform.BILIBILI,
                profile_url=creator_url
            )
            
            # 处理视频条目 - Bilibili格式相对简单
            for entry in entries[:max_count]:
                try:
                    if isinstance(entry, dict):
                        video_url = entry.get('url', '')
                        bv_id = entry.get('id', '')
                        
                        video_item = CreatorVideoItem(
                            title=f"Bilibili视频 {bv_id}",  # 简化标题
                            url=video_url,
                            bv_id=bv_id
                        )
                        videos.append(video_item)
                        logger.debug(f"添加Bilibili视频: {bv_id}")
                        
                except Exception as e:
                    logger.warning(f"处理Bilibili视频条目失败: {e}")
                    continue
            
            logger.info(f"成功获取到 {len(videos)} 个Bilibili视频")
            return CreatorVideosResponse(
                creator_info=creator_info,
                videos=videos,
                total_count=len(videos),
                has_more=len(entries) > max_count
            )
            
        except Exception as e:
            logger.error(f"获取Bilibili用户视频失败: {e}")
            return self._create_error_response(creator_url, f"服务暂不可用: {str(e)[:50]}", Platform.BILIBILI)
    
    def _create_empty_response(self, creator_url: str, platform: Platform) -> CreatorVideosResponse:
        """创建空的响应"""
        return CreatorVideosResponse(
            creator_info=CreatorInfo(
                name="Unknown Creator",
                platform=platform,
                profile_url=creator_url
            ),
            videos=[],
            total_count=0,
            has_more=False
        )
    
    def _create_error_response(self, creator_url: str, error_msg: str, platform: Platform) -> CreatorVideosResponse:
        """创建错误响应"""
        return CreatorVideosResponse(
            creator_info=CreatorInfo(
                name="服务暂不可用",
                platform=platform,
                profile_url=creator_url,
                description=error_msg
            ),
            videos=[],
            total_count=0,
            has_more=False
        )


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
    

    
    async def download_video(self, url: str, quality: VideoQuality = VideoQuality.WORST) -> str:
        """使用yt-dlp命令行下载TikTok视频"""
        logger.info(f"开始下载TikTok视频: {url}, 质量: {quality}")
        
        try:
            # 创建临时目录
            temp_dir = tempfile.mkdtemp(dir=TEMP_DIR)
            logger.info(f"创建临时目录: {temp_dir}")
            
            # 构建命令行参数
            cmd = [
                'yt-dlp',
                '-f', 'worst',  # 直接使用最低质量
                '-o', f'{temp_dir}/%(title).50s.%(ext)s',  # 输出文件名模板
                '--no-warnings',  # 不显示警告
                '--merge-output-format', 'mp4',  # 合并为mp4格式
                url
            ]
            
            logger.info(f"执行命令: {' '.join(cmd)}")
            
            # 使用线程池执行命令行下载
            def run_download():
                try:
                    result = subprocess.run(
                        cmd, 
                        capture_output=True, 
                        text=True, 
                        timeout=120,  # 2分钟超时，适合TikTok
                        encoding='utf-8'
                    )
                    
                    if result.returncode != 0:
                        logger.error(f"yt-dlp命令失败: {result.stderr}")
                        raise Exception(f"TikTok下载失败: {result.stderr}")
                    
                    logger.info("yt-dlp命令执行成功")
                    
                    # 查找下载的文件
                    files = os.listdir(temp_dir)
                    video_files = [f for f in files if f.lower().endswith(('.mp4', '.webm', '.mkv', '.m4v', '.flv'))]
                    
                    if not video_files:
                        logger.error(f"下载完成但未找到视频文件，目录内容: {files}")
                        raise Exception("下载完成但未找到视频文件")
                    
                    file_path = os.path.join(temp_dir, video_files[0])
                    file_size = os.path.getsize(file_path)
                    
                    if file_size == 0:
                        logger.error(f"下载的文件为空: {video_files[0]}")
                        raise Exception("下载的文件为空")
                    
                    logger.info(f"成功下载TikTok视频: {video_files[0]}, 大小: {file_size} bytes")
                    return file_path
                    
                except subprocess.TimeoutExpired:
                    logger.error("yt-dlp命令执行超时")
                    raise Exception("下载超时，请稍后重试或选择其他视频")
                except Exception as e:
                    logger.error(f"命令执行异常: {e}")
                    raise
            
            # 使用线程池异步执行下载
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(run_download)
                file_path = await asyncio.wrap_future(future)
                return file_path
            
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
        """获取TikTok博主视频列表 - 使用命令行版本"""
        logger.info(f"处理TikTok用户链接: {creator_url}")
        
        try:
            import subprocess
            import json
            
            # 🎯 使用命令行版本 - 基于用户提供的工作示例
            cmd = [
                'yt-dlp', 
                '-J',  # 输出JSON
                '--flat-playlist',  # 扁平化播放列表
                '-I', f'1-{max_count}',  # 限制数量
                creator_url
            ]
            
            logger.info(f"执行命令: {' '.join(cmd)}")
            
            # 使用线程池执行命令行
            def run_command():
                try:
                    result = subprocess.run(
                        cmd, 
                        capture_output=True, 
                        text=True, 
                        timeout=60,  # 60秒超时
                        encoding='utf-8'
                    )
                    if result.returncode == 0:
                        return json.loads(result.stdout)
                    else:
                        logger.error(f"yt-dlp命令失败: {result.stderr}")
                        return None
                except Exception as e:
                    logger.error(f"命令执行异常: {e}")
                    return None
            
            # 异步执行
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(run_command)
                try:
                    info = await asyncio.wait_for(
                        asyncio.wrap_future(future), 
                        timeout=90  # 总超时90秒
                    )
                except asyncio.TimeoutError:
                    logger.warning(f"命令执行超时: {creator_url}")
                    return self._create_error_response(creator_url, "请求超时，请稍后重试")
            
            if not info:
                logger.warning(f"无法获取TikTok播放列表信息: {creator_url}")
                return self._create_error_response(creator_url, "无法获取视频列表")
            
            # 解析结果 - TikTok返回详细的视频信息
            videos = []
            entries = info.get('entries', [])
            
            if not entries:
                logger.warning("entries为空")
                return self._create_empty_response(creator_url)
            
            # 创建者信息 - 从主信息或第一个视频获取
            creator_name = info.get('title', 'TikTok用户')
            if entries and len(entries) > 0:
                first_entry = entries[0]
                creator_name = first_entry.get('channel', first_entry.get('uploader', creator_name))
            
            creator_info = CreatorInfo(
                name=creator_name,
                platform=Platform.TIKTOK,
                profile_url=creator_url
            )
            
            # 处理视频条目 - TikTok格式包含丰富信息
            for entry in entries[:max_count]:
                try:
                    if isinstance(entry, dict):
                        # 处理数值字段
                        duration = entry.get("duration")
                        if duration is not None and isinstance(duration, (int, float)):
                            duration = int(duration)
                        
                        view_count = entry.get("view_count")
                        if view_count is not None and isinstance(view_count, (int, float)):
                            view_count = int(view_count)
                        
                        # 获取缩略图
                        thumbnails = entry.get("thumbnails", [])
                        thumbnail_url = None
                        if thumbnails:
                            # 选择第一个可用的缩略图
                            thumbnail_url = thumbnails[0].get("url") if len(thumbnails) > 0 else None
                        
                        # 处理upload_date - TikTok返回整数时间戳，需要转换为字符串
                        upload_date = entry.get("timestamp")
                        if upload_date is not None and isinstance(upload_date, (int, float)):
                            upload_date = str(int(upload_date))
                        
                        video_item = CreatorVideoItem(
                            title=entry.get("title", "TikTok视频"),
                            url=entry.get("url", ""),
                            thumbnail=thumbnail_url,
                            duration=duration,
                            view_count=view_count,
                            upload_date=upload_date
                        )
                        videos.append(video_item)
                        logger.debug(f"添加TikTok视频: {video_item.title[:30]}")
                        
                except Exception as e:
                    logger.warning(f"处理TikTok视频条目失败: {e}")
                    continue
            
            logger.info(f"成功获取到 {len(videos)} 个TikTok视频")
            return CreatorVideosResponse(
                creator_info=creator_info,
                videos=videos,
                total_count=len(videos),
                has_more=len(entries) > max_count
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


class YouTubeDownloader(VideoDownloader):
    """YouTube视频下载器 (使用yt-dlp)"""
    
    def supports_url(self, url: str) -> bool:
        youtube_patterns = [
            r'youtube\.com',
            r'youtu\.be',
            r'm\.youtube\.com',
            r'www\.youtube\.com'
        ]
        return any(re.search(pattern, url, re.IGNORECASE) for pattern in youtube_patterns)
    

    
    async def download_video(self, url: str, quality: VideoQuality = VideoQuality.WORST) -> str:
        """使用yt-dlp命令行下载YouTube视频"""
        logger.info(f"开始下载YouTube视频: {url}, 质量: {quality}")
        
        try:
            # 创建临时目录
            temp_dir = tempfile.mkdtemp(dir=TEMP_DIR)
            logger.info(f"创建临时目录: {temp_dir}")
            
            # 构建命令行参数
            cmd = [
                'yt-dlp',
                '-f', 'worst',  # 直接使用最低质量
                '-o', f'{temp_dir}/%(title).50s.%(ext)s',  # 输出文件名模板
                '--no-warnings',  # 不显示警告
                url
            ]
            
            # 检查是否有cookie文件，如果有则添加cookie参数
            cookie_file_path = "./cookies.txt"
            if os.path.exists(cookie_file_path):
                cmd.extend(['--cookies', cookie_file_path])
                logger.info("使用cookie文件进行认证")
            
            logger.info(f"执行命令: {' '.join(cmd)}")
            
            # 使用线程池执行命令行下载
            def run_download():
                try:
                    result = subprocess.run(
                        cmd, 
                        capture_output=True, 
                        text=True, 
                        timeout=DOWNLOAD_TIMEOUT,  # 使用全局超时设置
                        encoding='utf-8'
                    )
                    
                    if result.returncode != 0:
                        logger.error(f"yt-dlp命令失败: {result.stderr}")
                        raise Exception(f"下载失败: {result.stderr}")
                    
                    logger.info("yt-dlp命令执行成功")
                    
                    # 查找下载的文件
                    files = os.listdir(temp_dir)
                    video_files = [f for f in files if f.lower().endswith(('.mp4', '.webm', '.mkv', '.m4v', '.flv', '.avi'))]
                    
                    if not video_files:
                        logger.error(f"下载完成但未找到视频文件，目录内容: {files}")
                        raise Exception("下载完成但未找到视频文件")
                    
                    file_path = os.path.join(temp_dir, video_files[0])
                    file_size = os.path.getsize(file_path)
                    
                    if file_size == 0:
                        logger.error(f"下载的文件为空: {video_files[0]}")
                        raise Exception("下载的文件为空")
                    
                    logger.info(f"成功下载YouTube视频: {video_files[0]}, 大小: {file_size} bytes")
                    return file_path
                    
                except subprocess.TimeoutExpired:
                    logger.error("yt-dlp命令执行超时")
                    raise Exception("下载超时")
                except Exception as e:
                    logger.error(f"命令执行异常: {e}")
                    raise
            
            # 使用线程池异步执行下载
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(run_download)
                file_path = await asyncio.wrap_future(future)
                return file_path
                
        except Exception as e:
            logger.error(f"YouTube视频下载失败: {url}, 错误: {str(e)}")
            # 清理可能创建的临时目录
            try:
                if 'temp_dir' in locals() and os.path.exists(temp_dir):
                    import shutil
                    shutil.rmtree(temp_dir)
            except:
                pass
            raise
    
    async def get_creator_videos(self, creator_url: str, max_count: int = 20) -> CreatorVideosResponse:
        """获取YouTube频道视频列表 - 使用命令行版本"""
        logger.info(f"处理YouTube频道链接: {creator_url}")
        
        try:
            import subprocess
            import json
            
            # 🎯 使用命令行版本 - 基于用户提供的工作示例
            cmd = [
                'yt-dlp', 
                '-J',  # 输出JSON
                '--flat-playlist',  # 扁平化播放列表
                '-I', f'1-{max_count}',  # 限制数量
                creator_url
            ]
            
            logger.info(f"执行命令: {' '.join(cmd)}")
            
            # 使用线程池执行命令行
            def run_command():
                try:
                    result = subprocess.run(
                        cmd, 
                        capture_output=True, 
                        text=True, 
                        timeout=60,  # 60秒超时
                        encoding='utf-8'
                    )
                    if result.returncode == 0:
                        return json.loads(result.stdout)
                    else:
                        logger.error(f"yt-dlp命令失败: {result.stderr}")
                        return None
                except Exception as e:
                    logger.error(f"命令执行异常: {e}")
                    return None
            
            # 异步执行
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(run_command)
                try:
                    info = await asyncio.wait_for(
                        asyncio.wrap_future(future), 
                        timeout=90  # 总超时90秒
                    )
                except asyncio.TimeoutError:
                    logger.warning(f"命令执行超时: {creator_url}")
                    return self._create_error_response(creator_url, "请求超时，请稍后重试", Platform.YOUTUBE)
            
            if not info:
                logger.warning(f"无法获取YouTube频道信息: {creator_url}")
                return self._create_error_response(creator_url, "无法获取视频列表", Platform.YOUTUBE)
            
            # 解析结果 - YouTube返回复杂的嵌套结构
            videos = []
            entries = info.get('entries', [])
            
            if not entries:
                logger.warning("entries为空")
                return self._create_empty_response(creator_url, Platform.YOUTUBE)
            
            # 创建者信息 - 从主信息获取
            creator_name = info.get('channel', info.get('uploader', 'YouTube用户'))
            follower_count = info.get('channel_follower_count')
            if follower_count is not None and isinstance(follower_count, (int, float)):
                follower_count = int(follower_count)
            
            creator_info = CreatorInfo(
                name=creator_name,
                platform=Platform.YOUTUBE,
                profile_url=creator_url,
                follower_count=follower_count
            )
            
            # 处理YouTube的嵌套结构
            for main_entry in entries:
                if isinstance(main_entry, dict) and main_entry.get('_type') == 'playlist':
                    # YouTube返回嵌套的playlist结构，需要提取内部的entries
                    sub_entries = main_entry.get('entries', [])
                    logger.info(f"找到YouTube子播放列表，包含 {len(sub_entries)} 个视频")
                    
                    for entry in sub_entries[:max_count]:
                        try:
                            if isinstance(entry, dict):
                                # 处理数值字段
                                duration = entry.get("duration")
                                if duration is not None and isinstance(duration, (int, float)):
                                    duration = int(duration)
                                
                                view_count = entry.get("view_count")
                                if view_count is not None and isinstance(view_count, (int, float)):
                                    view_count = int(view_count)
                                
                                # 获取缩略图
                                thumbnails = entry.get("thumbnails", [])
                                thumbnail_url = None
                                if thumbnails:
                                    # 选择合适分辨率的缩略图
                                    for thumb in thumbnails:
                                        if thumb.get("height", 0) >= 138:  # 选择较高质量的缩略图
                                            thumbnail_url = thumb.get("url")
                                            break
                                    if not thumbnail_url and thumbnails:
                                        thumbnail_url = thumbnails[0].get("url")
                                
                                video_item = CreatorVideoItem(
                                    title=entry.get("title", "YouTube视频"),
                                    url=entry.get("url", ""),
                                    thumbnail=thumbnail_url,
                                    duration=duration,
                                    view_count=view_count
                                )
                                videos.append(video_item)
                                logger.debug(f"添加YouTube视频: {video_item.title[:30]}")
                                
                        except Exception as e:
                            logger.warning(f"处理YouTube视频条目失败: {e}")
                            continue
            
            logger.info(f"成功获取到 {len(videos)} 个YouTube视频")
            return CreatorVideosResponse(
                creator_info=creator_info,
                videos=videos,
                total_count=len(videos),
                has_more=False  # 命令行版本已经限制了数量
            )
            
        except Exception as e:
            logger.error(f"获取YouTube频道视频失败: {e}")
            return self._create_error_response(creator_url, f"服务暂不可用: {str(e)[:50]}", Platform.YOUTUBE)
    
    def _create_empty_response(self, creator_url: str, platform: Platform) -> CreatorVideosResponse:
        """创建空的响应"""
        return CreatorVideosResponse(
            creator_info=CreatorInfo(
                name="Unknown Creator",
                platform=platform,
                profile_url=creator_url
            ),
            videos=[],
            total_count=0,
            has_more=False
        )
    
    def _create_error_response(self, creator_url: str, error_msg: str, platform: Platform) -> CreatorVideosResponse:
        """创建错误响应"""
        return CreatorVideosResponse(
            creator_info=CreatorInfo(
                name="服务暂不可用",
                platform=platform,
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
            TikTokDownloader(),
            YouTubeDownloader()
        ]
    
    def normalize_input(self, input_str: str) -> str:
        """
        将用户名或简化URL标准化为完整的URL，支持多平台
        
        平台前缀规则：
        - # 开头 → YouTube 
        - @ 开头 → TikTok
        - 。开头 → Bilibili
        """
        input_str = input_str.strip()
        
        # 如果已经是完整的URL，直接返回
        if input_str.startswith(('http://', 'https://')):
            return input_str
        
        # 根据前缀符号判断平台
        if input_str.startswith('#'):
            # YouTube: #username
            return self._normalize_youtube_input(input_str)
        elif input_str.startswith('@'):
            # TikTok: @username  
            return self._normalize_tiktok_input(input_str)
        elif input_str.startswith('。'):
            # Bilibili: 。username
            return self._normalize_bilibili_input(input_str)
        
        # 无前缀的情况，尝试通过URL内容判断
        if self._is_youtube_input(input_str):
            return self._normalize_youtube_input(input_str)
        elif self._is_bilibili_input(input_str):
            return self._normalize_bilibili_input(input_str)
        
        # 默认作为TikTok处理（向后兼容）
        return self._normalize_tiktok_input(input_str)
    
    def _is_youtube_input(self, input_str: str) -> bool:
        """判断是否是YouTube输入"""
        # 检查前缀符号
        if input_str.startswith('#'):
            return True
        
        # 检查是否包含YouTube特征
        youtube_indicators = [
            'youtube.com',
            'youtu.be', 
            '/watch?v=',
            '/channel/',
            '/c/',
        ]
        
        # 如果包含明确的YouTube标识
        for indicator in youtube_indicators:
            if indicator in input_str.lower():
                return True
            
        return False
    
    def _is_bilibili_input(self, input_str: str) -> bool:
        """判断是否是Bilibili输入"""
        # 检查前缀符号
        if input_str.startswith('。'):
            return True
        
        # 检查是否包含Bilibili特征
        bilibili_indicators = [
            'bilibili.com',
            'space.bilibili.com',
            'b23.tv'
        ]
        
        for indicator in bilibili_indicators:
            if indicator in input_str.lower():
                return True
            
        return False
    
    def _normalize_youtube_input(self, input_str: str) -> str:
        """标准化YouTube输入 - 只处理#前缀或明确的YouTube URL"""
        import re
        
        # 🚨 重要：此函数只应处理 # 前缀的输入，@ 前缀应该被TikTok处理！
        
        # 处理 # 前缀格式
        if input_str.startswith('#'):
            # 移除#前缀，获取实际内容
            content = input_str[1:].strip()
            
            # 如果包含watch?v=，需要提取真正的视频ID
            if 'watch?v=' in content:
                # 使用正则提取视频ID：从 raycastapp/watch?v=A0tCQ3FDzcs 中提取 A0tCQ3FDzcs
                video_id_match = re.search(r'watch\?v=([a-zA-Z0-9_-]+)', content)
                if video_id_match:
                    video_id = video_id_match.group(1)
                    return f"https://www.youtube.com/watch?v={video_id}"
                else:
                    # 如果提取失败，尝试直接处理
                    return f"https://www.youtube.com/{content}"
            
            # 如果是纯视频ID（11位字符）
            elif len(content) == 11 and re.match(r'^[a-zA-Z0-9_-]+$', content):
                return f"https://www.youtube.com/watch?v={content}"
            
            # 🎯 用户频道处理 - 直接生成频道页面URL（不加/videos后缀，让get_creator_videos方法处理）
            elif content.startswith('@'):
                return f"https://www.youtube.com/{content}"
            else:
                return f"https://www.youtube.com/@{content}"
        
        # 处理明确的YouTube URL（无前缀但包含YouTube特征）
        if 'watch?v=' in input_str or 'youtu.be/' in input_str:
            if not input_str.startswith(('http://', 'https://')):
                return f"https://www.youtube.com/{input_str}"
        
        # 处理明确的YouTube频道URL
        if input_str.startswith('@') and ('youtube.com' in input_str or 'youtu.be' in input_str):
            return f"https://www.youtube.com/{input_str}"
        
        # ❌ 如果到这里，说明输入不是YouTube格式，不应该处理
        # 这种情况不应该发生，因为调用此函数前应该已经判断过是YouTube
        return f"https://www.youtube.com/@{input_str}"
    
    def _normalize_bilibili_input(self, input_str: str) -> str:
        """标准化Bilibili输入 - 简化版本"""
        # 处理 。前缀格式
        if input_str.startswith('。'):
            # 移除。前缀，获取实际内容
            content = input_str[1:].strip()
            
            # 如果是纯数字，说明是用户ID
            if content.isdigit():
                return f"https://space.bilibili.com/{content}"
            # 如果是BV开头，说明是视频ID
            elif content.startswith('BV'):
                return f"https://www.bilibili.com/video/{content}/"
            # 其他情况，默认作为用户ID
            else:
                return f"https://space.bilibili.com/{content}"
        
        # 无前缀的情况，保持原有逻辑
        if input_str.isdigit():
            return f"https://space.bilibili.com/{input_str}"
        elif input_str.startswith('BV'):
            return f"https://www.bilibili.com/video/{input_str}/"
        elif 'space.bilibili.com' in input_str:
            if not input_str.startswith(('http://', 'https://')):
                return f"https://{input_str}"
            return input_str
        elif 'bilibili.com/video' in input_str:
            if not input_str.startswith(('http://', 'https://')):
                return f"https://www.{input_str}"
            return input_str
        else:
            # 默认作为用户ID处理
            return f"https://space.bilibili.com/{input_str}"
    
    def _normalize_tiktok_input(self, input_str: str) -> str:
        """标准化TikTok输入"""
        # 如果包含video/，说明是视频URL格式
        if '/video/' in input_str:
            # 处理 @username/video/123456 格式
            if input_str.startswith('@'):
                return f"https://www.tiktok.com/{input_str}"
            else:
                # 处理 username/video/123456 格式
                return f"https://www.tiktok.com/@{input_str}"
        
        # 如果以@开头，移除@
        if input_str.startswith('@'):
            input_str = input_str[1:]
        
        # 拼接成完整的TikTok用户页面URL
        return f"https://www.tiktok.com/@{input_str}"
    
    # 向后兼容
    def normalize_tiktok_input(self, input_str: str) -> str:
        """向后兼容的方法"""
        return self.normalize_input(input_str)
    
    def detect_platform(self, url: str) -> Platform:
        """检测视频平台"""
        for downloader in self.downloaders:
            if downloader.supports_url(url):
                if isinstance(downloader, BilibiliDownloader):
                    return Platform.BILIBILI
                elif isinstance(downloader, TikTokDownloader):
                    return Platform.TIKTOK
                elif isinstance(downloader, YouTubeDownloader):
                    return Platform.YOUTUBE
        return Platform.UNKNOWN
    
    def _get_downloader(self, url: str) -> Optional[VideoDownloader]:
        """获取对应的下载器"""
        for downloader in self.downloaders:
            if downloader.supports_url(url):
                return downloader
        return None
    

    
    async def download_video(self, url: str, quality: VideoQuality = VideoQuality.WORST) -> str:
        """下载视频，返回文件路径"""
        logger.info(f"开始下载视频: {url}")
        
        # 规范化URL - 使用新的通用方法
        normalized_url = self.normalize_input(url)
        logger.info(f"规范化URL: {url} -> {normalized_url}")
        
        downloader = self._get_downloader(normalized_url)
        if not downloader:
            raise Exception(f"Unsupported platform for URL: {normalized_url}")
        
        return await downloader.download_video(normalized_url, quality)
    
    async def get_creator_videos(self, creator_url: str, max_count: int = 20) -> CreatorVideosResponse:
        """获取博主视频列表 - 支持多平台用户名和URL"""
        logger.info(f"原始输入: {creator_url}")
        
        # 首先规范化输入（处理多平台用户名）
        normalized_url = self.normalize_input(creator_url)
        logger.info(f"规范化后URL: {normalized_url}")
        
        # 根据平台检测选择对应的下载器
        platform = self.detect_platform(normalized_url)
        logger.info(f"检测到平台: {platform}")
        
        # 查找对应的下载器
        downloader = None
        for d in self.downloaders:
            if isinstance(d, BilibiliDownloader) and platform == Platform.BILIBILI:
                downloader = d
                break
            elif isinstance(d, TikTokDownloader) and platform == Platform.TIKTOK:
                downloader = d
                break
            elif isinstance(d, YouTubeDownloader) and platform == Platform.YOUTUBE:
                downloader = d
                break
        
        if downloader and hasattr(downloader, 'get_creator_videos'):
            return await downloader.get_creator_videos(normalized_url, max_count)
        
        # 不支持的平台或该平台不支持获取创作者视频
        raise Exception(f"不支持的平台或该平台不支持获取创作者视频: {creator_url} (平台: {platform})")
    
    def _get_downloader_by_creator_url(self, creator_url: str) -> Optional[VideoDownloader]:
        """根据博主URL获取对应的下载器 - 仅支持TikTok"""
        # 只支持TikTok博主页面
        if re.search(r'tiktok\.com/@', creator_url):
            return next((d for d in self.downloaders if isinstance(d, TikTokDownloader)), None)
        
        return None


# 全局实例
video_service = VideoService()

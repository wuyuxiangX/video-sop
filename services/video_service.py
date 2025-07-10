"""
视频下载服务 - 基于video-downloader设计，支持base64编码的URL
优先下载Audio Only，如果不支持则下载最低质量视频
"""

import asyncio
import subprocess
import json
import os
import tempfile
import logging
import base64
import shutil
from typing import Optional, Dict, Any, List
from concurrent.futures import ThreadPoolExecutor

from models import Platform, VideoQuality, CreatorInfo, CreatorVideoItem, CreatorVideosResponse

logger = logging.getLogger(__name__)

# 配置常量
TEMP_DIR = "./temp"
DOWNLOAD_TIMEOUT = 300

# 支持的媒体文件扩展名
AUDIO_EXTENSIONS = ['.mp3', '.m4a', '.aac', '.ogg', '.opus', '.wav', '.flac']
VIDEO_EXTENSIONS = ['.mp4', '.webm', '.mkv', '.m4v', '.flv', '.avi', '.mov']
ALL_MEDIA_EXTENSIONS = AUDIO_EXTENSIONS + VIDEO_EXTENSIONS


def validate_executables() -> bool:
    """验证必要的可执行文件是否存在"""
    required_tools = ['yt-dlp', 'ffmpeg', 'ffprobe']
    missing_tools = []
    
    for tool in required_tools:
        result = subprocess.run(['which', tool], capture_output=True, text=True)
        if result.returncode != 0:
            missing_tools.append(tool)
    
    if missing_tools:
        logger.error(f"缺少必要工具: {', '.join(missing_tools)}")
        return False
    
    logger.info("所有必要工具已安装")
    return True


def decode_base64_url(input_str: str) -> str:
    """解码base64编码的URL"""
    try:
        # 检查是否为base64编码
        if not is_base64_encoded(input_str):
            return input_str
            
        decoded_bytes = base64.b64decode(input_str)
        decoded_str = decoded_bytes.decode('utf-8')
        logger.info(f"成功解码base64 URL: {decoded_str}")
        return decoded_str
    except Exception as e:
        logger.debug(f"base64解码失败: {e}")
        return input_str


def is_base64_encoded(input_str: str) -> bool:
    """检查字符串是否为base64编码"""
    try:
        # 基本格式检查
        if len(input_str) % 4 != 0 or len(input_str) < 8:
            return False
            
        # 检查字符集
        import string
        base64_chars = string.ascii_letters + string.digits + '+/='
        if not all(c in base64_chars for c in input_str):
            return False
            
        # 尝试解码
        decoded = base64.b64decode(input_str, validate=True).decode('utf-8')
        
        # 检查解码后的内容是否包含URL特征
        url_patterns = ['http://', 'https://', '.com', '.tv', '.net', '.org', '.co']
        return any(pattern in decoded.lower() for pattern in url_patterns)
        
    except Exception:
        return False


def ensure_temp_dir() -> str:
    """确保临时目录存在"""
    if not os.path.exists(TEMP_DIR):
        os.makedirs(TEMP_DIR, exist_ok=True)
    return TEMP_DIR


def cleanup_temp_files(temp_dir: str):
    """清理临时文件"""
    try:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
            logger.debug(f"清理临时目录: {temp_dir}")
    except Exception as e:
        logger.warning(f"清理临时目录失败: {e}")


def detect_platform(url: str) -> Platform:
    """检测视频平台"""
    url_lower = url.lower()
    
    if any(pattern in url_lower for pattern in ['bilibili.com', 'b23.tv']):
        return Platform.BILIBILI
    elif any(pattern in url_lower for pattern in ['youtube.com', 'youtu.be']):
        return Platform.YOUTUBE
    elif any(pattern in url_lower for pattern in ['tiktok.com']):
        return Platform.TIKTOK
    
    return Platform.UNKNOWN


class VideoService:
    """视频服务主类 - 简化版本，专注于base64编码URL下载"""
    
    def __init__(self):
        # 验证依赖
        validate_executables()
        logger.info("VideoService 初始化完成")
    
    def normalize_input(self, input_str: str) -> str:
        """标准化输入 - 仅支持base64解码"""
        input_str = input_str.strip()
        
        # 尝试base64解码
        decoded_input = decode_base64_url(input_str)
        if decoded_input != input_str:
            logger.info(f"检测到base64编码，已解码")
            return decoded_input
        
        # 如果不是base64，直接返回（假设是完整URL）
        return input_str
    
    async def get_video_info(self, url: str) -> Dict[str, Any]:
        """获取视频信息"""
        try:
            cmd = [
                'yt-dlp',
                '--dump-json',
                '--format-sort=resolution,ext,tbr',
                url
            ]
            
            logger.info(f"获取视频信息: {url}")
            
            def run_command():
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=60,
                    encoding='utf-8'
                )
                if result.returncode != 0:
                    raise Exception(f"获取视频信息失败: {result.stderr}")
                return json.loads(result.stdout)
            
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(run_command)
                return await asyncio.wrap_future(future)
                
        except Exception as e:
            logger.error(f"获取视频信息失败: {e}")
            raise
    
    def select_best_format(self, video_info: Dict[str, Any]) -> str:
        """选择最佳格式 - 优先Audio Only，否则最低质量视频"""
        formats_data = video_info.get('formats', [])
        if not formats_data:
            return 'bestaudio/worst'
        
        # 分类格式
        audio_only_formats = []
        video_formats = []
        
        for fmt in formats_data:
            vcodec = fmt.get('vcodec', '')
            acodec = fmt.get('acodec', '')
            
            has_video = vcodec and vcodec != 'none'
            has_audio = acodec and acodec != 'none'
            
            if has_audio and not has_video:
                audio_only_formats.append(fmt)
            elif has_video:
                video_formats.append(fmt)
        
        # 优先选择音频格式
        if audio_only_formats:
            best_audio = max(audio_only_formats, key=lambda x: x.get('tbr', 0) or 0)
            logger.info(f"选择音频格式: {best_audio.get('format_id')} ({best_audio.get('ext')})")
            return best_audio.get('format_id', 'bestaudio')
        
        # 选择最低质量视频
        if video_formats:
            video_formats.sort(key=lambda x: (
                x.get('height', 0) or 0,
                x.get('width', 0) or 0,
                x.get('tbr', 0) or 0
            ))
            worst_video = video_formats[0]
            format_selector = worst_video.get('format_id', 'worst')
            
            # 如果视频没有音频，添加最佳音频
            if not (worst_video.get('acodec') and worst_video.get('acodec') != 'none'):
                format_selector += '+bestaudio'
            
            logger.info(f"选择视频格式: {format_selector}")
            return format_selector
        
        return 'bestaudio/worst'
    
    async def download_video(self, url: str, quality: VideoQuality = VideoQuality.WORST) -> str:
        """下载视频 - 优先Audio Only"""
        logger.info(f"开始下载视频: {url}")
        
        # 标准化URL（base64解码）
        normalized_url = self.normalize_input(url)
        
        # 检测平台
        platform = detect_platform(normalized_url)
        logger.info(f"检测到平台: {platform}")
        
        temp_dir = None
        try:
            # 创建临时目录
            ensure_temp_dir()
            temp_dir = tempfile.mkdtemp(dir=TEMP_DIR)
            
            # 获取视频信息
            video_info = await self.get_video_info(normalized_url)
            
            # 检查是否为直播
            if video_info.get('live_status') not in [None, 'not_live']:
                raise Exception("不支持直播流下载")
            
            # 选择格式
            format_selector = self.select_best_format(video_info)
            
            # 执行下载
            cmd = [
                'yt-dlp',
                '-P', temp_dir,
                '-f', format_selector,
                '-o', '%(title).50s.%(ext)s',
                '--print', 'after_move:filepath',
                '--no-warnings',
                normalized_url
            ]
            
            # 添加cookie支持
            cookie_file = "./cookies.txt"
            if os.path.exists(cookie_file):
                cmd.extend(['--cookies', cookie_file])
            
            logger.info(f"执行下载: {format_selector}")
            
            def run_download():
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=DOWNLOAD_TIMEOUT,
                    encoding='utf-8'
                )
                
                if result.returncode != 0:
                    raise Exception(f"下载失败: {result.stderr}")
                
                # 提取文件路径
                output_lines = result.stdout.strip().split('\n')
                file_path = None
                
                for line in output_lines:
                    if line.startswith('/') and os.path.exists(line):
                        file_path = line
                        break
                
                if not file_path:
                    # 查找下载的文件
                    files = os.listdir(temp_dir)
                    media_files = [f for f in files if any(f.lower().endswith(ext) for ext in ALL_MEDIA_EXTENSIONS)]
                    
                    if not media_files:
                        raise Exception("下载完成但未找到媒体文件")
                    
                    file_path = os.path.join(temp_dir, media_files[0])
                
                # 验证文件
                if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
                    raise Exception("下载的文件无效或为空")
                
                logger.info(f"下载成功: {os.path.basename(file_path)} ({os.path.getsize(file_path)} bytes)")
                return file_path
            
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(run_download)
                file_path = await asyncio.wrap_future(future)
                
            logger.info(f"视频下载成功: {os.path.basename(file_path)}")
            return file_path
            
        except Exception as e:
            logger.error(f"视频下载失败: {e}")
            if temp_dir and os.path.exists(temp_dir):
                cleanup_temp_files(temp_dir)
            raise
    
    async def get_creator_videos(self, creator_url: str, max_count: int = 20) -> CreatorVideosResponse:
        """获取创作者视频列表"""
        logger.info(f"获取创作者视频: {creator_url}")
        
        # 标准化URL（base64解码）
        normalized_url = self.normalize_input(creator_url)
        
        # 检测平台
        platform = detect_platform(normalized_url)
        logger.info(f"检测到平台: {platform}")
        
        try:
            cmd = [
                'yt-dlp',
                '-J',
                '--flat-playlist',
                '-I', f'1-{max_count}',
                normalized_url
            ]
            
            def run_command():
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=90,
                    encoding='utf-8'
                )
                if result.returncode == 0:
                    return json.loads(result.stdout)
                else:
                    logger.error(f"命令失败: {result.stderr}")
                    return None
            
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(run_command)
                try:
                    info = await asyncio.wait_for(asyncio.wrap_future(future), timeout=120)
                except asyncio.TimeoutError:
                    return self._create_error_response(creator_url, "请求超时", platform)
            
            if not info:
                return self._create_error_response(creator_url, "无法获取视频列表", platform)
            
            # 解析结果
            return self._parse_playlist_info(info, creator_url, platform, max_count)
            
        except Exception as e:
            logger.error(f"获取创作者视频失败: {e}")
            return self._create_error_response(creator_url, str(e), platform)
    
    def _parse_playlist_info(self, info: Dict[str, Any], url: str, platform: Platform, max_count: int) -> CreatorVideosResponse:
        """解析播放列表信息"""
        videos: List[CreatorVideoItem] = []
        entries = info.get('entries', [])
        
        if not entries:
            return self._create_empty_response(url, platform)
        
        # 创建者信息
        creator_name = info.get('channel', info.get('uploader', info.get('title', '未知创作者')))
        
        creator_info = CreatorInfo(
            name=creator_name,
            platform=platform,
            profile_url=url
        )
        
        # 处理视频条目
        for entry in entries[:max_count]:
            try:
                if isinstance(entry, dict):
                    # 处理嵌套结构（如YouTube）
                    if entry.get('_type') == 'playlist':
                        sub_entries = entry.get('entries', [])
                        for sub_entry in sub_entries[:max_count - len(videos)]:
                            video_item = self._create_video_item(sub_entry, platform)
                            if video_item:
                                videos.append(video_item)
                    else:
                        video_item = self._create_video_item(entry, platform)
                        if video_item:
                            videos.append(video_item)
                            
            except Exception as e:
                logger.warning(f"处理视频条目失败: {e}")
                continue
        
        logger.info(f"成功获取到 {len(videos)} 个视频")
        return CreatorVideosResponse(
            creator_info=creator_info,
            videos=videos,
            total_count=len(videos),
            has_more=len(entries) > max_count
        )
    
    def _create_video_item(self, entry: Dict[str, Any], platform: Platform) -> Optional[CreatorVideoItem]:
        """创建视频项目"""
        try:
            video_item = CreatorVideoItem(
                title=entry.get("title", "未知标题"),
                url=entry.get("url", ""),
                thumbnail=None,
                duration=entry.get("duration") if isinstance(entry.get("duration"), (int, float)) else None,
                view_count=entry.get("view_count") if isinstance(entry.get("view_count"), (int, float)) else None
            )
            
            # 处理缩略图
            thumbnails = entry.get("thumbnails", [])
            if thumbnails:
                for thumb in thumbnails:
                    if thumb.get("height", 0) >= 120:
                        video_item.thumbnail = thumb.get("url")
                        break
                if not video_item.thumbnail and thumbnails:
                    video_item.thumbnail = thumbnails[0].get("url")
            
            # Bilibili特殊处理
            if platform == Platform.BILIBILI:
                video_item.bv_id = entry.get("id", "")
            
            return video_item
            
        except Exception as e:
            logger.warning(f"创建视频项目失败: {e}")
            return None
    
    def _create_empty_response(self, url: str, platform: Platform) -> CreatorVideosResponse:
        """创建空响应"""
        return CreatorVideosResponse(
            creator_info=CreatorInfo(
                name="未知创作者",
                platform=platform,
                profile_url=url
            ),
            videos=[],
            total_count=0,
            has_more=False
        )
    
    def _create_error_response(self, url: str, error_msg: str, platform: Platform) -> CreatorVideosResponse:
        """创建错误响应"""
        return CreatorVideosResponse(
            creator_info=CreatorInfo(
                name="服务暂不可用",
                platform=platform,
                profile_url=url,
                description=error_msg
            ),
            videos=[],
            total_count=0,
            has_more=False
        )


# 全局实例
video_service = VideoService()

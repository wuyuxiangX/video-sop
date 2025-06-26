#!/usr/bin/env python3
"""
YouTube认证测试脚本
用于验证cookies配置是否正确
"""

import os
import sys
import asyncio
import logging

# 添加项目路径到sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.video_service import VideoService

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def test_youtube_auth():
    """测试YouTube认证"""
    print("🔍 YouTube认证测试开始...")
    
    # 检查cookie文件
    cookie_file = "./cookies.txt"
    if os.path.exists(cookie_file):
        print(f"✅ 发现cookie文件: {cookie_file}")
        file_size = os.path.getsize(cookie_file)
        print(f"   文件大小: {file_size} bytes")
    else:
        print(f"⚠️  未找到cookie文件: {cookie_file}")
        print("   将使用无cookies模式测试")
    
    # 创建视频服务实例
    video_service = VideoService()
    
    # 测试YouTube视频
    test_videos = [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",  # 经典测试视频
        "#dQw4w9WgXcQ",  # 简化格式
    ]
    
    for i, test_url in enumerate(test_videos, 1):
        print(f"\n🧪 测试 {i}: {test_url}")
        try:
            # 标准化URL
            normalized_url = video_service.normalize_input(test_url)
            print(f"   标准化URL: {normalized_url}")
            
            # 获取视频信息
            print("   正在获取视频信息...")
            video_info = await video_service.get_video_info(normalized_url)
            
            print(f"✅ 成功获取视频信息!")
            print(f"   标题: {video_info.title}")
            print(f"   上传者: {video_info.uploader}")
            print(f"   时长: {video_info.duration}秒")
            print(f"   观看次数: {video_info.view_count}")
            
            return True
            
        except Exception as e:
            print(f"❌ 测试失败: {str(e)}")
            if "Sign in to confirm you're not a bot" in str(e):
                print("   → 这是认证问题，需要配置cookies")
            elif "cookiefile" in str(e).lower():
                print("   → cookie文件可能有问题")
            continue
    
    return False

def check_environment():
    """检查环境"""
    print("🔧 环境检查...")
    
    # 检查yt-dlp
    try:
        import yt_dlp
        print(f"✅ yt-dlp: 已安装")
    except ImportError:
        print("❌ yt-dlp未安装")
        return False
    
    # 检查依赖
    required_modules = ['asyncio', 'logging', 'os', 'sys']
    for module in required_modules:
        try:
            __import__(module)
            print(f"✅ {module}: 可用")
        except ImportError:
            print(f"❌ {module}: 不可用")
            return False
    
    return True

def show_help():
    """显示帮助信息"""
    print("""
📖 使用说明:

1. 如果测试失败，请按照以下步骤配置cookies:

   a) 在本地浏览器中登录YouTube
   b) 使用浏览器插件导出cookies.txt
   c) 将cookies.txt上传到项目根目录
   d) 重新运行此测试脚本

2. 获取cookies的方法:
   
   方法1 - 使用浏览器插件:
   - 安装"Get cookies.txt LOCALLY"插件
   - 访问YouTube并导出cookies
   
   方法2 - 使用命令行:
   yt-dlp --cookies-from-browser chrome --cookies cookies.txt --print-to-file cookies "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

3. 故障排除:
   - 确保cookies.txt在项目根目录
   - 检查文件权限: chmod 644 cookies.txt
   - 确保cookies没有过期
   - 重启服务进程

更多详细信息请查看: README_YouTube_Cookies.md
""")

async def main():
    print("🚀 YouTube认证配置测试工具")
    print("=" * 50)
    
    # 环境检查
    if not check_environment():
        print("\n❌ 环境检查失败")
        return
    
    # 认证测试
    success = await test_youtube_auth()
    
    print("\n" + "=" * 50)
    if success:
        print("🎉 YouTube认证测试成功!")
        print("   你的配置工作正常，可以开始使用服务了。")
    else:
        print("💡 YouTube认证测试失败")
        print("   需要配置cookies来解决认证问题。")
        show_help()

if __name__ == "__main__":
    asyncio.run(main()) 
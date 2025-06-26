#!/usr/bin/env python3
"""
Cookie管理API使用示例
演示如何通过API上传和管理YouTube cookies
"""

import requests
import json
import os
from typing import Optional

# API基础URL（根据你的服务器地址调整）
BASE_URL = "http://localhost:8000/api/v1/auth"

class CookieAPIClient:
    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url
    
    def check_cookie_status(self) -> dict:
        """检查当前cookie状态"""
        try:
            response = requests.get(f"{self.base_url}/cookie-status")
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            return {"error": str(e)}
    
    def upload_cookies(self, cookie_file_path: str) -> dict:
        """上传cookie文件"""
        if not os.path.exists(cookie_file_path):
            return {"error": f"文件不存在: {cookie_file_path}"}
        
        try:
            with open(cookie_file_path, 'rb') as f:
                files = {'cookie_file': ('cookies.txt', f, 'text/plain')}
                response = requests.post(f"{self.base_url}/upload-cookies", files=files)
            
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            return {"error": str(e)}
    
    def delete_cookies(self) -> dict:
        """删除cookie文件"""
        try:
            response = requests.delete(f"{self.base_url}/cookies")
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            return {"error": str(e)}
    
    def restore_cookies(self) -> dict:
        """从备份恢复cookie文件"""
        try:
            response = requests.post(f"{self.base_url}/restore-cookies")
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            return {"error": str(e)}

def print_json(data: dict, title: str = ""):
    """格式化打印JSON数据"""
    if title:
        print(f"\n{'='*20} {title} {'='*20}")
    print(json.dumps(data, indent=2, ensure_ascii=False))

def main():
    print("🍪 Cookie管理API示例")
    print("=" * 50)
    
    client = CookieAPIClient()
    
    # 1. 检查当前状态
    print("\n1️⃣ 检查当前cookie状态")
    status = client.check_cookie_status()
    print_json(status)
    
    # 2. 演示上传功能（如果有cookie文件）
    cookie_file = "./cookies.txt"
    if os.path.exists(cookie_file):
        print(f"\n2️⃣ 发现本地cookie文件，演示上传...")
        upload_result = client.upload_cookies(cookie_file)
        print_json(upload_result)
        
        # 再次检查状态
        print("\n📊 上传后状态:")
        status = client.check_cookie_status()
        print_json(status)
    else:
        print(f"\n2️⃣ 未发现本地cookie文件 ({cookie_file})")
        print("   创建示例文件...")
        
        # 创建一个示例cookie文件
        sample_cookies = """# Netscape HTTP Cookie File
# This is a sample cookie file for demonstration
.youtube.com	TRUE	/	FALSE	1234567890	VISITOR_INFO1_LIVE	sample_value
.youtube.com	TRUE	/	FALSE	1234567890	YSC	sample_ysc_value
.google.com	TRUE	/	FALSE	1234567890	NID	sample_nid_value
"""
        with open(cookie_file, 'w', encoding='utf-8') as f:
            f.write(sample_cookies)
        
        print(f"   ✅ 已创建示例文件: {cookie_file}")
        
        # 尝试上传
        upload_result = client.upload_cookies(cookie_file)
        print_json(upload_result, "上传结果")
    
    # 3. 演示其他功能
    while True:
        print("\n" + "="*50)
        print("请选择操作:")
        print("1. 检查cookie状态")
        print("2. 删除cookies")
        print("3. 从备份恢复cookies")
        print("4. 上传新的cookie文件")
        print("0. 退出")
        
        choice = input("\n请输入选择 (0-4): ").strip()
        
        if choice == "0":
            break
        elif choice == "1":
            result = client.check_cookie_status()
            print_json(result, "Cookie状态")
        elif choice == "2":
            result = client.delete_cookies()
            print_json(result, "删除结果")
        elif choice == "3":
            result = client.restore_cookies()
            print_json(result, "恢复结果")
        elif choice == "4":
            file_path = input("请输入cookie文件路径: ").strip()
            if file_path:
                result = client.upload_cookies(file_path)
                print_json(result, "上传结果")
        else:
            print("❌ 无效选择")

def test_with_curl():
    """显示curl命令示例"""
    print("\n🌐 Curl命令示例:")
    print("="*50)
    
    base_url = "http://localhost:8000/api/v1/auth"
    
    print("1. 检查cookie状态:")
    print(f"curl -X GET {base_url}/cookie-status")
    
    print("\n2. 上传cookie文件:")
    print(f"curl -X POST {base_url}/upload-cookies \\")
    print("     -F 'cookie_file=@cookies.txt'")
    
    print("\n3. 删除cookies:")
    print(f"curl -X DELETE {base_url}/cookies")
    
    print("\n4. 恢复cookies:")
    print(f"curl -X POST {base_url}/restore-cookies")

if __name__ == "__main__":
    try:
        # 检查服务是否可用
        response = requests.get(f"{BASE_URL}/cookie-status", timeout=5)
        response.raise_for_status()
        
        # 运行主程序
        main()
        
        # 显示curl示例
        show_curl = input("\n显示curl命令示例? (y/n): ").strip().lower()
        if show_curl == 'y':
            test_with_curl()
            
    except requests.RequestException as e:
        print(f"❌ 无法连接到API服务: {e}")
        print("请确保视频服务正在运行并且可以访问")
        print("\n如果服务正在运行，尝试直接使用curl命令:")
        test_with_curl()
    except KeyboardInterrupt:
        print("\n\n👋 已退出")
    except Exception as e:
        print(f"❌ 发生错误: {e}") 
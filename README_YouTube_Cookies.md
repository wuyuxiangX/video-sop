# YouTube认证问题解决方案

## 问题描述

在服务器环境中使用yt-dlp下载YouTube视频时，可能会遇到以下错误：
```
ERROR: [youtube] dQw4w9WgXcQ: Sign in to confirm you're not a bot. Use --cookies-from-browser or --cookies for the authentication.
```

这是因为YouTube的反机器人检测机制，需要通过cookies进行身份验证。

## 解决方案

### 方案1：使用Cookie文件（推荐）

#### 步骤1：导出cookies
在你的本地计算机上：

1. **使用浏览器插件导出cookies**：
   - 安装"Get cookies.txt LOCALLY"浏览器插件
   - 登录YouTube
   - 访问任意YouTube视频页面
   - 点击插件图标，下载cookies.txt文件

2. **手动导出cookies（Chrome）**：
   ```bash
   # 使用yt-dlp命令行工具导出cookies
   yt-dlp --cookies-from-browser chrome --cookies cookies.txt --print-to-file cookies "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
   ```

#### 步骤2：上传到服务器
将cookies.txt文件上传到项目根目录（与main.py同级）：
```bash
scp cookies.txt your-server:/path/to/video-sop/cookies.txt
```

#### 步骤3：重启服务
重启你的视频服务，系统会自动检测并使用cookies.txt文件。

### 方案2：环境变量方式

如果不想使用文件，可以通过环境变量传递cookies：

```bash
export YOUTUBE_COOKIES="your_cookies_string_here"
```

### 方案3：使用代理（备选）

如果cookies方案不可行，可以尝试使用代理：

```bash
# 在启动服务前设置代理
export HTTP_PROXY=http://your-proxy:port
export HTTPS_PROXY=http://your-proxy:port
```

## Cookie文件格式示例

cookies.txt文件应该遵循Netscape格式：
```
# Netscape HTTP Cookie File
.youtube.com	TRUE	/	FALSE	1234567890	cookie_name	cookie_value
```

## 注意事项

1. **安全性**：cookies.txt包含敏感信息，请妥善保管
2. **有效期**：cookies会过期，需要定期更新
3. **账户安全**：建议使用专门的测试账户
4. **服务器权限**：确保服务器进程有读取cookies.txt的权限

## 验证是否生效

检查日志中是否出现以下信息：
```
发现cookie文件，将使用cookies进行认证
尝试配置 1: 使用cookie文件获取YouTube信息
配置 1 (cookie文件) 成功获取YouTube信息
```

## 故障排除

1. **找不到cookie文件**：确保cookies.txt在项目根目录
2. **权限问题**：检查文件读取权限 `chmod 644 cookies.txt`
3. **格式错误**：确保cookie文件格式正确
4. **过期问题**：重新导出新的cookies

## 自动化脚本

你可以创建一个脚本来定期更新cookies：

```bash
#!/bin/bash
# update_cookies.sh
# 从本地浏览器获取最新cookies并上传到服务器

# 在本地执行
yt-dlp --cookies-from-browser chrome --cookies /tmp/cookies.txt --print-to-file cookies "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# 上传到服务器
scp /tmp/cookies.txt your-server:/path/to/video-sop/cookies.txt

# 重启服务（可选）
ssh your-server "systemctl restart video-sop"
```

## 法律声明

请确保你的使用符合YouTube的服务条款和相关法律法规。本工具仅用于学习和研究目的。 
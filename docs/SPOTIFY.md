# Spotify 歌词接入

Mio 1.2 接入 [akashrchandran/spotify-lyrics-api](https://github.com/akashrchandran/spotify-lyrics-api)，使用**你自己的服务**获取指定 Spotify 歌曲的歌词。Mio 不读取浏览器 Cookie、不内置共享账号，也不把你的登录会话交给公共代理。

## 在 Windows 启动本地服务

1. 安装并启动 Docker Desktop，选择 Linux 容器模式。
2. 在 Mio 解压目录（或源码根目录）打开 PowerShell，运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-spotify.ps1
```

3. 脚本会交互询问你自己 Spotify 会话的 `SP_DC`，输入不会显示。请按上游的 [会话说明](https://github.com/akashrchandran/spotify-lyrics-api#deployment) 在自己的浏览器中查看；不要发到聊天、提交 GitHub 或粘贴到不可信网站。
4. 脚本构建并启动容器，服务监听 `http://127.0.0.1:8765/`。首次构建需要下载 PHP 基础镜像和依赖。
5. 在 Mio 的“歌词与罗马音”页点击 **Spotify 链接…**，填写本地服务地址，粘贴歌曲链接，点击“获取并预览”。也支持 22 位 Track ID 和 `spotify:track:` URI。

SP_DC 通过进程环境传入 Docker，不写入项目 `.env` 或配置文件。Docker 容器配置仍保存该环境变量，能够管理 Docker 的本机用户可能查看它。停止使用时删除容器；不要分享容器检查输出。脚本执行后会清除自身的 SP_DC 环境变量。

停止并删除本地服务：

```powershell
docker stop mio-spotify-lyrics
docker rm mio-spotify-lyrics
```

会话过期后重新运行启动脚本，填写自己的新会话。Mio 仅保存服务地址，不保存 SP_DC。远程自建服务地址必须使用 HTTPS，本地回环地址可使用 HTTP；本版地址栏不接受带账号、密码或密钥查询参数的 URL。

## 获取后如何写入

Spotify 歌词成功获取后进入左侧编辑区，并添加到当前歌曲的可选歌词版本中。可离线生成罗马音，在“写入与记录”中选择：Spotify 原文、当前编辑内容、原文＋罗马音预览，或保留文件原有歌词。确认预览后再保存。

该项目接收歌曲链接 / ID，不提供按本地曲名自动搜索 Spotify 曲目的功能。本版不会把 Spotify 混入无需账号的自动搜索列表，现有网易云、酷狗、LRCLIB 继续独立可用。

## 失败提示

- 无法连接：先启动 Docker 服务，核对端口与地址。
- 401 / 500：检查服务端登录会话、上游令牌流程及网络。上游可能用 500 表示无效会话。
- 403：该账号或地区无法获取此内容。
- 404：该曲在 Spotify 没有可用歌词。
- 429：请求过于频繁，请稍后再试。
- 证书错误：配置有效 HTTPS 证书；程序不会通过关闭证书校验绕过错误。

失败不会清空编辑区，不影响其他歌词来源。

## 上游代码与验证边界

随发行包提供的 `integrations/spotify-lyrics-api` 固定上游提交 `e158b96b854778d8ff51a3c9544ebb4f68b64907`，保留 GPL v3 许可和作者信息。修改说明见该目录的 `UPSTREAM.md`。

与上游原样部署相比，本地版本启用 TLS 校验，缩短超时，移除通配 CORS，限制令牌缓存权限并隐藏原始异常；容器只映射回环地址、以非 root 用户运行、文件系统只读、令牌缓存在临时内存目录。

**已经验证的是：客户端 URL / ID 校验、真实本地 HTTP 请求、同步与普通歌词格式、错误状态及编辑保护。没有使用用户账号完成 Spotify 实际歌词获取。** 当前开发机 Docker 引擎未启动，也没有配置 SP_DC，不能把协议测试当作真实账号成功证明。GitHub Actions 另外构建 Docker 镜像、检查 PHP 语法并验证无凭据错误返回。

这是非官方接入，上游也提示了服务条款方面的不确定性。内部接口与令牌机制变化可能导致失效；不能保证绕过账号、地区或曲目本身的访问限制。歌词版权仍归各自权利人。

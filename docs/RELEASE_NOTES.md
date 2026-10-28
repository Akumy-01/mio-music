# Mio Music 1.3.0 · Spotify 内置获取

Spotify 获取无需先安装 Docker 或运行独立后端。内置适配参考 spotify-lyrics-api 的自有会话流程，Mio 直接请求并转换歌词；高级自建服务模式继续保留。

- 首次在“Spotify 获取…”中配置自己的 SP_DC，会话默认保存到当前 Windows 用户的凭据管理器，也可仅在本次运行使用。
- 之后将 Spotify 歌曲链接粘贴到曲名搜索框，点击“查找歌词”即可获取；也支持独立窗口内的 Track ID / URI。
- 会话更新与清除、令牌内存缓存、401 一次刷新、明确的 403 / 404 / 429 / 网络错误提示；不读取浏览器 Cookie，不把会话放入项目配置或日志。
- 获取后加入可选歌词版本，继续使用原有预览、日语罗马音、封面选择、安全写入和撤销。

75 项自动测试通过，覆盖原生 Windows 凭据、协议模拟、敏感信息隔离、配置窗口和主界面链接快捷获取。最终 Windows EXE 完成独立烟雾检查。没有使用真实 Spotify 个人会话完成取词；非官方内部接口有失效可能。首次配置步骤与验证边界见 docs/SPOTIFY.md。

下载 MioMusic-windows-x64.zip，完整解压后运行 MioMusic.exe；确认界面 v1.3.0。无需安装 Python、PHP 或 Docker。Spotify 仍需自己的有效会话和可访问相应服务的网络。

# 可选团队账号：兼容定义

同一主程序上的团队共享账号保护现有 local-user 学习空间，不创建多租户、不迁移私人记录；账号信息复用现有 SQLite meta 表，键 local-account-v1，不新增 schema 或表。未配置时行为完全兼容。不同电脑的独立服务不会自动同步；服务继续仅绑定 loopback，未提供公网托管或远程协作。

新增 /api/account/status（GET）、setup/login/logout/password（POST）。setup、logout、password 要求现有 X-Xueya-Token；启用后除 health、status、login 和独立 stopToken 保护的 shutdown 外，全部 /api/ 路径要求8小时 HttpOnly/SameSite=Strict 会话 Cookie。账号路由要求 loopback Host，现有 Origin 验证继续执行。密码 PBKDF2-HMAC-SHA256 600000轮与独立随机盐；会话仅在服务内存，重启后重新登录；更换密码撤销所有旧会话。五次失败后60秒冷却。

此功能保护 HTTP 资料接口，不对原有浏览器 localStorage 副本或本机磁盘提供加密，不能防止有本机文件访问权的人读取旧副本。三个团队成员共享同一账号和权限，没有独立成绩、权限分级、云同步或找回密码服务。停用或重置需明确维护操作，不自动删资料。

按本地使用者要求，设置或修改密码接受6至256字符；/api/account/password 支持可选 username 字段，经当前密码验证后同时改名，仍保留原学习空间并撤销旧会话。账号可为3至40位纯数字。

# Nomi Auth Plugin

现有 NoneBot 实例中的 QQ 官方适配器插件，只处理指定群，通过 [Nomi Auth](https://github.com/NomiTeam/nomi-auth) 完成无密码登录、注册和改名。

## 命令

- `登录 <验证码>`：验证码由启动器提供；没有账号时提示继续注册。
- `注册 <id>`：仅认领申请的成员可使用。ID 为 3 至 16 位字母、数字或下划线。
- `改名 <新id>`：修改本人游戏名，默认冷却 7 天，UUID 不变。

成功回复显示当前 ID，不发送令牌，不艾特成员。是否需要艾特机器人取决于群消息权限；当前群支持直接发送。

## 安装与配置

在机器人实例目录执行（Windows 路径示例）：

```text
uv pip install --python .venv/Scripts/python.exe -e ./nomi-auth-plugin
```

Linux 使用 `.venv/bin/python`。在实例入口调用 `nonebot.load_plugin("nomi_auth_plugin")`，或通过 pyproject.toml 加载，二选一。

将 `.env.example` 的字段加入实例配置，应用 ID、群 OpenID 和内部服务凭证须与后端匹配。无前缀命令需设置 `COMMAND_START=["", "/"]`。缺少配置时业务命令禁用。

需要获取群 ID 时临时启用 `NOMI_DISCOVERY=true`，在目标群发送 `Nomi群信息`；从本地日志读取应用和群 ID 后关闭该选项。插件会串行处理请求并有限重试，同一事件不会重复执行。

## lobby 部署与检查

实例位于 `/home/naipu/minecraft/nomi-bot`，归 `mcadmin:mcadmin`；`.env` 和 `.env.prod` 权限为 0600，后端地址为 `http://127.0.0.1:8000`。`deploy/bot.service` 使用实例的 `bot.py`，管理开机自启和失败重启。

在插件目录执行 `uv sync --python 3.12`、`uv run pytest -q`、`uv run ruff check src tests`。父实例的配置、机器人密钥和虚拟环境不属于本仓库。

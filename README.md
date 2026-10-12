# Nomi Auth Plugin

Nomi 账号注册验证的 NoneBot 插件，位于现有 nomi-bot 实例内，使用 QQ 官方适配器。

## 安装到现有实例

在 `nomi-bot` 目录执行：

```text
uv pip install --python .venv/Scripts/python.exe -e ./nomi-auth-plugin
```

Linux 将 Python 路径改为 `.venv/bin/python`。在实例 pyproject.toml 的 `[tool.nonebot.plugins]` 中，将 `nomi-auth-plugin = ["nomi_auth_plugin"]` 加入配置，或在机器人入口调用 `nonebot.load_plugin("nomi_auth_plugin")`，不要同时重复加载。

把 `.env.example` 的字段加入实例环境配置，机器人应用 ID、群 OpenID 和 API 凭证须与后端一致。命令前缀由实例配置 `COMMAND_START=["", "/"]` 控制，入口为 `登录 <码>`；未注册成员按提示发送 `注册 <id>`。已有成员发送 `改名 <新id>` 修改游戏名。`账号帮助` 已移除。不修改已有 QQ 平台密钥。

后端不在线时有限重试，保留同一消息 ID；注册命令串行处理。群内成功回复显示本次账号 ID（当前游戏名），不透露管理或游戏令牌。注册提示为普通回复，不使用 QQ OpenID 艾特。

未填写配置时插件可加载，但注册与登录均禁用。暂时设置 `NOMI_DISCOVERY=true`，在目标群艾特机器人发送 `Nomi群信息`，本地日志会显示应用 ID 与群 OpenID，不向群发送这些字段；取得后关闭 discovery 并填写配置。QQ 官方适配器需要相应群消息权限。全量群消息可用时不用艾特；只开放艾特事件时需要艾特。测试群已验证两种业务命令可以直接发送。

## 开发检查

```text
uv sync --python 3.12
uv run pytest -q
uv run ruff check src tests
```

父目录的机器人配置、.env.prod 和虚拟环境不属于本仓库。当前测试群已验证统一登录触发注册、成功回复和游戏会话领取。插件自动化测试使用模拟 HTTP，不登录 QQ。

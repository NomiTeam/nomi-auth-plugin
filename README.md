# Nomi Auth Plugin

Nomi 账号注册验证的 NoneBot 插件，位于现有 nomi-bot 实例内，使用 QQ 官方适配器。

## 安装到现有实例

在 `nomi-bot` 目录执行：

```text
uv pip install --python .venv/Scripts/python.exe -e ./nomi-auth-plugin
```

Linux 将 Python 路径改为 `.venv/bin/python`。在实例 pyproject.toml 的 `[tool.nonebot.plugins]` 中，将 `nomi-auth-plugin = ["nomi_auth_plugin"]` 加入配置，或在机器人入口调用 `nonebot.load_plugin("nomi_auth_plugin")`，不要同时重复加载。

把 `.env.example` 的字段加入实例环境配置，机器人应用 ID、群 OpenID 和 API 凭证须与后端一致。命令前缀由实例配置 `COMMAND_START=["", "/"]` 控制，支持 `@机器人 注册 <码>`、`找回 <码>` 和 `账号帮助`。不修改已有 QQ 平台密钥。

后端不在线时有限重试，保留同一消息 ID；注册命令串行处理。群内只返回操作结果，不透露密码、管理令牌或其他用户的资料。

未填写配置时插件可加载，但注册与找回均禁用。暂时设置 `NOMI_DISCOVERY=true`，在目标群艾特机器人发送 `Nomi群信息`，本地日志会显示应用 ID 与群 OpenID，不向群发送这些字段；取得后关闭 discovery 并填写配置。QQ 官方适配器还需要开启群艾特消息事件权限，例如机器人配置中的 `intent.c2c_group_at_messages=true`。

## 开发检查

```text
uv sync --python 3.12
uv run pytest -q
uv run ruff check src tests
```

父目录的机器人配置、.env.prod 和虚拟环境不属于本仓库。真实群事件与正式机器人权限仍需联调；插件测试使用模拟 HTTP，不登录 QQ。

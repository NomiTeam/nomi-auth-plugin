# Nomi Auth Plugin

这是一个 NoneBot 插件，使用 QQ 官方适配器接收指定群的消息，再调用 [Nomi Auth Neo](https://github.com/NomiTeam/nomi-auth-neo) 完成无密码登录、注册和改名。插件不直接访问数据库。

## 命令

| 命令 | 说明 | 示例 |
| --- | --- | --- |
| `登录 验证码` | 发送启动器提供的验证码 | `登录 AAAA-BBBB-CCCC` |
| `注册 ID` | 没有账号时，按提示为已认领的申请选择 ID | `注册 Alice` |
| `改名 新ID` | 修改本人的游戏名，UUID 不变 | `改名 NewAlice` |

ID 为 3–16 位字母、数字或下划线。改名默认冷却 7 天，以后端配置为准。成功回复显示当前 ID，不发送令牌，也不艾特成员。是否需要艾特机器人，取决于 QQ 的群消息权限。

## 安装

需要已有的 NoneBot 实例和 QQ 官方适配器。在机器人目录执行：

```shell
uv pip install --python .venv/bin/python -e ./nomi-auth-plugin
```

Windows 将 Python 路径改为 `.venv/Scripts/python.exe`。

在实例入口加入 `nonebot.load_plugin("nomi_auth_plugin")`，或在实例的 `pyproject.toml` 中加载，选择一种即可。

## 配置

将 `.env.example` 的字段加入机器人现有配置。应用 ID、群 OpenID 和服务凭证必须与后端一致。无前缀命令需要 `COMMAND_START=["", "/"]`；缺少必要配置时业务命令禁用。

需要获取群 ID 时，临时设置 `NOMI_DISCOVERY=true`，在目标群发送 `Nomi群信息`，从机器人日志读取应用和群 ID，完成后关闭该选项。

请求总等待默认 15 秒，每次 HTTP 请求默认最多 8 秒，包含有限重试。相同事件重试会保留原事件 ID，后端不会重复执行操作。

跨机器部署时，建议使用 HTTPS，并填写与认证服务一致的独立服务密钥。

插件使用系统信任链校验服务端证书和主机名，不跟随重定向。自签 CA 可通过 `NOMI_TLS_CA_CERT=/path/to/server-ca.pem` 配置；证书无效时启动失败或直接报告验证错误，网络中断和服务端临时错误进行有限重试。

## 项目结构

```text
src/nomi_auth_plugin/
├── __init__.py - 注册命令和关闭回调
├── commands.py - 群校验、参数检查和回复
├── client.py   - 后端请求、重试和响应校验
├── tls.py      - 证书加载和 TLS 校验
├── queue.py    - 按成员和验证码维护请求顺序
├── messages.py - 面向群友的中文提示
└── config.py   - NoneBot 配置
```

同一成员的命令按顺序处理，同一个验证码也只有一条认领队列，其他申请可以并行。等待中的消息即使取消，也不能让后来的消息越过它前面仍在运行的请求。

## 开发检查

```shell
uv sync --python 3.12
uv run ruff check src tests
uv run ruff format --check src tests
uv run pyrefly check
uv run pytest -q
```

测试使用构造的群事件，联动测试启动 Nomi Auth Neo 的实际可执行文件：

```shell
NOMI_TEST_NEO_BINARY=/path/to/nomi-auth-neo uv run pytest -q
```

Windows 通过 `$env:NOMI_TEST_NEO_BINARY` 设置 exe 路径。未设置时明确跳过联动测试。

联动测试默认检查 SQLite。配置 `NOMI_TEST_MYSQL_DATABASE/USER/PASSWORD` 后也会检查 MariaDB，可选 `NOMI_TEST_MYSQL_HOST/PORT`；库名必须以 `nomi_auth_test_` 开头。测试使用随机应用标识和账号名，不清空数据库，测试库应单独保留或删除。

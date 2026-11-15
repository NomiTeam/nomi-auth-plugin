"""
Chinese replies shown to group members. Command examples use plain arguments.
"""

LOGIN_USAGE = "用法：登录 启动器显示的验证码"
REGISTRATION_PROMPT = (
    "你还没有账号，请在验证码到期前发送：注册 ID。"
    "ID 为 3 至 16 位字母、数字或下划线，例如：注册 Alice。"
)

ERROR_MESSAGES = {
    "MTLS_REQUIRED": "账号服务证书验证失败，请联系管理员检查机器人证书配置。",
    "NO_PENDING_REGISTRATION": "没有待注册申请，请先发送启动器的登录码。",
    "REQUEST_IN_PROGRESS": "你已有待注册申请，请先完成或关闭启动器窗口。",
    "INVALID_NAME": "ID 须为 3 至 16 位字母、数字或下划线，本次请求已关闭。",
    "INVALID_REQUEST": "请求格式无效，请重新申请。",
    "RENAME_COOLDOWN": "尚在改名冷却期，本次请求已关闭。",
    "ACCOUNT_NOT_FOUND": "你在这个群内还没有账号，请先发送启动器的登录码。",
    "ACCOUNT_UNAVAILABLE": "该账号已停用，请联系管理员。",
    "IDENTITY_ALREADY_BOUND": "你在这个群内已有账号，请通过群验证码登录。",
    "INVALID_CODE": "验证码无效，请检查后重试。",
    "CODE_USED": "验证码已使用或申请已结束。",
    "REQUEST_EXPIRED": "验证码已过期，请在启动器重新申请。",
    "NAME_TAKEN": "ID 已被占用，本次请求已关闭，请重新申请。",
    "IDENTITY_MISMATCH": "必须使用该账号绑定的群成员身份登录。",
    "WRONG_GROUP": "当前群或机器人不在后端允许范围。",
    "RATE_LIMITED": "请求过于频繁，请稍后重试。",
}


def success_reply(operation: str, status: str, name: str) -> str:
    """
    Format the current account ID without exposing tokens or member mentions.
    """
    verb = {"VERIFIED": "登录", "REGISTERED": "注册", "RENAMED": "改名"}[status]
    instruction = "请重新登录启动器。" if operation == "改名" else "请查看启动器。"
    return f"{verb}成功，账号 ID：{name}。{instruction}"

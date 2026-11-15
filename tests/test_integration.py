import os
import socket
import subprocess
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

import httpx
import nonebot
import pytest

try:
    nonebot.get_driver()
except ValueError:
    nonebot.init(driver="~none")

from nomi_auth_plugin.client import AuthClient, BackendError
from nomi_auth_plugin.config import Config


def wait_for_service(process, url):
    with httpx.Client(trust_env=False) as client:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if process.poll() is not None:
                pytest.fail("The Rust service exited during startup")
            try:
                if client.get(url + "/health", timeout=1).status_code == 200:
                    return
            except httpx.TransportError:
                pass
            time.sleep(0.1)
    pytest.fail("The Rust service did not become ready")


@pytest.fixture(params=["sqlite", "mysql"])
def service(request, tmp_path):
    configured = os.environ.get("NOMI_TEST_NEO_BINARY")
    if not configured:
        pytest.skip("Set NOMI_TEST_NEO_BINARY to a built Nomi Auth Neo executable")
    binary = Path(configured).resolve()
    if not binary.is_file():
        pytest.fail("NOMI_TEST_NEO_BINARY does not point to a file")
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith("NOMI_")
    }
    app_id = "test-app-" + uuid.uuid4().hex
    environment.update(
        NOMI_DATA_DIR=str(tmp_path / "data"),
        NOMI_DATABASE_BACKEND=request.param,
        NOMI_BOT_TOKEN="x" * 32,
        NOMI_BOT_APP_ID=app_id,
        NOMI_GROUP_OPENID="group",
    )
    if request.param == "mysql":
        database = os.environ.get("NOMI_TEST_MYSQL_DATABASE", "")
        if not database:
            pytest.skip("A separate MariaDB test database was not configured")
        if not database.startswith("nomi_auth_test_"):
            pytest.fail("Refusing to use a database outside the test namespace")
        environment.update(
            NOMI_MYSQL_DATABASE=database,
            NOMI_MYSQL_HOST=os.environ.get("NOMI_TEST_MYSQL_HOST", "127.0.0.1"),
            NOMI_MYSQL_PORT=os.environ.get("NOMI_TEST_MYSQL_PORT", "3306"),
            NOMI_MYSQL_USER=os.environ["NOMI_TEST_MYSQL_USER"],
            NOMI_MYSQL_PASSWORD=os.environ["NOMI_TEST_MYSQL_PASSWORD"],
        )
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    # Configuration is supplied by the test environment rather than initial setup.
    (tmp_path / ".env").write_text("", encoding="utf-8")
    suffix = uuid.uuid4().hex[:10]
    with (tmp_path / "service.log").open("wb") as log:
        process = subprocess.Popen(
            [str(binary), "serve", "--host", "127.0.0.1", "--port", str(port)],
            env=environment,
            cwd=tmp_path,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            wait_for_service(process, url)
            yield SimpleNamespace(
                url=url,
                app_id=app_id,
                name="User" + suffix,
                renamed_name="New" + suffix,
            )
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)


def backend_client(service):
    return AuthClient(
        Config(
            nomi_auth_base_url=service.url,
            nomi_bot_api_token="x" * 32,
            nomi_allowed_group_openid="group",
            nomi_bot_app_id=service.app_id,
        )
    )


@pytest.mark.asyncio
async def test_group_registration_login_rename_and_game_join(service):
    backend = backend_client(service)
    try:
        async with httpx.AsyncClient(base_url=service.url, trust_env=False) as launcher:
            request = (await launcher.post("/api/v1/logins", json={})).json()
            claim = await backend.submit(
                "登录", request["code"], "group", "member", "claim"
            )
            assert claim["status"] == "AWAITING_NAME"
            registered = await backend.submit(
                "注册", service.name, "group", "member", "register"
            )
            assert registered["status"] == "REGISTERED"

            poll_headers = {
                "Authorization": "Bearer " + request["poll_token"],
                "X-Request-ID": "a" * 64,
            }
            session_path = f"/api/v1/logins/{request['request_id']}/session"
            session = (await launcher.post(session_path, headers=poll_headers)).json()
            assert (
                await launcher.post(session_path, headers=poll_headers)
            ).json() == session
            profile_id = session["game"]["selectedProfile"]["id"]
            assert profile_id == registered["uuid"]

            joined = await launcher.post(
                "/api/yggdrasil/sessionserver/session/minecraft/join",
                json={
                    "accessToken": session["game"]["accessToken"],
                    "selectedProfile": profile_id,
                    "serverId": "test-server",
                },
            )
            assert joined.status_code == 204
            renamed = await backend.submit(
                "改名", service.renamed_name, "group", "member", "rename"
            )
            assert (
                renamed["uuid"] == profile_id
                and renamed["name"] == service.renamed_name
            )
            verified = await launcher.get(
                "/api/yggdrasil/sessionserver/session/minecraft/hasJoined",
                params={"username": service.renamed_name, "serverId": "test-server"},
            )
            assert verified.json()["id"] == profile_id

            request = (await launcher.post("/api/v1/logins", json={})).json()
            existing = await backend.submit(
                "登录", request["code"], "group", "member", "login-again"
            )
            assert existing == {
                "status": "VERIFIED",
                "name": service.renamed_name,
                "uuid": profile_id,
            }
    finally:
        await backend.close()


@pytest.mark.asyncio
async def test_real_name_conflict_closes_registration_once(service):
    backend = backend_client(service)
    try:
        async with httpx.AsyncClient(base_url=service.url, trust_env=False) as launcher:
            for member in ("first", "second"):
                request = (await launcher.post("/api/v1/logins", json={})).json()
                await backend.submit(
                    "登录", request["code"], "group", member, "claim-" + member
                )
                if member == "first":
                    await backend.submit(
                        "注册", service.name, "group", member, "register-" + member
                    )
                else:
                    with pytest.raises(BackendError, match="ID 已被占用"):
                        await backend.submit(
                            "注册",
                            service.name.lower(),
                            "group",
                            member,
                            "register-" + member,
                        )
            response = await launcher.get(
                f"/api/v1/logins/{request['request_id']}",
                headers={"Authorization": "Bearer " + request["poll_token"]},
            )
            assert response.json()["status"] == "FAILED"
            assert response.json()["error"] == "NAME_TAKEN"
            retry = (await launcher.post("/api/v1/logins", json={})).json()
            unregistered = await backend.submit(
                "登录", retry["code"], "group", "second", "verify-no-account"
            )
            assert unregistered["status"] == "AWAITING_NAME"
    finally:
        await backend.close()

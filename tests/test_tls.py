import datetime
import importlib
import json
import ssl
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import nonebot
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from pydantic import ValidationError

nonebot.init(driver="~none")
Config = importlib.import_module("nomi_auth_plugin.config").Config
AuthClient = importlib.import_module("nomi_auth_plugin.client").AuthClient
BackendError = importlib.import_module("nomi_auth_plugin.errors").BackendError


def certificate(directory, name, issuer=None, hostname="localhost", expired=False):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    moment = datetime.datetime.now(datetime.timezone.utc)
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer[1].subject if issuer else subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(moment - datetime.timedelta(days=2))
        .not_valid_after(
            moment - datetime.timedelta(days=1)
            if expired
            else moment + datetime.timedelta(days=1)
        )
        .add_extension(x509.BasicConstraints(ca=issuer is None, path_length=None), True)
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(key.public_key()), False
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(
                (issuer[0] if issuer else key).public_key()
            ),
            False,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=issuer is not None,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=issuer is None,
                crl_sign=issuer is None,
                encipher_only=False,
                decipher_only=False,
            ),
            True,
        )
    )
    if issuer:
        builder = builder.add_extension(
            x509.SubjectAlternativeName([x509.DNSName(hostname)]), False
        )
        builder = builder.add_extension(
            x509.ExtendedKeyUsage(
                [ExtendedKeyUsageOID.SERVER_AUTH, ExtendedKeyUsageOID.CLIENT_AUTH]
            ),
            False,
        )
    cert = builder.sign(issuer[0] if issuer else key, hashes.SHA256())
    cert_path, key_path = directory / (name + ".pem"), directory / (name + ".key")
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return key, cert, cert_path, key_path


@pytest.fixture
def certificates(tmp_path, monkeypatch):
    monkeypatch.setenv("NO_PROXY", "localhost,127.0.0.1")
    ca = certificate(tmp_path, "ca")
    return ca, certificate(tmp_path, "server", ca), certificate(tmp_path, "client", ca)


@contextmanager
def tls_server(ca, server):
    events = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            events.append(self.connection.getpeercert())
            self.rfile.read(int(self.headers["Content-Length"]))
            body = json.dumps({"status": "VERIFIED", "name": "Alice"}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    listener = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(server[2], server[3])
    context.load_verify_locations(ca[2])
    context.verify_mode = ssl.CERT_REQUIRED
    listener.socket = context.wrap_socket(listener.socket, server_side=True)
    worker = threading.Thread(target=listener.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"https://localhost:{listener.server_port}", events
    finally:
        listener.shutdown()
        listener.server_close()
        worker.join(timeout=5)


def config(url, **options):
    return Config(
        nomi_auth_base_url=url,
        nomi_bot_api_token="x" * 32,
        nomi_allowed_group_openid="group",
        nomi_bot_app_id="app",
        **options,
    )


@pytest.mark.asyncio
async def test_real_mutual_tls(certificates):
    ca, server, client = certificates
    with tls_server(ca, server) as (url, events):
        auth = AuthClient(
            config(
                url,
                nomi_tls_ca_cert=str(ca[2]),
                nomi_tls_client_cert=str(client[2]),
                nomi_tls_client_key=str(client[3]),
            )
        )
        try:
            assert (await auth.submit("登录", "code", "group", "member", "event"))[
                "name"
            ] == "Alice"
            assert events and events[0]["subject"]
        finally:
            await auth.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        "missing_client",
        "untrusted_server",
        "hostname",
        "untrusted_client",
        "expired_client",
    ],
)
async def test_real_certificate_failure_does_not_retry(
    certificates, monkeypatch, failure, tmp_path
):
    ca, server, client = certificates
    if failure == "untrusted_client":
        other_ca = certificate(tmp_path, "other-ca")
        client = certificate(tmp_path, "untrusted-client", other_ca)
    if failure == "expired_client":
        client = certificate(tmp_path, "expired-client", ca, expired=True)
    pauses = []

    async def sleep(delay):
        pauses.append(delay)

    monkeypatch.setattr("nomi_auth_plugin.client.asyncio.sleep", sleep)
    with tls_server(ca, server) as (url, events):
        options = {"nomi_tls_ca_cert": str(ca[2])}
        if failure != "missing_client":
            options.update(
                nomi_tls_client_cert=str(client[2]), nomi_tls_client_key=str(client[3])
            )
        if failure == "untrusted_server":
            options.pop("nomi_tls_ca_cert")
        if failure == "hostname":
            url = url.replace("localhost", "127.0.0.1")
        auth = AuthClient(config(url, **options))
        try:
            with pytest.raises(BackendError, match="TLS|安全连接失败"):
                await auth.submit("登录", "code", "group", "member", "event")
            assert pauses == []
            assert events == []
        finally:
            await auth.close()


@pytest.mark.parametrize(
    "options",
    [
        {"nomi_tls_client_cert": "cert"},
        {"nomi_tls_client_key": "key"},
        {"nomi_tls_ca_cert": "ca"},
        {"nomi_tls_client_cert": "cert", "nomi_tls_client_key": "key"},
    ],
)
def test_tls_configuration_requires_pair_and_https(options):
    with pytest.raises(ValidationError):
        config("http://localhost", **options)


def test_invalid_certificate_fails_before_requests(tmp_path):
    invalid = tmp_path / "invalid.pem"
    invalid.write_text("invalid")
    with pytest.raises(ssl.SSLError):
        AuthClient(config("https://localhost", nomi_tls_ca_cert=str(invalid)))


@pytest.mark.asyncio
async def test_redirect_is_not_followed_or_retried():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(307, headers={"Location": "https://other.test"})

    auth = AuthClient(config("https://auth.test"), httpx.MockTransport(handler))
    try:
        with pytest.raises(BackendError, match="重定向"):
            await auth.submit("登录", "code", "group", "member", "event")
        assert len(calls) == 1
    finally:
        await auth.close()


@pytest.mark.parametrize(
    "options",
    [
        {"nomi_tls_client_cert": "cert"},
        {"nomi_tls_client_key": "key"},
    ],
)
def test_https_does_not_allow_incomplete_client_credentials(options):
    with pytest.raises(ValidationError, match="together"):
        config("https://localhost", **options)


def test_mismatched_client_key_fails_before_requests(certificates):
    ca, server, client = certificates
    with pytest.raises(ssl.SSLError):
        AuthClient(
            config(
                "https://localhost",
                nomi_tls_ca_cert=str(ca[2]),
                nomi_tls_client_cert=str(client[2]),
                nomi_tls_client_key=str(server[3]),
            )
        )


@pytest.mark.asyncio
async def test_secure_service_status_still_retries(certificates):
    ca, _, _ = certificates
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(503)
        return httpx.Response(200, json={"status": "VERIFIED", "name": "Alice"})

    auth = AuthClient(
        config("https://auth.test", nomi_tls_ca_cert=str(ca[2])),
        httpx.MockTransport(handler),
    )
    try:
        assert (await auth.submit("登录", "code", "group", "member", "event"))[
            "name"
        ] == "Alice"
        assert len(calls) == 2
    finally:
        await auth.close()


@pytest.mark.asyncio
async def test_raw_ssl_alert_is_not_retried():
    calls = []

    def handler(request):
        calls.append(request)
        raise ssl.SSLError("TLSV1_ALERT_UNKNOWN_CA")

    auth = AuthClient(config("https://auth.test"), httpx.MockTransport(handler))
    try:
        with pytest.raises(BackendError, match="TLS"):
            await auth.submit("登录", "code", "group", "member", "event")
        assert len(calls) == 1
    finally:
        await auth.close()


@pytest.mark.asyncio
async def test_proxy_certificate_rejection_is_not_retried():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(403, json={"code": "MTLS_REQUIRED"})

    auth = AuthClient(config("https://auth.test"), httpx.MockTransport(handler))
    try:
        with pytest.raises(BackendError, match="证书验证失败"):
            await auth.submit("登录", "code", "group", "member", "event")
        assert len(calls) == 1
    finally:
        await auth.close()


@pytest.mark.asyncio
async def test_secure_network_failure_has_generic_message(certificates):
    ca, _, _ = certificates
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ConnectTimeout("Connection timed out")

    auth = AuthClient(
        config("https://auth.test", nomi_tls_ca_cert=str(ca[2])),
        httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(BackendError, match="安全连接失败"):
            await auth.submit("登录", "code", "group", "member", "event")
        assert len(calls) == 1
    finally:
        await auth.close()

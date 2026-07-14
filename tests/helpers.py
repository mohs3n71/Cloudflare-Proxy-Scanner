import os
import tempfile
from contextlib import contextmanager

from proxy_tester.proxy_config import ProxyProfile


DEFAULT_VLESS_URL = (
    "vless://11111111-1111-4111-8111-111111111111@example.com:443"
    "?encryption=none&security=tls&sni=example.com&fp=chrome"
    "&alpn=h2%2Chttp%2F1.1&insecure=0&allowInsecure=0&type=ws"
    "&host=example.com&path=%2Fws#sample"
)


def sample_profile():
    return ProxyProfile(
        protocol="vless",
        file="sample.txt",
        name="sample.txt",
        uuid="11111111-1111-4111-8111-111111111111",
        password="",
        port=443,
        security="tls",
        sni="example.com",
        fingerprint="chrome",
        alpn="h2,http/1.1",
        allow_insecure=False,
        network="ws",
        ws_host="example.com",
        ws_path="/ws",
        encryption="none",
        alter_id=0,
        vmess_security="auto",
        header_type="none",
    )


@contextmanager
def temp_text_file(content, suffix=".txt"):
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        yield path
    finally:
        if os.path.exists(path):
            os.remove(path)

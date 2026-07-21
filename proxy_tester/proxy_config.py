import base64
import json
import os
import urllib.parse
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProxyProfile:
    protocol: str
    file: str
    name: str
    uuid: str
    password: str
    port: int
    security: str
    sni: str
    fingerprint: str
    alpn: str
    allow_insecure: bool
    network: str
    ws_host: str
    ws_path: str
    encryption: str
    alter_id: int
    vmess_security: str
    header_type: str
    xhttp_mode: str = ""
    xhttp_extra: dict = field(default_factory=dict)


SUPPORTED_SCHEMES = ("vless", "vmess", "trojan")
SUPPORTED_NETWORKS = ("ws", "xhttp")


def decode_base64(value):
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded).decode("utf-8")


def encode_base64(value):
    return base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=")


def find_config_line(path):
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if any(stripped.startswith(f"{scheme}://") for scheme in SUPPORTED_SCHEMES):
                return stripped
    raise ValueError(f"No supported config found in {path}. Use vless://, vmess://, or trojan://")


def find_proxy_config_line(path):
    return find_config_line(path)


def first_query_value(query, key, default=""):
    value = query.get(key, [default])
    return value[0] if value else default


def normalize_network(value, protocol, path):
    network = str(value or "ws").strip().lower()
    if network == "splithttp":
        network = "xhttp"
    if network not in SUPPORTED_NETWORKS:
        supported = ", ".join(SUPPORTED_NETWORKS)
        raise ValueError(f"Unsupported {protocol} transport in {path}: {value}. Supported: {supported}")
    return network


def parse_xhttp_extra(value, path):
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    try:
        extra = json.loads(value)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid XHTTP extra JSON in {path}: {exc}") from exc
    if not isinstance(extra, dict):
        raise ValueError(f"Invalid XHTTP extra JSON in {path}: expected an object")
    return extra


def parse_proxy_config(path):
    url = find_config_line(path)
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme == "vmess":
        return parse_vmess_config(path, url)
    if parsed.scheme == "trojan":
        return parse_trojan_config(path, parsed)
    if parsed.scheme != "vless":
        raise ValueError(f"Unsupported config scheme in {path}")
    if not parsed.username:
        raise ValueError(f"Missing UUID in {path}")
    if not parsed.port:
        raise ValueError(f"Missing port in {path}")

    query = urllib.parse.parse_qs(parsed.query)
    network = normalize_network(first_query_value(query, "type", "ws"), "VLESS", path)

    sni = first_query_value(query, "sni", parsed.hostname or "")
    ws_host = first_query_value(query, "host", sni)
    allow_insecure = first_query_value(query, "allowInsecure", first_query_value(query, "insecure", "0"))

    return ProxyProfile(
        protocol="vless",
        file=path,
        name=os.path.basename(path),
        uuid=urllib.parse.unquote(parsed.username),
        password="",
        port=parsed.port,
        security=first_query_value(query, "security", "tls"),
        sni=urllib.parse.unquote(sni),
        fingerprint=urllib.parse.unquote(first_query_value(query, "fp", "chrome")),
        alpn=urllib.parse.unquote(first_query_value(query, "alpn", "http/1.1")),
        allow_insecure=allow_insecure in ("1", "true", "True"),
        network=network,
        ws_host=urllib.parse.unquote(ws_host),
        ws_path=urllib.parse.unquote(first_query_value(query, "path", "/")),
        encryption=first_query_value(query, "encryption", "none"),
        alter_id=0,
        vmess_security="auto",
        header_type="none",
        xhttp_mode=urllib.parse.unquote(first_query_value(query, "mode", "")) if network == "xhttp" else "",
        xhttp_extra=parse_xhttp_extra(first_query_value(query, "extra", ""), path) if network == "xhttp" else {},
    )


def parse_vmess_config(path, url):
    raw = url[len("vmess://") :]
    try:
        data = json.loads(decode_base64(raw))
    except Exception as exc:
        raise ValueError(f"Invalid vmess:// config in {path}: {exc}") from exc

    network = normalize_network(data.get("net") or "ws", "VMess", path)
    uuid = data.get("id") or ""
    if not uuid:
        raise ValueError(f"Missing VMess id in {path}")
    port = data.get("port")
    if not port:
        raise ValueError(f"Missing VMess port in {path}")

    host = data.get("host") or data.get("add") or ""
    sni = data.get("sni") or host
    return ProxyProfile(
        protocol="vmess",
        file=path,
        name=os.path.basename(path),
        uuid=uuid,
        password="",
        port=int(port),
        security=data.get("tls") or "tls",
        sni=sni,
        fingerprint=data.get("fp") or "chrome",
        alpn=data.get("alpn") or "http/1.1",
        allow_insecure=str(data.get("allowInsecure") or data.get("insecure") or "0") in ("1", "true", "True"),
        network=network,
        ws_host=host,
        ws_path=data.get("path") or "/",
        encryption="none",
        alter_id=int(data.get("aid") or 0),
        vmess_security=data.get("scy") or "auto",
        header_type=data.get("type") or "none",
        xhttp_mode=str(data.get("mode") or "") if network == "xhttp" else "",
        xhttp_extra=parse_xhttp_extra(data.get("extra"), path) if network == "xhttp" else {},
    )


def parse_trojan_config(path, parsed):
    if not parsed.username:
        raise ValueError(f"Missing Trojan password in {path}")
    if not parsed.port:
        raise ValueError(f"Missing port in {path}")

    query = urllib.parse.parse_qs(parsed.query)
    network = normalize_network(first_query_value(query, "type", "ws"), "Trojan", path)

    sni = first_query_value(query, "sni", parsed.hostname or "")
    ws_host = first_query_value(query, "host", sni)
    allow_insecure = first_query_value(query, "allowInsecure", first_query_value(query, "insecure", "0"))
    return ProxyProfile(
        protocol="trojan",
        file=path,
        name=os.path.basename(path),
        uuid="",
        password=urllib.parse.unquote(parsed.username),
        port=parsed.port,
        security=first_query_value(query, "security", "tls"),
        sni=urllib.parse.unquote(sni),
        fingerprint=urllib.parse.unquote(first_query_value(query, "fp", "chrome")),
        alpn=urllib.parse.unquote(first_query_value(query, "alpn", "http/1.1")),
        allow_insecure=allow_insecure in ("1", "true", "True"),
        network=network,
        ws_host=urllib.parse.unquote(ws_host),
        ws_path=urllib.parse.unquote(first_query_value(query, "path", "/")),
        encryption="none",
        alter_id=0,
        vmess_security="auto",
        header_type="none",
        xhttp_mode=urllib.parse.unquote(first_query_value(query, "mode", "")) if network == "xhttp" else "",
        xhttp_extra=parse_xhttp_extra(first_query_value(query, "extra", ""), path) if network == "xhttp" else {},
    )


def make_proxy_url(ip, name, profile):
    if profile.protocol == "vmess":
        data = {
            "v": "2",
            "ps": name,
            "add": ip,
            "port": str(profile.port),
            "id": profile.uuid,
            "aid": str(profile.alter_id),
            "scy": profile.vmess_security,
            "net": profile.network,
            "type": profile.header_type,
            "host": profile.ws_host,
            "path": profile.ws_path,
            "tls": profile.security,
            "sni": profile.sni,
            "fp": profile.fingerprint,
            "alpn": profile.alpn,
        }
        if profile.network == "xhttp":
            data["mode"] = profile.xhttp_mode
            if profile.xhttp_extra:
                data["extra"] = json.dumps(profile.xhttp_extra, separators=(",", ":"))
        return f"vmess://{encode_base64(json.dumps(data, separators=(',', ':')))}"
    if profile.protocol == "trojan":
        query = common_url_query(profile)
        encoded_query = urllib.parse.urlencode(query, quote_via=urllib.parse.quote)
        encoded_name = urllib.parse.quote(name, safe="")
        password = urllib.parse.quote(profile.password, safe="")
        return f"trojan://{password}@{ip}:{profile.port}?{encoded_query}#{encoded_name}"

    query = {
        "encryption": profile.encryption,
        **common_url_query(profile),
    }
    encoded_query = urllib.parse.urlencode(query, quote_via=urllib.parse.quote)
    encoded_name = urllib.parse.quote(name, safe="")
    return f"vless://{profile.uuid}@{ip}:{profile.port}?{encoded_query}#{encoded_name}"


def common_url_query(profile):
    query = {
        "security": profile.security,
        "sni": profile.sni,
        "fp": profile.fingerprint,
        "alpn": profile.alpn,
        "insecure": "1" if profile.allow_insecure else "0",
        "allowInsecure": "1" if profile.allow_insecure else "0",
        "type": profile.network,
        "host": profile.ws_host,
        "path": profile.ws_path,
    }
    if profile.network == "xhttp":
        query["mode"] = profile.xhttp_mode
        if profile.xhttp_extra:
            query["extra"] = json.dumps(profile.xhttp_extra, separators=(",", ":"))
    return query

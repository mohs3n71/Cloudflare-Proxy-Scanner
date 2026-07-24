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
    address: str = ""
    flow: str = ""
    grpc_service_name: str = ""
    grpc_authority: str = ""
    reality_public_key: str = ""
    reality_short_id: str = ""
    reality_spider_x: str = ""
    shadowsocks_method: str = ""


SUPPORTED_SCHEMES = ("vless", "vmess", "trojan", "ss")
SUPPORTED_NETWORKS = ("ws", "xhttp", "tcp", "grpc")


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
    raise ValueError(f"No supported config found in {path}. Use vless://, vmess://, trojan://, or ss://")


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
    return parse_proxy_url(url, source=path, name=os.path.basename(path))


def parse_proxy_url(url, source="<input>", name=None):
    url = url.strip()
    parsed = urllib.parse.urlparse(url)
    profile_name = name or config_display_name(url, source)
    if parsed.scheme == "vmess":
        return parse_vmess_config(source, url, profile_name)
    if parsed.scheme == "trojan":
        return parse_trojan_config(source, parsed, profile_name)
    if parsed.scheme == "ss":
        return parse_shadowsocks_config(source, url, profile_name)
    if parsed.scheme != "vless":
        raise ValueError(f"Unsupported config scheme in {source}")
    if not parsed.username:
        raise ValueError(f"Missing UUID in {source}")
    if not parsed.port:
        raise ValueError(f"Missing port in {source}")

    query = urllib.parse.parse_qs(parsed.query)
    network = normalize_network(first_query_value(query, "type", "ws"), "VLESS", source)

    sni = first_query_value(query, "sni", parsed.hostname or "")
    ws_host = first_query_value(query, "host", sni)
    allow_insecure = first_query_value(query, "allowInsecure", first_query_value(query, "insecure", "0"))

    return ProxyProfile(
        protocol="vless",
        file=source,
        name=profile_name,
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
        xhttp_extra=parse_xhttp_extra(first_query_value(query, "extra", ""), source) if network == "xhttp" else {},
        address=parsed.hostname or "",
        flow=urllib.parse.unquote(first_query_value(query, "flow", "")),
        grpc_service_name=urllib.parse.unquote(
            first_query_value(query, "serviceName", first_query_value(query, "service_name", ""))
        ),
        grpc_authority=urllib.parse.unquote(first_query_value(query, "authority", ws_host)),
        reality_public_key=urllib.parse.unquote(first_query_value(query, "pbk", "")),
        reality_short_id=urllib.parse.unquote(first_query_value(query, "sid", "")),
        reality_spider_x=urllib.parse.unquote(first_query_value(query, "spx", "")),
    )


def parse_vmess_config(path, url, name=None):
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
    transport_security = str(data.get("tls") or "none")
    return ProxyProfile(
        protocol="vmess",
        file=path,
        name=name or os.path.basename(path),
        uuid=uuid,
        password="",
        port=int(port),
        security=transport_security,
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
        address=str(data.get("add") or ""),
        grpc_service_name=str(data.get("path") or "") if network == "grpc" else "",
        grpc_authority=str(data.get("host") or "") if network == "grpc" else "",
    )


def parse_trojan_config(path, parsed, name=None):
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
        name=name or os.path.basename(path),
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
        address=parsed.hostname or "",
        grpc_service_name=urllib.parse.unquote(
            first_query_value(query, "serviceName", first_query_value(query, "service_name", ""))
        ),
        grpc_authority=urllib.parse.unquote(first_query_value(query, "authority", ws_host)),
        reality_public_key=urllib.parse.unquote(first_query_value(query, "pbk", "")),
        reality_short_id=urllib.parse.unquote(first_query_value(query, "sid", "")),
        reality_spider_x=urllib.parse.unquote(first_query_value(query, "spx", "")),
    )


def config_display_name(url, source="<input>"):
    parsed = urllib.parse.urlparse(url)
    if parsed.fragment:
        return urllib.parse.unquote(parsed.fragment)
    if parsed.scheme == "vmess":
        try:
            return str(json.loads(decode_base64(url[len("vmess://") :])).get("ps") or "VMess")
        except Exception:
            return "VMess"
    return os.path.basename(source) if source not in ("", "<input>") else parsed.scheme.upper()


def parse_shadowsocks_config(path, url, name=None):
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query)
    if first_query_value(query, "plugin", ""):
        raise ValueError(f"Shadowsocks plugins are not supported by Xray core in {path}")

    method = password = address = ""
    port = None
    if parsed.hostname and parsed.port and parsed.username:
        credentials = urllib.parse.unquote(parsed.username)
        try:
            credentials = decode_base64(credentials)
        except Exception:
            if parsed.password is not None:
                credentials = f"{urllib.parse.unquote(parsed.username)}:{urllib.parse.unquote(parsed.password)}"
        if ":" not in credentials:
            raise ValueError(f"Invalid Shadowsocks credentials in {path}")
        method, password = credentials.split(":", 1)
        address, port = parsed.hostname, parsed.port
    else:
        encoded = url[len("ss://") :].split("#", 1)[0].split("?", 1)[0]
        try:
            decoded = decode_base64(encoded)
            credentials, endpoint = decoded.rsplit("@", 1)
            method, password = credentials.split(":", 1)
            endpoint_parsed = urllib.parse.urlparse(f"ss://{endpoint}")
            address, port = endpoint_parsed.hostname, endpoint_parsed.port
        except Exception as exc:
            raise ValueError(f"Invalid Shadowsocks config in {path}: {exc}") from exc

    if not method or not password or not address or not port:
        raise ValueError(f"Incomplete Shadowsocks config in {path}")
    return ProxyProfile(
        protocol="shadowsocks",
        file=path,
        name=name or config_display_name(url, path),
        uuid="",
        password=password,
        port=port,
        security="none",
        sni="",
        fingerprint="",
        alpn="",
        allow_insecure=False,
        network="tcp",
        ws_host="",
        ws_path="",
        encryption="none",
        alter_id=0,
        vmess_security="auto",
        header_type="none",
        address=address,
        shadowsocks_method=method,
    )


def make_proxy_url(ip, name, profile):
    if profile.protocol == "shadowsocks":
        credentials = encode_base64(f"{profile.shadowsocks_method}:{profile.password}")
        encoded_name = urllib.parse.quote(name, safe="")
        host = f"[{ip}]" if ":" in ip and not ip.startswith("[") else ip
        return f"ss://{credentials}@{host}:{profile.port}#{encoded_name}"
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
        if profile.network == "grpc":
            data["path"] = profile.grpc_service_name
            data["host"] = profile.grpc_authority
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
    if profile.flow:
        query["flow"] = profile.flow
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
    elif profile.network == "grpc":
        query["serviceName"] = profile.grpc_service_name
        if profile.grpc_authority:
            query["authority"] = profile.grpc_authority
    if profile.security == "reality":
        query["pbk"] = profile.reality_public_key
        query["sid"] = profile.reality_short_id
        query["spx"] = profile.reality_spider_x
    return query

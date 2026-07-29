"""快捷入口：从 URL / 页面 HTML 解析准确的名称与备注。"""

from __future__ import annotations

import html as html_lib
import logging
import re
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

from web_favicon_proxy import normalize_page_url

logger = logging.getLogger("web-agent")

_USER_AGENT = "YaahlanWebAgent/1.0"
_TIMEOUT_S = 8
_MAX_HTML_BYTES = 512 * 1024

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_META_CONTENT_RE = re.compile(
    r'<meta[^>]+(?:name|property)=["\'](?P<key>[^"\']+)["\'][^>]+content=["\'](?P<val>[^"\']*)["\']',
    re.I,
)
_META_CONTENT_ALT_RE = re.compile(
    r'<meta[^>]+content=["\'](?P<val>[^"\']*)["\'][^>]+(?:name|property)=["\'](?P<key>[^"\']+)["\']',
    re.I,
)
_UUID_RE = re.compile(r"^[a-f0-9-]{8,}$", re.I)
_FILE_EXT_RE = re.compile(r"\.(md|html?|json|py|js|tsx?|vue)$", re.I)

# 精确 host → (label, description)
_KNOWN_HOSTS: dict[str, tuple[str, str]] = {
    "tunnel.wemomo.com": ("Tunnel 抓包", "HTTP 抓包查询"),
    "yaahlan-admin-alpha.wemomo.com": ("Yaahlan Admin", "测试后台 · 用户/动态/运营查询"),
    "mse.wemomo.com": ("MSE 配置", "服务配置 / familyPkConfig 等"),
    "mdp-nova-alpha.wemomo.com": ("MDP Nova", "中台配置 / 礼物道具等"),
    "alpha-mdp-user-admin-api-stage.wemomo.com": ("道具管理 API", "Stage 道具查询后台接口"),
    "risk-backend-oversea.wemomo.com": ("风控后台", "海外风控 · 设备/账号"),
    "melon-gateway-alpha-stage.immomo.com": ("Melon Gateway", "Yaahlan CMS / 家族等网关"),
    "test-s.immomo.com": ("test-s H5", "测试环境 H5 宿主页"),
    "aegis.immomo.com": ("Aegis 应用", "应用发布 / 配置"),
    "oa.dingtalk.com": ("钉钉 OA", "钉钉办公 / 文档"),
    "open.dingtalk.com": ("钉钉开放平台", "应用 / OAuth 配置"),
    "ai-yaahlan.wemomo.com": ("服务端 Agent", "查接口实现 / MOA 定义 / 代码"),
    "127.0.0.1": ("本地服务", "本机开发 / 调试"),
    "localhost": ("本地服务", "本机开发 / 调试"),
}

# host 包含关键字 → (label, description)
_KNOWN_HOST_CONTAINS: list[tuple[str, str, str]] = [
    ("git.wemomo.com", "GitLab", "Git 仓库 / 文档"),
    ("gitlab.", "GitLab", "Git 仓库 / 文档"),
    ("dingtalk.com", "钉钉", "钉钉协作 / 文档"),
    ("wemomo.com", "内网平台", "陌陌内网服务"),
    ("immomo.com", "内网平台", "陌陌内网服务"),
    ("yaahlan", "Yaahlan", "Yaahlan 相关服务"),
]


def _strip_html(text: str) -> str:
    cleaned = re.sub(r"<[^>]+>", " ", text or "")
    cleaned = html_lib.unescape(cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _parse_meta_tags(html: str) -> dict[str, str]:
    meta: dict[str, str] = {}
    for pattern in (_META_CONTENT_RE, _META_CONTENT_ALT_RE):
        for match in pattern.finditer(html):
            key = match.group("key").lower()
            val = _strip_html(match.group("val"))
            if val and key not in meta:
                meta[key] = val
    return meta


def _extract_html_metadata(html: str) -> tuple[str, str]:
    title = ""
    match = _TITLE_RE.search(html)
    if match:
        title = _strip_html(match.group(1))
    meta = _parse_meta_tags(html)
    description = (
        meta.get("description")
        or meta.get("og:description")
        or meta.get("twitter:description")
        or ""
    )
    og_title = meta.get("og:title") or meta.get("twitter:title") or ""
    if og_title and (not title or len(og_title) < len(title)):
        title = og_title
    return title, description


def _clean_title(title: str, host: str) -> str:
    text = re.sub(r"\s+", " ", (title or "").strip())
    if not text:
        return ""
    host_base = host.split(":")[0].lower()
    suffixes = [
        r"\s*[-|·|—]\s*GitLab.*$",
        r"\s*[-|·|—]\s*Yaahlan.*$",
        r"\s*[-|·|—]\s*钉钉.*$",
        r"\s*[-|·|—]\s*DingTalk.*$",
        r"\s*[-|·|—]\s*Momo.*$",
        r"\s*[-|·|—]\s*陌陌.*$",
        rf"\s*[-|·|—]\s*{re.escape(host_base)}.*$",
        r"\s*[-|·|—]\s*Admin.*$",
    ]
    for pattern in suffixes:
        text = re.sub(pattern, "", text, flags=re.I).strip()
    return text[:40]


def _host_without_www(hostname: str) -> str:
    host = (hostname or "").strip().lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _known_host_metadata(host: str) -> tuple[str, str] | None:
    if host in _KNOWN_HOSTS:
        return _KNOWN_HOSTS[host]
    for needle, label, desc in _KNOWN_HOST_CONTAINS:
        if needle in host:
            return label, desc
    return None


def _segment_label(segment: str) -> str:
    text = unquote(segment or "").strip()
    if not text or _UUID_RE.match(text):
        return ""
    text = _FILE_EXT_RE.sub("", text)
    text = text.replace("-", " ").replace("_", " ")
    text = re.sub(r"\s+", " ", text).strip()
    if not text or len(text) < 2:
        return ""
    if text.isascii() and len(text) <= 4 and text.islower():
        return text.upper()
    return text[:40]


def _path_metadata(parsed, host: str) -> tuple[str, str]:
    path = unquote(parsed.path or "")
    segments = [s for s in path.split("/") if s]
    label = ""
    description_parts: list[str] = []

    if "git.wemomo.com" in host or "gitlab." in host:
        if "/-/blob/" in path or "/-/tree/" in path:
            blob_idx = path.find("/-/blob/")
            tree_idx = path.find("/-/tree/")
            idx = blob_idx if blob_idx >= 0 else tree_idx
            if idx >= 0:
                tail = path[idx:].split("/")
                if len(tail) >= 3:
                    filename = tail[-1]
                    file_label = _segment_label(filename)
                    if file_label:
                        label = file_label
                        repo_parts = tail[3:-1] if len(tail) > 4 else []
                        if repo_parts:
                            description_parts.append("/".join(repo_parts[-2:]))
        if not label and segments:
            label = _segment_label(segments[-1])
        if not description_parts:
            description_parts.append(host)
            if path and path != "/":
                description_parts.append(path[:60])
        desc = " · ".join(p for p in description_parts if p)[:80]
        if not desc:
            desc = "Git 仓库 / 文档"
        return label or "GitLab", desc

    hash_part = (parsed.fragment or "").strip()
    if hash_part.startswith("/"):
        hash_segments = [s for s in hash_part.split("/") if s]
        if hash_segments:
            hash_label = _segment_label(hash_segments[-1])
            if hash_label:
                label = hash_label

    if not label:
        for segment in reversed(segments):
            candidate = _segment_label(segment)
            if not candidate:
                continue
            if candidate.lower() in ("index", "home", "default", "api", "v1", "v2", "v3"):
                continue
            label = candidate
            break

    port = f":{parsed.port}" if parsed.port and parsed.port not in (80, 443) else ""
    base = f"{host}{port}"
    if path and path != "/":
        description_parts.append(f"{base}{path[:50]}")
    else:
        description_parts.append(base)
    if hash_part:
        description_parts.append(f"#{hash_part[:24]}")
    desc = " · ".join(description_parts)[:80]
    return label, desc


def _heuristic_metadata(url: str) -> dict[str, str]:
    parsed = urlparse(normalize_page_url(url))
    host = _host_without_www(parsed.hostname or "")
    if not host:
        text = url[:40]
        return {"label": text, "description": url[:80], "source": "fallback"}

    known = _known_host_metadata(host)
    path_label, path_desc = _path_metadata(parsed, host)

    if known:
        label, desc = known
        if path_label and path_label.lower() not in (label.lower(), host.lower(), "gitlab"):
            label = path_label
        if path_desc and path_desc not in (desc, host):
            has_detail = " · " in path_desc or path_desc.count("/") > host.count("/")
            if has_detail or (not desc):
                desc = path_desc
        return {"label": label[:40], "description": desc[:80], "source": "known_host"}

    label = path_label or host.split(".")[0].upper() if host.count(".") == 0 else host.split(".")[0]
    if not path_label:
        label = host if len(host) <= 40 else host[:40]
    desc = path_desc or host
    return {"label": label[:40], "description": desc[:80], "source": "heuristic"}


def fetch_page_html(url: str) -> str | None:
    normalized = normalize_page_url(url)
    if not normalized:
        return None
    parsed = urlparse(normalized)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None
    try:
        req = Request(normalized, headers={"User-Agent": _USER_AGENT, "Accept": "text/html,*/*"})
        with urlopen(req, timeout=_TIMEOUT_S) as resp:
            ctype = (resp.headers.get_content_type() or "").lower()
            if "html" not in ctype and "text" not in ctype:
                return None
            data = resp.read(_MAX_HTML_BYTES + 1)
            if len(data) > _MAX_HTML_BYTES:
                data = data[:_MAX_HTML_BYTES]
            charset = "utf-8"
            for key, val in resp.headers.items():
                if key.lower() == "content-type" and "charset=" in val.lower():
                    charset = val.split("charset=")[-1].split(";")[0].strip() or charset
                    break
            return data.decode(charset, errors="replace")
    except (HTTPError, URLError, TimeoutError, ValueError, UnicodeDecodeError) as exc:
        logger.debug("bookmark metadata fetch miss %s: %s", normalized, exc)
        return None


def resolve_bookmark_metadata(url: str, *, fetch_html: bool = True) -> dict[str, str]:
    """解析 URL，返回 label / description / source。"""
    normalized = normalize_page_url(url)
    if not normalized:
        return {"label": "", "description": "", "source": "empty"}

    parsed = urlparse(normalized)
    host = _host_without_www(parsed.hostname or "")

    page_title = ""
    page_desc = ""
    if fetch_html:
        html = fetch_page_html(normalized)
        if html:
            page_title, page_desc = _extract_html_metadata(html)

    heuristic = _heuristic_metadata(normalized)
    label = heuristic["label"]
    description = heuristic["description"]
    source = heuristic["source"]

    if page_title:
        cleaned = _clean_title(page_title, host)
        if cleaned and len(cleaned) >= 2:
            label = cleaned[:40]
            source = "page_title"

    if page_desc:
        page_desc = re.sub(r"\s+", " ", page_desc.strip())[:80]
        if page_desc:
            description = page_desc
            if source == "heuristic":
                source = "page_description"

    # 页面标题过泛时保留路径/已知站点名
    generic_titles = {"", "home", "index", "welcome", "登录", "login", "dashboard", "管理后台"}
    if label.lower() in generic_titles or label.lower() == host.lower():
        fallback_label = heuristic["label"]
        if fallback_label and fallback_label.lower() not in generic_titles:
            label = fallback_label

    if not description or description == host:
        if heuristic["description"] and heuristic["description"] != host:
            description = heuristic["description"]

    return {
        "label": label[:40],
        "description": description[:80],
        "source": source,
    }

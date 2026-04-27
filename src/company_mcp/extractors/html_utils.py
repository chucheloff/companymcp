import json
import re
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urljoin


class _TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            value = re.sub(r"\s+", " ", unescape(data)).strip()
            if value:
                self.parts.append(value)


def extract_title(html: str) -> str | None:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    value = re.sub(r"\s+", " ", unescape(match.group(1))).strip()
    return value or None


def extract_meta(html: str) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for match in re.finditer(r"<meta\s+([^>]+)>", html, flags=re.IGNORECASE | re.DOTALL):
        attrs = _parse_attrs(match.group(1))
        key = attrs.get("name") or attrs.get("property")
        content = attrs.get("content")
        if key and content:
            metadata[key.lower()] = re.sub(r"\s+", " ", unescape(content)).strip()
    return metadata


def extract_json_ld(html: str) -> list[dict]:
    blocks: list[dict] = []
    pattern = r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>'
    for match in re.finditer(pattern, html, flags=re.IGNORECASE | re.DOTALL):
        raw = unescape(match.group(1)).strip()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            blocks.append(parsed)
        elif isinstance(parsed, list):
            blocks.extend(item for item in parsed if isinstance(item, dict))
    return blocks


def extract_text(html: str, *, limit: int = 12_000) -> str:
    parser = _TextParser()
    parser.feed(html)
    text = " ".join(parser.parts)
    return re.sub(r"\s+", " ", text).strip()[:limit]


def extract_links(html: str, base_url: str) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    for match in re.finditer(r"<a\s+([^>]+)>(.*?)</a>", html, flags=re.IGNORECASE | re.DOTALL):
        attrs = _parse_attrs(match.group(1))
        href = attrs.get("href")
        if not href:
            continue
        label = extract_text(match.group(2), limit=200)
        links.append((urljoin(base_url, href), label))
    return links


def _parse_attrs(raw: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    pattern = r"([\w:-]+)\s*=\s*([\"'])(.*?)\2"
    for key, _quote, value in re.findall(pattern, raw, flags=re.DOTALL):
        attrs[key.lower()] = unescape(value).strip()
    return attrs

import socket
from ipaddress import ip_address
from urllib.parse import urljoin, urlparse

import httpx

from company_mcp.cache.store import get_json, set_json
from company_mcp.extractors.base import PageDocument
from company_mcp.extractors.browser_snapshot import snapshot_url
from company_mcp.extractors.html_utils import extract_meta, extract_text, extract_title
from company_mcp.extractors.registry import EXTRACTOR_VERSION, merge_facts, run_extractors
from company_mcp.mcp.schemas import CompanyPayload, CompanyProfileInput, CompanyProfileOutput, SourceEvidence

MAX_REDIRECTS = 5


def _normalize_domain(domain: str) -> str:
    candidate = domain.strip().lower()
    if candidate.startswith("http://") or candidate.startswith("https://"):
        parsed = urlparse(candidate)
        candidate = parsed.netloc or parsed.path

    # Drop path, credentials, and port if provided by caller.
    candidate = candidate.split("/", 1)[0]
    candidate = candidate.rsplit("@", 1)[-1]
    candidate = candidate.split(":", 1)[0]
    return candidate.strip(".")


async def build_company_profile(data: CompanyProfileInput) -> CompanyProfileOutput:
    normalized_domain = _normalize_domain(data.domain)
    if not _is_safe_public_domain(normalized_domain):
        return CompanyProfileOutput(
            company=CompanyPayload(
                name=normalized_domain.split(".")[0].replace("-", " ").title(),
                domain=normalized_domain,
                description="Blocked domain.",
            ),
            confidence=0.0,
            sources=[],
            warnings=["Domain is blocked by SSRF policy (localhost/private IP/reserved target)."],
        )

    cache_key = f"company_profile:{EXTRACTOR_VERSION}:{normalized_domain}:{data.pipeline}"
    cached = await get_json(cache_key)
    if cached:
        return CompanyProfileOutput.model_validate(cached)

    homepage = f"https://{normalized_domain}"
    candidates = [
        homepage,
        f"{homepage}/about",
        f"{homepage}/company",
        f"{homepage}/careers",
        f"{homepage}/jobs",
        f"{homepage}/team",
        f"{homepage}/press",
        f"{homepage}/news",
    ]
    selected_urls = candidates[: data.max_pages]

    warnings: list[str] = []
    sources: list[SourceEvidence] = []
    pages: list[PageDocument] = []

    if data.pipeline == "browser_snapshot":
        for url in selected_urls:
            try:
                page = await snapshot_url(url, validate_url=_validate_public_url)
                description = (
                    page.metadata.get("description")
                    or page.metadata.get("og:description")
                    or page.metadata.get("twitter:description")
                )
                evidence = description or "Fetched page successfully."
                sources.append(SourceEvidence(url=page.url, title=page.title, evidence=evidence))
                pages.append(page)
            except UnsafeUrlError as exc:
                warnings.append(f"Blocked {url}: {exc}")
            except Exception as exc:
                warnings.append(f"Failed to fetch {url}: {type(exc).__name__}.")
    else:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=False) as client:
            for url in selected_urls:
                try:
                    response = await _fetch_public_url(client, url)
                    if response.status_code >= 400:
                        warnings.append(f"Skipped {url}: HTTP {response.status_code}.")
                        continue
                    html_text = response.text
                    metadata = extract_meta(html_text)
                    title = extract_title(html_text) or f"{normalized_domain} page"
                    description = (
                        metadata.get("description")
                        or metadata.get("og:description")
                        or metadata.get("twitter:description")
                    )
                    evidence = description or "Fetched page successfully."
                    sources.append(SourceEvidence(url=str(response.url), title=title, evidence=evidence))
                    pages.append(
                        PageDocument(
                            url=str(response.url),
                            title=title,
                            html=html_text,
                            text=extract_text(html_text),
                            metadata=metadata,
                        )
                    )
                except UnsafeUrlError as exc:
                    warnings.append(f"Blocked {url}: {exc}")
                except Exception as exc:
                    warnings.append(f"Failed to fetch {url}: {type(exc).__name__}.")

    if not pages:
        payload = CompanyPayload(
            name=normalized_domain.split(".")[0].replace("-", " ").title(),
            domain=normalized_domain,
            description="No reachable pages for profile extraction.",
            careers_url=f"{homepage}/careers",
        )
        result = CompanyProfileOutput(
            company=payload,
            confidence=0.05,
            sources=[],
            warnings=warnings + ["No evidence found; returning empty profile scaffold."],
        )
        await set_json(cache_key, result.model_dump(mode="json"), ttl_seconds=3600)
        return result

    extractor_results = await run_extractors(pages, data.pipeline)
    facts = merge_facts(extractor_results)
    warnings.extend(facts.warnings)

    payload = CompanyPayload(
        name=facts.name or normalized_domain.split(".")[0].replace("-", " ").title(),
        domain=normalized_domain,
        description=facts.description or "Profile extracted from public company pages.",
        industry=facts.industry,
        products=facts.products,
        hq=facts.hq,
        size=facts.size,
        careers_url=facts.careers_url or f"{homepage}/careers",
        linkedin_url=facts.linkedin_url,
    )
    if facts.evidence:
        sources.extend(
            SourceEvidence(url=pages[0].url, title="Extractor evidence", evidence=item)
            for item in facts.evidence[:3]
        )

    result = CompanyProfileOutput(
        company=payload,
        confidence=max(facts.confidence, 0.35 if len(pages) == 1 else 0.55),
        sources=sources,
        warnings=list(dict.fromkeys(warnings)),
    )
    ttl_seconds = max(3600, data.freshness_hours * 3600)
    await set_json(cache_key, result.model_dump(mode="json"), ttl_seconds=ttl_seconds)
    return result


class UnsafeUrlError(ValueError):
    pass


async def _fetch_public_url(client: httpx.AsyncClient, url: str) -> httpx.Response:
    current_url = _validate_public_url(url)
    for _ in range(MAX_REDIRECTS + 1):
        response = await client.get(current_url)
        final_url = _validate_public_url(str(response.url))
        if response.is_redirect:
            location = response.headers.get("location")
            if not location:
                raise UnsafeUrlError("redirect response has no Location header")
            current_url = _validate_public_url(urljoin(final_url, location))
            continue
        return response
    raise UnsafeUrlError(f"too many redirects; limit is {MAX_REDIRECTS}")


def _validate_public_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise UnsafeUrlError("only https URLs are allowed")
    if not parsed.hostname:
        raise UnsafeUrlError("URL is missing a hostname")
    if not _is_safe_public_domain(parsed.hostname):
        raise UnsafeUrlError("target host is localhost, private, reserved, or unresolved")
    return parsed.geturl()


def _is_safe_public_domain(domain: str) -> bool:
    if not domain:
        return False
    lowered = domain.lower().strip()
    blocked_hosts = {"localhost", "localhost.localdomain"}
    if lowered in blocked_hosts or lowered.endswith(".local"):
        return False

    # Block direct IPs in non-public ranges.
    try:
        ip = ip_address(lowered)
        return not _is_blocked_ip(ip)
    except ValueError:
        pass

    # Resolve host and ensure all answers are public.
    try:
        infos = socket.getaddrinfo(lowered, 443, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return False

    for info in infos:
        raw_ip = info[4][0]
        ip = ip_address(raw_ip)
        if _is_blocked_ip(ip):
            return False
    return True


def _is_blocked_ip(ip) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def _extract_title(html: str) -> str | None:
    return extract_title(html)


def _extract_meta_description(html: str) -> str | None:
    return extract_meta(html).get("description")

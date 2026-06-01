"""
Public SEO audit helpers for any website URL.
"""

from __future__ import annotations

import json
import re
import socket
import ssl
import sys
import time
from collections import Counter, defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser
from typing import Any, DefaultDict, Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, urlencode, urldefrag, urljoin, urlparse

import requests

def _log_progress(message: str) -> None:
    sys.stdout.write(f"PROGRESS: {message}\n")
    sys.stdout.flush()


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
}

MAX_INTERNAL_LINK_SAMPLES = 40
MAX_CRAWL_PAGES = 5
MAX_CRAWL_DEPTH = 1
MAX_BROKEN_LINK_CHECKS = 10
MAX_CRAWL_PAGES_HARD_LIMIT = 20
TRACKING_QUERY_PARAMS = {"fbclid", "gclid", "msclkid", "yclid", "mc_cid", "mc_eid"}
STATIC_FILE_SUFFIXES = (
    ".7z",
    ".avi",
    ".css",
    ".doc",
    ".docx",
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".js",
    ".mov",
    ".mp3",
    ".mp4",
    ".pdf",
    ".png",
    ".ppt",
    ".pptx",
    ".rar",
    ".svg",
    ".webp",
    ".wmv",
    ".xls",
    ".xlsx",
    ".zip",
)


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _strip_www(hostname: str) -> str:
    hostname = hostname.lower().strip()
    if hostname.startswith("www."):
        return hostname[4:]
    return hostname


def _is_internal_link(link_host: str, base_host: str) -> bool:
    link_host = _strip_www(link_host)
    base_host = _strip_www(base_host)
    if not link_host or not base_host:
        return False
    return (
        link_host == base_host
        or link_host.endswith(f".{base_host}")
        or base_host.endswith(f".{link_host}")
    )


def _normalize_candidates(url_or_domain: str) -> List[str]:
    raw = url_or_domain.strip()
    if not raw:
        return []
    if "://" in raw:
        return [raw]
    return [f"https://{raw}", f"http://{raw}"]


def _first_meta(meta_tags: Dict[str, List[str]], key: str) -> str:
    values = meta_tags.get(key.lower(), [])
    return values[0] if values else ""


def _unique_preserve_order(values: List[str]) -> List[str]:
    seen_values = set()
    ordered_values: List[str] = []

    for value in values:
        if value in seen_values:
            continue
        seen_values.add(value)
        ordered_values.append(value)

    return ordered_values


def _looks_like_html_candidate(candidate_url: str) -> bool:
    path = urlparse(candidate_url).path.lower()
    return not path.endswith(STATIC_FILE_SUFFIXES)


def _normalize_crawl_candidate(candidate_url: str) -> str:
    normalized_url, _ = urldefrag(candidate_url)
    parsed_url = urlparse(normalized_url)

    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        return ""

    filtered_query = [
        (key, value)
        for key, value in parse_qsl(parsed_url.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in TRACKING_QUERY_PARAMS
    ]

    normalized_query = urlencode(filtered_query, doseq=True)
    return parsed_url._replace(query=normalized_query).geturl()


def _summarize_page(result: Dict[str, Any]) -> Dict[str, Any]:
    """Return a compact page summary for crawl results."""
    return {
        "url": result.get("url", ""),
        "final_url": result.get("final_url", ""),
        "status_code": result.get("status_code"),
        "score": result.get("score"),
        "summary": result.get("summary", ""),
        "title": result.get("content", {}).get("title", ""),
        "meta_description": result.get("content", {}).get("meta_description", ""),
        "h1_count": result.get("headings", {}).get("h1_count", 0),
        "h2_count": result.get("headings", {}).get("h2_count", 0),
        "images_missing_alt": result.get("images", {}).get("missing_alt", 0),
        "internal_links": result.get("links", {}).get("internal", 0),
        "external_links": result.get("links", {}).get("external", 0),
        "indexable": not result.get("technical", {}).get("noindex", False),
        "redirect_count": result.get("technical", {}).get("redirect_count", 0),
        "broken_links_count": result.get("broken_links", {}).get("broken_count", 0),
        "issues": result.get("issues", []),
        "recommendations": result.get("recommendations", []),
        "geo_optimization": result.get("geo_optimization", {}),
    }


class _SEOAuditParser(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        parsed = urlparse(base_url)
        self.base_url = base_url
        self.base_host = parsed.hostname or ""
        self.in_body = False
        self.in_title = False
        self.current_heading_level: Optional[str] = None
        self.current_heading_parts: List[str] = []
        self.title_parts: List[str] = []
        self.visible_text_parts: List[str] = []
        self.meta_tags: DefaultDict[str, List[str]] = defaultdict(list)
        self.headings: Dict[str, List[str]] = {"h1": [], "h2": [], "h3": []}
        self.canonical: str = ""
        self.html_lang: str = ""
        self.hreflang_tags: List[Dict[str, str]] = []
        self.geo_tags: Dict[str, str] = {}
        self.conversational_headings_count = 0
        self.statistics_count = 0
        self.definitions_count = 0
        self.json_ld_count = 0
        self.in_json_ld = False
        self.json_ld_parts: List[str] = []
        self.json_ld_blocks: List[str] = []
        self.images_total = 0
        self.images_missing_alt = 0
        self.links_total = 0
        self.internal_links = 0
        self.external_links = 0
        self.nofollow_links = 0
        self.internal_link_samples: List[str] = []
        self.external_link_samples: List[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        tag = tag.lower()
        attrs_dict = {key.lower(): value for key, value in attrs}

        if tag == "html":
            self.html_lang = attrs_dict.get("lang", "") or ""
        elif tag == "body":
            self.in_body = True
        elif tag == "title":
            self.in_title = True
        elif tag in {"script", "style"}:
            self._ignored_depth += 1
            if tag == "script" and (attrs_dict.get("type", "").lower() == "application/ld+json"):
                self.json_ld_count += 1
                self.in_json_ld = True
                self.json_ld_parts = []
        elif tag in {"h1", "h2", "h3"}:
            self.current_heading_level = tag
            self.current_heading_parts = []
        elif tag == "meta":
            key = (
                attrs_dict.get("name")
                or attrs_dict.get("property")
                or attrs_dict.get("http-equiv")
                or attrs_dict.get("itemprop")
                or ""
            ).strip().lower()
            content = (attrs_dict.get("content") or "").strip()
            if key and content:
                self.meta_tags[key].append(content)
                if key in {"geo.position", "geo.region", "geo.placename", "icbm"}:
                    self.geo_tags[key] = content
        elif tag == "link":
            rel_value = (attrs_dict.get("rel") or "").lower().split()
            href = (attrs_dict.get("href") or "").strip()
            if "canonical" in rel_value and href:
                self.canonical = urljoin(self.base_url, href)
            if "alternate" in rel_value and attrs_dict.get("hreflang") and href:
                self.hreflang_tags.append({
                    "hreflang": attrs_dict.get("hreflang") or "",
                    "href": urljoin(self.base_url, href)
                })
        elif tag == "img":
            self.images_total += 1
            alt_text = attrs_dict.get("alt")
            if alt_text is None or not alt_text.strip():
                self.images_missing_alt += 1
        elif tag == "a":
            self.links_total += 1
            href = (attrs_dict.get("href") or "").strip()
            rel_value = (attrs_dict.get("rel") or "").lower().split()

            if href:
                absolute_href = urljoin(self.base_url, href)
                parsed_href = urlparse(absolute_href)
                if parsed_href.scheme in {"http", "https"}:
                    if _is_internal_link(parsed_href.hostname or "", self.base_host):
                        self.internal_links += 1
                        if len(self.internal_link_samples) < MAX_INTERNAL_LINK_SAMPLES:
                            self.internal_link_samples.append(absolute_href)
                    else:
                        self.external_links += 1
                        if len(self.external_link_samples) < MAX_INTERNAL_LINK_SAMPLES:
                            self.external_link_samples.append(absolute_href)

            if any(token in {"nofollow", "ugc", "sponsored"} for token in rel_value):
                self.nofollow_links += 1

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()

        if tag == "body":
            self.in_body = False
        elif tag == "title":
            self.in_title = False
        elif tag in {"script", "style"}:
            if self.in_json_ld:
                self.json_ld_blocks.append("".join(self.json_ld_parts))
                self.in_json_ld = False
            if self._ignored_depth > 0:
                self._ignored_depth -= 1
        elif self.current_heading_level == tag:
            heading_text = _clean_text("".join(self.current_heading_parts))
            if heading_text:
                self.headings[tag].append(heading_text[:200])
                q_words = {"cómo", "qué", "por qué", "cuándo", "dónde", "quién", "cual", "cuál", "how", "what", "why", "where", "who", "when", "which", "?"}
                heading_lower = heading_text.lower()
                if any(qw in heading_lower for qw in q_words) or heading_lower.strip().endswith("?"):
                    self.conversational_headings_count += 1
            self.current_heading_level = None
            self.current_heading_parts = []

    def handle_data(self, data: str) -> None:
        if self.in_json_ld:
            self.json_ld_parts.append(data)
            return

        if self._ignored_depth > 0:
            return

        if self.in_title:
            self.title_parts.append(data)

        if self.current_heading_level:
            self.current_heading_parts.append(data)

        if self.in_body:
            self.visible_text_parts.append(data)
            # Count percentages and statistics
            pct_matches = re.findall(r'\b\d+(?:\.\d+)?\s*(?:%|percent|por\s*ciento)\b', data, re.IGNORECASE)
            self.statistics_count += len(pct_matches)
            # Count explicit definitions
            def_matches = re.findall(r'\b(?:is\s+a|es\s+un|es\s+una|se\s+define\s+como|refers\s+to|refiere\s+a)\b', data, re.IGNORECASE)
            self.definitions_count += len(def_matches)


def _fetch_page(url_or_domain: str, timeout: int) -> Tuple[Optional[requests.Response], Optional[str], Optional[str], Optional[int], List[Dict[str, Any]]]:
    last_error: Optional[str] = None
    for candidate_url in _normalize_candidates(url_or_domain):
        started_at = time.perf_counter()
        try:
            response = requests.get(
                candidate_url,
                headers=DEFAULT_HEADERS,
                timeout=timeout,
                allow_redirects=True,
            )
            elapsed_ms = int((time.perf_counter() - started_at) * 1000)
            redirect_chain = [
                {"url": r.url, "status_code": r.status_code}
                for r in response.history
            ]
            return response, candidate_url, None, elapsed_ms, redirect_chain
        except requests.RequestException as exc:
            last_error = str(exc)

    return None, None, last_error, None, []


def _build_score(result: Dict[str, Any]) -> Tuple[int, List[Dict[str, str]], List[str]]:
    score = 100
    checks: List[Dict[str, str]] = []
    recommendations: List[str] = []

    def add_check(condition: bool, penalty: int, check_name: str, fail_message: str, pass_message: str) -> None:
        nonlocal score
        if condition:
            checks.append({"check": check_name, "status": "pass", "message": pass_message})
            return

        score = max(0, score - penalty)
        checks.append({"check": check_name, "status": "warn", "message": fail_message})
        recommendations.append(fail_message)

    title = result["content"]["title"]
    meta_description = result["content"]["meta_description"]
    canonical = result["technical"]["canonical"]
    h1_count = result["headings"]["h1_count"]
    noindex = result["technical"]["noindex"]
    word_count = result["content"]["word_count"]
    images_missing_alt = result["images"]["missing_alt"]
    html_lang = result["technical"]["html_lang"]

    add_check(bool(title), 20, "title", "Missing page title.", "Page title found.")
    if title:
        add_check(10 <= len(title) <= 70, 5, "title_length", "Title length is outside the usual SEO range (10-70 characters).", "Title length is in a good range.")

    add_check(bool(meta_description), 15, "meta_description", "Missing meta description.", "Meta description found.")
    if meta_description:
        add_check(50 <= len(meta_description) <= 160, 5, "meta_description_length", "Meta description length is outside the usual SEO range (50-160 characters).", "Meta description length is in a good range.")

    add_check(bool(canonical), 5, "canonical", "Missing canonical tag.", "Canonical tag found.")
    add_check(h1_count > 0, 10, "h1", "Missing H1 heading.", "At least one H1 heading found.")
    add_check(not noindex, 30, "indexability", "Page appears to be marked noindex.", "Page does not appear to be marked noindex.")
    add_check(word_count >= 200, 5, "content_depth", "Page has very little visible text for SEO analysis.", "Page has enough visible text for a basic SEO audit.")
    add_check(images_missing_alt == 0, min(10, images_missing_alt * 2), "image_alt", "Some images are missing alt text.", "Images appear to have alt text.")
    add_check(bool(html_lang), 3, "language", "Missing html lang attribute.", "HTML lang attribute found.")

    redirect_count = result["technical"].get("redirect_count", 0)
    add_check(
        redirect_count <= 1,
        3,
        "redirect_chain",
        f"Page has a long redirect chain ({redirect_count} hops).",
        "No excessive redirects.",
    )

    json_ld = result["technical"].get("json_ld", {})
    if json_ld.get("count", 0) > 0:
        add_check(
            json_ld.get("invalid_count", 0) == 0,
            3,
            "json_ld_valid",
            "Some JSON-LD blocks contain invalid syntax.",
            "All JSON-LD blocks are valid.",
        )

    if result["technical"]["og_title"] and result["technical"]["og_description"]:
        checks.append({"check": "social_meta", "status": "pass", "message": "Open Graph title and description found."})
    else:
        score = max(0, score - 3)
        checks.append({"check": "social_meta", "status": "warn", "message": "Open Graph title or description is missing."})
        recommendations.append("Add Open Graph title and description for better social sharing.")

    if result["technical"]["x_robots_tag"]:
        checks.append({"check": "x_robots_tag", "status": "info", "message": f"X-Robots-Tag: {result['technical']['x_robots_tag']}"})

    return score, checks, recommendations


def _validate_json_ld(blocks: List[str]) -> Dict[str, Any]:
    """Validate JSON-LD blocks and extract structured data types."""
    valid_count = 0
    invalid_count = 0
    types_found: List[str] = []
    errors: List[str] = []

    for i, block in enumerate(blocks):
        try:
            data = json.loads(block)
            valid_count += 1
            if isinstance(data, dict):
                t = data.get("@type")
                if isinstance(t, str):
                    types_found.append(t)
                elif isinstance(t, list):
                    types_found.extend(str(item) for item in t)
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        t = item.get("@type")
                        if isinstance(t, str):
                            types_found.append(t)
                        elif isinstance(t, list):
                            types_found.extend(str(v) for v in t)
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            invalid_count += 1
            errors.append(f"Block {i + 1}: {str(exc)}")

    return {
        "count": len(blocks),
        "valid_count": valid_count,
        "invalid_count": invalid_count,
        "types_found": types_found,
        "errors": errors,
    }


def _check_single_link(url: str, link_type: str, timeout: int) -> Optional[Dict[str, Any]]:
    try:
        resp = requests.head(
            url,
            headers=DEFAULT_HEADERS,
            timeout=timeout,
            allow_redirects=True,
        )
        if resp.status_code >= 400:
            return {
                "url": url,
                "status_code": resp.status_code,
                "error": None,
                "type": link_type,
            }
    except requests.RequestException as exc:
        return {
            "url": url,
            "status_code": None,
            "error": str(exc),
            "type": link_type,
        }
    return None


def _check_broken_links(
    internal_samples: List[str],
    external_samples: List[str],
    timeout: int = 3,
    link_cache: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Check a sample of internal and external links for broken URLs."""
    broken: List[Dict[str, Any]] = []
    checked = 0
    unique_links: List[Tuple[str, str]] = []

    for link_type, samples in [("internal", internal_samples), ("external", external_samples)]:
        for url in samples[:MAX_BROKEN_LINK_CHECKS]:
            checked += 1
            if link_cache is not None and url in link_cache:
                cached_res = link_cache[url]
                if cached_res:
                    res_copy = cached_res.copy()
                    res_copy["type"] = link_type
                    broken.append(res_copy)
            else:
                unique_links.append((url, link_type))

    if unique_links:
        _log_progress(f"Checking {len(unique_links)} unique link samples in parallel...")
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {
                executor.submit(_check_single_link, url, link_type, timeout): url
                for url, link_type in unique_links
            }
            for future in as_completed(futures):
                res = future.result()
                url = futures[future]
                if link_cache is not None:
                    link_cache[url] = res
                if res:
                    broken.append(res)

    return {
        "checked": checked,
        "broken": broken,
        "broken_count": len(broken),
    }


def _check_ssl(start_url: str, timeout: int = 10) -> Dict[str, Any]:
    """Check HTTPS/SSL configuration for the given URL."""
    parsed = urlparse(start_url)
    hostname = parsed.hostname or ""
    uses_https = parsed.scheme == "https"
    certificate = None
    http_redirects_to_https = False
    issues: List[str] = []
    ssl_recommendations: List[str] = []

    # Check SSL certificate
    if hostname:
        try:
            context = ssl.create_default_context()
            with socket.create_connection((hostname, 443), timeout=timeout) as sock:
                with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                    cert = ssock.getpeercert()
                    if cert:
                        import datetime

                        issuer_parts = []
                        for rdn in cert.get("issuer", ()):
                            for attr_type, attr_value in rdn:
                                if attr_type in ("organizationName", "commonName"):
                                    issuer_parts.append(attr_value)
                        issuer = ", ".join(issuer_parts) if issuer_parts else "Unknown"

                        expires_str = cert.get("notAfter", "")
                        try:
                            expires_dt = datetime.datetime.strptime(
                                expires_str, "%b %d %H:%M:%S %Y %Z"
                            )
                            days_remaining = (
                                expires_dt - datetime.datetime.utcnow()
                            ).days
                        except (ValueError, TypeError):
                            days_remaining = -1

                        certificate = {
                            "valid": True,
                            "issuer": issuer,
                            "expires": expires_str,
                            "days_remaining": days_remaining,
                        }

                        if days_remaining < 30:
                            issues.append(
                                f"SSL certificate expires soon ({days_remaining} days remaining)."
                            )
                            ssl_recommendations.append(
                                "Renew the SSL certificate before it expires."
                            )
        except Exception as exc:
            certificate = {"valid": False, "issuer": "", "expires": "", "days_remaining": -1}
            issues.append(f"SSL certificate error: {str(exc)}")
            ssl_recommendations.append(
                "Install a valid SSL certificate (consider free options like Let's Encrypt)."
            )

    # Check HTTP -> HTTPS redirect
    if uses_https and hostname:
        try:
            http_url = f"http://{hostname}/"
            resp = requests.get(
                http_url,
                headers=DEFAULT_HEADERS,
                timeout=timeout,
                allow_redirects=True,
            )
            http_redirects_to_https = resp.url.startswith("https://")
            if not http_redirects_to_https:
                issues.append("HTTP does not redirect to HTTPS.")
                ssl_recommendations.append(
                    "Configure server to redirect all HTTP traffic to HTTPS."
                )
        except Exception:
            pass
    elif not uses_https:
        issues.append("Site is not using HTTPS.")
        ssl_recommendations.append(
            "Migrate the site to HTTPS for better security and SEO."
        )

    return {
        "uses_https": uses_https,
        "http_redirects_to_https": http_redirects_to_https,
        "certificate": certificate,
        "issues": issues,
        "recommendations": ssl_recommendations,
    }


def _detect_duplicates(pages: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Detect duplicate titles and meta descriptions across crawled pages."""
    title_map: DefaultDict[str, List[str]] = defaultdict(list)
    desc_map: DefaultDict[str, List[str]] = defaultdict(list)

    for page in pages:
        url = page.get("url", "") or page.get("final_url", "")
        title = page.get("content", {}).get("title", "")
        desc = page.get("content", {}).get("meta_description", "")
        if title:
            title_map[title].append(url)
        if desc:
            desc_map[desc].append(url)

    duplicate_titles = [
        {"title": title, "urls": urls, "count": len(urls)}
        for title, urls in title_map.items()
        if len(urls) > 1
    ]
    duplicate_descriptions = [
        {"description": desc, "urls": urls, "count": len(urls)}
        for desc, urls in desc_map.items()
        if len(urls) > 1
    ]

    return {
        "duplicate_titles": duplicate_titles,
        "duplicate_descriptions": duplicate_descriptions,
        "has_duplicates": bool(duplicate_titles or duplicate_descriptions),
    }


def _audit_site_assets(start_url: str, timeout: int = 20) -> Dict[str, Any]:
    """
    Fetch and audit robots.txt and sitemap.xml for the starting website.
    Checks robots.txt first to locate custom sitemap URLs.
    """
    parsed = urlparse(start_url)
    if not parsed.scheme or not parsed.netloc:
        return {}
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    
    robots_url = f"{base_url}/robots.txt"
    robots_exists = False
    robots_status = None
    sitemaps_found = []
    robots_issues = []
    robots_recs = []
    
    # 1. Fetch and audit robots.txt
    try:
        response = requests.get(
            robots_url,
            headers=DEFAULT_HEADERS,
            timeout=timeout,
            allow_redirects=True,
        )
        robots_status = response.status_code
        
        # Initialize default AI agent permissions
        ai_agents = {
            "gptbot": "Allowed",
            "google-extended": "Allowed",
            "anthropic-ai": "Allowed",
            "perplexitybot": "Allowed",
            "applebot-extended": "Allowed",
            "cohere-ai": "Allowed",
            "bytespider": "Allowed",
        }
        
        if response.status_code == 200:
            robots_exists = True
            # Parse lines for Sitemap directives and AI crawler controls
            lines = response.text.splitlines()
            current_agents = []
            wildcard_blocked = False
            last_was_directive = False

            for line in lines:
                line_striped = line.strip()
                if not line_striped or line_striped.startswith("#"):
                    continue
                if "#" in line_striped:
                    line_striped = line_striped.split("#", 1)[0].strip()
                
                parts = line_striped.split(":", 1)
                if len(parts) != 2:
                    continue
                key = parts[0].strip().lower()
                val = parts[1].strip()
                
                if key == "sitemap":
                    if val:
                        sitemaps_found.append(val)
                elif key == "user-agent":
                    if last_was_directive:
                        current_agents = []
                        last_was_directive = False
                    current_agents.append(val.lower())
                elif key in ("allow", "disallow"):
                    last_was_directive = True
                    is_disallow = (key == "disallow")
                    for agent in current_agents:
                        if agent == "*":
                            if is_disallow and val == "/":
                                wildcard_blocked = True
                        else:
                            for bot in ai_agents:
                                if bot in agent:
                                    if is_disallow and val == "/":
                                        ai_agents[bot] = "Blocked"
                                    elif not is_disallow and val == "/":
                                        ai_agents[bot] = "Allowed"

            if wildcard_blocked:
                for bot in ai_agents:
                    if ai_agents[bot] == "Allowed":
                        ai_agents[bot] = "Blocked"
            
            if not sitemaps_found:
                robots_issues.append("No Sitemap directive found in robots.txt.")
                robots_recs.append("Add a Sitemap directive (e.g., 'Sitemap: https://domain.com/sitemap.xml') to robots.txt to help search engines discover your sitemap.")
            
            if "user-agent" not in response.text.lower():
                robots_issues.append("robots.txt does not contain any 'User-agent' directives.")
                robots_recs.append("Add standard directives like 'User-agent: *' and 'Disallow: /' rules if there are private areas.")
        else:
            robots_issues.append(f"robots.txt is missing or inaccessible (HTTP {response.status_code}).")
            robots_recs.append("Create a robots.txt file at the root of your domain to guide search engine web crawlers.")
    except Exception as exc:
        robots_issues.append(f"Failed to fetch robots.txt: {str(exc)}")
        robots_recs.append("Ensure your server is configured to allow requests to /robots.txt.")

    # 2. Determine sitemap URL
    # If one or more sitemaps found in robots.txt, check the first one
    if sitemaps_found:
        sitemap_url = sitemaps_found[0]
        via_robots = True
    else:
        sitemap_url = f"{base_url}/sitemap.xml"
        via_robots = False

    sitemap_exists = False
    sitemap_status = None
    url_count = 0
    is_xml = False
    sitemap_issues = []
    sitemap_recs = []

    # 3. Fetch and audit sitemap.xml
    try:
        response = requests.get(
            sitemap_url,
            headers=DEFAULT_HEADERS,
            timeout=timeout,
            allow_redirects=True,
        )
        sitemap_status = response.status_code
        if response.status_code == 200:
            sitemap_exists = True
            content_type = response.headers.get("content-type", "").lower()
            body_preview = response.text[:1000]
            
            # Basic validation of XML sitemap format
            is_xml = "xml" in content_type or "<urlset" in body_preview or "<sitemapindex" in body_preview
            
            if not is_xml:
                sitemap_issues.append("Sitemap file does not appear to be valid XML format.")
                sitemap_recs.append("Ensure your sitemap is outputting valid XML with proper content-type headers.")
            else:
                # Count URLs using loc tag matching
                locs = re.findall(r"<loc>(.*?)</loc>", response.text, flags=re.IGNORECASE)
                url_count = len(locs)
                
                if url_count == 0:
                    sitemap_issues.append("Sitemap is empty (contains no URLs).")
                    sitemap_recs.append("Populate your sitemap with all active, indexable URLs on your website.")
        else:
            sitemap_issues.append(f"Sitemap file is missing or inaccessible (HTTP {response.status_code}).")
            sitemap_recs.append("Create a sitemap.xml file and submit it to search consoles (Google, Bing) to speed up indexing.")
    except Exception as exc:
        sitemap_issues.append(f"Failed to fetch sitemap: {str(exc)}")
        sitemap_recs.append("Verify sitemap availability and check server/network settings.")

    ssl_result = _check_ssl(start_url, timeout)

    return {
        "robots_txt": {
            "url": robots_url,
            "exists": robots_exists,
            "status_code": robots_status,
            "sitemaps_found": sitemaps_found,
            "issues": robots_issues,
            "recommendations": robots_recs,
            "ai_agents": ai_agents,
        },
        "sitemap": {
            "url": sitemap_url,
            "via_robots": via_robots,
            "exists": sitemap_exists,
            "status_code": sitemap_status,
            "url_count": url_count,
            "is_xml": is_xml,
            "issues": sitemap_issues,
            "recommendations": sitemap_recs,
        },
        "ssl": ssl_result,
    }


def crawl_website(url_or_domain: str, max_pages: int = MAX_CRAWL_PAGES, timeout: int = 20) -> Dict[str, Any]:
    """Crawl and audit several internal pages from a public website."""
    _log_progress(f"Initializing crawler for: {url_or_domain}")
    effective_max_pages = max(1, min(max_pages, MAX_CRAWL_PAGES_HARD_LIMIT))
    
    # Initialize global link checking cache for this crawl session
    link_cache = {}

    _log_progress(f"Crawling page 1/{effective_max_pages}: {url_or_domain}")
    start_result = audit_website(url_or_domain, timeout, link_cache=link_cache)
    if "error" in start_result:
        _log_progress(f"Failed to crawl start page: {start_result['error']}")
        return start_result

    pages: List[Dict[str, Any]] = [start_result]
    start_url = start_result.get("final_url") or start_result.get("url") or url_or_domain
    
    _log_progress("Auditing Robots.txt and Sitemap.xml files...")
    site_checks = _audit_site_assets(start_url, timeout)
    
    normalized_start_url = _normalize_crawl_candidate(start_url)
    visited = {normalized_start_url or start_url}
    queue = deque()

    for internal_link in start_result.get("links", {}).get("internal_samples", []):
        normalized_link = _normalize_crawl_candidate(internal_link)
        if normalized_link and _looks_like_html_candidate(normalized_link):
            queue.append((normalized_link, 1))

    while queue and len(pages) < effective_max_pages:
        next_url, depth = queue.popleft()
        if next_url in visited:
            continue

        visited.add(next_url)
        _log_progress(f"Crawling page {len(pages) + 1}/{effective_max_pages}: {next_url}")
        page_result = audit_website(next_url, timeout, link_cache=link_cache)
        pages.append(page_result)

        if "error" in page_result or depth >= MAX_CRAWL_DEPTH:
            continue

        for internal_link in page_result.get("links", {}).get("internal_samples", []):
            normalized_link = _normalize_crawl_candidate(internal_link)
            if not normalized_link or normalized_link in visited:
                continue
            if not _looks_like_html_candidate(normalized_link):
                continue
            queue.append((normalized_link, depth + 1))

    _log_progress("Compiling aggregate crawl metrics...")
    successful_pages = [page for page in pages if "error" not in page]
    scores = [page.get("score", 0) for page in successful_pages if isinstance(page.get("score"), int)]
    issue_counter: Counter[str] = Counter()
    for page in successful_pages:
        issue_counter.update(page.get("issues", []))

    aggregate = {
        "page_count": len(pages),
        "successful_pages": len(successful_pages),
        "failed_pages": len(pages) - len(successful_pages),
        "average_score": round(sum(scores) / len(scores), 1) if scores else None,
        "best_score": max(scores) if scores else None,
        "worst_score": min(scores) if scores else None,
        "indexable_pages": sum(1 for page in successful_pages if not page.get("technical", {}).get("noindex", False)),
        "pages_with_missing_alt": sum(1 for page in successful_pages if page.get("images", {}).get("missing_alt", 0) > 0),
        "common_issues": [
            {"issue": issue, "count": count}
            for issue, count in issue_counter.most_common(10)
        ],
    }

    _log_progress("Scanning for cross-page duplicate title and description elements...")
    duplicate_content = _detect_duplicates(pages)

    _log_progress("Assembling final technical SEO report...")
    return {
        "input": url_or_domain,
        "start_url": start_url,
        "max_pages": effective_max_pages,
        "pages": [_summarize_page(page) for page in pages],
        "aggregate": aggregate,
        "site_checks": site_checks,
        "duplicate_content": duplicate_content,
    }


def audit_website(
    url_or_domain: str,
    timeout: int = 20,
    link_cache: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Run a public on-page SEO audit for a URL or domain.
    """
    response, requested_url, fetch_error, elapsed_ms, redirect_chain = _fetch_page(url_or_domain, timeout)
    if response is None:
        return {
            "input": url_or_domain,
            "error": fetch_error or "Failed to fetch the page.",
        }

    final_url = response.url
    parser = _SEOAuditParser(final_url)
    try:
        parser.feed(response.text)
        parser.close()
    except Exception:
        pass

    title = _clean_text("".join(parser.title_parts))
    visible_text = _clean_text(" ".join(parser.visible_text_parts))
    meta_description = _first_meta(parser.meta_tags, "description")
    robots_values = parser.meta_tags.get("robots", []) + parser.meta_tags.get("googlebot", [])
    x_robots_tag = response.headers.get("x-robots-tag", "")
    combined_robots = " ".join(robots_values + [x_robots_tag]).lower()
    noindex = "noindex" in combined_robots
    nofollow = "nofollow" in combined_robots or parser.nofollow_links > 0

    json_ld_result = _validate_json_ld(parser.json_ld_blocks)

    result: Dict[str, Any] = {
        "input": url_or_domain,
        "url": requested_url or url_or_domain,
        "final_url": final_url,
        "status_code": response.status_code,
        "response_time_ms": elapsed_ms,
        "score": 0,
        "summary": "",
        "technical": {
            "content_type": response.headers.get("content-type", ""),
            "canonical": parser.canonical,
            "html_lang": parser.html_lang,
            "x_robots_tag": x_robots_tag,
            "noindex": noindex,
            "nofollow": nofollow,
            "json_ld_count": parser.json_ld_count,
            "json_ld": json_ld_result,
            "redirect_chain": redirect_chain,
            "redirect_count": len(redirect_chain),
            "og_title": _first_meta(parser.meta_tags, "og:title"),
            "og_description": _first_meta(parser.meta_tags, "og:description"),
            "og_image": _first_meta(parser.meta_tags, "og:image"),
            "twitter_card": _first_meta(parser.meta_tags, "twitter:card"),
        },
        "content": {
            "title": title,
            "title_length": len(title),
            "meta_description": meta_description,
            "meta_description_length": len(meta_description),
            "word_count": len(re.findall(r"\b[\w'-]+\b", visible_text, flags=re.UNICODE)),
            "text_length": len(visible_text),
            "text_preview": visible_text[:300],
        },
        "headings": {
            "h1_count": len(parser.headings["h1"]),
            "h2_count": len(parser.headings["h2"]),
            "h3_count": len(parser.headings["h3"]),
            "h1": parser.headings["h1"][:10],
            "h2": parser.headings["h2"][:10],
            "h3": parser.headings["h3"][:10],
        },
        "images": {
            "total": parser.images_total,
            "missing_alt": parser.images_missing_alt,
        },
        "links": {
            "total": parser.links_total,
            "internal": parser.internal_links,
            "external": parser.external_links,
            "nofollow": parser.nofollow_links,
            "internal_samples": _unique_preserve_order(parser.internal_link_samples),
            "external_samples": _unique_preserve_order(parser.external_link_samples),
        },
    }

    result["geo_optimization"] = {
        "html_lang": parser.html_lang,
        "hreflang_tags": parser.hreflang_tags,
        "geo_tags": parser.geo_tags,
        "conversational_headings_count": parser.conversational_headings_count,
        "statistics_count": parser.statistics_count,
        "definitions_count": parser.definitions_count,
    }

    score, checks, recommendations = _build_score(result)

    # Geo targeting checks
    if not parser.html_lang:
        score = max(0, score - 2)
        checks.append({"check": "geo_html_lang", "status": "warn", "message": "HTML lang attribute is missing."})
        recommendations.append("Add the 'lang' attribute to the <html> tag to specify the page's language.")
    else:
        checks.append({"check": "geo_html_lang", "status": "pass", "message": f"HTML lang attribute declared: {parser.html_lang}"})

    # Broken links check (done after scoring, modifies score directly)
    broken_links_result = _check_broken_links(
        result["links"]["internal_samples"],
        result["links"]["external_samples"],
        link_cache=link_cache,
    )
    result["broken_links"] = broken_links_result

    internal_broken = [b for b in broken_links_result["broken"] if b["type"] == "internal"]
    external_broken = [b for b in broken_links_result["broken"] if b["type"] == "external"]
    if internal_broken:
        score = max(0, score - 5)
        checks.append({"check": "broken_links_internal", "status": "warn", "message": f"Found {len(internal_broken)} broken internal link(s)."})
        recommendations.append(f"Fix {len(internal_broken)} broken internal link(s).")
    else:
        checks.append({"check": "broken_links_internal", "status": "pass", "message": "No broken internal links found."})
    if external_broken:
        score = max(0, score - 3)
        checks.append({"check": "broken_links_external", "status": "warn", "message": f"Found {len(external_broken)} broken external link(s)."})
        recommendations.append(f"Fix {len(external_broken)} broken external link(s).")
    else:
        checks.append({"check": "broken_links_external", "status": "pass", "message": "No broken external links found."})

    result["score"] = score
    result["checks"] = checks
    result["recommendations"] = recommendations[:10]
    result["issues"] = [r for r in recommendations]
    result["summary"] = (
        f"SEO audit for {urlparse(final_url).hostname or final_url}: "
        f"score {score}/100, {len(recommendations)} recommendation(s)."
    )
    return result

"""
Generate readable SEO reports from crawl results.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from seo_mcp.seo_audit import crawl_website


DEFAULT_MAX_PAGES = 5
DEFAULT_TIMEOUT = 20
DEFAULT_REPORT_DIR = "reports"
MAX_ITEMS = 8


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return slug or "seo-report"


def _score_color(score: Optional[int]) -> str:
    if score is None:
        return "#64748b"
    if score >= 85:
        return "#10b981"
    if score >= 70:
        return "#f59e0b"
    return "#ef4444"


def _score_label(score: Optional[int]) -> str:
    if score is None:
        return "No score"
    if score >= 85:
        return "Strong"
    if score >= 70:
        return "Needs attention"
    return "High risk"


def _format_score(score: Optional[int]) -> str:
    return "N/A" if score is None else str(score)


def _unique_preserve_order(values: Iterable[str]) -> List[str]:
    seen_values = set()
    ordered_values: List[str] = []
    for value in values:
        if value in seen_values:
            continue
        seen_values.add(value)
        ordered_values.append(value)
    return ordered_values


def _normalize_pages(crawl_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    pages = crawl_result.get("pages", []) or []
    return [page for page in pages if isinstance(page, dict)]


def _aggregate_counters(pages: List[Dict[str, Any]]) -> Dict[str, Any]:
    issue_counter: Counter[str] = Counter()
    recommendation_counter: Counter[str] = Counter()

    for page in pages:
        issue_counter.update(page.get("issues", []) or [])
        recommendation_counter.update(page.get("recommendations", []) or [])

    return {
        "common_issues": issue_counter.most_common(MAX_ITEMS),
      "recommendations": [recommendation for recommendation, _ in recommendation_counter.most_common(MAX_ITEMS)],
    }


def _build_report_context(crawl_result: Dict[str, Any]) -> Dict[str, Any]:
    pages = _normalize_pages(crawl_result)
    aggregate = crawl_result.get("aggregate", {}) or {}
    scored_pages = [page for page in pages if isinstance(page.get("score"), int)]
    sorted_pages = sorted(scored_pages, key=lambda page: page.get("score", 0))

    average_score = aggregate.get("average_score")
    if average_score is None and scored_pages:
        average_score = round(sum(page.get("score", 0) for page in scored_pages) / len(scored_pages), 1)

    site_label = crawl_result.get("start_url") or crawl_result.get("input") or "SEO Report"
    site_label = re.sub(r"^https?://", "", str(site_label), flags=re.IGNORECASE)
    site_label = site_label.rstrip("/") or "SEO Report"

    aggregate_counts = _aggregate_counters(pages)

    return {
        "title": site_label,
        "start_url": crawl_result.get("start_url") or crawl_result.get("input") or "",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "pages": pages,
        "sorted_pages": sorted_pages,
        "aggregate": {
            "page_count": aggregate.get("page_count", len(pages)),
            "successful_pages": aggregate.get("successful_pages", len(pages)),
            "failed_pages": aggregate.get("failed_pages", 0),
            "average_score": average_score,
            "best_score": aggregate.get("best_score"),
            "worst_score": aggregate.get("worst_score"),
            "indexable_pages": aggregate.get("indexable_pages", 0),
            "pages_with_missing_alt": aggregate.get("pages_with_missing_alt", 0),
            "common_issues": aggregate.get("common_issues", []),
        },
        "common_issues": aggregate_counts["common_issues"],
        "recommendations": aggregate_counts["recommendations"],
        "max_pages": crawl_result.get("max_pages", DEFAULT_MAX_PAGES),
        "site_checks": crawl_result.get("site_checks"),
        "duplicate_content": crawl_result.get("duplicate_content"),
    }


def _render_issue_pills(issues: List[str]) -> str:
    if not issues:
        return '<span class="chip chip--neutral">No major issues</span>'
    return "".join(f'<span class="chip chip--warn">{escape(issue)}</span>' for issue in issues[:3])


def _render_recommendation_list(items: List[str]) -> str:
    if not items:
        return '<li class="muted">No recommendations generated.</li>'
    return "".join(f"<li>{escape(item)}</li>" for item in items[:MAX_ITEMS])


def render_markdown_report(crawl_result: Dict[str, Any]) -> str:
    data = _build_report_context(crawl_result)
    aggregate = data["aggregate"]

    lines: List[str] = [f"# SEO Report: {data['title']}", "", f"Generated at: {data['generated_at']}", ""]

    if crawl_result.get("error"):
        lines += ["## Error", "", str(crawl_result["error"]), ""]
        return "\n".join(lines).strip() + "\n"

    lines += [
        "## Summary",
        f"- Start URL: {data['start_url']}",
        f"- Pages crawled: {aggregate['page_count']}",
        f"- Successful pages: {aggregate['successful_pages']}",
        f"- Failed pages: {aggregate['failed_pages']}",
        f"- Average score: {aggregate['average_score']}",
        f"- Best score: {aggregate['best_score']}",
        f"- Worst score: {aggregate['worst_score']}",
        f"- Indexable pages: {aggregate['indexable_pages']}",
        f"- Pages with missing alt text: {aggregate['pages_with_missing_alt']}",
        "",
    ]

    site_checks = data.get("site_checks")
    if site_checks:
        lines += [
            "## Robots.txt & Sitemap.xml Review",
            "",
            "### Robots.txt Status",
        ]
        robots = site_checks.get("robots_txt", {})
        if robots.get("exists"):
            lines.append(f"- **Status**: Found (HTTP {robots.get('status_code')})")
            lines.append(f"- **URL**: {robots.get('url')}")
            sitemaps = robots.get("sitemaps_found", [])
            if sitemaps:
                lines.append("- **Sitemaps Declared in robots.txt**:")
                for sm in sitemaps:
                    lines.append(f"  - {sm}")
            else:
                lines.append("- **Sitemaps Declared**: None found in robots.txt")
        else:
            lines.append(f"- **Status**: Missing or inaccessible (HTTP {robots.get('status_code') or 'Error'})")
            lines.append(f"- **URL**: {robots.get('url')}")
            
        if robots.get("issues"):
            lines.append("- **Issues Found**:")
            for issue in robots["issues"]:
                lines.append(f"  - ⚠️ {issue}")
        
        lines += [
            "",
            "### Sitemap.xml Status",
        ]
        sitemap = site_checks.get("sitemap", {})
        if sitemap.get("exists"):
            lines.append(f"- **Status**: Found (HTTP {sitemap.get('status_code')})")
            lines.append(f"- **URL**: {sitemap.get('url')}")
            lines.append(f"- **Format**: {'XML Sitemap' if sitemap.get('is_xml') else 'Unknown Format'}")
            lines.append(f"- **Discovered URL Count**: {sitemap.get('url_count')}")
            if sitemap.get("via_robots"):
                lines.append("- **Discovery Method**: Located via Robots.txt Sitemap directive")
            else:
                lines.append("- **Discovery Method**: Fallback to default location")
        else:
            lines.append(f"- **Status**: Missing or inaccessible (HTTP {sitemap.get('status_code') or 'Error'})")
            lines.append(f"- **URL**: {sitemap.get('url')}")
            
        if sitemap.get("issues"):
            lines.append("- **Issues Found**:")
            for issue in sitemap["issues"]:
                lines.append(f"  - ⚠️ {issue}")

        lines.append("")

        # SSL Status (inside the site_checks block)
        ssl_data = site_checks.get("ssl")
        if ssl_data:
            lines += ["", "### HTTPS/SSL Status"]
            lines.append(f"- **Uses HTTPS**: {'Yes' if ssl_data.get('uses_https') else 'No'}")
            lines.append(f"- **HTTP Redirects to HTTPS**: {'Yes' if ssl_data.get('http_redirects_to_https') else 'No'}")
            cert = ssl_data.get("certificate")
            if cert:
                lines.append(f"- **Certificate Valid**: {'Yes' if cert.get('valid') else 'No'}")
                lines.append(f"- **Issuer**: {cert.get('issuer', 'Unknown')}")
                lines.append(f"- **Expires**: {cert.get('expires', 'Unknown')}")
                lines.append(f"- **Days Remaining**: {cert.get('days_remaining', 'N/A')}")
            if ssl_data.get("issues"):
                lines.append("- **Issues**:")
                for issue in ssl_data["issues"]:
                    lines.append(f"  - ⚠️ {issue}")
            lines.append("")

    # Broken Links section
    broken_pages = [p for p in data["pages"] if p.get("broken_links_count", 0) > 0]
    if broken_pages:
        lines += ["## Broken Links Detected", ""]
        for page in broken_pages:
            lines.append(f"- **{page.get('final_url') or page.get('url')}**: {page.get('broken_links_count')} broken link(s)")
        lines.append("")

    # Duplicate Content section
    dupes = data.get("duplicate_content")
    if dupes and dupes.get("has_duplicates"):
        lines += ["## Duplicate Content", ""]
        for dt in dupes.get("duplicate_titles", []):
            lines.append(f"- **Duplicate Title** ({dt['count']}x): \"{dt['title']}\"")
            for url in dt["urls"]:
                lines.append(f"  - {url}")
        for dd in dupes.get("duplicate_descriptions", []):
            desc_preview = dd["description"][:80] + "..." if len(dd["description"]) > 80 else dd["description"]
            lines.append(f"- **Duplicate Description** ({dd['count']}x): \"{desc_preview}\"")
            for url in dd["urls"]:
                lines.append(f"  - {url}")
        lines.append("")

    lines += [
        "## Worst Pages",
    ]

    if data["sorted_pages"]:
        for page in data["sorted_pages"][:MAX_ITEMS]:
            lines.append(
                f"- [{_format_score(page.get('score'))}] {page.get('final_url') or page.get('url')} - {page.get('title') or 'Untitled'}"
            )
    else:
        lines.append("- No page data available.")

    lines += ["", "## Common Issues"]
    if data["common_issues"]:
        for issue, count in data["common_issues"]:
            lines.append(f"- {issue} ({count})")
    else:
        lines.append("- No recurring issues found.")

    lines += ["", "## Page Details", "| Score | URL | Title | Indexable | Issues |", "| --- | --- | --- | --- | --- |"]
    for page in data["pages"]:
        issues = ", ".join(page.get("issues", [])) or "-"
        lines.append(
            f"| {_format_score(page.get('score'))} | {page.get('final_url') or page.get('url') or ''} | {page.get('title') or 'Untitled'} | {'Yes' if page.get('indexable', True) else 'No'} | {issues} |"
        )

    lines += ["", "## Recommendations"]
    if data["recommendations"]:
        for recommendation in data["recommendations"]:
            lines.append(f"- {recommendation}")
    else:
        lines.append("- No recommendations generated.")

    return "\n".join(lines).strip() + "\n"


def render_html_report(crawl_result: Dict[str, Any]) -> str:
    data = _build_report_context(crawl_result)
    aggregate = data["aggregate"]
    average_score = aggregate.get("average_score")
    average_score_value = average_score if isinstance(average_score, (int, float)) else None
    score_color = _score_color(average_score_value)
    score_label = _score_label(average_score_value)

    summary_cards = [
        ("Pages", aggregate["page_count"]),
        ("Successful", aggregate["successful_pages"]),
        ("Failed", aggregate["failed_pages"]),
        ("Indexable", aggregate["indexable_pages"]),
        ("Missing Alt", aggregate["pages_with_missing_alt"]),
        ("Worst Score", aggregate["worst_score"]),
    ]

    score_rows_html = "".join(
        f"""
        <div class="score-row">
          <div class="score-row__meta">
            <span>{escape(page.get('title') or 'Untitled')}</span>
            <strong>{_format_score(page.get('score'))}</strong>
          </div>
          <div class="score-bar"><span style="width:{max(0, min(int(page.get('score') or 0), 100))}%; background:{_score_color(page.get('score'))};"></span></div>
          <div class="score-row__url">{escape(page.get('final_url') or page.get('url') or '')}</div>
        </div>
        """
        for page in data["pages"]
    ) or '<div class="empty-state">No page data available.</div>'

    common_issue_html = "".join(
        f"<li><span>{escape(issue)}</span><strong>{count}</strong></li>" for issue, count in data["common_issues"]
    ) or '<li class="muted">No recurring issues found.</li>'

    worst_page_html = "".join(
        f"<li><strong>{_format_score(page.get('score'))}</strong> {escape(page.get('final_url') or page.get('url') or '')}<br><span>{escape(page.get('title') or 'Untitled')}</span></li>"
        for page in data["sorted_pages"][:MAX_ITEMS]
    ) or '<li class="muted">No page data available.</li>'

    recommendation_html = _render_recommendation_list(data["recommendations"])

    page_rows_html = "".join(
        f"""
        <tr>
          <td><span class="score-pill" style="background:{_score_color(page.get('score'))}22;color:{_score_color(page.get('score'))};border-color:{_score_color(page.get('score'))}55">{_format_score(page.get('score'))}</span></td>
          <td><a href="{escape(page.get('final_url') or page.get('url') or '')}" target="_blank" rel="noreferrer">{escape(page.get('final_url') or page.get('url') or '')}</a></td>
          <td>{escape(page.get('title') or 'Untitled')}</td>
          <td>{'Yes' if page.get('indexable', True) else 'No'}</td>
          <td>{page.get('redirect_count', 0)}</td>
          <td>{escape(', '.join(page.get('issues', [])) or '-')}</td>
          <td>{escape(', '.join(page.get('recommendations', [])) or '-')}</td>
        </tr>
        """
        for page in data["pages"]
    ) or '<tr><td colspan="7" class="muted">No page data available.</td></tr>'

    site_checks = data.get("site_checks")
    site_assets_html = ""
    if site_checks:
        robots = site_checks.get("robots_txt", {})
        sitemap = site_checks.get("sitemap", {})
        
        # Robots txt card
        if robots.get("exists"):
            robots_status_class = "pass"
            robots_badge_class = "pass"
            robots_status_text = "Active"
        elif robots.get("status_code") == 404:
            robots_status_class = "warn"
            robots_badge_class = "warn"
            robots_status_text = "Not Found"
        else:
            robots_status_class = "fail"
            robots_badge_class = "fail"
            robots_status_text = "Error"
            
        sitemaps_declared = ", ".join(robots.get("sitemaps_found", [])) or "None declared"
        robots_issues_li = "".join(f"<li>⚠️ {escape(issue)}</li>" for issue in robots.get("issues", []))
        if not robots_issues_li:
            robots_issues_li = "<li class='muted'>✅ No issues found</li>"
            
        # Sitemap card
        if sitemap.get("exists"):
            if sitemap.get("is_xml") and sitemap.get("url_count", 0) > 0:
                sitemap_status_class = "pass"
                sitemap_badge_class = "pass"
                sitemap_status_text = "Valid"
            else:
                sitemap_status_class = "warn"
                sitemap_badge_class = "warn"
                sitemap_status_text = "Has Warnings"
        elif sitemap.get("status_code") == 404:
            sitemap_status_class = "fail"
            sitemap_badge_class = "fail"
            sitemap_status_text = "Missing"
        else:
            sitemap_status_class = "fail"
            sitemap_badge_class = "fail"
            sitemap_status_text = "Error"
            
        discovery_method = "Via Robots.txt" if sitemap.get("via_robots") else "Default Path"
        sitemap_issues_li = "".join(f"<li>⚠️ {escape(issue)}</li>" for issue in sitemap.get("issues", []))
        if not sitemap_issues_li:
            sitemap_issues_li = "<li class='muted'>✅ No issues found</li>"

        # SSL card
        ssl_data = site_checks.get("ssl", {})
        ssl_card_html = ""
        if ssl_data:
            if ssl_data.get("uses_https") and ssl_data.get("certificate", {}).get("valid"):
                ssl_status_class = "pass"
                ssl_status_text = "Secure"
            elif ssl_data.get("uses_https"):
                ssl_status_class = "warn"
                ssl_status_text = "Warning"
            else:
                ssl_status_class = "fail"
                ssl_status_text = "Insecure"
            
            cert = ssl_data.get("certificate")
            cert_details = ""
            if cert:
                cert_details = f"""
                <div class="asset-detail-item">
                  <span>Certificate</span>
                  <span class="asset-detail-value">{'Valid' if cert.get('valid') else 'Invalid'}</span>
                </div>
                <div class="asset-detail-item">
                  <span>Issuer</span>
                  <span class="asset-detail-value">{escape(str(cert.get('issuer', 'Unknown')))}</span>
                </div>
                <div class="asset-detail-item">
                  <span>Days Remaining</span>
                  <span class="asset-detail-value">{escape(str(cert.get('days_remaining', 'N/A')))}</span>
                </div>
                """
            
            ssl_issues_li = "".join(f"<li>⚠️ {escape(issue)}</li>" for issue in ssl_data.get("issues", []))
            if not ssl_issues_li:
                ssl_issues_li = "<li class='muted'>✅ No issues found</li>"
            
            ssl_card_html = f"""
            <div class="asset-card asset-card--{ssl_status_class}">
              <div class="asset-header">
                <span class="asset-title">HTTPS / SSL</span>
                <span class="asset-status-badge asset-status-badge--{ssl_status_class}">{ssl_status_text}</span>
              </div>
              <div class="asset-details">
                <div class="asset-detail-item">
                  <span>HTTPS</span>
                  <span class="asset-detail-value">{'Yes' if ssl_data.get('uses_https') else 'No'}</span>
                </div>
                <div class="asset-detail-item">
                  <span>HTTP → HTTPS</span>
                  <span class="asset-detail-value">{'Yes' if ssl_data.get('http_redirects_to_https') else 'No'}</span>
                </div>
                {cert_details}
              </div>
              <div class="asset-issues-title">Technical Audits</div>
              <ul class="asset-issues-list">
                {ssl_issues_li}
              </ul>
            </div>
            """
            
        site_assets_html = f"""
        <section class="panel" style="margin-top: 22px;">
          <h2>Robots.txt &amp; Sitemap.xml Review</h2>
          <div class="site-assets-grid">
            
            <div class="asset-card asset-card--{robots_status_class}">
              <div class="asset-header">
                <span class="asset-title">robots.txt</span>
                <span class="asset-status-badge asset-status-badge--{robots_badge_class}">{robots_status_text}</span>
              </div>
              <div class="asset-details">
                <div class="asset-detail-item">
                  <span>URL</span>
                  <span class="asset-detail-value"><a href="{escape(robots.get('url', ''))}" target="_blank" rel="noreferrer">{escape(robots.get('url', ''))}</a></span>
                </div>
                <div class="asset-detail-item">
                  <span>HTTP Status</span>
                  <span class="asset-detail-value">{escape(str(robots.get('status_code') or 'N/A'))}</span>
                </div>
                <div class="asset-detail-item">
                  <span>Sitemaps Declared</span>
                  <span class="asset-detail-value">{escape(sitemaps_declared)}</span>
                </div>
              </div>
              <div class="asset-issues-title">Technical Audits</div>
              <ul class="asset-issues-list">
                {robots_issues_li}
              </ul>
            </div>

            <div class="asset-card asset-card--{sitemap_status_class}">
              <div class="asset-header">
                <span class="asset-title">sitemap.xml</span>
                <span class="asset-status-badge asset-status-badge--{sitemap_badge_class}">{sitemap_status_text}</span>
              </div>
              <div class="asset-details">
                <div class="asset-detail-item">
                  <span>URL</span>
                  <span class="asset-detail-value"><a href="{escape(sitemap.get('url', ''))}" target="_blank" rel="noreferrer">{escape(sitemap.get('url', ''))}</a></span>
                </div>
                <div class="asset-detail-item">
                  <span>HTTP Status</span>
                  <span class="asset-detail-value">{escape(str(sitemap.get('status_code') or 'N/A'))}</span>
                </div>
                <div class="asset-detail-item">
                  <span>Discovery Method</span>
                  <span class="asset-detail-value">{escape(discovery_method)}</span>
                </div>
                <div class="asset-detail-item">
                  <span>Format</span>
                  <span class="asset-detail-value">{"XML Sitemap" if sitemap.get("is_xml") else "Invalid Format"}</span>
                </div>
                <div class="asset-detail-item">
                  <span>Discovered URLs</span>
                  <span class="asset-detail-value">{escape(str(sitemap.get("url_count", 0)))} URLs</span>
                </div>
              </div>
              <div class="asset-issues-title">Technical Audits</div>
              <ul class="asset-issues-list">
                {sitemap_issues_li}
              </ul>
            </div>

            {ssl_card_html}

          </div>
        </section>
        """

    if crawl_result.get("error"):
        body_sections = f"""
        <section class="section section--error">
          <h2>Crawl Error</h2>
          <p>{escape(str(crawl_result['error']))}</p>
        </section>
        """
    else:
        # Broken links summary
        broken_items = []
        for page in data["pages"]:
            blc = page.get("broken_links_count", 0)
            if blc > 0:
                page_url = escape(page.get('final_url') or page.get('url') or '')
                broken_items.append(f"<li><strong>{blc}</strong> broken link(s) on <a href=\"{page_url}\" target=\"_blank\" rel=\"noreferrer\">{page_url}</a></li>")
        broken_links_html = "".join(broken_items) if broken_items else '<li class="muted">No broken links detected.</li>'

        # JSON-LD summary from pages
        json_ld_items = []
        for page in data["pages"]:
            page_url = page.get('final_url') or page.get('url') or ''
            rc = page.get("redirect_count", 0)
            # We don't have json_ld per-page in summary, so show redirect info instead
        # For JSON-LD, we can show a general message
        json_ld_html = '<li class="muted">JSON-LD validation details available in per-page audit data.</li>'

        # Duplicate content
        dupes = data.get("duplicate_content")
        duplicate_content_html = ""
        if dupes and dupes.get("has_duplicates"):
            dup_items = []
            for dt in dupes.get("duplicate_titles", []):
                urls_str = ", ".join(f'<a href="{escape(u)}" target="_blank" rel="noreferrer">{escape(u)}</a>' for u in dt["urls"][:3])
                dup_items.append(f'<li><strong>Duplicate Title ({dt["count"]}x):</strong> "{escape(dt["title"][:60])}"<br><span class="muted">{urls_str}</span></li>')
            for dd in dupes.get("duplicate_descriptions", []):
                urls_str = ", ".join(f'<a href="{escape(u)}" target="_blank" rel="noreferrer">{escape(u)}</a>' for u in dd["urls"][:3])
                desc_preview = dd["description"][:60] + "..." if len(dd["description"]) > 60 else dd["description"]
                dup_items.append(f'<li><strong>Duplicate Description ({dd["count"]}x):</strong> "{escape(desc_preview)}"<br><span class="muted">{urls_str}</span></li>')
            dup_list = "".join(dup_items)
            duplicate_content_html = f"""
        <section class="panel" style="margin-top: 22px;">
          <h2>Duplicate Content</h2>
          <ul class="list">{dup_list}</ul>
        </section>
        """

        body_sections = f"""
        {site_assets_html}

        <section class="section-grid">
          <section class="panel">
            <h2>Score Distribution</h2>
            <div class="score-stack">{score_rows_html}</div>
          </section>
          <section class="panel">
            <h2>Common Issues</h2>
            <ul class="list">{common_issue_html}</ul>
          </section>
        </section>

        <section class="section-grid">
          <section class="panel">
            <h2>Worst Pages</h2>
            <ul class="list">{worst_page_html}</ul>
          </section>
          <section class="panel">
            <h2>Recommended Next Actions</h2>
            <ul class="list">{recommendation_html}</ul>
          </section>
        </section>

        <section class="section-grid">
          <section class="panel">
            <h2>Broken Links</h2>
            <ul class="list">{broken_links_html}</ul>
          </section>
          <section class="panel">
            <h2>Structured Data (JSON-LD)</h2>
            <ul class="list">{json_ld_html}</ul>
          </section>
        </section>

        {duplicate_content_html}

        <section class="panel">
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Score</th>
                  <th>URL</th>
                  <th>Title</th>
                  <th>Indexable</th>
                  <th>Redirects</th>
                  <th>Issues</th>
                  <th>Recommendations</th>
                </tr>
              </thead>
              <tbody>
                {page_rows_html}
              </tbody>
            </table>
          </div>
        </section>
        """

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SEO Report - {escape(data['title'])}</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #07111f;
      --panel: rgba(15, 23, 42, 0.86);
      --panel-border: rgba(148, 163, 184, 0.18);
      --text: #e2e8f0;
      --muted: #94a3b8;
      --accent: #38bdf8;
      --shadow: 0 24px 80px rgba(0, 0, 0, 0.35);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif;
      background:
        radial-gradient(circle at top left, rgba(56, 189, 248, 0.18), transparent 30%),
        radial-gradient(circle at top right, rgba(16, 185, 129, 0.12), transparent 28%),
        linear-gradient(180deg, #050b16 0%, var(--bg) 100%);
      color: var(--text);
      min-height: 100vh;
    }}
    a {{ color: inherit; text-decoration: none; }}
    .container {{ max-width: 1280px; margin: 0 auto; padding: 32px 20px 56px; }}
    .hero {{
      background: linear-gradient(135deg, rgba(15, 23, 42, 0.95), rgba(9, 15, 28, 0.95));
      border: 1px solid var(--panel-border);
      border-radius: 28px;
      box-shadow: var(--shadow);
      padding: 28px;
    }}
    .eyebrow {{ text-transform: uppercase; letter-spacing: 0.18em; color: var(--accent); font-size: 12px; font-weight: 700; }}
    h1 {{ margin: 10px 0 10px; font-size: clamp(30px, 4vw, 48px); line-height: 1.05; }}
    .subtitle {{ color: var(--muted); max-width: 78ch; line-height: 1.6; }}
    .hero-grid {{ display: grid; grid-template-columns: minmax(0, 1.35fr) minmax(260px, 0.65fr); gap: 20px; margin-top: 24px; }}
    .hero-panel, .panel, .section {{
      background: var(--panel);
      border: 1px solid var(--panel-border);
      border-radius: 22px;
      box-shadow: 0 18px 50px rgba(0, 0, 0, 0.25);
    }}
    .hero-panel {{ padding: 20px; }}
    .score-badge {{
      display: flex; flex-direction: column; justify-content: center; align-items: center;
      min-height: 230px; padding: 24px; border-radius: 22px;
      background: linear-gradient(180deg, rgba(56, 189, 248, 0.14), rgba(15, 23, 42, 0.3));
      border: 1px solid rgba(56, 189, 248, 0.18);
    }}
    .score-badge__value {{ font-size: clamp(46px, 8vw, 76px); font-weight: 800; line-height: 1; color: {score_color}; }}
    .score-badge__label {{ margin-top: 8px; font-size: 14px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.14em; }}
    .score-badge__meta {{ margin-top: 12px; color: var(--text); font-weight: 600; }}
    .meta-line {{ margin-top: 8px; color: var(--muted); font-size: 14px; text-align: center; word-break: break-word; }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 14px; margin-top: 20px; }}
    .card {{ padding: 16px; background: rgba(148, 163, 184, 0.04); border: 1px solid rgba(148, 163, 184, 0.12); border-radius: 18px; }}
    .card__label {{ color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.12em; margin-bottom: 10px; }}
    .card__value {{ font-size: 26px; font-weight: 800; }}
    .section {{ margin-top: 22px; padding: 20px; }}
    .section-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; margin-top: 22px; }}
    .section h2, .panel h2 {{ margin: 0 0 14px; font-size: 20px; }}
    .score-stack {{ display: grid; gap: 12px; }}
    .score-row {{ display: grid; gap: 8px; padding: 12px 0; border-bottom: 1px solid rgba(148, 163, 184, 0.12); }}
    .score-row:last-child {{ border-bottom: 0; padding-bottom: 0; }}
    .score-row__meta {{ display: flex; justify-content: space-between; gap: 12px; color: var(--text); font-size: 14px; }}
    .score-row__url {{ color: var(--muted); font-size: 13px; word-break: break-all; }}
    .score-bar {{ height: 12px; border-radius: 999px; background: rgba(148, 163, 184, 0.14); overflow: hidden; }}
    .score-bar span {{ display: block; height: 100%; border-radius: inherit; }}
    .list {{ margin: 0; padding-left: 18px; color: var(--text); }}
    .list li {{ margin: 8px 0; }}
    .muted {{ color: var(--muted); }}
    .chip-row {{ display: flex; flex-wrap: wrap; gap: 10px; }}
    .chip {{ padding: 8px 12px; border-radius: 999px; font-size: 13px; font-weight: 700; }}
    .chip--warn {{ background: rgba(245, 158, 11, 0.12); color: #f59e0b; }}
    .chip--neutral {{ background: rgba(56, 189, 248, 0.12); color: #38bdf8; }}
    .table-wrap {{ overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 14px; min-width: 900px; }}
    thead th {{ text-align: left; color: var(--muted); font-weight: 700; font-size: 12px; text-transform: uppercase; letter-spacing: 0.12em; padding: 14px 10px; border-bottom: 1px solid rgba(148, 163, 184, 0.18); }}
    tbody td {{ padding: 14px 10px; border-bottom: 1px solid rgba(148, 163, 184, 0.12); vertical-align: top; }}
    tbody tr:hover {{ background: rgba(148, 163, 184, 0.04); }}
    .score-pill {{ display: inline-flex; align-items: center; justify-content: center; min-width: 52px; padding: 6px 10px; border-radius: 999px; border: 1px solid transparent; font-weight: 700; }}
    .footer {{ margin-top: 26px; color: var(--muted); font-size: 13px; text-align: center; }}
    .empty-state {{ color: var(--muted); padding: 16px 0; }}
    .site-assets-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin-top: 14px; }}
    .asset-card {{ padding: 20px; background: rgba(148, 163, 184, 0.04); border: 1px solid rgba(148, 163, 184, 0.12); border-radius: 18px; position: relative; overflow: hidden; }}
    .asset-card::before {{ content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px; }}
    .asset-card--pass::before {{ background: linear-gradient(90deg, #10b981, transparent); }}
    .asset-card--warn::before {{ background: linear-gradient(90deg, #f59e0b, transparent); }}
    .asset-card--fail::before {{ background: linear-gradient(90deg, #ef4444, transparent); }}
    .asset-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; }}
    .asset-title {{ font-size: 16px; font-weight: 700; color: var(--text); }}
    .asset-status-badge {{ padding: 4px 10px; border-radius: 999px; font-size: 12px; font-weight: 700; text-transform: uppercase; }}
    .asset-status-badge--pass {{ background: rgba(16, 185, 129, 0.15); color: #10b981; }}
    .asset-status-badge--warn {{ background: rgba(245, 158, 11, 0.15); color: #f59e0b; }}
    .asset-status-badge--fail {{ background: rgba(239, 68, 68, 0.15); color: #ef4444; }}
    .asset-details {{ display: flex; flex-direction: column; gap: 8px; font-size: 13px; color: var(--muted); }}
    .asset-detail-item {{ display: flex; justify-content: space-between; border-bottom: 1px solid rgba(148, 163, 184, 0.08); padding-bottom: 6px; }}
    .asset-detail-item:last-child {{ border-bottom: none; padding-bottom: 0; }}
    .asset-detail-value {{ font-weight: 600; color: var(--text); word-break: break-all; text-align: right; max-width: 60%; }}
    .asset-issues-title {{ margin-top: 15px; font-size: 13px; font-weight: 700; color: var(--text); }}
    .asset-issues-list {{ list-style: none; padding: 0; margin: 8px 0 0; font-size: 12px; }}
    .asset-issues-list li {{ display: flex; gap: 6px; margin-bottom: 6px; line-height: 1.4; }}
    .asset-issues-list li:last-child {{ margin-bottom: 0; }}
    @media (max-width: 900px) {{
      .hero-grid, .section-grid {{ grid-template-columns: 1fr; }}
      .container {{ padding: 20px 14px 44px; }}
      .hero, .section, .panel {{ padding: 18px; border-radius: 20px; }}
      table {{ display: block; overflow-x: auto; white-space: nowrap; }}
    }}
  </style>
</head>
<body>
  <div class="container">
    <section class="hero">
      <div class="eyebrow">SEO Report</div>
      <h1>{escape(data['title'])}</h1>
      <p class="subtitle">A shareable summary of the crawl, with page-level scores, recurring issues, and prioritized next steps. Generated automatically from the public SEO audit workflow.</p>
      <div class="hero-grid">
        <div class="hero-panel">
          <div class="cards">
            {''.join(f'<div class="card"><div class="card__label">{escape(str(label))}</div><div class="card__value">{escape(_format_score(value) if value is not None else "N/A")}</div></div>' for label, value in summary_cards)}
          </div>
          <div class="chip-row" style="margin-top: 16px;">
            <span class="chip chip--neutral">Scope: {escape(str(data['max_pages']))} max pages</span>
            <span class="chip chip--neutral">Average score: {escape(_format_score(average_score))}</span>
            <span class="chip chip--neutral">Best score: {escape(_format_score(aggregate.get('best_score')))}</span>
            <span class="chip chip--neutral">Label: {escape(score_label)}</span>
          </div>
          <div class="meta-line">Start URL: <a href="{escape(data['start_url'])}" target="_blank" rel="noreferrer">{escape(data['start_url'])}</a></div>
          <div class="meta-line">Generated at {escape(data['generated_at'])}</div>
        </div>
        <div class="score-badge">
          <div class="score-badge__value">{escape(_format_score(average_score))}</div>
          <div class="score-badge__label">Average Score</div>
          <div class="score-badge__meta">{escape(score_label)}</div>
          <div class="meta-line" style="margin-top: 18px;">Use the tables below to find the worst URLs quickly.</div>
        </div>
      </div>
    </section>

    {body_sections}

    <div class="footer">SEO MCP report generated from crawl data. Keep this file with the project or share it with stakeholders.</div>
  </div>
</body>
</html>
"""
    return html


def render_report(crawl_result: Dict[str, Any], format: str = "html") -> str:
  normalized_format = format.lower().strip()
  if normalized_format == "html":
    return render_html_report(crawl_result)
  if normalized_format in {"md", "markdown"}:
    return render_markdown_report(crawl_result)
  if normalized_format == "json":
    return json.dumps(crawl_result, ensure_ascii=False, indent=2)
  raise ValueError(f"Unsupported report format: {format}")


def _default_output_path(target: str, output_format: str) -> Path:
  slug = _slugify(re.sub(r"^https?://", "", target.strip(), flags=re.IGNORECASE))
  extension = {"html": ".html", "md": ".md", "markdown": ".md", "json": ".json"}[output_format.lower()]
  return Path.cwd() / DEFAULT_REPORT_DIR / f"seo-report-{slug}{extension}"


def export_report(
  target: str,
  output: Optional[str] = None,
  output_format: str = "html",
  max_pages: int = DEFAULT_MAX_PAGES,
  timeout: int = DEFAULT_TIMEOUT,
) -> Path:
  crawl_result = crawl_website(target, max_pages=max_pages, timeout=timeout)
  report_text = render_report(crawl_result, format=output_format)

  output_path = Path(output) if output else _default_output_path(target, output_format)
  if not output_path.suffix:
    extension = {"html": ".html", "md": ".md", "markdown": ".md", "json": ".json"}[output_format.lower()]
    output_path = output_path.with_suffix(extension)

  output_path.parent.mkdir(parents=True, exist_ok=True)
  output_path.write_text(report_text, encoding="utf-8")
  return output_path


def build_report(
  target: str,
  output_format: str = "html",
  max_pages: int = DEFAULT_MAX_PAGES,
  timeout: int = DEFAULT_TIMEOUT,
) -> str:
  crawl_result = crawl_website(target, max_pages=max_pages, timeout=timeout)
  return render_report(crawl_result, format=output_format)


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Generate an SEO report from a public website crawl.")
    parser.add_argument("target", help="Website URL or domain to audit")
    parser.add_argument(
        "--format",
        choices=["html", "md", "markdown", "json"],
        default="html",
        help="Report format to generate",
    )
    parser.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES, help="Maximum number of internal pages to crawl")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="Request timeout in seconds")
    parser.add_argument("--output", help="Output file path. Defaults to a generated file in the current directory.")
    args = parser.parse_args(argv)

    normalized_format = "md" if args.format == "markdown" else args.format

    if normalized_format == "json" and not args.output:
        print(build_report(args.target, output_format=normalized_format, max_pages=args.max_pages, timeout=args.timeout))
        return

    output_path = export_report(
        args.target,
        output=args.output,
        output_format=normalized_format,
        max_pages=args.max_pages,
        timeout=args.timeout,
    )
    print(f"Report saved to {output_path}")


if __name__ == "__main__":
    main()

---
name: seo-audit
description: 'Audit public websites for SEO issues. Use when analyzing title tags, meta descriptions, H1/H2 structure, canonical URLs, robots/noindex, sitemap signals, image alt text, internal links, crawl results, and page-by-page SEO scores.'
---

# SEO Audit Skill

## When to Use
- Review a public website or a set of internal pages.
- Inspect title, meta description, headings, canonical, robots, indexability, image alt text, and internal linking.
- Compare page-level SEO scores and identify repeated patterns across a crawl.

## Procedure
1. Start with the smallest useful scope. Use `audit_website()` for a single page and `crawl_website()` for site-level context.
2. Read the aggregate first: average score, best/worst score, indexable pages, and common issues.
3. Compare each page for unique title, description length, H1 count, canonical presence, and missing alt text.
4. Flag template-level problems when the same issue appears across multiple URLs.
5. Return a prioritized list of fixes with the affected URLs and the exact problem to change.

## Preferred Checks
- Title should be unique and within a sensible length.
- Meta description should summarize the page and stay within a practical length.
- Prefer one H1 per page.
- Canonical should be present and consistent with the final URL.
- `noindex` should be absent unless the page is intentionally hidden.
- Image alt text should exist on meaningful images.
- Internal pages should be discoverable through crawl paths.

## Output Style
- Lead with the most important issues.
- Separate quick wins from structural fixes.
- Mention the page URL, the symptom, and the recommended fix.
- If useful, call out follow-up checks such as robots.txt, sitemap.xml, duplicate titles, or thin content.
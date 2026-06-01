---
name: report-generator
description: 'Generate readable SEO reports from crawl results as Markdown, HTML, or JSON summaries. Use when turning crawl output into tables, cards, charts, prioritized recommendations, or shareable deliverables.'
---

# Report Generator Skill

## When to Use
- Turn `crawl_website()` output into a human-friendly report.
- Create Markdown, HTML, or printable summaries for stakeholders.
- Show scores, issues, recommendations, and page-level comparisons.

## Procedure
1. Start with an executive summary and the overall site score.
2. Add a page table with URL, title, score, indexability, and key issues.
3. Group recommendations by severity and by affected page.
4. Highlight quick wins separately from structural problems.
5. Keep the report readable on both desktop and mobile.

## Report Sections
- Site summary and crawl scope.
- Score distribution and worst pages.
- Common issues across pages.
- Page-by-page detail.
- Recommended next actions.

## Output Rules
- Every recommendation should point to a concrete page or pattern.
- Avoid vague summaries that do not help the reader act.
- Prefer simple self-contained templates before adding new dependencies.
- Make tables concise and easy to scan.
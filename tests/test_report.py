import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seo_mcp.report import render_html_report, render_markdown_report, render_report


SAMPLE_CRAWL_RESULT = {
    "input": "ucv.edu.pe",
    "start_url": "https://www.ucv.edu.pe/",
    "max_pages": 4,
    "pages": [
        {
            "url": "https://www.ucv.edu.pe/",
            "final_url": "https://www.ucv.edu.pe/",
            "status_code": 200,
            "score": 85,
            "summary": "SEO audit for www.ucv.edu.pe: score 85/100, 2 recommendation(s).",
            "title": "UCV | Universidad César Vallejo",
            "meta_description": "Tú sí puedes salir adelante...",
            "h1_count": 1,
            "h2_count": 2,
            "images_missing_alt": 116,
            "internal_links": 243,
            "external_links": 14,
            "indexable": True,
            "issues": ["Some images are missing alt text."],
            "recommendations": ["Add descriptive alt text to images."],
        },
        {
            "url": "https://www.ucv.edu.pe/programas/pregrados",
            "final_url": "https://www.ucv.edu.pe/programas/pregrados",
            "status_code": 200,
            "score": 90,
            "summary": "SEO audit for www.ucv.edu.pe: score 90/100, 1 recommendation(s).",
            "title": "Programas Pregrados | Universidad César Vallejo",
            "meta_description": "Explora los pregrados...",
            "h1_count": 1,
            "h2_count": 0,
            "images_missing_alt": 10,
            "internal_links": 241,
            "external_links": 14,
            "indexable": True,
            "issues": ["Some images are missing alt text."],
            "recommendations": ["Add descriptive alt text to images."],
        },
    ],
    "aggregate": {
        "page_count": 4,
        "successful_pages": 4,
        "failed_pages": 0,
        "average_score": 88.8,
        "best_score": 90,
        "worst_score": 85,
        "indexable_pages": 4,
        "pages_with_missing_alt": 4,
        "common_issues": [{"issue": "Some images are missing alt text.", "count": 2}],
    },
    "site_checks": {
        "robots_txt": {
            "url": "https://www.ucv.edu.pe/robots.txt",
            "exists": True,
            "status_code": 200,
            "sitemaps_found": ["https://www.ucv.edu.pe/custom-sitemap.xml"],
            "issues": [],
            "recommendations": [],
        },
        "sitemap": {
            "url": "https://www.ucv.edu.pe/custom-sitemap.xml",
            "via_robots": True,
            "exists": True,
            "status_code": 200,
            "url_count": 482,
            "is_xml": True,
            "issues": [],
            "recommendations": [],
        },
        "ssl": {
            "uses_https": True,
            "http_redirects_to_https": True,
            "certificate": {
                "valid": True,
                "issuer": "Let's Encrypt",
                "expires": "2026-09-01",
                "days_remaining": 92,
            },
            "issues": [],
            "recommendations": [],
        },
    },
    "duplicate_content": {
        "duplicate_titles": [
            {
                "title": "UCV | Universidad César Vallejo",
                "urls": ["https://www.ucv.edu.pe/", "https://www.ucv.edu.pe/home"],
                "count": 2,
            }
        ],
        "duplicate_descriptions": [],
        "has_duplicates": True,
    },
}

# Add new fields to pages for broken links and redirect counts
SAMPLE_CRAWL_RESULT["pages"][0]["broken_links_count"] = 2
SAMPLE_CRAWL_RESULT["pages"][0]["redirect_count"] = 0
SAMPLE_CRAWL_RESULT["pages"][1]["broken_links_count"] = 0
SAMPLE_CRAWL_RESULT["pages"][1]["redirect_count"] = 1


class ReportRenderTests(unittest.TestCase):
    def test_markdown_report_contains_summary_and_pages(self) -> None:
        markdown = render_markdown_report(SAMPLE_CRAWL_RESULT)
        self.assertIn("SEO Report", markdown)
        self.assertIn("Average score: 88.8", markdown)
        self.assertIn("UCV | Universidad César Vallejo", markdown)
        self.assertIn("Common Issues", markdown)
        self.assertIn("Robots.txt & Sitemap.xml Review", markdown)
        self.assertIn("custom-sitemap.xml", markdown)
        self.assertIn("Discovered URL Count**: 482", markdown)
        # SSL check
        self.assertIn("HTTPS/SSL Status", markdown)
        self.assertIn("Uses HTTPS", markdown)
        # Broken links check
        self.assertIn("Broken Links", markdown)
        # Duplicate content check
        self.assertIn("Duplicate Content", markdown)
        self.assertIn("Duplicate Title", markdown)

    def test_html_report_contains_cards_and_table(self) -> None:
        html = render_html_report(SAMPLE_CRAWL_RESULT)
        self.assertIn("<html lang=\"en\">", html)
        self.assertIn("Average Score", html)
        self.assertIn("Score Distribution", html)
        self.assertIn("Programas Pregrados", html)
        self.assertIn("Robots.txt &amp; Sitemap.xml Review", html)
        self.assertIn("custom-sitemap.xml", html)
        self.assertIn("482 URLs", html)
        # SSL check
        self.assertIn("HTTPS / SSL", html)
        self.assertIn("Secure", html)
        # Broken links check
        self.assertIn("Broken Links", html)
        # Duplicate content check
        self.assertIn("Duplicate Content", html)
        # Redirect column in table
        self.assertIn("Redirects", html)

    def test_json_report_passthrough(self) -> None:
        json_report = render_report(SAMPLE_CRAWL_RESULT, format="json")
        self.assertIn('"average_score": 88.8', json_report)
        self.assertIn('"pages"', json_report)


if __name__ == "__main__":
    unittest.main()
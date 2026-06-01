---
name: testing-pytest
description: 'Create or improve Python tests with pytest or unittest. Use when adding regression coverage for SEO crawlers, HTTP-mocked functions, output-shape checks, edge cases, or bug fixes in src/seo_mcp.'
---

# Testing Skill

## When to Use
- Add regression coverage for crawler or parser behavior.
- Test output shape, scoring, and issue detection.
- Mock HTTP calls so tests do not depend on live websites.
- Verify bug fixes before expanding the scope of a change.

## Procedure
1. Test public behavior first: inputs, outputs, and error handling.
2. Mock `requests.get` and `requests.post` for SEO-related code.
3. Cover happy path, redirects, missing fields, noindex cases, and network failures.
4. Assert the important keys in returned dictionaries, not the entire object unless that is the point of the test.
5. Keep tests deterministic and fast.

## Test Patterns
- Use sample HTML fixtures for page parsing.
- Build a small synthetic link graph for crawl logic.
- Verify that repeated issues appear in aggregate summaries.
- Test edge cases such as empty titles, missing descriptions, and images without alt text.

## Validation
- Run the narrowest test target that covers the change.
- Re-run the same test after fixing a failure.
- If the project does not yet include pytest, use `unittest` and `unittest.mock` before introducing new tooling.
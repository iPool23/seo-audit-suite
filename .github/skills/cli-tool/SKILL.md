---
name: cli-tool
description: 'Build or improve Python CLI tools and command-line entrypoints. Use when adding argparse-style commands, JSON output, report export, exit codes, or python -m interfaces for the SEO MCP project.'
---

# CLI Tool Skill

## When to Use
- Add a command-line entrypoint for SEO audits or report export.
- Improve `python -m` usage for the project.
- Expose flags like `--url`, `--max-pages`, `--timeout`, `--output`, and `--format`.
- Make a tool easier to automate from scripts or CI.

## Procedure
1. Keep the CLI thin. Put logic in the library code and parsing in the entrypoint.
2. Support a clear help message and sensible defaults.
3. Emit JSON by default when the result is intended for automation.
4. Use explicit exit codes for success and failure.
5. Validate the command manually with a real example after changes.

## CLI Rules
- Do not duplicate crawling or scoring logic in the CLI layer.
- Make file output optional and predictable.
- Prefer structured output that can be piped to other tools.
- Keep error messages actionable and short.

## Useful Flags
- `--url` or positional URL/domain input.
- `--max-pages` to control crawl size.
- `--timeout` to control network requests.
- `--output` to save a report.
- `--format` for `json`, `md`, or `html` when supported.
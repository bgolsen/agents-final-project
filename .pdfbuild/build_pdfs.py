"""One-off build script: renders README.md / ARCHITECTURE.md / SCRIPT.md to
styled, print-friendly PDFs via markdown->HTML->headless-Chrome-print.
Mermaid diagrams in ARCHITECTURE.md are pre-rendered to SVG via mermaid-cli
and inlined. Not part of the application -- a docs tool, run once.
"""
from __future__ import annotations

import re
import subprocess
import sys
import uuid
from pathlib import Path

import markdown
from pygments.formatters import HtmlFormatter

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / ".pdfbuild"
CHROME = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
PUPPETEER_CFG = BUILD / "puppeteer-config.json"

DOCS = ["README.md", "ARCHITECTURE.md", "SCRIPT.md"]

CSS = """
@page { size: Letter; margin: 20mm 18mm; }
:root { color-scheme: light; }
* { box-sizing: border-box; }
body {
  font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
  color: #1a1a1a;
  font-size: 10.7pt;
  line-height: 1.55;
  max-width: 100%;
}
.titlepage {
  padding-top: 18vh;
  page-break-after: always;
  text-align: center;
}
.titlepage h1 { font-size: 26pt; margin-bottom: 0.3em; border: none; }
.titlepage .subtitle { font-size: 13pt; color: #555; margin-bottom: 2em; }
.titlepage .meta { font-size: 10pt; color: #888; }
h1, h2, h3, h4 { font-family: "Segoe UI Semibold", "Helvetica Neue", Arial, sans-serif; color: #111; page-break-after: avoid; }
h1 { font-size: 19pt; border-bottom: 2.5px solid #2b5fb0; padding-bottom: 0.2em; margin-top: 1.6em; }
h2 { font-size: 14.5pt; border-bottom: 1px solid #ccc; padding-bottom: 0.15em; margin-top: 1.5em; color: #1c3f7a; }
h3 { font-size: 12pt; margin-top: 1.2em; color: #23447f; }
h4 { font-size: 10.7pt; margin-top: 1em; }
a { color: #1a5fb4; text-decoration: none; }
code, pre, .codehilite { font-family: "Cascadia Code", Consolas, "Courier New", monospace; font-size: 9pt; }
p code, li code, td code { background: #f0f1f4; border: 1px solid #e0e2e8; border-radius: 3px; padding: 0.05em 0.35em; }
pre { background: #f6f7fa; border: 1px solid #e0e2e8; border-radius: 5px; padding: 0.7em 0.9em; overflow-x: auto; page-break-inside: avoid; white-space: pre-wrap; word-wrap: break-word; }
pre code { background: none; border: none; padding: 0; }
blockquote { border-left: 3px solid #2b5fb0; margin: 0.8em 0; padding: 0.2em 1em; color: #444; background: #f7f9fc; }
table { border-collapse: collapse; width: 100%; margin: 1em 0; font-size: 9.5pt; page-break-inside: avoid; }
th, td { border: 1px solid #d5d8de; padding: 0.4em 0.6em; text-align: left; vertical-align: top; }
th { background: #eaf0fb; color: #1c3f7a; }
tr:nth-child(even) td { background: #fafbfc; }
hr { border: none; border-top: 1px solid #ddd; margin: 1.6em 0; }
ul, ol { padding-left: 1.4em; }
li { margin: 0.15em 0; }
.mermaid-diagram { text-align: center; margin: 1.2em 0; page-break-inside: avoid; }
.mermaid-diagram svg { max-width: 100%; height: auto; }
strong { color: #111; }
"""

TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8"><title>{title}</title>
<style>{css}
{pygments_css}
</style></head>
<body>
<div class="titlepage">
  <h1>{title}</h1>
  <div class="subtitle">{subtitle}</div>
  <div class="meta">Multi-Agent Incident Response System &mdash; Track 2 Capstone<br>
  github.com/bgolsen/agents-final-project</div>
</div>
{body}
</body></html>
"""

TITLES = {
    "README.md": ("README", "Setup &amp; run instructions"),
    "ARCHITECTURE.md": ("Architecture", "System design, diagrams, framework justification &amp; technical analysis"),
    "SCRIPT.md": ("Demo Video Script", "Narration script &amp; step-by-step live-demo walkthrough"),
}


def render_mermaid_to_svg(mmd_source: str, out_svg: Path) -> str:
    mmd_path = out_svg.with_suffix(".mmd")
    mmd_path.write_text(mmd_source, encoding="utf-8")
    subprocess.run(
        [
            "npx", "-y", "@mermaid-js/mermaid-cli",
            "-i", str(mmd_path), "-o", str(out_svg),
            "--puppeteerConfigFile", str(PUPPETEER_CFG),
            "--backgroundColor", "white",
        ],
        check=True, cwd=ROOT, shell=True,
        env={"PUPPETEER_SKIP_CHROMIUM_DOWNLOAD": "true", **__import__("os").environ},
        capture_output=True, text=True,
    )
    return out_svg.read_text(encoding="utf-8")


def extract_and_replace_mermaid(md_text: str, doc_stem: str) -> str:
    placeholders: dict[str, str] = {}

    def _repl(match: re.Match) -> str:
        token = f"MERMAIDPLACEHOLDER{uuid.uuid4().hex}"
        svg_path = BUILD / f"{doc_stem}_{len(placeholders)}.svg"
        svg = render_mermaid_to_svg(match.group(1), svg_path)
        placeholders[token] = f'<div class="mermaid-diagram">{svg}</div>'
        return f"\n\n{token}\n\n"

    new_text = re.sub(r"```mermaid\n(.*?)```", _repl, md_text, flags=re.DOTALL)
    return new_text, placeholders


def build_one(name: str) -> None:
    title, subtitle = TITLES[name]
    md_text = (ROOT / name).read_text(encoding="utf-8")

    placeholders: dict[str, str] = {}
    if "```mermaid" in md_text:
        md_text, placeholders = extract_and_replace_mermaid(md_text, Path(name).stem)

    html_body = markdown.markdown(
        md_text,
        extensions=["extra", "codehilite", "sane_lists", "toc"],
        extension_configs={"codehilite": {"guess_lang": False}},
    )
    for token, svg_html in placeholders.items():
        html_body = html_body.replace(f"<p>{token}</p>", svg_html).replace(token, svg_html)

    pygments_css = HtmlFormatter().get_style_defs(".codehilite")
    full_html = TEMPLATE.format(title=title, subtitle=subtitle, css=CSS, pygments_css=pygments_css, body=html_body)

    html_path = BUILD / f"{Path(name).stem}.html"
    html_path.write_text(full_html, encoding="utf-8")

    pdf_path = ROOT / f"{Path(name).stem}.pdf"
    subprocess.run(
        [
            CHROME, "--headless=new", "--disable-gpu", "--no-sandbox",
            f"--print-to-pdf={pdf_path}",
            "--print-to-pdf-no-header",
            "--no-pdf-header-footer",
            html_path.as_uri(),
        ],
        check=True, capture_output=True, text=True,
    )
    print(f"built {pdf_path}")


if __name__ == "__main__":
    BUILD.mkdir(exist_ok=True)
    for doc in DOCS:
        build_one(doc)

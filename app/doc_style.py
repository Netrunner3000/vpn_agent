"""
doc_style.py — Shared stylesheet for the in-app guides.

Both documents render in the same QTextBrowser and should look identical.
Keeping the CSS here means a change to the reading experience happens once
rather than drifting between two copies.

QTextBrowser supports a subset of CSS 2.1 — no flexbox, no custom properties,
no media queries. Everything here stays inside what it actually renders.
"""

DOC_CSS = """
body {
    background-color: #0f0f0f;
    color: #d0d0d0;
    font-family: -apple-system, "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
    line-height: 1.7;
    margin: 0;
    padding: 0 4px;
}
h1 { color: #00e5ff; font-size: 20px; border-bottom: 1px solid #1a2a2a; padding-bottom: 8px; margin-top: 24px; }
h2 { color: #90caf9; font-size: 16px; margin-top: 28px; border-bottom: 1px solid #1a1a1a; padding-bottom: 5px; }
h3 { color: #80cbc4; font-size: 13px; margin-top: 18px; font-weight: bold; }
h4 { color: #aaaaaa; font-size: 12px; margin-top: 14px; font-weight: bold; }
p  { margin: 8px 0; }
a  { color: #4fc3f7; }
code {
    background: #1a1a1a;
    color: #c5e1a5;
    padding: 2px 6px;
    border-radius: 3px;
    font-family: "Menlo", "Monaco", "Courier New", monospace;
    font-size: 11px;
}
pre {
    background: #111111;
    color: #c5e1a5;
    padding: 14px 16px;
    border-radius: 6px;
    border-left: 3px solid #2a3a2a;
    font-family: "Menlo", "Monaco", "Courier New", monospace;
    font-size: 11px;
    margin: 10px 0;
    white-space: pre-wrap;
}
ul, ol { padding-left: 22px; margin: 8px 0; }
li { margin: 4px 0; }
hr { border: none; border-top: 1px solid #1e1e1e; margin: 24px 0; }
table { border-collapse: collapse; width: 100%; margin: 12px 0; }
th { background: #1a1a1a; color: #90caf9; padding: 8px 12px; text-align: left; border: 1px solid #2a2a2a; font-size: 12px; }
td { padding: 7px 12px; border: 1px solid #1e1e1e; color: #cccccc; font-size: 12px; }
.warn  { color: #ff9800; font-weight: bold; }
.danger{ color: #f44336; font-weight: bold; }
.ok    { color: #66bb6a; font-weight: bold; }
.note  { color: #90caf9; }
.tip   { background: #0a1a0a; border-left: 3px solid #2e7d32; padding: 8px 12px; border-radius: 4px; margin: 10px 0; }
.warning-box { background: #1a0e00; border-left: 3px solid #ff6f00; padding: 8px 12px; border-radius: 4px; margin: 10px 0; }
.danger-box  { background: #1a0000; border-left: 3px solid #c62828; padding: 8px 12px; border-radius: 4px; margin: 10px 0; }
.toc { background: #111111; border: 1px solid #1e1e1e; border-radius: 6px; padding: 14px 18px; margin: 14px 0; }
.toc a { color: #80cbc4; text-decoration: none; }
.toc li { margin: 3px 0; font-size: 12px; }
"""


def wrap(body_html: str) -> str:
    """Wrap document body markup in the shared page shell."""
    return (
        "<!DOCTYPE html>\n<html>\n<head>\n<style>"
        + DOC_CSS
        + "</style>\n</head>\n<body>\n"
        + body_html
        + "\n</body>\n</html>"
    )

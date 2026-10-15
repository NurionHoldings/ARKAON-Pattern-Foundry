"""Validate the deployable static homepage without external dependencies."""
from html.parser import HTMLParser
from pathlib import Path

class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = False
        self.title_text = ""
        self.main_count = 0
        self.lang_ko = False
        self.viewport = False
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "html":
            self.lang_ko = attrs.get("lang") == "ko"
        if tag == "title":
            self.title = True
        if tag == "main":
            self.main_count += 1
        if tag == "meta" and attrs.get("name") == "viewport":
            self.viewport = True
    def handle_endtag(self, tag):
        if tag == "title":
            self.title = False
    def handle_data(self, data):
        if self.title:
            self.title_text += data

page = Path(__file__).resolve().parents[1] / "index.html"
if not page.is_file():
    raise SystemExit("FAIL: root index.html missing")
html = page.read_text(encoding="utf-8")
parser = Page()
parser.feed(html)
checks = {
    "Korean language": parser.lang_ko,
    "Page title": bool(parser.title_text.strip()),
    "Mobile viewport": parser.viewport,
    "One main landmark": parser.main_count == 1,
    "Honest preview status": "기능 검증용 미리보기" in html,
    "No external script dependency": "<script" not in html.lower(),
}
for name, passed in checks.items():
    print(("PASS" if passed else "FAIL") + ": " + name)
if not all(checks.values()):
    raise SystemExit(1)

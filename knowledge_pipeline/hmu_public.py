"""Read public HMU HTML as inert data and keep exact, reproducible evidence."""

import hashlib
import re
import unicodedata
from html.parser import HTMLParser
from urllib.parse import urlsplit


class Node:
    def __init__(self, tag="", attrs=()):
        self.tag, self.attrs, self.children = tag, dict(attrs), []

    def walk(self):
        yield self
        for child in self.children:
            if isinstance(child, Node):
                yield from child.walk()

    def text(self):
        if self.tag in {"script", "style"}:
            return ""
        return " ".join(
            " ".join(
                c.text() if isinstance(c, Node) else c for c in self.children
            ).split()
        )

    def has_class(self, name):
        return name in self.attrs.get("class", "").split()


class Parser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.root = Node()
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in {
            "area",
            "base",
            "br",
            "col",
            "embed",
            "hr",
            "img",
            "input",
            "link",
            "meta",
            "param",
            "source",
            "track",
            "wbr",
        }:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(Node(tag, attrs))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                self.stack = self.stack[:i]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def parse_html(text):
    parser = Parser()
    parser.feed(text)
    return parser.root


def normalized_name(text):
    text = unicodedata.normalize("NFC", text).casefold()
    return " ".join(re.findall(r"\w+", text))


def validate_hmu_url(url):
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or not (
            parsed.hostname == "hmu.edu.vn" or parsed.hostname.endswith(".hmu.edu.vn")
        )
        or parsed.username
        or parsed.password
    ):
        raise ValueError("source_is_not_hmu_https")


def course_listings(html):
    rows = []
    for box in parse_html(html).walk():
        if not box.has_class("coursebox"):
            continue
        title_node = next((n for n in box.walk() if n.has_class("coursename")), None)
        summary = next((n.text() for n in box.walk() if n.has_class("summary")), "")
        title = title_node.text() if title_node else ""
        match = re.match(r"^([^\s.]+)\.\s*(.+)$", title)
        if not match:
            continue
        rows.append(
            {
                "lms_course_id": box.attrs["data-courseid"],
                "title": title,
                "course_code": match[1],
                "course_name": match[2],
                "summary": summary,
                "selector": f'[data-courseid="{box.attrs["data-courseid"]}"] .coursename',
            }
        )
    return rows


def program_sections(html):
    dom = parse_html(html)
    box = next(
        (n for n in dom.walk() if n.has_class("generalbox") and n.has_class("info")),
        None,
    )
    if box is None:
        raise ValueError("hmu_program_description_missing")
    blocks = []
    for n in box.walk():
        if n.tag in {"h3", "h4", "h5", "h6", "p", "li", "tr"} and n.text():
            blocks.append({"tag": n.tag, "text": n.text()})
    return blocks


def extract_plos(pages):
    """Keep original page offsets and domain headings, including page continuations."""
    rows, domain, seen = [], "", set()
    for pn, text in enumerate(pages, 1):
        matches = list(re.finditer(r"(?m)^PLO\s*(\d+)\s*[:.]", text))
        for i, match in enumerate(matches):
            code = "PLO" + match[1]
            if code in seen:
                raise ValueError("duplicate_hmu_plo_code")
            seen.add(code)
            headings = list(
                re.finditer(r"(?m)^2\.\d\.\s*[^\n]+", text[: match.start()])
            )
            if headings:
                domain = " ".join(headings[-1][0].split())
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            next_heading = re.search(r"(?m)^2\.\d\.\s*", text[match.end() : end])
            if next_heading:
                end = match.end() + next_heading.start()
            while end > match.start() and text[end - 1].isspace():
                end -= 1
            rows.append(
                {
                    "code": code,
                    "page": pn,
                    "start": match.start(),
                    "end": end,
                    "quote": text[match.start() : end],
                    "domain": domain,
                }
            )
    return rows


def evidence(html_bytes, url, selector, quote, fetched_at, snapshot_path):
    validate_hmu_url(url)
    dom = parse_html(html_bytes.decode("utf-8-sig"))
    if quote not in dom.text():
        raise ValueError("hmu_quote_not_in_snapshot")
    return {
        "source_url": url,
        "source_sha256": hashlib.sha256(html_bytes).hexdigest(),
        "selector": selector,
        "quote": quote,
        "fetched_at_utc": fetched_at,
        "snapshot_path": snapshot_path,
        "publisher": "Trường Đại học Y Hà Nội",
    }

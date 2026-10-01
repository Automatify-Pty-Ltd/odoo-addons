import re

try:
    import markdown
except ImportError:  # pragma: no cover - enforced by the addon manifest
    markdown = None

from lxml import etree, html

from odoo.tools import html_sanitize


_FENCE_RE = re.compile(
    r"^```(?P<language>[A-Za-z0-9_+.-]*)\s*\n(?P<body>.*?)\n```$",
    re.DOTALL,
)
_PRE_RE = re.compile(r"^\s*<pre(?P<attrs>[^>]*)>(?P<body>.*?)</pre>\s*$", re.DOTALL)
_LANGUAGE_ID_RE = re.compile(r'\bdata-language-id=["\']([^"\']+)["\']')
_CODE_CLASS_RE = re.compile(r"(?:^|\s)language-([A-Za-z0-9_+.-]+)(?:\s|$)")
_WHITESPACE_RE = re.compile(r"[ \t\r\f\v]+")
_BLANK_LINES_RE = re.compile(r"\n[ \t]*\n(?:[ \t]*\n)+")
_BACKTICK_RUN_RE = re.compile(r"`+")


def markdown_to_html(source):
    """Convert Markdown into sanitized HTML suitable for Knowledge page content."""
    if markdown is None:
        raise RuntimeError("The Python 'Markdown' package is required.")

    rendered = markdown.markdown(
        source or "",
        extensions=["extra", "sane_lists"],
        output_format="html5",
    )
    root = html.fragment_fromstring(rendered, create_parent="div")
    _normalize_code_blocks(root)

    serialized = _inner_html(root)
    return html_sanitize(
        serialized,
        silent=False,
        sanitize_tags=True,
        sanitize_attributes=True,
        sanitize_style=True,
        sanitize_form=True,
        strip_style=False,
        strip_classes=False,
    )


def html_to_markdown(source):
    """Convert saved Odoo HTML back into portable Markdown."""
    root = html.fragment_fromstring(source or "", create_parent="div")
    result = _render_children(root).strip()
    result = _BLANK_LINES_RE.sub("\n\n", result)
    return f"{result}\n" if result else ""


def _normalize_code_blocks(root):
    for pre in root.xpath(".//pre"):
        code = pre.find("code")
        language = _language_from_element(code) or _language_from_element(pre)
        if language:
            pre.set("data-embedded", "readonlySyntaxHighlighting")
            pre.set("data-language-id", language)

        if code is not None:
            text = code.text_content()
            pre.clear()
            if language:
                pre.set("data-embedded", "readonlySyntaxHighlighting")
                pre.set("data-language-id", language)
            _append_text_with_breaks(pre, text)


def _language_from_element(element):
    if element is None:
        return None
    data_language = element.get("data-language-id")
    if data_language:
        return data_language.strip()
    classes = element.get("class", "")
    match = _CODE_CLASS_RE.search(classes)
    return match.group(1) if match else None


def _append_text_with_breaks(element, text):
    lines = (text or "").split("\n")
    element.text = lines[0] if lines else ""
    previous = None
    for line in lines[1:]:
        br = etree.SubElement(element, "br")
        br.tail = line
        previous = br
    if previous is not None and text.endswith("\n"):
        previous.tail = (previous.tail or "")


def _inner_html(root):
    parts = []
    if root.text:
        parts.append(root.text)
    for child in root:
        parts.append(etree.tostring(child, encoding="unicode", method="html"))
    return "".join(parts)


def _render_children(element, indent=""):
    parts = []
    if element.text and element.text.strip():
        parts.append(_normalize_inline_text(element.text))
    for child in element:
        parts.append(_render_element(child, indent=indent))
        if child.tail and child.tail.strip():
            parts.append(_normalize_inline_text(child.tail))
    return "".join(parts)


def _render_element(element, indent=""):
    tag = element.tag.lower() if isinstance(element.tag, str) else ""

    if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
        level = int(tag[1])
        return f"{'#' * level} {_render_inline_children(element).strip()}\n\n"

    if tag == "p":
        text = _render_inline_children(element).strip()
        return f"{text}\n\n" if text else "\n"

    if tag in {"strong", "b"}:
        return f"**{_render_inline_children(element)}**"

    if tag in {"em", "i"}:
        return f"*{_render_inline_children(element)}*"

    if tag == "code":
        text = element.text_content()
        fence = "`" * (max((len(run) for run in _BACKTICK_RUN_RE.findall(text)), default=0) + 1)
        if len(fence) < 1:
            fence = "`"
        return f"{fence}{text}{fence}"

    if tag == "pre":
        language = element.get("data-language-id") or ""
        text = _pre_text(element)
        text = text.rstrip("\n")
        return f"```{language}\n{text}\n```\n\n"

    if tag == "a":
        label = _render_inline_children(element) or element.get("href", "")
        href = element.get("href", "")
        return f"[{label}]({href})" if href else label

    if tag == "img":
        alt = element.get("alt", "")
        src = element.get("src", "")
        title = element.get("title")
        suffix = f' "{title}"' if title else ""
        return f"![{alt}]({src}{suffix})" if src else ""

    if tag == "br":
        return "\n"

    if tag == "hr":
        return "---\n\n"

    if tag == "blockquote":
        content = _render_children(element).strip()
        return "\n".join(f"> {line}" if line else ">" for line in content.splitlines()) + "\n\n"

    if tag in {"ul", "ol"}:
        ordered = tag == "ol"
        lines = []
        for index, child in enumerate(element, start=1):
            if not isinstance(child.tag, str) or child.tag.lower() != "li":
                continue
            marker = f"{index}." if ordered else "-"
            item = _render_list_item(child).strip()
            item_lines = item.splitlines() or [""]
            lines.append(f"{indent}{marker} {item_lines[0]}")
            continuation = " " * (len(marker) + 1)
            lines.extend(f"{indent}{continuation}{line}" for line in item_lines[1:])
        return "\n".join(lines) + "\n\n"

    if tag == "table":
        return _render_table(element)

    if tag in {"thead", "tbody", "tfoot", "tr", "th", "td", "div", "span"}:
        return _render_children(element, indent=indent)

    return _render_children(element, indent=indent)


def _render_inline_children(element):
    parts = []
    if element.text:
        parts.append(_normalize_inline_text(element.text))
    for child in element:
        parts.append(_render_element(child))
        if child.tail:
            parts.append(_normalize_inline_text(child.tail))
    return "".join(parts)


def _render_list_item(element):
    parts = []
    if element.text:
        parts.append(_normalize_inline_text(element.text))
    for child in element:
        tag = child.tag.lower() if isinstance(child.tag, str) else ""
        if tag in {"ul", "ol"}:
            parts.append("\n" + _render_element(child, indent="  ").strip())
        else:
            parts.append(_render_element(child).strip())
        if child.tail:
            parts.append(_normalize_inline_text(child.tail))
    return "".join(parts)


def _render_table(table):
    rows = []
    for row in table.xpath(".//tr"):
        cells = []
        for cell in row:
            if isinstance(cell.tag, str) and cell.tag.lower() in {"th", "td"}:
                cells.append(_render_inline_children(cell).strip().replace("|", "\\|"))
        if cells:
            rows.append(cells)

    if not rows:
        return ""

    width = max(len(row) for row in rows)
    padded = [row + [""] * (width - len(row)) for row in rows]
    header = padded[0]
    separator = ["---"] * width
    body = padded[1:]

    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(separator) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in body)
    return "\n".join(lines) + "\n\n"


def _pre_text(pre):
    pieces = []
    if pre.text:
        pieces.append(pre.text)
    for child in pre:
        if isinstance(child.tag, str) and child.tag.lower() == "br":
            pieces.append("\n")
        else:
            pieces.append(child.text_content())
        if child.tail:
            pieces.append(child.tail)
    return "".join(pieces)


def _normalize_inline_text(text):
    return _WHITESPACE_RE.sub(" ", text or "")

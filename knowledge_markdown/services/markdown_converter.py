import html as html_stdlib
import re

from lxml import etree, html

from odoo.tools.mail import html_sanitize

try:
    import markdown
except ImportError:  # pragma: no cover - Odoo checks external_dependencies first.
    markdown = None


_BLOCK_TAGS = {
    "address",
    "article",
    "aside",
    "blockquote",
    "div",
    "dl",
    "fieldset",
    "figcaption",
    "figure",
    "footer",
    "form",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "hr",
    "li",
    "main",
    "nav",
    "ol",
    "p",
    "pre",
    "section",
    "table",
    "ul",
}

_CODE_CLASS_RE = re.compile(r"(?:^|\s)language-([A-Za-z0-9_+.-]+)(?:\s|$)")
_WHITESPACE_RE = re.compile(r"[ \t\r\f\v]+")
_BLANK_LINES_RE = re.compile(r"\n[ \t]*\n(?:[ \t]*\n)+")
_BACKTICK_RUN_RE = re.compile(r"`+")


def markdown_to_html(source):
    """Convert Markdown into sanitized HTML suitable for document.page.content."""
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
        sanitize_tags=True,
        sanitize_attributes=True,
        sanitize_style=True,
    )


def html_to_markdown(source):
    """Convert Odoo HTML content to portable Markdown."""
    if not source:
        return ""

    root = html.fragment_fromstring(source, create_parent="div")
    rendered = _render_children(root, block=True)
    rendered = _BLANK_LINES_RE.sub("\n\n", rendered)
    return rendered.strip() + ("\n" if rendered.strip() else "")


def _normalize_code_blocks(root):
    for pre in list(root.iter("pre")):
        code = pre.find("code")
        if code is None:
            continue

        language = _language_from_code_class(code.get("class", "")) or "plaintext"
        source = code.text_content()
        _set_odoo_pre_source(pre, source, language)


def _language_from_code_class(value):
    match = _CODE_CLASS_RE.search(value or "")
    return match.group(1) if match else None


def _set_odoo_pre_source(pre, source, language):
    tail = pre.tail
    pre.clear()
    pre.tail = tail
    pre.set("data-embedded", "readonlySyntaxHighlighting")
    pre.set("data-language-id", language or "plaintext")

    lines = (source or "").split("\n")
    if lines and lines[-1] == "":
        lines.pop()

    pre.text = lines[0] if lines else ""
    for line in lines[1:]:
        br = etree.SubElement(pre, "br")
        br.tail = line


def _inner_html(root):
    parts = []
    if root.text:
        parts.append(html_stdlib.escape(root.text))
    for child in root:
        parts.append(
            etree.tostring(child, encoding="unicode", method="html", with_tail=True)
        )
    return "".join(parts)


def _render_children(node, *, block=False, list_depth=0):
    parts = []
    if node.text:
        parts.append(_escape_text(node.text, block=block))

    for child in node:
        parts.append(_render_node(child, list_depth=list_depth))
        if child.tail:
            parts.append(_escape_text(child.tail, block=block))

    return "".join(parts)


def _render_node(node, *, list_depth=0):
    tag = _tag(node)
    if not tag:
        return ""

    if tag in {"script", "style"}:
        return ""

    if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
        level = int(tag[1])
        text = _render_inline_children(node).strip()
        return f"{'#' * level} {text}\n\n" if text else ""

    if tag == "p":
        text = _render_inline_children(node).strip()
        return f"{text}\n\n" if text else "\n"

    if tag in {"strong", "b"}:
        text = _render_inline_children(node).strip()
        return f"**{text}**" if text else ""

    if tag in {"em", "i"}:
        text = _render_inline_children(node).strip()
        return f"*{text}*" if text else ""

    if tag in {"s", "del", "strike"}:
        text = _render_inline_children(node).strip()
        return f"~~{text}~~" if text else ""

    if tag == "code":
        return _inline_code(node.text_content())

    if tag == "a":
        label = _render_inline_children(node).strip() or _escape_text(node.get("href", ""))
        href = _escape_url(node.get("href", ""))
        suffix = _markdown_title(node.get("title"))
        return f"[{label}]({href}{suffix})" if href else label

    if tag == "img":
        alt = _escape_text(node.get("alt", ""))
        src = _escape_url(node.get("src", ""))
        suffix = _markdown_title(node.get("title"))
        return f"![{alt}]({src}{suffix})" if src else ""

    if tag == "br":
        return "\n"

    if tag == "pre":
        return _render_pre(node)

    if tag == "blockquote":
        body = _render_children(node, block=True, list_depth=list_depth).strip()
        if not body:
            return ""
        quoted = "\n".join(f"> {line}" if line else ">" for line in body.splitlines())
        return f"{quoted}\n\n"

    if tag in {"ul", "ol"}:
        return _render_list(node, list_depth=list_depth)

    if tag == "li":
        return _render_inline_children(node)

    if tag == "table":
        return _render_table(node)

    if tag == "hr":
        return "---\n\n"

    if tag in {"thead", "tbody", "tfoot", "tr", "th", "td"}:
        return _render_children(node, block=True, list_depth=list_depth)

    if tag in _BLOCK_TAGS:
        body = _render_children(node, block=True, list_depth=list_depth).strip()
        return f"{body}\n\n" if body else ""

    return _render_inline_children(node)


def _render_inline_children(node):
    parts = []
    if node.text:
        parts.append(_escape_text(node.text))

    for child in node:
        tag = _tag(child)
        if tag in {"ul", "ol", "table", "blockquote", "pre"}:
            rendered = _render_node(child)
            if rendered:
                parts.append(f"\n\n{rendered.strip()}\n\n")
        else:
            parts.append(_render_node(child))
        if child.tail:
            parts.append(_escape_text(child.tail))

    return "".join(parts)


def _render_pre(pre):
    language = pre.get("data-language-id")
    source = _pre_source(pre)

    if not language:
        code = pre.find("code")
        if code is not None:
            language = _language_from_code_class(code.get("class", ""))
            source = code.text_content()

    info = "" if not language or language == "plaintext" else language
    longest = max((len(run) for run in _BACKTICK_RUN_RE.findall(source)), default=0)
    fence = "`" * max(3, longest + 1)
    source = source.rstrip("\n")
    return f"{fence}{info}\n{source}\n{fence}\n\n"


def _pre_source(pre):
    parts = [pre.text or ""]
    for child in pre:
        if _tag(child) == "br":
            parts.append("\n")
            if child.tail:
                parts.append(child.tail)
        else:
            parts.append(child.text_content())
            if child.tail:
                parts.append(child.tail)
    return "".join(parts)


def _render_list(node, *, list_depth=0):
    ordered = _tag(node) == "ol"
    items = [child for child in node if _tag(child) == "li"]
    if not items:
        return ""

    lines = []
    start = 1
    if ordered:
        try:
            start = int(node.get("start", "1"))
        except ValueError:
            start = 1

    for index, item in enumerate(items):
        marker = f"{start + index}." if ordered else "-"
        inline_parts = []
        nested_lists = []

        if item.text:
            inline_parts.append(_escape_text(item.text))
        for child in item:
            if _tag(child) in {"ul", "ol"}:
                nested_lists.append(child)
            else:
                inline_parts.append(_render_node(child, list_depth=list_depth + 1))
            if child.tail:
                inline_parts.append(_escape_text(child.tail))

        item_text = _normalize_inline_space("".join(inline_parts)).strip()
        prefix = "    " * list_depth
        lines.append(f"{prefix}{marker} {item_text}".rstrip())

        for nested in nested_lists:
            nested_text = _render_list(nested, list_depth=list_depth + 1).rstrip("\n")
            if nested_text:
                lines.append(nested_text)

    return "\n".join(lines) + "\n\n"


def _render_table(table):
    rows = []
    header_flags = []

    for row in table.xpath(".//tr"):
        cells = [cell for cell in row if _tag(cell) in {"th", "td"}]
        if not cells:
            continue
        rows.append([_table_cell(cell) for cell in cells])
        header_flags.append(any(_tag(cell) == "th" for cell in cells))

    if not rows:
        return ""

    width = max(len(row) for row in rows)
    rows = [row + [""] * (width - len(row)) for row in rows]

    header_index = next((i for i, flag in enumerate(header_flags) if flag), 0)
    header = rows[header_index]
    body = rows[:header_index] + rows[header_index + 1 :]

    def row_line(values):
        return "| " + " | ".join(value.replace("|", "\\|") for value in values) + " |"

    lines = [row_line(header), row_line(["---"] * width)]
    lines.extend(row_line(row) for row in body)
    return "\n".join(lines) + "\n\n"


def _table_cell(cell):
    value = _render_inline_children(cell).strip()
    return _normalize_inline_space(value).replace("\n", "<br>")


def _inline_code(value):
    value = (value or "").replace("\n", " ")
    longest = max((len(run) for run in _BACKTICK_RUN_RE.findall(value)), default=0)
    fence = "`" * max(1, longest + 1)
    padding = " " if value.startswith("`") or value.endswith("`") else ""
    return f"{fence}{padding}{value}{padding}{fence}"


def _normalize_inline_space(value):
    return _WHITESPACE_RE.sub(" ", value or "")


def _escape_text(value, *, block=False):
    value = value or ""
    value = value.replace("\\", "\\\\")
    value = re.sub(r"([`*_[\]<>])", r"\\\1", value)
    if block:
        value = re.sub(r"(?m)^([#>+-])(?=\s)", r"\\\1", value)
        value = re.sub(r"(?m)^(\d+)\.(?=\s)", r"\1\\.", value)
    return value


def _escape_url(value):
    return (value or "").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _markdown_title(value):
    if not value:
        return ""
    return ' "' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _tag(node):
    return node.tag.lower() if isinstance(node.tag, str) else ""

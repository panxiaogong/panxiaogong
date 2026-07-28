from __future__ import annotations

import argparse
import html
import re
import shutil
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from functools import partial
from html.parser import HTMLParser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import quote

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape


WEB_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = WEB_ROOT.parent

COMMENT_META_RE = re.compile(r"^%\s*([A-Za-z0-9_-]+)\s*:\s*(.*?)\s*$")
BEGIN_ENV_RE = re.compile(r"^\\begin\{([A-Za-z*]+)\}(?:\[(.*?)\])?\s*$")
COMMAND_CALL_RE = re.compile(r"\\([A-Za-z]+[*]?)")

HEADING_LEVELS = {
    "part": 1,
    "section": 2,
    "subsection": 3,
    "subsubsection": 4,
    "paragraph": 5,
}

MATH_ENVIRONMENTS = {
    "equation",
    "equation*",
    "align",
    "align*",
    "gather",
    "gather*",
    "multline",
    "multline*",
    "split",
    "cases",
    "matrix",
    "pmatrix",
    "bmatrix",
    "vmatrix",
    "Vmatrix",
    "array",
}

CALLOUT_LABELS = {
    "definition": "定义",
    "theorem": "定理",
    "lemma": "引理",
    "corollary": "推论",
    "proposition": "命题",
    "example": "例",
    "remark": "注记",
    "proof": "证明",
    "abstract": "摘要",
}

NUMBERED_CALLOUTS = {
    "definition",
    "theorem",
    "lemma",
    "corollary",
    "proposition",
    "example",
}

INLINE_ONE_ARG = {
    "textbf": "strong",
    "textit": "em",
    "emph": "em",
    "underline": "span class=\"underline\"",
    "texttt": "code",
    "textsc": "span class=\"smallcaps\"",
}

SPECIAL_TEXT_COMMANDS = {
    "%": "%",
    "$": "$",
    "&": "&",
    "#": "#",
    "_": "_",
    "{": "{",
    "}": "}",
    "LaTeX": "LaTeX",
    "TeX": "TeX",
    "textbackslash": "\\",
    "quad": "<span class=\"latex-space latex-space--wide\"></span>",
    "qquad": "<span class=\"latex-space latex-space--wider\"></span>",
    "ldots": "...",
    "cdots": "...",
    "today": datetime.now().strftime("%Y-%m-%d"),
}

METADATA_COMMAND_MAP = {
    "title": "title",
    "author": "author",
    "date": "date",
    "slug": "slug",
    "summary": "summary",
    "description": "summary",
    "tags": "tags",
    "navtitle": "nav_title",
}


@dataclass
class Heading:
    level: int
    text: str
    anchor: str


@dataclass
class Document:
    source_path: Path
    kind: str
    title: str
    slug: str
    url: str
    output_path: Path
    html: str
    summary: str
    author: str
    date_raw: str
    date_display: str
    date_sort: datetime
    tags: list[str] = field(default_factory=list)
    toc: list[Heading] = field(default_factory=list)
    nav_title: str = ""
    collection_path: tuple[str, ...] = ()
    is_home: bool = False
    previous_post: "Document | None" = None
    next_post: "Document | None" = None


class HtmlTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def text(self) -> str:
        return "".join(self.parts)


def strip_html(value: str) -> str:
    parser = HtmlTextExtractor()
    parser.feed(value)
    return re.sub(r"\s+", " ", parser.text()).strip()


def prettify_slug_piece(value: str) -> str:
    if re.search(r"[\u4e00-\u9fff]", value):
        return value
    return value.replace("-", " ").replace("_", " ").title() or value


def normalize_slug(value: str) -> str:
    cleaned = value.strip().replace("\\", "/").strip("/")
    if cleaned in {"", ".", "/"}:
        return ""

    parts: list[str] = []
    for part in cleaned.split("/"):
        normalized = re.sub(
            r"[^\w\u4e00-\u9fff-]+",
            "-",
            part,
            flags=re.UNICODE,
        )
        normalized = re.sub(r"-{2,}", "-", normalized).strip("-")
        if normalized:
            parts.append(normalized)
    return "/".join(parts)


def slugify_fragment(value: str) -> str:
    normalized = normalize_slug(value)
    if "/" in normalized:
        normalized = normalized.split("/")[-1]
    return normalized or "section"


def build_page_url(base_url: str, slug: str) -> str:
    prefix = "" if base_url == "/" else base_url.rstrip("/")
    if not slug:
        return prefix or "/"
    return f"{prefix}/{slug.strip('/')}/"


def build_asset_url(base_url: str, relative_path: str) -> str:
    prefix = "" if base_url == "/" else base_url.rstrip("/")
    clean = relative_path.replace("\\", "/").lstrip("/")
    return f"{prefix}/{clean}" if prefix else f"/{clean}"


def parse_date_value(raw: str | None, fallback: datetime) -> tuple[str, str, datetime]:
    if not raw:
        return fallback.strftime("%Y-%m-%d"), fallback.strftime("%Y-%m-%d"), fallback

    candidate = raw.strip()
    format_map = {
        "%Y-%m-%d": "%Y-%m-%d",
        "%Y/%m/%d": "%Y-%m-%d",
        "%Y-%m-%d %H:%M": "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S": "%Y-%m-%d %H:%M:%S",
    }
    for fmt, display_fmt in format_map.items():
        try:
            parsed = datetime.strptime(candidate, fmt)
            return candidate, parsed.strftime(display_fmt), parsed
        except ValueError:
            continue
    return candidate, candidate, fallback


def parse_tag_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    pieces = re.split(r"[,;，；]\s*", raw)
    return [piece.strip() for piece in pieces if piece.strip()]


def split_leading_comment_metadata(raw: str) -> tuple[dict[str, str], str]:
    metadata: dict[str, str] = {}
    lines = raw.splitlines()
    index = 0

    while index < len(lines):
        line = lines[index]
        matched = COMMENT_META_RE.match(line)
        if matched:
            key, value = matched.groups()
            metadata[key.lower()] = value.strip()
            index += 1
            continue
        if not line.strip() and metadata:
            index += 1
            break
        break

    return metadata, "\n".join(lines[index:])


def consume_group(text: str, start_index: int, opener: str = "{", closer: str = "}") -> tuple[str, int]:
    if start_index >= len(text) or text[start_index] != opener:
        raise ValueError(f"Expected {opener!r} at position {start_index}")

    depth = 0
    buffer: list[str] = []
    index = start_index

    while index < len(text):
        char = text[index]
        if char == "\\" and index + 1 < len(text):
            next_char = text[index + 1]
            if next_char in {opener, closer}:
                buffer.append(char)
                buffer.append(next_char)
                index += 2
                continue
        if char == opener:
            depth += 1
            if depth > 1:
                buffer.append(char)
        elif char == closer:
            depth -= 1
            if depth == 0:
                return "".join(buffer), index + 1
            buffer.append(char)
        else:
            buffer.append(char)
        index += 1

    raise ValueError(f"Unclosed group starting at position {start_index}")


def find_braced_command(text: str, command: str, start_index: int = 0) -> tuple[str, int, int] | None:
    pattern = re.compile(rf"\\{re.escape(command)}\*?\s*\{{")
    matched = pattern.search(text, start_index)
    if not matched:
        return None
    opening_index = matched.end() - 1
    value, end_index = consume_group(text, opening_index)
    return value, matched.start(), end_index


def pull_command_metadata(text: str, metadata: dict[str, str]) -> tuple[str, dict[str, str]]:
    working = text
    for command, key in METADATA_COMMAND_MAP.items():
        search_index = 0
        while True:
            result = find_braced_command(working, command, search_index)
            if not result:
                break
            value, start, end = result
            if not metadata.get(key):
                metadata[key] = value.strip()
            working = working[:start] + working[end:]
            search_index = start

    working = re.sub(r"\\maketitle\b", "", working)
    return working, metadata


def extract_document_body(text: str) -> str:
    begin = re.search(r"\\begin\{document\}", text)
    end = re.search(r"\\end\{document\}", text)
    if begin and end and begin.start() < end.start():
        return text[begin.end() : end.start()]
    return text


def expand_inputs(text: str, source_path: Path, visited: set[Path]) -> str:
    pattern = re.compile(r"^[ \t]*\\(?:input|include)\{([^}]+)\}[ \t]*$", flags=re.MULTILINE)

    def replace(match: re.Match[str]) -> str:
        raw_target = match.group(1).strip()
        candidate = (source_path.parent / raw_target).resolve()
        if not candidate.suffix:
            candidate = candidate.with_suffix(".tex")
        if not candidate.exists() or candidate in visited:
            return ""
        visited.add(candidate)
        included_raw = candidate.read_text(encoding="utf-8")
        _, stripped = split_leading_comment_metadata(included_raw)
        stripped, _ = pull_command_metadata(stripped, {})
        body = extract_document_body(stripped)
        return expand_inputs(body, candidate, visited)

    return pattern.sub(replace, text)


def summarize_html(html_value: str, limit: int = 150) -> str:
    plain = strip_html(html_value)
    if len(plain) <= limit:
        return plain
    shortened = plain[:limit].rstrip("，,；;。 ")
    return f"{shortened}…"


class LatexHtmlConverter:
    def __init__(self, content_root: Path, base_url: str) -> None:
        self.content_root = content_root.resolve()
        self.base_url = base_url
        self.content_asset_prefix = "content-assets"
        self.headings: list[Heading] = []
        self.used_ids: set[str] = set()
        self.callout_counters: defaultdict[str, int] = defaultdict(int)

    def convert(self, text: str, source_path: Path) -> tuple[str, list[Heading]]:
        self.headings = []
        self.used_ids = set()
        self.callout_counters = defaultdict(int)
        lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        html_output = self._render_blocks(lines, source_path)
        html_output = html_output.replace(
            "__TOC_PLACEHOLDER__",
            self._render_inline_toc(),
        )
        return html_output, list(self.headings)

    def _render_blocks(self, lines: list[str], source_path: Path) -> str:
        parts: list[str] = []
        paragraph_lines: list[str] = []
        index = 0

        def flush_paragraph() -> None:
            nonlocal paragraph_lines
            if not paragraph_lines:
                return
            raw = " ".join(piece.strip() for piece in paragraph_lines if piece.strip())
            raw = re.sub(r"\s+", " ", raw).strip()
            paragraph_lines = []
            if raw:
                parts.append(f"<p>{self._render_inline(raw, source_path)}</p>")

        while index < len(lines):
            line = lines[index]
            stripped = line.strip()

            if not stripped:
                flush_paragraph()
                index += 1
                continue

            if stripped.startswith("%"):
                flush_paragraph()
                index += 1
                continue

            heading_match = self._match_heading(stripped)
            if heading_match:
                flush_paragraph()
                parts.append(self._render_heading(*heading_match, source_path))
                index += 1
                continue

            if stripped == r"\tableofcontents":
                flush_paragraph()
                parts.append("__TOC_PLACEHOLDER__")
                index += 1
                continue

            if stripped in {r"\newpage", r"\clearpage"}:
                flush_paragraph()
                parts.append("<hr class=\"page-break\" />")
                index += 1
                continue

            if self._is_display_math_start(stripped):
                flush_paragraph()
                block_html, next_index = self._collect_display_math(lines, index)
                parts.append(block_html)
                index = next_index
                continue

            begin_match = BEGIN_ENV_RE.match(stripped)
            if begin_match:
                flush_paragraph()
                env_name, option = begin_match.groups()
                env_lines, next_index = self._collect_environment(lines, index, env_name)
                parts.append(self._render_environment(env_name, option, env_lines, source_path))
                index = next_index
                continue

            if stripped.startswith(r"\includegraphics"):
                flush_paragraph()
                parts.append(self._render_figure([stripped], source_path))
                index += 1
                continue

            paragraph_lines.append(line)
            index += 1

        flush_paragraph()
        return "\n".join(part for part in parts if part)

    def _match_heading(self, stripped: str) -> tuple[str, str] | None:
        for command in HEADING_LEVELS:
            pattern = re.compile(rf"\\{command}\*?\s*\{{")
            matched = pattern.match(stripped)
            if not matched:
                continue
            try:
                title, _ = consume_group(stripped, matched.end() - 1)
            except ValueError:
                return None
            return command, title
        return None

    def _render_heading(self, command: str, title: str, source_path: Path) -> str:
        level = HEADING_LEVELS[command]
        text = strip_html(self._render_inline(title, source_path))
        anchor = self._unique_anchor(text or title)
        self.headings.append(Heading(level=level, text=text or title, anchor=anchor))
        tag = f"h{min(level, 6)}"
        return f"<{tag} id=\"{anchor}\">{self._render_inline(title, source_path)}</{tag}>"

    def _unique_anchor(self, value: str) -> str:
        base = slugify_fragment(value)
        candidate = base
        suffix = 2
        while candidate in self.used_ids:
            candidate = f"{base}-{suffix}"
            suffix += 1
        self.used_ids.add(candidate)
        return candidate

    def _is_display_math_start(self, stripped: str) -> bool:
        if stripped.startswith("$$") or stripped.startswith(r"\["):
            return True
        begin_match = BEGIN_ENV_RE.match(stripped)
        return bool(begin_match and begin_match.group(1) in MATH_ENVIRONMENTS)

    def _collect_display_math(self, lines: list[str], start_index: int) -> tuple[str, int]:
        stripped = lines[start_index].strip()
        if stripped.startswith("$$"):
            collected = [lines[start_index]]
            if stripped.endswith("$$") and stripped != "$$":
                return self._wrap_math_block("\n".join(collected)), start_index + 1
            index = start_index + 1
            while index < len(lines):
                collected.append(lines[index])
                if lines[index].strip().endswith("$$"):
                    return self._wrap_math_block("\n".join(collected)), index + 1
                index += 1
            return self._wrap_math_block("\n".join(collected)), index

        if stripped.startswith(r"\["):
            collected = [lines[start_index]]
            if stripped.endswith(r"\]") and stripped != r"\[":
                return self._wrap_math_block("\n".join(collected)), start_index + 1
            index = start_index + 1
            while index < len(lines):
                collected.append(lines[index])
                if lines[index].strip().endswith(r"\]"):
                    return self._wrap_math_block("\n".join(collected)), index + 1
                index += 1
            return self._wrap_math_block("\n".join(collected)), index

        begin_match = BEGIN_ENV_RE.match(stripped)
        if begin_match:
            env_name = begin_match.group(1)
            env_lines, next_index = self._collect_environment(lines, start_index, env_name)
            raw = [f"\\begin{{{env_name}}}", *env_lines, f"\\end{{{env_name}}}"]
            return self._wrap_math_block("\n".join(raw)), next_index

        return self._wrap_math_block(lines[start_index]), start_index + 1

    def _collect_environment(self, lines: list[str], start_index: int, env_name: str) -> tuple[list[str], int]:
        content: list[str] = []
        depth = 0
        index = start_index

        while index < len(lines):
            stripped = lines[index].strip()
            begin_match = BEGIN_ENV_RE.match(stripped)
            if begin_match and begin_match.group(1) == env_name:
                depth += 1
                if depth > 1:
                    content.append(lines[index])
                index += 1
                continue

            if stripped == f"\\end{{{env_name}}}":
                depth -= 1
                if depth == 0:
                    return content, index + 1
                content.append(lines[index])
                index += 1
                continue

            content.append(lines[index])
            index += 1

        return content, index

    def _render_environment(
        self,
        env_name: str,
        option: str | None,
        env_lines: list[str],
        source_path: Path,
    ) -> str:
        if env_name in MATH_ENVIRONMENTS:
            raw = [f"\\begin{{{env_name}}}", *env_lines, f"\\end{{{env_name}}}"]
            return self._wrap_math_block("\n".join(raw))

        if env_name in {"itemize", "enumerate"}:
            return self._render_list(env_name, env_lines, source_path)

        if env_name == "quote":
            inner = self._render_blocks(env_lines, source_path)
            return f"<blockquote class=\"latex-quote\">{inner}</blockquote>"

        if env_name == "center":
            inner = self._render_blocks(env_lines, source_path)
            return f"<div class=\"latex-center\">{inner}</div>"

        if env_name == "verbatim":
            raw = "\n".join(env_lines).strip("\n")
            return f"<pre class=\"latex-code\"><code>{html.escape(raw)}</code></pre>"

        if env_name == "figure":
            return self._render_figure(env_lines, source_path)

        if env_name in CALLOUT_LABELS:
            return self._render_callout(env_name, option, env_lines, source_path)

        inner = self._render_blocks(env_lines, source_path)
        return f"<section class=\"latex-block latex-block--generic\">{inner}</section>"

    def _render_list(self, env_name: str, env_lines: list[str], source_path: Path) -> str:
        tag = "ol" if env_name == "enumerate" else "ul"
        items = self._split_list_items(env_lines)
        rendered_items: list[str] = []
        for item_lines in items:
            inner = self._render_blocks(item_lines, source_path).strip()
            rendered_items.append(f"<li>{inner}</li>")
        return f"<{tag} class=\"article-list article-list--{tag}\">\n" + "\n".join(rendered_items) + f"\n</{tag}>"

    def _split_list_items(self, env_lines: list[str]) -> list[list[str]]:
        items: list[list[str]] = []
        current: list[str] = []
        depth = 0

        for line in env_lines:
            stripped = line.strip()
            begin_match = BEGIN_ENV_RE.match(stripped)
            if begin_match:
                if depth == 0 and current and stripped.startswith(r"\item"):
                    items.append(current)
                    current = [stripped[len(r"\item") :].strip()]
                    continue
                depth += 1

            if stripped.startswith(r"\item") and depth == 0:
                if current:
                    items.append(current)
                current = [stripped[len(r"\item") :].strip()]
                continue

            current.append(line)

            if stripped.startswith(r"\end{") and depth > 0:
                depth -= 1

        if current:
            items.append(current)
        return items

    def _render_callout(
        self,
        env_name: str,
        option: str | None,
        env_lines: list[str],
        source_path: Path,
    ) -> str:
        label = CALLOUT_LABELS[env_name]
        if env_name in NUMBERED_CALLOUTS:
            self.callout_counters[env_name] += 1
            label = f"{label} {self.callout_counters[env_name]}"
        if option:
            label = f"{label} · {self._render_inline(option, source_path)}"
        inner = self._render_blocks(env_lines, source_path)
        return (
            f"<section class=\"latex-block latex-block--{env_name}\">"
            f"<div class=\"block-label\">{label}</div>"
            f"<div class=\"block-body\">{inner}</div>"
            f"</section>"
        )

    def _render_figure(self, env_lines: list[str], source_path: Path) -> str:
        joined = "\n".join(env_lines)
        include_match = re.search(r"\\includegraphics(?:\[(?P<options>[^\]]*)\])?\s*\{", joined, flags=re.S)
        if not include_match:
            return ""
        image_path, _ = consume_group(joined, include_match.end() - 1)
        options = include_match.group("options")
        asset_url = self._resolve_asset_url(image_path, source_path)

        caption_match = find_braced_command(joined, "caption")
        caption = caption_match[0].strip() if caption_match else ""
        alt_text = strip_html(self._render_inline(caption, source_path)) or Path(image_path).stem
        width_style = self._latex_width_to_style(options or "")

        image_html = (
            f"<img src=\"{asset_url}\" alt=\"{html.escape(alt_text)}\" "
            f"loading=\"lazy\"{width_style} />"
        )
        if caption:
            caption_html = f"<figcaption>{self._render_inline(caption, source_path)}</figcaption>"
        else:
            caption_html = ""
        return f"<figure class=\"article-figure\">{image_html}{caption_html}</figure>"

    def _latex_width_to_style(self, options: str) -> str:
        if not options:
            return ""
        matched = re.search(r"width\s*=\s*([0-9.]+)\s*\\(?:textwidth|linewidth)", options)
        if not matched:
            return ""
        width_percent = min(max(float(matched.group(1)) * 100, 10.0), 100.0)
        return f" style=\"width: min(100%, {width_percent:.0f}%);\""

    def _resolve_asset_url(self, raw_path: str, source_path: Path) -> str:
        if re.match(r"^(https?:)?//", raw_path) or raw_path.startswith("/"):
            return raw_path

        candidates = [
            (source_path.parent / raw_path).resolve(),
            (self.content_root / raw_path).resolve(),
        ]
        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                try:
                    relative = candidate.relative_to(self.content_root).as_posix()
                except ValueError:
                    continue
                quoted = quote(relative, safe="/-_.~")
                return build_asset_url(
                    self.base_url,
                    f"{self.content_asset_prefix}/{quoted}",
                )

        return build_asset_url(self.base_url, raw_path)

    def _wrap_math_block(self, raw_math: str) -> str:
        return f"<div class=\"math-block\">{html.escape(raw_math.strip(), quote=False)}</div>"

    def _render_inline_toc(self) -> str:
        headings = [heading for heading in self.headings if heading.level >= 2]
        if not headings:
            return ""
        items = [
            (
                "<li>"
                f"<a href=\"#{heading.anchor}\">{html.escape(heading.text)}</a>"
                "</li>"
            )
            for heading in headings
        ]
        return (
            "<nav class=\"inline-toc\">"
            "<div class=\"inline-toc__label\">本文提纲</div>"
            "<ul>"
            + "".join(items)
            + "</ul></nav>"
        )

    def _render_inline(self, text: str, source_path: Path) -> str:
        rendered, _ = self._consume_inline(text, 0, source_path)
        return rendered

    def _consume_inline(self, text: str, start_index: int, source_path: Path) -> tuple[str, int]:
        result: list[str] = []
        index = start_index

        while index < len(text):
            if text.startswith(r"\)", index) or text.startswith("}", index):
                break

            if text.startswith(r"\(", index):
                end = text.find(r"\)", index + 2)
                if end == -1:
                    result.append(html.escape(text[index:]))
                    index = len(text)
                    continue
                raw_math = text[index + 2 : end]
                result.append(
                    f"<span class=\"math-inline\">\\({html.escape(raw_math, quote=False)}\\)</span>"
                )
                index = end + 2
                continue

            if text[index] == "$":
                closing = self._find_unescaped(text, "$", index + 1)
                if closing == -1:
                    result.append("&#36;")
                    index += 1
                    continue
                raw_math = text[index + 1 : closing]
                result.append(
                    f"<span class=\"math-inline\">\\({html.escape(raw_math, quote=False)}\\)</span>"
                )
                index = closing + 1
                continue

            if text[index] == "{":
                inner, next_index = consume_group(text, index)
                rendered, _ = self._consume_inline(inner, 0, source_path)
                result.append(rendered)
                index = next_index
                continue

            if text[index] == "`":
                closing = text.find("`", index + 1)
                if closing == -1:
                    result.append("`")
                    index += 1
                    continue
                code_content = html.escape(text[index + 1 : closing])
                result.append(f"<code>{code_content}</code>")
                index = closing + 1
                continue

            if text[index] == "~":
                result.append("&nbsp;")
                index += 1
                continue

            if text.startswith(r"\\", index):
                result.append("<br />")
                index += 2
                continue

            if text[index] == "\\":
                command, next_index = self._read_command(text, index)
                if command in SPECIAL_TEXT_COMMANDS:
                    result.append(SPECIAL_TEXT_COMMANDS[command])
                    index = next_index
                    continue

                if command in INLINE_ONE_ARG:
                    inner, next_index = self._read_next_group(text, next_index)
                    if inner is None:
                        result.append(html.escape(text[index:next_index]))
                        index = next_index
                        continue
                    tag_spec = INLINE_ONE_ARG[command]
                    if " " in tag_spec:
                        tag_name, attrs = tag_spec.split(" ", 1)
                        inner_html, _ = self._consume_inline(inner, 0, source_path)
                        result.append(f"<{tag_name} {attrs}>{inner_html}</{tag_name}>")
                    else:
                        inner_html, _ = self._consume_inline(inner, 0, source_path)
                        result.append(f"<{tag_spec}>{inner_html}</{tag_spec}>")
                    index = next_index
                    continue

                if command == "href":
                    href, next_index = self._read_next_group(text, next_index)
                    label, next_index = self._read_next_group(text, next_index)
                    if href is None or label is None:
                        result.append(html.escape(text[index:next_index]))
                        index = next_index
                        continue
                    label_html, _ = self._consume_inline(label, 0, source_path)
                    safe_href = html.escape(href.strip(), quote=True)
                    result.append(
                        f"<a href=\"{safe_href}\" target=\"_blank\" rel=\"noreferrer\">{label_html}</a>"
                    )
                    index = next_index
                    continue

                if command == "url":
                    href, next_index = self._read_next_group(text, next_index)
                    if href is None:
                        result.append(html.escape(text[index:next_index]))
                        index = next_index
                        continue
                    safe_href = html.escape(href.strip(), quote=True)
                    visible = html.escape(href.strip())
                    result.append(
                        f"<a href=\"{safe_href}\" target=\"_blank\" rel=\"noreferrer\">{visible}</a>"
                    )
                    index = next_index
                    continue

                if command == "footnote":
                    note, next_index = self._read_next_group(text, next_index)
                    if note is None:
                        result.append(html.escape(text[index:next_index]))
                        index = next_index
                        continue
                    note_html, _ = self._consume_inline(note, 0, source_path)
                    result.append(
                        f"<span class=\"inline-note\" title=\"{html.escape(strip_html(note_html), quote=True)}\">"
                        f"<sup>注</sup>{note_html}</span>"
                    )
                    index = next_index
                    continue

                if command in {"label"}:
                    _, next_index = self._read_next_group(text, next_index)
                    index = next_index
                    continue

                if command in {"ref", "eqref"}:
                    label, next_index = self._read_next_group(text, next_index)
                    fallback = html.escape(label or "")
                    wrapper = f"({fallback})" if command == "eqref" else fallback
                    result.append(f"<span class=\"cross-ref\">{wrapper}</span>")
                    index = next_index
                    continue

                group, next_index = self._read_next_group(text, next_index)
                if group is not None:
                    inner_html, _ = self._consume_inline(group, 0, source_path)
                    result.append(inner_html)
                    index = next_index
                    continue

                result.append(html.escape(text[index:next_index]))
                index = next_index
                continue

            result.append(html.escape(text[index]))
            index += 1

        return "".join(result), index

    def _read_command(self, text: str, start_index: int) -> tuple[str, int]:
        if start_index + 1 >= len(text):
            return "\\", start_index + 1

        index = start_index + 1
        if text[index].isalpha():
            while index < len(text) and (text[index].isalpha() or text[index] == "*"):
                index += 1
            return text[start_index + 1 : index], index

        return text[index], index + 1

    def _read_next_group(self, text: str, start_index: int) -> tuple[str | None, int]:
        index = start_index
        while index < len(text) and text[index].isspace():
            index += 1
        if index >= len(text) or text[index] != "{":
            return None, index
        value, next_index = consume_group(text, index)
        return value, next_index

    def _find_unescaped(self, text: str, marker: str, start_index: int) -> int:
        index = start_index
        while index < len(text):
            if text[index] == marker and text[index - 1] != "\\":
                return index
            index += 1
        return -1


def load_config(config_path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}

    site = raw.setdefault("site", {})
    content = raw.setdefault("content", {})

    site.setdefault("title", "MathBlog")
    site.setdefault("subtitle", "A LaTeX-native academic site")
    site.setdefault("description", "A static site generated from LaTeX sources.")
    site.setdefault("author", "MathBlog")
    site.setdefault("language", "zh-CN")
    site.setdefault("base_url", "/")

    content.setdefault("source_root", "..")
    content.setdefault(
        "reserved_dirs",
        [
            "WebCode",
            ".git",
            ".github",
            ".agents",
            ".codex",
            "__pycache__",
            "node_modules",
        ],
    )
    content.setdefault("output_dir", "./dist")
    return raw


def resolve_local_path(base_path: Path, raw_path: str) -> Path:
    return (base_path / raw_path).resolve()


def discover_content_roots(project_root: Path, reserved_dirs: list[str]) -> list[Path]:
    reserved = {name.casefold() for name in reserved_dirs}
    roots: list[Path] = []

    for entry in project_root.iterdir():
        if not entry.is_dir():
            continue
        if entry.name.startswith("."):
            continue
        if entry.name.casefold() in reserved:
            continue
        roots.append(entry)

    return sorted(roots)


def discover_root_tex_files(project_root: Path) -> list[Path]:
    return sorted(path for path in project_root.glob("*.tex") if path.is_file())


def discover_tex_files(roots: list[Path]) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        files.extend(path for path in root.rglob("*.tex") if path.is_file())
    return sorted(files)


def infer_document_kind(source_path: Path) -> str:
    raw_text = source_path.read_text(encoding="utf-8")
    metadata, _ = split_leading_comment_metadata(raw_text)
    explicit = metadata.get("kind", "").strip().lower()

    if explicit in {"home", "page", "post"}:
        return explicit
    if source_path.stem.lower() == "home":
        return "home"
    return "post"


def build_document(
    source_path: Path,
    kind: str,
    source_root: Path,
    converter: LatexHtmlConverter,
    site_config: dict[str, Any],
    base_url: str,
) -> Document:
    raw_text = source_path.read_text(encoding="utf-8")
    metadata, stripped = split_leading_comment_metadata(raw_text)
    stripped, metadata = pull_command_metadata(stripped, metadata)
    body = extract_document_body(stripped)
    body = expand_inputs(body, source_path, {source_path.resolve()}).strip()

    html_body, toc = converter.convert(body, source_path)
    fallback_date = datetime.fromtimestamp(source_path.stat().st_mtime)
    date_raw, date_display, date_sort = parse_date_value(metadata.get("date"), fallback_date)

    title = metadata.get("title") or (toc[0].text if toc else prettify_slug_piece(source_path.stem))
    nav_title = metadata.get("nav_title") or title

    relative = source_path.relative_to(source_root)
    if kind == "home":
        slug = ""
    elif kind == "page":
        if metadata.get("slug"):
            slug = normalize_slug(metadata["slug"])
        else:
            slug = normalize_slug(relative.with_suffix("").as_posix())
    else:
        slug = normalize_slug(metadata.get("slug") or relative.with_suffix("").as_posix())

    is_home = kind == "home"
    output_path = (
        resolve_local_path(WEB_ROOT, site_config["content"]["output_dir"]) / "index.html"
        if is_home
        else resolve_local_path(WEB_ROOT, site_config["content"]["output_dir"]) / slug / "index.html"
    )
    url = build_page_url(base_url, slug)

    summary = metadata.get("summary") or summarize_html(html_body)
    author = metadata.get("author") or site_config["site"]["author"]
    tags = parse_tag_list(metadata.get("tags"))

    collection_path = () if is_home else relative.parent.parts

    return Document(
        source_path=source_path,
        kind=kind,
        title=title,
        slug=slug,
        url=url,
        output_path=output_path,
        html=html_body,
        summary=summary,
        author=author,
        date_raw=date_raw,
        date_display=date_display,
        date_sort=date_sort,
        tags=tags,
        toc=toc,
        nav_title=nav_title,
        collection_path=collection_path,
        is_home=is_home,
    )


def build_post_tree(posts: list[Document], active_slug: str) -> list[dict[str, Any]]:
    root: list[dict[str, Any]] = []

    for post in posts:
        cursor = root
        for segment in post.collection_path:
            existing = next((node for node in cursor if node["title"] == prettify_slug_piece(segment) and node["url"] is None), None)
            if not existing:
                existing = {
                    "title": prettify_slug_piece(segment),
                    "url": None,
                    "active": False,
                    "children": [],
                }
                cursor.append(existing)
            if existing["url"] is None:
                existing["url"] = post.url
            cursor = existing["children"]

        cursor.append(
            {
                "title": post.nav_title,
                "url": post.url,
                "active": post.slug == active_slug,
                "children": [],
            }
        )

    def sort_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        branches = [node for node in nodes if node["children"]]
        leaves = [node for node in nodes if not node["children"]]
        branches.sort(key=lambda node: node["title"].lower())
        leaves.sort(key=lambda node: node["title"].lower())
        for branch in branches:
            branch["children"] = sort_nodes(branch["children"])
            branch["active"] = branch["active"] or any(child["active"] for child in branch["children"])
        return branches + leaves

    return sort_nodes(root)


def build_navigation_tree(documents: list[Document], active_slug: str) -> list[dict[str, Any]]:
    root: list[dict[str, Any]] = []

    ordered_documents = sorted(
        documents,
        key=lambda item: (item.collection_path, item.nav_title.lower(), item.slug),
    )

    for document in ordered_documents:
        cursor = root
        for segment in document.collection_path:
            existing = next(
                (
                    node
                    for node in cursor
                    if node["title"] == prettify_slug_piece(segment) and node["children"]
                ),
                None,
            )
            if not existing:
                existing = {
                    "title": prettify_slug_piece(segment),
                    "url": None,
                    "active": False,
                    "children": [],
                }
                cursor.append(existing)
            if existing["url"] is None:
                existing["url"] = document.url
            cursor = existing["children"]

        cursor.append(
            {
                "title": document.nav_title,
                "url": document.url,
                "active": document.slug == active_slug,
                "children": [],
            }
        )

    def sort_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        nodes.sort(key=lambda node: node["title"].lower())
        for node in nodes:
            if node["children"]:
                node["children"] = sort_nodes(node["children"])
                node["active"] = node["active"] or any(child["active"] for child in node["children"])
        return nodes

    return sort_nodes(root)


def build_page_links(pages: list[Document], active_slug: str) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []
    for page in sorted((page for page in pages if not page.is_home), key=lambda item: item.nav_title.lower()):
        links.append(
            {
                "title": page.nav_title,
                "url": page.url,
                "active": page.slug == active_slug,
            }
        )
    return links


def build_post_groups(posts: list[Document]) -> list[dict[str, Any]]:
    groups: defaultdict[str, list[Document]] = defaultdict(list)
    for post in posts:
        key = prettify_slug_piece(post.collection_path[0]) if post.collection_path else "未分类"
        groups[key].append(post)

    grouped: list[dict[str, Any]] = []
    for title in sorted(groups.keys(), key=lambda item: item.lower()):
        grouped.append(
            {
                "title": title,
                "posts": sorted(groups[title], key=lambda item: item.date_sort, reverse=True),
            }
        )
    return grouped


def write_text_if_changed(path: Path, content: str) -> None:
    encoded = content.encode('utf-8')
    if path.exists() and path.read_bytes() == encoded:
        return
    path.write_bytes(encoded)


def copy_directory(source: Path, target: Path) -> None:
    if not source.exists():
        return
    shutil.copytree(source, target, dirs_exist_ok=True)


def copy_content_assets(content_root: Path, content_roots: list[Path], output_root: Path) -> None:
    for root in content_roots:
        for item in root.rglob("*"):
            if not item.is_file() or item.suffix.lower() == ".tex":
                continue
            destination = output_root / "content-assets" / item.relative_to(content_root)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, destination)


def render_site(config_path: Path, should_clean: bool = True) -> Path:
    config = load_config(config_path)
    site = config["site"]
    content = config["content"]

    content_root = resolve_local_path(WEB_ROOT, content["source_root"])
    content_roots = discover_content_roots(content_root, content["reserved_dirs"])
    output_dir = resolve_local_path(WEB_ROOT, content["output_dir"])
    templates_dir = WEB_ROOT / "templates"
    assets_dir = WEB_ROOT / "assets"

    if should_clean and output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    copy_directory(assets_dir, output_dir / "assets")
    copy_content_assets(content_root, content_roots, output_dir)

    converter = LatexHtmlConverter(content_root=content_root, base_url=site["base_url"])

    source_paths = [*discover_root_tex_files(content_root), *discover_tex_files(content_roots)]
    pages: list[Document] = []
    posts: list[Document] = []

    for path in sorted(source_paths):
        kind = infer_document_kind(path)
        document = build_document(path, kind, content_root, converter, config, site["base_url"])
        if document.is_home or document.kind == "page":
            pages.append(document)
        else:
            posts.append(document)

    home_pages = [page for page in pages if page.is_home]
    if len(home_pages) > 1:
        locations = ", ".join(str(page.source_path.relative_to(content_root)) for page in home_pages)
        raise ValueError(f"Multiple home documents found: {locations}")

    if not home_pages:
        pages.insert(
            0,
            Document(
                source_path=content_root / "home.tex",
                kind="home",
                title=site["title"],
                slug="",
                url=build_page_url(site["base_url"], ""),
                output_path=output_dir / "index.html",
                html="<p>欢迎来到新的 LaTeX 数学站点。你可以在仓库根目录下任意内容文件夹里的 <code>home.tex</code> 中自定义首页内容。</p>",
                summary=site["description"],
                author=site["author"],
                date_raw="",
                date_display="",
                date_sort=datetime.now(),
                nav_title="首页",
                is_home=True,
            ),
        )


    # 按课程文件夹（collection）分组，使上一篇/下一篇链接仅在同一课程内跳转
    collection_groups: dict[tuple[str, ...], list[Document]] = defaultdict(list)
    for post in posts:
        collection_groups[post.collection_path].append(post)

    for group in collection_groups.values():
        group.sort(key=lambda item: item.date_sort, reverse=True)
        for index, post in enumerate(group):
            if index > 0:
                post.next_post = group[index - 1]
            if index + 1 < len(group):
                post.previous_post = group[index + 1]


    home_page = next(page for page in pages if page.is_home)
    other_pages = [page for page in pages if not page.is_home]

    jinja = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )

    sidebar_template = jinja.get_template("sidebar.html")
    all_navigation_docs = [home_page, *other_pages, *posts]
    shared_navigation_tree = build_navigation_tree(all_navigation_docs, "")
    sidebar_html = sidebar_template.render(
        site=site,
        navigation_tree=shared_navigation_tree,
    )
    write_text_if_changed(output_dir / "sidebar.html", sidebar_html)

    last_updated = max(
        [home_page.date_sort, *(page.date_sort for page in other_pages), *(post.date_sort for post in posts)],
        default=datetime.now(),
    )

    base_context = {
        "site": site,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "last_updated": last_updated.strftime("%Y-%m-%d"),
        "post_count": len(posts),
        "page_count": len(other_pages),
        "recent_posts": posts[:6],
        "post_groups": build_post_groups(posts),
        "content_root_label": "仓库根目录下与 WebCode 同级的内容文件夹",
    }

    def render_document(document: Document) -> None:
        template_name = "home.html" if document.is_home else "page.html"
        template = jinja.get_template(template_name)
        rendered = template.render(
            **base_context,
            document=document,
            other_pages=other_pages,
            toc=[heading for heading in document.toc if heading.level >= 2],
        )
        document.output_path.parent.mkdir(parents=True, exist_ok=True)
        write_text_if_changed(document.output_path, rendered)

    render_document(home_page)
    for page in other_pages:
        render_document(page)
    for post in posts:
        render_document(post)

    return output_dir


def serve_directory(root: Path, port: int) -> None:
    handler = partial(SimpleHTTPRequestHandler, directory=str(root))
    with ThreadingHTTPServer(("127.0.0.1", port), handler) as server:
        print(f"Serving {root} at http://127.0.0.1:{port}")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the LaTeX-driven MathBlog site.")
    parser.add_argument(
        "--config",
        default=str(WEB_ROOT / "config.yml"),
        help="Path to the site config file.",
    )
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="Keep existing files in the output directory.",
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Serve the built site locally after building.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port used with --serve.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_path = Path(args.config).resolve()
    if not config_path.exists():
        print(f"Config file not found: {config_path}", file=sys.stderr)
        return 1

    output_dir = render_site(config_path, should_clean=not args.no_clean)
    print(f"Build complete: {output_dir}")

    if args.serve:
        serve_directory(output_dir, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

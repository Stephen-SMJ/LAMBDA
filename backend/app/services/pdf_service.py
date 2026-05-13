"""PDF export service with embedded images using fpdf2."""

import base64
import html
import mimetypes
import re
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime
from urllib.parse import parse_qs, unquote, urlparse
from fpdf import FPDF
from PIL import Image
import io
import requests


class PDFService:
    """Service for generating PDF reports with embedded images."""
    
    def __init__(self):
        self.images_dir = Path("./data/images")
        self.images_dir.mkdir(parents=True, exist_ok=True)
    
    def markdown_to_pdf(
        self,
        markdown_content: str,
        conversation_title: str,
        output_path: str,
        tool_calls: List[Dict[str, Any]] = None
    ) -> str:
        """
        Convert Markdown report to PDF with embedded images.
        
        Args:
            markdown_content: The markdown report content
            conversation_title: Title of the conversation
            output_path: Where to save the PDF
            tool_calls: List of tool calls with image information
            
        Returns:
            Path to the generated PDF
        """
        try:
            self._markdown_to_pdf_weasyprint(markdown_content, conversation_title, output_path)
            return output_path
        except Exception as e:
            print(f"WeasyPrint PDF generation failed, falling back to fpdf2: {e}")

        pdf = MarkdownPDF(conversation_title)
        pdf.add_page()
        
        # Parse and render markdown
        self._render_markdown(pdf, markdown_content)
        
        # Save PDF
        pdf.output(output_path)
        
        return output_path

    def markdown_to_slides_pdf(
        self,
        markdown_content: str,
        conversation_title: str,
        output_path: str
    ) -> str:
        """Convert Markdown report to a slide-deck style PDF (landscape, one slide per section)."""
        from weasyprint import HTML

        slides_html = self._build_slides_html(markdown_content, conversation_title)
        slides_html = self._embed_html_images_as_data_uris(slides_html)

        today = datetime.now().strftime("%B %d, %Y")
        document_html = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>{html.escape(conversation_title or "LAMBDA Slides")}</title>
  <style>
    @page {{
      size: A4 landscape;
      margin: 0;
    }}
    * {{ box-sizing: border-box; }}
    html, body {{
      margin: 0;
      padding: 0;
      font-family: "DejaVu Sans", "Noto Sans", sans-serif;
      color: #1f2937;
    }}
    .slide {{
      width: 297mm;
      height: 210mm;
      padding: 14mm 18mm;
      page-break-after: always;
      position: relative;
      overflow: hidden;
    }}
    .slide:last-child {{
      page-break-after: auto;
    }}

    /* Cover slide */
    .slide-cover {{
      background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
      color: #fff;
      display: flex;
      flex-direction: column;
      justify-content: center;
      align-items: center;
      text-align: center;
    }}
    .slide-cover .logo {{
      font-size: 14pt;
      letter-spacing: 4px;
      text-transform: uppercase;
      color: #94a3b8;
      margin-bottom: 24mm;
    }}
    .slide-cover h1 {{
      font-size: 32pt;
      font-weight: 700;
      margin: 0 0 10mm 0;
      line-height: 1.2;
      color: #fff;
      border: none;
    }}
    .slide-cover .subtitle {{
      font-size: 14pt;
      color: #cbd5e1;
      margin-bottom: 20mm;
    }}
    .slide-cover .meta {{
      font-size: 11pt;
      color: #94a3b8;
    }}
    .slide-cover .accent-bar {{
      position: absolute;
      bottom: 0;
      left: 0;
      right: 0;
      height: 4mm;
      background: linear-gradient(90deg, #3b82f6, #8b5cf6, #ec4899);
    }}

    /* TOC slide */
    .slide-toc {{
      background: #fff;
      display: flex;
      flex-direction: column;
    }}
    .slide-toc h2 {{
      font-size: 22pt;
      color: #0f172a;
      margin: 0 0 10mm 0;
      padding-bottom: 4mm;
      border-bottom: 2px solid #e2e8f0;
    }}
    .toc-list {{
      list-style: none;
      padding: 0;
      margin: 0;
      flex: 1;
      display: flex;
      flex-direction: column;
      justify-content: center;
    }}
    .toc-list li {{
      font-size: 14pt;
      padding: 4mm 0;
      border-bottom: 1px solid #f1f5f9;
      color: #334155;
      display: flex;
      align-items: baseline;
    }}
    .toc-list li .num {{
      font-size: 18pt;
      font-weight: 700;
      color: #3b82f6;
      width: 12mm;
      flex-shrink: 0;
    }}
    .slide-toc .accent-bar {{
      position: absolute;
      top: 0;
      left: 0;
      width: 25mm;
      height: 100%;
      background: linear-gradient(180deg, #3b82f6, #8b5cf6);
      opacity: 0.08;
    }}

    /* Content slides */
    .slide-content {{
      background: #fff;
      display: flex;
      flex-direction: column;
    }}
    .slide-content .slide-header {{
      display: flex;
      align-items: center;
      margin-bottom: 4mm;
      padding-bottom: 2mm;
      border-bottom: 1.5px solid #e2e8f0;
      flex-shrink: 0;
    }}
    .slide-content .slide-header .slide-num {{
      font-size: 11pt;
      font-weight: 700;
      color: #fff;
      background: linear-gradient(135deg, #3b82f6, #8b5cf6);
      width: 10mm;
      height: 10mm;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      margin-right: 4mm;
      flex-shrink: 0;
    }}
    .slide-content .slide-header h2 {{
      font-size: 20pt;
      color: #0f172a;
      margin: 0;
      border: none;
      line-height: 1.2;
    }}
    .slide-content .slide-body {{
      flex: 1;
      font-size: 11pt;
      line-height: 1.45;
      overflow: hidden;
      max-height: 155mm;
    }}
    .slide-content .slide-body h3 {{
      font-size: 13pt;
      color: #1e293b;
      margin: 3mm 0 2mm 0;
    }}
    .slide-content .slide-body h4 {{
      font-size: 11.5pt;
      color: #334155;
      margin: 2mm 0 1.5mm 0;
    }}
    .slide-content .slide-body p {{
      margin: 0 0 2mm 0;
    }}
    .slide-content .slide-body ul, .slide-content .slide-body ol {{
      margin: 1mm 0 2mm 5mm;
      padding-left: 3mm;
    }}
    .slide-content .slide-body li {{
      margin: 0.8mm 0;
    }}
    .slide-content .slide-body pre {{
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 2mm;
      padding: 2mm 3mm;
      font-size: 8pt;
      line-height: 1.35;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      font-family: "DejaVu Sans Mono", monospace;
      max-height: 30mm;
      overflow: hidden;
      page-break-inside: avoid;
    }}
    .slide-content .slide-body code {{
      font-family: "DejaVu Sans Mono", monospace;
      background: #f1f5f9;
      padding: 0.5mm 1.5mm;
      border-radius: 1mm;
      font-size: 0.9em;
    }}
    .slide-content .slide-body img {{
      display: block;
      max-width: 90%;
      max-height: 45mm;
      height: auto;
      margin: 2mm auto 3mm;
      page-break-inside: avoid;
    }}
    .slide-content .slide-body table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 8pt;
      margin: 2mm 0;
      page-break-inside: avoid;
    }}
    .slide-content .slide-body th, .slide-content .slide-body td {{
      border: 1px solid #cbd5e1;
      padding: 1.5mm 2mm;
      text-align: left;
    }}
    .slide-content .slide-body th {{
      background: #f1f5f9;
      font-weight: 700;
    }}
    .slide-content .slide-body tr:nth-child(even) td {{
      background: #f8fafc;
    }}
    .slide-content .slide-footer {{
      margin-top: auto;
      padding-top: 2mm;
      border-top: 1px solid #e2e8f0;
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 8pt;
      color: #94a3b8;
      flex-shrink: 0;
    }}

    /* Closing slide */
    .slide-closing {{
      background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
      color: #fff;
      display: flex;
      flex-direction: column;
      justify-content: center;
      align-items: center;
      text-align: center;
    }}
    .slide-closing h2 {{
      font-size: 28pt;
      margin: 0 0 8mm 0;
      color: #fff;
      border: none;
    }}
    .slide-closing p {{
      font-size: 12pt;
      color: #94a3b8;
      margin: 0;
    }}
    .slide-closing .accent-bar {{
      position: absolute;
      bottom: 0;
      left: 0;
      right: 0;
      height: 4mm;
      background: linear-gradient(90deg, #3b82f6, #8b5cf6, #ec4899);
    }}
  </style>
</head>
<body>
{slides_html}
</body>
</html>"""
        HTML(string=document_html, base_url="http://127.0.0.1:8000").write_pdf(output_path)
        return output_path

    def _split_body_into_slides(self, body_html: str) -> list[str]:
        """Split overflowing body HTML into multiple slide-sized chunks."""
        # Extract top-level block elements
        block_re = re.compile(
            r'<(p|h3|h4|blockquote)\b[^>]*>.*?</\1>'
            r'|<(ul|ol|pre|table)\b[^>]*>.*?</\2>'
            r'|<img\b[^>]*>'
            r'|<hr\b[^>]*>',
            re.DOTALL | re.IGNORECASE
        )
        blocks = [m.group(0) for m in block_re.finditer(body_html)]
        if not blocks:
            return [body_html] if body_html.strip() else ["<p></p>"]

        def estimate_weight(block: str) -> float:
            tag = re.match(r'<(\w+)', block, re.IGNORECASE)
            tag_name = (tag.group(1).lower() if tag else "")
            text = re.sub(r'<[^>]+>', '', block)
            if tag_name == "img":
                return 0.45
            if tag_name in ("h3",):
                return 0.08
            if tag_name in ("h4",):
                return 0.06
            if tag_name == "hr":
                return 0.03
            if tag_name == "pre":
                lines = block.count('\n') + 1
                return min(0.5, lines / 6 * 0.25 + 0.05)
            if tag_name == "table":
                rows = len(re.findall(r'<tr[>\s]', block, re.IGNORECASE))
                return min(0.6, rows * 0.06 + 0.08)
            if tag_name in ("ul", "ol"):
                items = len(re.findall(r'<li[>\s]', block, re.IGNORECASE))
                return min(0.5, items * 0.09 + 0.04)
            if tag_name == "blockquote":
                return min(0.4, len(text) / 600)
            # <p> and fallback
            return min(0.4, len(text) / 500 + 0.02)

        MAX_WEIGHT = 2.0
        slides_blocks: list[list[str]] = []
        current: list[str] = []
        current_weight = 0.0

        for block in blocks:
            w = estimate_weight(block)
            if current_weight + w > MAX_WEIGHT and current:
                slides_blocks.append(current)
                current = [block]
                current_weight = w
            else:
                current.append(block)
                current_weight += w
        if current:
            slides_blocks.append(current)

        return ["\n".join(sb) for sb in slides_blocks]

    def _build_slides_html(self, markdown: str, conversation_title: str) -> str:
        """Parse markdown and build slide HTML (cover + toc + sections + closing)."""
        lines = markdown.splitlines()

        # Extract main title from first H1, fallback to conversation_title
        report_title = conversation_title or "Data Analysis Report"
        report_subtitle = ""
        for line in lines:
            if line.strip().startswith("# "):
                report_title = line.strip()[2:].strip()
                break
            elif line.strip().startswith("## ") and not report_subtitle:
                report_subtitle = line.strip()[3:].strip()

        # Split by H2 sections
        sections = []
        current_title = ""
        current_lines = []

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("## "):
                if current_title or current_lines:
                    sections.append((current_title, current_lines))
                current_title = stripped[3:].strip()
                current_lines = []
            else:
                current_lines.append(line)
        if current_title or current_lines:
            sections.append((current_title, current_lines))

        # If no H2 sections found, treat whole doc as one section
        if not sections:
            sections = [(report_title, lines)]

        # Filter out empty sections
        sections = [(t, ls) for t, ls in sections if t or any(l.strip() for l in ls)]
        if not sections:
            sections = [(report_title, lines)]

        today = datetime.now().strftime("%B %d, %Y")
        slides = []

        # 1. Cover slide
        slides.append(f"""<div class="slide slide-cover">
  <div class="logo">LAMBDA</div>
  <h1>{html.escape(report_title)}</h1>
  <div class="subtitle">{html.escape(report_subtitle) if report_subtitle else "Data Analysis Report"}</div>
  <div class="meta">{today}</div>
  <div class="accent-bar"></div>
</div>""")

        # 2. TOC slide
        if len(sections) > 1:
            toc_items = ""
            for idx, (title, _) in enumerate(sections, start=1):
                if title:
                    toc_items += f"""<li><span class="num">{idx}</span>{html.escape(title)}</li>\n"""
            slides.append(f"""<div class="slide slide-toc">
  <div class="accent-bar"></div>
  <h2>Agenda</h2>
  <ul class="toc-list">
{toc_items}  </ul>
</div>""")

        # 3. Content slides
        slide_counter = 2 if len(sections) > 1 else 1
        for idx, (title, sec_lines) in enumerate(sections, start=1):
            # Skip the first section if it has no title (often H1 content before first H2)
            if not title and idx == 1:
                continue

            # Convert section markdown to HTML
            sec_md = "\n".join(sec_lines)
            body_html = self._markdown_to_html(sec_md)

            # Split overflowing sections into multiple slides
            sub_slides = self._split_body_into_slides(body_html)
            for sub_idx, sub_body in enumerate(sub_slides, start=1):
                slide_counter += 1
                sub_title = html.escape(title) if title else "Overview"
                if len(sub_slides) > 1:
                    sub_title += f" <span style='font-size:13pt;color:#64748b;'>({sub_idx}/{len(sub_slides)})</span>"
                slides.append(f"""<div class="slide slide-content">
  <div class="slide-header">
    <div class="slide-num">{slide_counter - 1}</div>
    <h2>{sub_title}</h2>
  </div>
  <div class="slide-body">
{sub_body}
  </div>
  <div class="slide-footer">
    <span>{html.escape(report_title)}</span>
    <span>{slide_counter - 1}</span>
  </div>
</div>""")

        # 4. Closing slide
        slides.append(f"""<div class="slide slide-closing">
  <h2>Thank You</h2>
  <p>Generated by LAMBDA &middot; {today}</p>
  <div class="accent-bar"></div>
</div>""")

        return "\n".join(slides)

    def _markdown_to_pdf_weasyprint(self, markdown_content: str, conversation_title: str, output_path: str) -> str:
        """Render markdown via HTML/CSS with WeasyPrint for higher-quality PDF output."""
        from weasyprint import HTML

        body_html = self._markdown_to_html(markdown_content)
        body_html = self._embed_html_images_as_data_uris(body_html)
        document_html = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>{html.escape(conversation_title or "LAMBDA Report")}</title>
  <style>
    @page {{
      size: A4;
      margin: 22mm 18mm 20mm 18mm;
      @bottom-center {{
        content: "Page " counter(page);
        color: #8a8a8a;
        font-size: 9px;
      }}
    }}
    body {{
      font-family: "DejaVu Sans", "Noto Sans", sans-serif;
      color: #171717;
      font-size: 11.5pt;
      line-height: 1.58;
    }}
    h1, h2, h3, h4 {{
      color: #111827;
      line-height: 1.25;
      margin: 1.2em 0 0.45em;
      break-after: avoid;
    }}
    h1 {{
      font-size: 25pt;
      border-bottom: 2px solid #111827;
      padding-bottom: 8px;
      margin-top: 0;
    }}
    h2 {{
      font-size: 18pt;
      border-bottom: 1px solid #d4d4d4;
      padding-bottom: 4px;
    }}
    h3 {{ font-size: 14.5pt; }}
    p {{ margin: 0.55em 0 0.95em; }}
    ul, ol {{ margin: 0.4em 0 1em 1.3em; padding: 0; }}
    li {{ margin: 0.25em 0; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin: 1em 0 1.25em;
      font-size: 9.5pt;
      break-inside: avoid;
    }}
    th, td {{
      border: 1px solid #d4d4d4;
      padding: 6px 8px;
      vertical-align: top;
    }}
    th {{
      background: #f3f4f6;
      font-weight: 700;
    }}
    tr:nth-child(even) td {{ background: #fafafa; }}
    img {{
      display: block;
      max-width: 80%;
      height: auto;
      margin: 12px auto 18px;
      break-inside: avoid;
    }}
    p[align="center"] {{ text-align: center; }}
    p[align="center"] img {{ margin-left: auto; margin-right: auto; }}
    pre {{
      background: #f5f5f5;
      border: 1px solid #e5e5e5;
      border-radius: 6px;
      padding: 10px 12px;
      white-space: pre-wrap;
      font-family: "DejaVu Sans Mono", monospace;
      font-size: 8.5pt;
      line-height: 1.35;
      overflow-wrap: anywhere;
    }}
    code {{
      font-family: "DejaVu Sans Mono", monospace;
      background: #f5f5f5;
      padding: 1px 4px;
      border-radius: 3px;
      font-size: 0.9em;
    }}
    blockquote {{
      color: #525252;
      border-left: 3px solid #d4d4d4;
      padding-left: 12px;
      margin-left: 0;
    }}
  </style>
</head>
<body>
{body_html}
</body>
</html>"""
        HTML(string=document_html, base_url="http://127.0.0.1:8000").write_pdf(output_path)
        return output_path

    def _embed_html_images_as_data_uris(self, html_content: str) -> str:
        """Inline report images so WeasyPrint does not depend on HTTP callbacks."""
        img_src_pattern = re.compile(r'(<img\b[^>]*\bsrc=["\'])([^"\']+)(["\'][^>]*>)', re.IGNORECASE)

        def replace(match: re.Match) -> str:
            prefix, src, suffix = match.groups()
            if src.startswith("data:image/"):
                return match.group(0)

            data_uri = self._image_src_to_data_uri(html.unescape(src))
            if not data_uri:
                return match.group(0)
            return f"{prefix}{html.escape(data_uri, quote=True)}{suffix}"

        return img_src_pattern.sub(replace, html_content)

    def _image_src_to_data_uri(self, src: str) -> str | None:
        """Resolve supported image references to a data URI for PDF rendering."""
        try:
            image_bytes, media_type = self._read_image_reference(src)
            if not image_bytes:
                return None

            if not media_type or media_type == "application/octet-stream":
                guessed_type, _ = mimetypes.guess_type(src)
                media_type = guessed_type or "image/png"

            if not media_type.startswith("image/"):
                return None

            encoded = base64.b64encode(image_bytes).decode("ascii")
            return f"data:{media_type};base64,{encoded}"
        except Exception as e:
            print(f"Error inlining PDF image {src}: {e}")
            return None

    def _read_image_reference(self, src: str) -> tuple[bytes | None, str | None]:
        """Read image bytes from proxy-object URLs, OSS URLs, data URLs, or local files."""
        if src.startswith("data:image/"):
            header, data = src.split(",", 1)
            media_type = header.split(";", 1)[0].replace("data:", "")
            return base64.b64decode(data), media_type

        object_name = self._extract_proxy_or_oss_object_name(src)
        if object_name:
            from app.services.oss_service import get_oss_service

            content = get_oss_service().bucket.get_object(object_name).read()
            media_type, _ = mimetypes.guess_type(object_name)
            return content, media_type or "application/octet-stream"

        if src.startswith("http://") or src.startswith("https://"):
            response = requests.get(src, timeout=30)
            response.raise_for_status()
            return response.content, response.headers.get("content-type")

        local_path = Path(src[1:] if src.startswith("/") else src)
        possible_paths = [
            local_path,
            self.images_dir / local_path.name,
            Path("./data") / local_path,
            Path("./data/images") / local_path.name,
        ]
        for path in possible_paths:
            if path.exists():
                media_type, _ = mimetypes.guess_type(str(path))
                return path.read_bytes(), media_type or "application/octet-stream"

        return None, None

    def _extract_proxy_or_oss_object_name(self, src: str) -> str:
        """Extract generated/uploads/latex OSS object paths from supported URLs."""
        allowed_prefixes = ("generated/", "uploads/", "latex/")

        if src.startswith("/api/v1/files/proxy-object") or "/api/v1/files/proxy-object" in src:
            parsed = urlparse(src)
            path_values = parse_qs(parsed.query).get("path", [])
            object_name = unquote(path_values[0]) if path_values else ""
        elif "lambda-app-prod.oss-cn-hongkong.aliyuncs.com/" in src:
            parsed = urlparse(src)
            object_name = unquote(parsed.path.lstrip("/"))
        else:
            object_name = unquote(src.lstrip("/"))

        # Some existing markdown files contain double-encoded paths.
        object_name = unquote(object_name)
        return object_name if object_name.startswith(allowed_prefixes) else ""

    def _markdown_to_html(self, markdown: str) -> str:
        """Small markdown-to-HTML converter for reports; keeps trusted image HTML blocks."""
        lines = markdown.splitlines()
        html_parts = []
        paragraph = []
        list_items = []
        ordered_items = []
        in_code = False
        code_lines = []

        def flush_paragraph():
            if paragraph:
                text = " ".join(paragraph).strip()
                html_parts.append(f"<p>{self._inline_markdown_to_html(text)}</p>")
                paragraph.clear()

        def flush_lists():
            if list_items:
                html_parts.append("<ul>" + "".join(f"<li>{self._inline_markdown_to_html(item)}</li>" for item in list_items) + "</ul>")
                list_items.clear()
            if ordered_items:
                html_parts.append("<ol>" + "".join(f"<li>{self._inline_markdown_to_html(item)}</li>" for item in ordered_items) + "</ol>")
                ordered_items.clear()

        i = 0
        while i < len(lines):
            raw_line = lines[i]
            stripped = raw_line.strip()

            if stripped.startswith("```"):
                if in_code:
                    html_parts.append(f"<pre><code>{html.escape(chr(10).join(code_lines))}</code></pre>")
                    code_lines = []
                    in_code = False
                else:
                    flush_paragraph()
                    flush_lists()
                    in_code = True
                i += 1
                continue

            if in_code:
                code_lines.append(raw_line)
                i += 1
                continue

            if not stripped:
                flush_paragraph()
                flush_lists()
                i += 1
                continue

            if stripped.startswith("|") and i + 1 < len(lines) and re.match(r'^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$', lines[i + 1]):
                flush_paragraph()
                flush_lists()
                table_lines = [stripped]
                i += 2
                while i < len(lines) and lines[i].strip().startswith("|"):
                    table_lines.append(lines[i].strip())
                    i += 1
                html_parts.append(self._markdown_table_to_html(table_lines))
                continue

            if stripped.startswith("#"):
                flush_paragraph()
                flush_lists()
                level = min(len(stripped) - len(stripped.lstrip("#")), 4)
                title = stripped[level:].strip()
                html_parts.append(f"<h{level}>{self._inline_markdown_to_html(title)}</h{level}>")
                i += 1
                continue

            if stripped in {"---", "***"}:
                flush_paragraph()
                flush_lists()
                html_parts.append("<hr>")
                i += 1
                continue

            if re.match(r'^<p\b[^>]*>\s*<img\b', stripped, re.IGNORECASE) or re.match(r'^<img\b', stripped, re.IGNORECASE):
                flush_paragraph()
                flush_lists()
                html_parts.append(stripped)
                i += 1
                continue

            image_match = re.match(r'!\[(.*?)\]\((.+?)\)', stripped)
            if image_match:
                flush_paragraph()
                flush_lists()
                alt = html.escape(image_match.group(1))
                src = html.escape(image_match.group(2), quote=True)
                html_parts.append(f'<p align="center"><img src="{src}" alt="{alt}" width="80%"></p>')
                i += 1
                continue

            bullet_match = re.match(r'^[-*+]\s+(.+)$', stripped)
            if bullet_match:
                flush_paragraph()
                ordered_items.clear()
                list_items.append(bullet_match.group(1))
                i += 1
                continue

            ordered_match = re.match(r'^\d+\.\s+(.+)$', stripped)
            if ordered_match:
                flush_paragraph()
                list_items.clear()
                ordered_items.append(ordered_match.group(1))
                i += 1
                continue

            paragraph.append(stripped)
            i += 1

        if in_code:
            html_parts.append(f"<pre><code>{html.escape(chr(10).join(code_lines))}</code></pre>")
        flush_paragraph()
        flush_lists()
        return "\n".join(html_parts)

    def _inline_markdown_to_html(self, text: str) -> str:
        text = html.escape(text)
        text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
        text = re.sub(r'\*\*\*([^*]+)\*\*\*', r'<strong><em>\1</em></strong>', text)
        text = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', text)
        text = re.sub(r'\*([^*]+)\*', r'<em>\1</em>', text)
        return text

    def _markdown_table_to_html(self, table_lines: List[str]) -> str:
        rows = [self._split_table_row(line) for line in table_lines]
        if not rows:
            return ""
        header = rows[0]
        body = rows[1:]
        head_html = "".join(f"<th>{self._inline_markdown_to_html(cell)}</th>" for cell in header)
        body_html = "".join(
            "<tr>" + "".join(f"<td>{self._inline_markdown_to_html(cell)}</td>" for cell in row) + "</tr>"
            for row in body
        )
        return f"<table><thead><tr>{head_html}</tr></thead><tbody>{body_html}</tbody></table>"
    
    def _render_markdown(self, pdf: 'MarkdownPDF', markdown: str):
        """Render markdown content to PDF."""
        lines = markdown.split('\n')
        i = 0
        
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            
            # Skip empty lines
            if not stripped:
                i += 1
                continue
            
            # Headers
            if stripped.startswith('# '):
                pdf.set_font_size(20)
                pdf.set_style('B')
                pdf.multi_cell(0, 10, stripped[2:])
                pdf.set_style('')
                pdf.ln(2)
                i += 1
                continue
            
            if stripped.startswith('## '):
                pdf.set_font_size(16)
                pdf.set_style('B')
                pdf.multi_cell(0, 8, stripped[3:])
                pdf.set_style('')
                pdf.ln(2)
                i += 1
                continue
            
            if stripped.startswith('### '):
                pdf.set_font_size(14)
                pdf.set_style('B')
                pdf.multi_cell(0, 7, stripped[4:])
                pdf.set_style('')
                pdf.ln(1)
                i += 1
                continue
            
            if stripped.startswith('#### '):
                pdf.set_font_size(12)
                pdf.set_style('B')
                pdf.multi_cell(0, 6, stripped[5:])
                pdf.set_style('')
                pdf.ln(1)
                i += 1
                continue
            
            # Horizontal rule
            if stripped == '---' or stripped == '***':
                pdf.ln(2)
                pdf.line(10, pdf.get_y(), 200, pdf.get_y())
                pdf.ln(2)
                i += 1
                continue
            
            # Code blocks
            if stripped.startswith('```'):
                language = stripped[3:].strip()
                i += 1
                code_lines = []
                while i < len(lines) and not lines[i].strip().startswith('```'):
                    code_lines.append(lines[i])
                    i += 1
                code = '\n'.join(code_lines)
                pdf.render_code_block(code, language)
                i += 1  # Skip closing ```
                continue

            # Markdown tables
            if stripped.startswith('|') and i + 1 < len(lines) and re.match(r'^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$', lines[i + 1]):
                table_lines = [stripped]
                i += 2  # Skip header separator
                while i < len(lines) and lines[i].strip().startswith('|'):
                    table_lines.append(lines[i].strip())
                    i += 1
                self._render_table(pdf, table_lines)
                continue
            
            # Images
            img_match = re.match(r'!\[(.*?)\]\((.+?)\)', stripped)
            if img_match:
                alt_text = img_match.group(1)
                img_path = img_match.group(2)
                self._embed_image(pdf, img_path, alt_text)
                i += 1
                continue

            html_img_match = re.search(r'<img\b[^>]*src=["\']([^"\']+)["\'][^>]*(?:alt=["\']([^"\']*)["\'])?[^>]*>', stripped, re.IGNORECASE)
            if html_img_match:
                img_path = html_img_match.group(1)
                alt_text = html_img_match.group(2) or ""
                self._embed_image(pdf, img_path, alt_text)
                i += 1
                continue
            
            # Blockquotes
            if stripped.startswith('> '):
                pdf.set_text_color(80, 80, 80)
                pdf.set_style('I')
                pdf.multi_cell(0, 5, stripped[2:])
                pdf.set_style('')
                pdf.set_text_color(0, 0, 0)
                pdf.ln(1)
                i += 1
                continue
            
            # Lists
            list_match = re.match(r'^(\s*)[-*+] (.+)$', line)
            if list_match:
                indent = len(list_match.group(1))
                content = list_match.group(2)
                bullet_x = 10 + (indent * 2)
                pdf.set_x(bullet_x)
                pdf.cell(3, 5, "-", ln=0)
                pdf.set_x(bullet_x + 4)
                pdf.multi_cell(0, 6.5, self._strip_inline_markdown(content))
                pdf.ln(1)
                i += 1
                continue
            
            # Numbered lists
            num_list_match = re.match(r'^(\s*)\d+\. (.+)$', line)
            if num_list_match:
                indent = len(num_list_match.group(1))
                content = num_list_match.group(2)
                num_x = 10 + (indent * 2)
                pdf.set_x(num_x)
                # Find the number
                num = re.match(r'^(\s*)(\d+)\.', line).group(2)
                pdf.cell(6, 5, num + '.', ln=0)
                pdf.set_x(num_x + 7)
                pdf.multi_cell(0, 6.5, self._strip_inline_markdown(content))
                pdf.ln(1)
                i += 1
                continue
            
            # Regular paragraph with inline formatting
            pdf.set_font('DejaVu', '', 11)
            pdf.multi_cell(0, 7, self._strip_inline_markdown(stripped))
            pdf.ln(2)
            i += 1

    def _strip_inline_markdown(self, text: str) -> str:
        """Convert simple inline markdown to readable plain text for PDF layout."""
        text = re.sub(r'`([^`]+)`', r'\1', text)
        text = re.sub(r'\*\*\*([^*]+)\*\*\*', r'\1', text)
        text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
        text = re.sub(r'\*([^*]+)\*', r'\1', text)
        text = re.sub(r'<[^>]+>', '', text)
        return text

    def _split_table_row(self, row: str) -> List[str]:
        row = row.strip().strip('|')
        return [self._strip_inline_markdown(cell.strip()) for cell in row.split('|')]

    def _render_table(self, pdf: 'MarkdownPDF', table_lines: List[str]):
        """Render a basic markdown table with wrapping cells."""
        if not table_lines:
            return

        rows = [self._split_table_row(line) for line in table_lines]
        if not rows:
            return

        col_count = max(len(row) for row in rows)
        usable_width = pdf.w - pdf.l_margin - pdf.r_margin
        col_width = usable_width / max(col_count, 1)
        line_height = 5.5

        for row_idx, row in enumerate(rows):
            row = row + [""] * (col_count - len(row))
            max_lines = max(1, max(len(pdf.multi_cell(col_width - 2, line_height, cell, split_only=True)) for cell in row))
            row_height = max_lines * line_height + 2

            if pdf.get_y() + row_height > pdf.page_break_trigger:
                pdf.add_page()

            x_start = pdf.get_x()
            y_start = pdf.get_y()
            fill = row_idx == 0
            if fill:
                pdf.set_fill_color(235, 235, 235)
                pdf.set_font('DejaVu', 'B', 9)
            else:
                pdf.set_fill_color(255, 255, 255)
                pdf.set_font('DejaVu', '', 9)

            for col_idx, cell in enumerate(row):
                x = x_start + col_idx * col_width
                pdf.rect(x, y_start, col_width, row_height, 'DF' if fill else 'D')
                pdf.set_xy(x + 1, y_start + 1)
                pdf.multi_cell(col_width - 2, line_height, cell)

            pdf.set_xy(x_start, y_start + row_height)

        pdf.set_font('DejaVu', '', 11)
        pdf.ln(3)
    
    def _render_inline_formatting(self, pdf: 'MarkdownPDF', text: str):
        """Render text with inline formatting (bold, italic, code)."""
        # Split by formatting patterns
        parts = re.split(r'(\*\*\*.*?\*\*\*|\*\*.*?\*\*|\*.*?\*|`.*?`)', text)
        
        for part in parts:
            if not part:
                continue
            
            # Bold + Italic
            if part.startswith('***') and part.endswith('***'):
                pdf.set_style('BI')
                pdf.write(5, part[3:-3])
                pdf.set_style('')
            # Bold
            elif part.startswith('**') and part.endswith('**'):
                pdf.set_style('B')
                pdf.write(5, part[2:-2])
                pdf.set_style('')
            # Italic
            elif part.startswith('*') and part.endswith('*'):
                pdf.set_style('I')
                pdf.write(5, part[1:-1])
                pdf.set_style('')
            # Inline code
            elif part.startswith('`') and part.endswith('`'):
                pdf.set_font('DejaVuMono', '', 9)
                pdf.set_text_color(200, 50, 50)  # Red color for code
                pdf.write(5, ' ' + part[1:-1] + ' ')
                pdf.set_text_color(0, 0, 0)
                pdf.set_font('DejaVu', '', 11)
            else:
                pdf.write(5, part)
    
    def _embed_image(self, pdf: 'MarkdownPDF', img_src: str, alt_text: str):
        """Embed an image into the PDF."""
        original_src = img_src
        image_bytes = None

        if img_src.startswith('/api/'):
            try:
                response = requests.get(f"http://127.0.0.1:8000{img_src}", timeout=30)
                response.raise_for_status()
                image_bytes = response.content
            except Exception as e:
                print(f"Error downloading proxy image {img_src}: {e}")
        elif img_src.startswith('http://') or img_src.startswith('https://'):
            try:
                response = requests.get(img_src, timeout=30)
                response.raise_for_status()
                image_bytes = response.content
            except Exception as e:
                print(f"Error downloading remote image {img_src}: {e}")
        elif img_src.startswith('data:image/'):
            try:
                image_bytes = base64.b64decode(img_src.split(',', 1)[1])
            except Exception as e:
                print(f"Error decoding data image: {e}")

        # Handle different local path formats
        if img_src.startswith('/'):
            img_src = img_src[1:]
        
        # Find image file
        possible_paths = [
            Path(img_src),
            self.images_dir / Path(img_src).name,
            Path("./data") / img_src,
            Path("./data/images") / Path(img_src).name,
        ]
        
        img_source = None
        for path in possible_paths:
            if path.exists():
                img_source = path
                break

        if image_bytes:
            img_source = io.BytesIO(image_bytes)

        if not img_source:
            pdf.set_text_color(150, 150, 150)
            pdf.cell(0, 5, f'[Image not found: {alt_text or original_src}]')
            pdf.set_text_color(0, 0, 0)
            pdf.ln(5)
            return
        
        try:
            # Open and resize image if needed
            with Image.open(img_source) as img:
                # Convert to RGB if necessary
                if img.mode in ('RGBA', 'P'):
                    img = img.convert('RGB')
                
                # Calculate dimensions to fit within page width (80% content width)
                max_width = (pdf.w - pdf.l_margin - pdf.r_margin) * 0.8
                max_height = 150
                
                pixel_width, pixel_height = img.size
                aspect = pixel_height / pixel_width
                img_width = max_width
                img_height = img_width * aspect
                
                if img_height > max_height:
                    img_height = max_height
                    img_width = img_height / aspect
                
                # Save to temporary buffer
                temp_buffer = io.BytesIO()
                img.save(temp_buffer, format='PNG')
                temp_buffer.seek(0)
                
                # Check if image fits on current page
                if pdf.get_y() + img_height > 270:
                    pdf.add_page()
                
                # Center the image
                x = (pdf.w - img_width) / 2
                pdf.image(temp_buffer, x=x, y=pdf.get_y(), w=img_width, h=img_height)
                pdf.set_y(pdf.get_y() + img_height + 5)
                
        except Exception as e:
            print(f"Error embedding image {original_src}: {e}")
            pdf.set_text_color(150, 150, 150)
            pdf.cell(0, 5, f'[Error loading image: {alt_text or original_src}]')
            pdf.set_text_color(0, 0, 0)
            pdf.ln(5)


class MarkdownPDF(FPDF):
    """Custom PDF class for rendering Markdown."""
    
    def __init__(self, title: str = "Report"):
        super().__init__()
        self.title = title
        self.current_style = ''
        
        # Add Unicode fonts (correct file names)
        self.add_font('DejaVu', '', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', uni=True)
        self.add_font('DejaVu', 'B', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', uni=True)
        self.add_font('DejaVu', 'I', '/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Oblique.ttf', uni=True)
        self.add_font('DejaVu', 'BI', '/usr/share/fonts/truetype/dejavu/DejaVuSansMono-BoldOblique.ttf', uni=True)
        
        # Monospace font for code
        self.add_font('DejaVuMono', '', '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf', uni=True)
        
        self.set_font('DejaVu', '', 11)
        self.set_auto_page_break(auto=True, margin=15)
    
    def header(self):
        """Add header with title."""
        if self.page_no() == 1:
            return  # Skip header on first page
        
        self.set_font('DejaVu', 'I', 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f'LAMBDA - {self.title}', ln=True, align='C')
        self.line(10, 18, 200, 18)
        self.ln(5)
        self.set_text_color(0, 0, 0)
    
    def footer(self):
        """Add footer with page number."""
        self.set_y(-15)
        self.set_font('DejaVu', 'I', 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f'Page {self.page_no()}', align='C')
    
    def set_style(self, style: str):
        """Set font style (B, I, BI, or empty)."""
        self.current_style = style
        self.set_font('DejaVu', style, self.font_size_pt)
    
    def set_font_size(self, size: float):
        """Set font size while keeping current style."""
        self.set_font('DejaVu', self.current_style, size)
    
    def render_code_block(self, code: str, language: str = ''):
        """Render a code block."""
        # Save current position
        start_y = self.get_y()
        
        # Background for code block
        self.set_fill_color(245, 245, 245)
        
        # Language label if present
        if language:
            self.set_font('DejaVu', 'I', 8)
            self.set_text_color(100, 100, 100)
            self.cell(0, 5, f'Language: {language}', ln=True)
            self.set_text_color(0, 0, 0)
        
        # Code content
        self.set_font('DejaVuMono', '', 8)
        
        # Calculate height needed
        lines = code.split('\n')
        line_height = 4
        block_height = len(lines) * line_height + 6
        
        # Check if we need a new page
        if start_y + block_height > 270:
            self.add_page()
            start_y = self.get_y()
        
        # Draw background
        self.rect(10, start_y, 190, block_height, 'F')
        
        # Draw code lines
        self.set_xy(12, start_y + 3)
        for line in lines[:100]:  # Limit to 100 lines
            if self.get_y() > 270:
                self.add_page()
                self.set_xy(12, 20)
            self.cell(0, line_height, line, ln=True)
        
        if len(lines) > 100:
            self.cell(0, line_height, '... (truncated)', ln=True)
        
        self.ln(5)
        self.set_font('DejaVu', self.current_style, 11)
        self.set_fill_color(255, 255, 255)

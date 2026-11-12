#!/usr/bin/env python
"""Parse the client's input documents into crd.md with stable block IDs (C-001, C-002, ...).

Usage:
  parse_doc.py <file-or-folder> [<file-or-folder> ...] [--as auto|frd|crd] [--force] [--project ID]
  parse_doc.py --attach-visuals [--project ID]     merge vision-agent results (01-frd/visuals/C-nnn.json)
  parse_doc.py --status [--project ID]             show document type, block counts and pending visuals

Formats (stdlib unless noted):
  .docx            paragraphs, headings, lists, tables, and embedded images (wireframes) -> image blocks
  .pdf             text per page (pypdf); with pdfplumber installed, tables are extracted as real tables.
                   Pages without a text layer (scans) are OCR'd when pytesseract is installed, otherwise
                   they become image blocks for the vision agent.
  .xlsx            one table block per sheet (chunked), shared strings resolved
  .csv .tsv        table blocks (dialect sniffed)
  .html .htm       wireframes/mockups: headings, text, forms (fields, types, required), navigation,
                   tables, buttons and dialogs
  .png .jpg .jpeg .gif .webp .bmp .tif .tiff   image blocks for the vision agent
  .md .txt         text

Writes:
  ../projects/<id>/input/<files>              copies of the originals (+ <name>_media/ for DOCX images)
  ../projects/<id>/01-frd/crd.md              every block prefixed with [C-nnn]
  ../projects/<id>/01-frd/crd-index.json      blocks with kind, text, file, page/sheet; pending visuals
  ../projects/<id>/01-frd/intake.json         document type: "frd" (client already wrote an FRD ->
                                              intake mode, no rewrite) or "crd" (raw requirements)

Image blocks stay "pending" until the visual-analyst agent writes 01-frd/visuals/C-nnn.json and
--attach-visuals merges them; gate.py crd-parsed fails while visuals are pending.
"""
from __future__ import annotations

import argparse
import csv
import io
import re
import shutil
import sys
import zipfile
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

from common import die, project_dir, read_json, rel, write_json, now, latest_version

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PKG_R = "{http://schemas.openxmlformats.org/package/2006/relationships}"
SS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff"}
TEXT_EXT = {".txt", ".md", ".markdown"}
SUPPORTED = {".docx", ".pdf", ".xlsx", ".xlsm", ".csv", ".tsv", ".html", ".htm"} | IMAGE_EXT | TEXT_EXT
TABLE_CHUNK = 40          # data rows per table block (keeps blocks citable and small)
MAX_PDF_PAGES = 500


def B(kind, text, **meta):
    return {"kind": kind, "text": text, **{k: v for k, v in meta.items() if v is not None}}


def md_table(rows: list[list[str]], caption: str | None = None) -> list[str]:
    """Markdown table blocks, chunked to TABLE_CHUNK data rows, header repeated in each chunk."""
    rows = [[str(c).replace("|", "/").replace("\n", " ").strip() for c in r] for r in rows]
    rows = [r for r in rows if any(c for c in r)]
    if not rows:
        return []
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    head, data = rows[0], rows[1:] or [[""] * width]
    out = []
    for start in range(0, len(data), TABLE_CHUNK):
        chunk = data[start:start + TABLE_CHUNK]
        lines = []
        if caption:
            span = f" (rows {start + 1}-{start + len(chunk)})" if len(data) > TABLE_CHUNK else ""
            lines.append(f"{caption}{span}")
        lines += ["| " + " | ".join(head) + " |", "|" + "---|" * width]
        lines += ["| " + " | ".join(r) + " |" for r in chunk]
        out.append("\n".join(lines))
    return out


# ---------------------------------------------------------------- DOCX
def blocks_from_docx(path: Path, media_dir: Path):
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("word/document.xml"))
        rels = {}
        if "word/_rels/document.xml.rels" in z.namelist():
            for r in ET.fromstring(z.read("word/_rels/document.xml.rels")):
                rels[r.get("Id")] = r.get("Target")
        extracted = {}

        def image(rid):
            target = rels.get(rid)
            if not target:
                return None
            name = "word/" + target.lstrip("/").replace("../", "") if not target.startswith("word/") else target
            if name not in z.namelist():
                return None
            if name not in extracted:
                media_dir.mkdir(parents=True, exist_ok=True)
                dest = media_dir / Path(name).name
                dest.write_bytes(z.read(name))
                extracted[name] = dest
            return extracted[name]

        body = root.find(f"{W}body")
        for el in body:
            if el.tag == f"{W}p":
                text = "".join(t.text or "" for t in el.iter(f"{W}t")).strip()
                for blip in el.iter(f"{A}blip"):
                    img = image(blip.get(f"{R}embed"))
                    if img is not None:
                        yield B("image", "", image=img)
                if not text:
                    continue
                style = el.find(f"{W}pPr/{W}pStyle")
                sval = style.get(f"{W}val", "") if style is not None else ""
                is_list = el.find(f"{W}pPr/{W}numPr") is not None
                m = re.match(r"(?i)heading\s*(\d)|title", sval)
                if m:
                    level = int(m.group(1)) if m.group(1) else 1
                    yield B("heading", ("#" * min(level + 1, 6)) + " " + text)
                elif is_list or sval.lower().startswith("list"):
                    yield B("list", "- " + text)
                else:
                    yield B("para", text)
            elif el.tag == f"{W}tbl":
                rows = []
                for tr in el.iter(f"{W}tr"):
                    rows.append([" ".join("".join(t.text or "" for t in p.iter(f"{W}t")).strip()
                                          for p in tc.iter(f"{W}p")).strip() for tc in tr.iter(f"{W}tc")])
                for t in md_table(rows):
                    yield B("table", t)
                for blip in el.iter(f"{A}blip"):
                    img = image(blip.get(f"{R}embed"))
                    if img is not None:
                        yield B("image", "", image=img)


# ---------------------------------------------------------------- PDF
def _ocr_pdf_page(page) -> str:
    """OCR one pdfplumber page if pytesseract (+ a renderer) is installed; '' otherwise."""
    try:
        import pytesseract  # noqa: F401
        img = page.to_image(resolution=200).original
        import pytesseract as pt
        return pt.image_to_string(img).strip()
    except Exception:
        return ""


def blocks_from_pdf(path: Path):
    try:
        import pdfplumber
    except ImportError:
        pdfplumber = None
    if pdfplumber is not None:
        with pdfplumber.open(str(path)) as pdf:
            if len(pdf.pages) > MAX_PDF_PAGES:
                print(f"WARNING: {path.name}: {len(pdf.pages)} pages; only the first {MAX_PDF_PAGES} parsed")
            for n, page in enumerate(pdf.pages[:MAX_PDF_PAGES], 1):
                tables = page.find_tables()
                rest = page
                for t in tables:
                    try:
                        rest = rest.outside_bbox(t.bbox)
                    except Exception:
                        pass
                text = (rest.extract_text() or "").strip()
                if not text and not tables:
                    text = _ocr_pdf_page(page)
                    if text:
                        for b in blocks_from_text(text):
                            yield {**b, "page": n, "ocr": True}
                    else:
                        yield B("image", "", page=n, scanned=True)
                    continue
                for b in blocks_from_text(text):
                    yield {**b, "page": n}
                for t in tables:
                    for chunk in md_table(t.extract() or [], caption=f"Table on page {n}"):
                        yield B("table", chunk, page=n)
        return
    try:
        from pypdf import PdfReader
    except ImportError:
        die("PDF parsing needs pypdf (pip install pypdf); install pdfplumber for table extraction")
    reader = PdfReader(str(path))
    if len(reader.pages) > MAX_PDF_PAGES:
        print(f"WARNING: {path.name}: {len(reader.pages)} pages; only the first {MAX_PDF_PAGES} parsed")
    for n, page in enumerate(reader.pages[:MAX_PDF_PAGES], 1):
        text = (page.extract_text() or "").strip()
        if not text:
            yield B("image", "", page=n, scanned=True)
            continue
        for b in blocks_from_text(text):
            yield {**b, "page": n}


# ---------------------------------------------------------------- spreadsheets
def _col(ref: str) -> int:
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group(0):
        n = n * 26 + ord(ch) - 64
    return n - 1


def blocks_from_xlsx(path: Path):
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        shared = []
        if "xl/sharedStrings.xml" in names:
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(f"{SS}si"):
                shared.append("".join(t.text or "" for t in si.iter(f"{SS}t")))
        targets = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        for sh in wb.iter(f"{SS}sheet"):
            target = targets.get(sh.get(f"{R}id"), "")
            sheet_path = target.lstrip("/") if target.startswith("/") else "xl/" + target
            if sheet_path not in names:
                continue
            rows = []
            for row in ET.fromstring(z.read(sheet_path)).iter(f"{SS}row"):
                cells, nxt = {}, 0
                for c in row.findall(f"{SS}c"):
                    idx = _col(c.get("r")) if c.get("r") else nxt
                    nxt = idx + 1
                    t, v = c.get("t"), c.find(f"{SS}v")
                    if t == "s" and v is not None:
                        val = shared[int(v.text)]
                    elif t == "inlineStr":
                        val = "".join(x.text or "" for x in c.iter(f"{SS}t"))
                    elif t == "b" and v is not None:
                        val = "TRUE" if v.text == "1" else "FALSE"
                    else:
                        val = v.text if v is not None and v.text else ""
                        if re.fullmatch(r"-?\d+\.0", val):
                            val = val[:-2]
                    cells[idx] = val
                if cells:
                    rows.append([cells.get(i, "") for i in range(max(cells) + 1)])
            for chunk in md_table(rows, caption=f"Sheet: {sh.get('name')}"):
                yield B("table", chunk, sheet=sh.get("name"))


def blocks_from_csv(path: Path):
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel_tab if path.suffix.lower() == ".tsv" else csv.excel
    rows = list(csv.reader(io.StringIO(text), dialect))
    for chunk in md_table(rows, caption=f"Table: {path.name}"):
        yield B("table", chunk)


# ---------------------------------------------------------------- HTML wireframes
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


class _Node:
    def __init__(self, tag, attrs, parent=None):
        self.tag, self.attrs, self.parent, self.children = tag, dict(attrs), parent, []

    def text(self) -> str:
        parts = []
        for c in self.children:
            parts.append(c if isinstance(c, str) else c.text())
        return re.sub(r"\s+", " ", " ".join(parts)).strip()

    def find_all(self, *tags):
        for c in self.children:
            if isinstance(c, _Node):
                if c.tag in tags:
                    yield c
                yield from c.find_all(*tags)


class _Tree(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = self.cur = _Node("root", [])

    def handle_starttag(self, tag, attrs):
        node = _Node(tag, attrs, self.cur)
        self.cur.children.append(node)
        if tag not in VOID:
            self.cur = node

    def handle_startendtag(self, tag, attrs):
        self.cur.children.append(_Node(tag, attrs, self.cur))

    def handle_endtag(self, tag):
        n = self.cur
        while n is not self.root and n.tag != tag:
            n = n.parent
        if n is not self.root:
            self.cur = n.parent

    def handle_data(self, data):
        if self.cur.tag not in ("script", "style") and data.strip():
            self.cur.children.append(data)


def _label(node: _Node) -> str:
    for k in ("aria-label", "title", "name", "id"):
        if node.attrs.get(k):
            return str(node.attrs[k])
    return node.text()[:60]


def _describe_form(form: _Node, labels: dict[str, str]) -> str:
    fields, actions = [], []
    for el in form.find_all("input", "select", "textarea", "button"):
        typ = el.attrs.get("type", "text" if el.tag == "input" else el.tag).lower()
        if el.tag == "button" or typ in ("submit", "button", "reset"):
            actions.append(el.text() or el.attrs.get("value") or typ)
            continue
        if typ == "hidden":
            continue
        name = labels.get(el.attrs.get("id", ""), "") or el.attrs.get("aria-label") or el.attrs.get("placeholder") \
            or el.attrs.get("name") or el.attrs.get("id") or "(unlabelled)"
        if el.parent is not None and el.parent.tag == "label" and not labels.get(el.attrs.get("id", "")):
            name = el.parent.text() or name
        bits = [typ]
        if "required" in el.attrs or el.attrs.get("aria-required") == "true":
            bits.append("required")
        for k in ("maxlength", "min", "max", "pattern"):
            if el.attrs.get(k):
                bits.append(f"{k}={el.attrs[k]}")
        if el.tag == "select":
            opts = [o.text() for o in el.find_all("option") if o.text()]
            if opts:
                bits.append("options: " + "/".join(opts[:12]))
        fields.append(f"{name} [{', '.join(bits)}]")
    title = form.attrs.get("aria-label") or form.attrs.get("name") or form.attrs.get("id") or "form"
    out = f"UI form '{title}'"
    if form.attrs.get("action"):
        out += f" (action {form.attrs.get('method', 'get').upper()} {form.attrs['action']})"
    out += ": fields: " + ("; ".join(fields) if fields else "none")
    if actions:
        out += ". Actions: " + ", ".join(actions)
    return out


def blocks_from_html(path: Path):
    tree = _Tree()
    tree.feed(path.read_text(encoding="utf-8", errors="replace"))
    root = tree.root
    labels = {lb.attrs.get("for"): lb.text() for lb in root.find_all("label") if lb.attrs.get("for")}
    title = next(root.find_all("title"), None)
    if title is not None and title.text():
        yield B("heading", f"## Screen: {title.text()}")
    loose_actions = []

    def walk(node: _Node):
        for c in node.children:
            if isinstance(c, str):
                continue
            t = c.tag
            if t in ("script", "style", "head", "template"):
                continue
            if re.fullmatch(r"h[1-6]", t) and c.text():
                yield B("heading", "#" * min(int(t[1]) + 1, 6) + " " + c.text())
            elif t == "form":
                yield B("ui", _describe_form(c, labels))
            elif t == "nav" or c.attrs.get("role") == "navigation":
                items = [a.text() for a in c.find_all("a", "button") if a.text()]
                yield B("ui", f"UI navigation '{_label(c)}': " + ", ".join(items))
            elif t == "table":
                rows = [[cell.text() for cell in tr.find_all("th", "td")] for tr in c.find_all("tr")]
                cap = next(c.find_all("caption"), None)
                for chunk in md_table(rows, caption=f"UI table: {cap.text()}" if cap is not None else "UI table"):
                    yield B("table", chunk)
            elif t == "dialog" or c.attrs.get("role") == "dialog":
                yield B("ui", f"UI dialog '{_label(c)}': {c.text()[:300]}")
            elif t in ("ul", "ol"):
                for li in c.children:
                    if isinstance(li, _Node) and li.tag == "li" and li.text():
                        yield B("list", "- " + li.text())
            elif t == "p" and c.text():
                yield B("para", c.text())
            elif t == "button" or (t == "a" and c.attrs.get("role") == "button"):
                if c.text():
                    loose_actions.append(c.text())
            elif t == "img":
                alt = c.attrs.get("alt") or c.attrs.get("src") or "image"
                yield B("ui", f"UI image placeholder: {alt}")
            else:
                yield from walk(c)

    yield from walk(root)
    if loose_actions:
        yield B("ui", "UI actions on the page: " + ", ".join(dict.fromkeys(loose_actions)))


# ---------------------------------------------------------------- text
def blocks_from_text(text: str):
    para: list[str] = []

    def flush():
        joined = " ".join(s.strip() for s in para).strip()
        para.clear()
        return joined or None

    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped:
            p = flush()
            if p:
                yield B("para", p)
            continue
        if re.match(r"^#{1,6}\s", stripped):
            p = flush()
            if p:
                yield B("para", p)
            yield B("heading", stripped)
        elif re.match(r"^([-*•]|\d+[.)])\s+", stripped):
            p = flush()
            if p:
                yield B("para", p)
            yield B("list", "- " + re.sub(r"^([-*•]|\d+[.)])\s+", "", stripped))
        elif stripped.startswith("|"):
            p = flush()
            if p:
                yield B("para", p)
            yield B("table", stripped)
        else:
            para.append(stripped)
    p = flush()
    if p:
        yield B("para", p)


def merge_tables(blocks):
    """Consecutive single-line table rows from text input become one table block."""
    out = []
    for b in blocks:
        prev = out[-1] if out else None
        if (b["kind"] == "table" and prev and prev["kind"] == "table" and "\n" not in b["text"]
                and prev.get("file") == b.get("file") and prev.get("page") == b.get("page")):
            prev["text"] += "\n" + b["text"]
        else:
            out.append(b)
    return out


# ---------------------------------------------------------------- document type (FRD intake vs CRD)
FRD_HEADINGS = re.compile(r"(?i)functional requirements? (document|specification)|requirements specification|"
                          r"\bFRD\b|\bSRS\b|software requirements")
REQ_IDS = re.compile(r"\b(?:FR|NFR|REQ|BR|UC|US|SR)[-_ ]?\d{1,4}\b|\b[A-Z]{2,5}-\d{2,4}\b")


def detect_doc_type(blocks) -> dict:
    text = "\n".join(b["text"] for b in blocks)
    ids = set(REQ_IDS.findall(text))
    headings = [b["text"] for b in blocks if b["kind"] == "heading"]
    title_hit = any(FRD_HEADINGS.search(h) for h in headings[:15]) or bool(FRD_HEADINGS.search(text[:2000]))
    modal = len(re.findall(r"(?i)\b(shall|must)\b", text))
    is_frd = (title_hit and len(ids) >= 3) or len(ids) >= 10
    return {"doc_type": "frd" if is_frd else "crd",
            "signals": {"frd_title": title_hit, "requirement_ids": len(ids), "shall_must": modal,
                        "sample_ids": sorted(ids)[:10]}}


# ---------------------------------------------------------------- visuals
def render_visual(v: dict) -> str:
    lines = [v.get("summary", "").strip()]
    s = v.get("screen") or {}
    if s:
        head = f"Screen: {s.get('screen_name', '?')}"
        if s.get("user_role"):
            head += f" (role: {s['user_role']})"
        lines.append(head)
        if s.get("layout"):
            lines.append(f"Layout: {s['layout']}")
        if s.get("navigation"):
            lines.append("Navigation: " + ", ".join(s["navigation"]))
        if s.get("form_fields"):
            lines.append("Fields: " + "; ".join(
                f"{f.get('label')} [{f.get('type', 'text')}{', required' if f.get('required') else ''}"
                f"{', options: ' + '/'.join(f['options']) if f.get('options') else ''}]" for f in s["form_fields"]))
        if s.get("buttons"):
            lines.append("Actions: " + ", ".join(
                b.get("label", "") + (f" -> {b['action']}" if b.get("action") else "") for b in s["buttons"]))
        for t in s.get("tables", []):
            lines.append(f"Table '{t.get('caption', '')}': columns " + ", ".join(t.get("columns", [])))
        if s.get("annotations"):
            lines.append("Annotations: " + " | ".join(s["annotations"]))
        if s.get("other_elements"):
            lines.append("Other elements: " + ", ".join(s["other_elements"]))
    if v.get("text"):
        lines.append(v["text"].strip())
    if v.get("mermaid"):
        lines += ["```mermaid", v["mermaid"].strip(), "```"]
    if v.get("uncertain"):
        lines.append("Unreadable/uncertain: " + "; ".join(v["uncertain"]))
    return "\n".join(x for x in lines if x)


# ---------------------------------------------------------------- render + main
def render_crd(index: dict) -> str:
    files = index.get("source_files") or [index.get("source_file")]
    lines = [f"<!-- source: {', '.join(files)} | parsed: {index['parsed_at']} | blocks: {len(index['blocks'])} "
             f"| type: {index.get('doc_type', 'crd')} -->", ""]
    for cid, b in index["blocks"].items():
        where = []
        if len(files) > 1 and b.get("file"):
            where.append(b["file"])
        if b.get("page"):
            where.append(f"p.{b['page']}")
        if b.get("sheet"):
            where.append(f"sheet {b['sheet']}")
        loc = f" ({', '.join(where)})" if where and b["kind"] != "heading" else ""
        if b["kind"] == "image":
            src = b.get("image") or b.get("file")
            tag = f"(image: {src}{', p.' + str(b['page']) if b.get('page') else ''})"
            lines.append(f"[{cid}] {tag} " + (b["text"] or "PENDING VISION ANALYSIS"))
        elif b["kind"] == "table":
            lines += [f"[{cid}] (table){loc}", b["text"]]
        else:
            lines.append(f"[{cid}]{loc} {b['text']}" if loc else f"[{cid}] {b['text']}")
        lines.append("")
    return "\n".join(lines)


def expand_inputs(paths: list[str]) -> list[Path]:
    out = []
    for p in paths:
        src = Path(p).resolve()
        if not src.exists():
            die(f"file not found: {p}")
        if src.is_dir():
            # skip images this tool extracted from DOCX files earlier (<name>_media/), so a re-ingest
            # of ../projects/<id>/input/ does not count them twice
            out += sorted(f for f in src.rglob("*") if f.is_file() and f.suffix.lower() in SUPPORTED
                          and not any(p.endswith("_media") for p in f.relative_to(src).parts[:-1]))
        else:
            out.append(src)
    if not out:
        die("no supported input files found")
    return out


def parse_files(pdir: Path, files: list[Path]) -> list[dict]:
    blocks = []
    for src in files:
        ext = src.suffix.lower()
        dest = pdir / "input" / src.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if src != dest.resolve():
            shutil.copy2(src, dest)
        if len(files) > 1:
            blocks.append(B("heading", f"# Source file: {src.name}", file=src.name))
        if ext == ".docx":
            got = list(blocks_from_docx(src, pdir / "input" / f"{src.stem}_media"))
        elif ext == ".pdf":
            got = list(blocks_from_pdf(src))
        elif ext in (".xlsx", ".xlsm"):
            got = list(blocks_from_xlsx(src))
        elif ext in (".csv", ".tsv"):
            got = list(blocks_from_csv(src))
        elif ext in (".html", ".htm"):
            got = list(blocks_from_html(src))
        elif ext in IMAGE_EXT:
            got = [B("image", "", image=dest)]
        elif ext in TEXT_EXT:
            got = list(blocks_from_text(src.read_text(encoding="utf-8", errors="replace")))
        elif ext == ".doc":
            die(f"{src.name}: legacy .doc is not supported; save it as .docx")
        else:
            die(f"unsupported format '{ext}'. Supported: {' '.join(sorted(SUPPORTED))}")
        if not got:
            print(f"WARNING: no content extracted from {src.name}")
        for b in got:
            b["file"] = src.name
            if b["kind"] == "image":
                b["image"] = rel(b["image"]) if b.get("image") else rel(dest)
        blocks += got
    return merge_tables(blocks)


def cmd_parse(pdir: Path, a):
    fdir = pdir / "01-frd"
    if read_json(fdir / "approval.json", default={}).get("decision") == "approved":
        die("the FRD is approved; the parsed input is locked. Start a new project for new input.")
    if latest_version(fdir, "frd", "json") and not a.force:
        die("an FRD already exists; re-parsing renumbers the C-IDs it cites. Use --force only to start Phase 1 over.")
    files = expand_inputs(a.files)
    blocks = parse_files(pdir, files)
    if not blocks:
        die("no content extracted")
    detected = detect_doc_type(blocks)
    doc_type = detected["doc_type"] if a.as_type == "auto" else a.as_type
    index = {"source_file": files[0].name, "source_files": [f.name for f in files], "parsed_at": now(),
             "doc_type": doc_type, "blocks": {}, "pending_visuals": []}
    for i, b in enumerate(blocks, 1):
        cid = f"C-{i:03d}"
        index["blocks"][cid] = b
        if b["kind"] == "image":
            index["pending_visuals"].append(cid)
    (fdir / "crd.md").write_text(render_crd(index), encoding="utf-8")
    write_json(fdir / "crd-index.json", index)
    write_json(fdir / "intake.json", {"doc_type": doc_type, "decided_by": "auto" if a.as_type == "auto" else "user",
                                      "detected": detected, "files": index["source_files"], "at": now()})
    kinds = {}
    for b in blocks:
        kinds[b["kind"]] = kinds.get(b["kind"], 0) + 1
    print(f"parsed {len(files)} file(s): {len(blocks)} blocks {kinds} -> {rel(fdir / 'crd.md')}")
    print(f"document type: {doc_type.upper()} ({'detected' if a.as_type == 'auto' else 'set by user'}; "
          f"signals {detected['signals']['requirement_ids']} requirement IDs, FRD title {detected['signals']['frd_title']})")
    if index["pending_visuals"]:
        print(f"PENDING VISUALS: {len(index['pending_visuals'])} image/scanned blocks need the visual-analyst agent: "
              f"{', '.join(index['pending_visuals'])}")


def cmd_attach(pdir: Path):
    from validate import validate
    fdir = pdir / "01-frd"
    index = read_json(fdir / "crd-index.json")
    still, attached = [], []
    for cid in index.get("pending_visuals", []):
        vf = fdir / "visuals" / f"{cid}.json"
        if not vf.exists():
            still.append(cid)
            continue
        errs = validate("visual", vf)
        if errs:
            die(f"{rel(vf)} invalid: {errs[0]}")
        v = read_json(vf)
        index["blocks"][cid]["visual"] = v
        index["blocks"][cid]["text"] = render_visual(v)
        attached.append(cid)
    index["pending_visuals"] = still
    (fdir / "crd.md").write_text(render_crd(index), encoding="utf-8")
    write_json(fdir / "crd-index.json", index)
    print(f"attached {len(attached)} visual(s); still pending: {', '.join(still) or 'none'}")
    if still:
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*")
    ap.add_argument("--as", dest="as_type", choices=["auto", "frd", "crd"], default="auto",
                    help="frd = the client's document is already an FRD (intake mode: keep their wording)")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--attach-visuals", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--project")
    a = ap.parse_args()
    pdir = project_dir(a.project)
    if a.attach_visuals:
        return cmd_attach(pdir)
    if a.status:
        idx = read_json(pdir / "01-frd" / "crd-index.json")
        print(f"type {idx.get('doc_type', 'crd')}; {len(idx['blocks'])} blocks; files {idx.get('source_files')}; "
              f"pending visuals: {', '.join(idx.get('pending_visuals', [])) or 'none'}")
        return
    if not a.files:
        ap.error("give at least one input file or folder")
    cmd_parse(pdir, a)


if __name__ == "__main__":
    sys.exit(main())

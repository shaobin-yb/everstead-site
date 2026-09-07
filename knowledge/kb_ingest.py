"""知识库入库与页面生成脚本 — everstead 成果站"知识库"栏目唯一工具

用法(必须用 py 启动器, 勿用 python 商店占位符):
  py kb_ingest.py topic add <主题名> --slug <topic-slug> [--desc ...] [--order N]
  py kb_ingest.py topic ls
  py kb_ingest.py add <文件路径|URL> --title "..." --topic <topic-slug> \
      [--slug s] [--desc ...] [--tags 合规,监管] [--date YYYY-MM-DD] \
      [--dpi N] [--no-render] [--force]
  py kb_ingest.py rm <slug> [--keep-files]
  py kb_ingest.py ls
  py kb_ingest.py build        # 从 manifest 全量重建页面(不重渲图片)

设计要点:
- 原子入库: 一切转换在 .work/<slug>/ 暂存, 全部成功后才落 files/ pages/ 与 manifest
- 原文件进 git 供下载; 渲染图 pages/<slug>/pNNN.* 页内翻页预览
- PPT/DOC/XLS 走 Office COM 转 PDF 再 pdftoppm 渲染(排版保真)
- 发布唯一入口仍是上层 publish.py, 本脚本只生成不 push

2026-09-07 老板立项: 知识库栏目(全公开, 图片翻页+下载, 按主题分类)
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

KB = Path(__file__).resolve().parent
MANIFEST = KB / "manifest.json"
FILES = KB / "files"
PAGES = KB / "pages"
WORK = KB / ".work"

TYPE_LABEL = {"ppt": "PPT", "pdf": "PDF", "doc": "文档", "xls": "表格", "link": "链接", "image": "图片", "html": "网页", "md": "文档"}
TYPE_ICON = {"ppt": "📽️", "pdf": "📄", "doc": "📝", "xls": "📊", "link": "🔗", "image": "🖼️", "html": "🌐", "md": "📝"}
EXT_TO_TYPE = {".pptx": "ppt", ".ppt": "ppt", ".pdf": "pdf",
               ".docx": "doc", ".doc": "doc",
               ".xlsx": "xls", ".xls": "xls",
               ".png": "image", ".jpg": "image", ".jpeg": "image",
               ".html": "html", ".htm": "html",
               ".md": "md"}
DPI_DEFAULT = {"pdf": 110, "ppt": 110, "doc": 110, "xls": 110}
JPEG_QUALITY = 88        # 文档类渲染图统一转 JPEG 的体积参数(屏幕阅读足够, 体积约 1/3)
MAX_FILE_MB = 100      # GitHub 硬限, 超过直接拒绝
WARN_FILE_MB = 50      # 建议限, 超过需 --force
PNG_BUDGET_MB = 25     # 单条目渲染图预算, 超了走降级


# ================= manifest =================

def load_manifest() -> dict:
    if not MANIFEST.exists():
        return {"version": 1, "topics": [], "items": []}
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def save_manifest(m: dict) -> None:
    WORK.mkdir(exist_ok=True)
    tmp = WORK / "manifest.tmp"
    tmp.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, MANIFEST)


def find_topic(m: dict, slug: str) -> dict | None:
    for t in m.get("topics", []):
        if t["slug"] == slug:
            return t
    return None


def find_item(m: dict, slug: str) -> dict | None:
    for it in m.get("items", []):
        if it["slug"] == slug:
            return it
    return None


# ================= 工具函数 =================

def esc(s) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def human_size(n: int) -> str:
    if n >= 1024 * 1024:
        return f"{n / 1024 / 1024:.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n} B"


def url_ok(url: str) -> bool:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.status < 400
    except Exception:
        return False


def md_to_html_light(text: str) -> str:
    """极简 md→html: 标题/表格/列表/代码块/粗体。够知识库说明文档用。"""
    out = []
    in_code = in_ul = in_ol = False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            out.append("</code></pre>" if in_code else '<pre style="background:#0d1a30;color:#7dd3fc;padding:12px;border-radius:8px;overflow:auto"><code>')
            in_code = not in_code
            continue
        if in_code:
            out.append(esc(line))
            continue
        if line.strip().startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            tag = "th" if line.replace("|", "").replace("-", "").replace(":", "").strip() == "" else "td"
            if tag == "th":
                continue  # 跳过表头分隔行
            out.append("<tr>" + "".join(f"<{tag} style='border:1px solid rgba(56,189,248,.16);padding:6px 10px'>{esc(c)}</{tag}>" for c in cells) + "</tr>")
            continue
        m = re.match(r"^(#{1,4})\s+(.*)$", line)
        if m:
            if in_ul: out.append("</ul>"); in_ul = False
            if in_ol: out.append("</ol>"); in_ol = False
            lv = len(m.group(1))
            out.append(f"<h{lv+2} style='color:#7dd3fc;margin:18px 0 8px'>{esc(m.group(2))}</h{lv+2}>")
            continue
        m = re.match(r"^\s*[-*]\s+(.*)$", line)
        if m:
            if in_ol: out.append("</ol>"); in_ol = False
            if not in_ul: out.append("<ul>"); in_ul = True
            out.append(f"<li>{esc(m.group(1))}</li>")
            continue
        m = re.match(r"^\s*\d+[.)]\s+(.*)$", line)
        if m:
            if in_ul: out.append("</ul>"); in_ul = False
            if not in_ol: out.append("<ol>"); in_ol = True
            out.append(f"<li>{esc(m.group(1))}</li>")
            continue
        if not line.strip():
            continue
        if in_ul: out.append("</ul>"); in_ul = False
        if in_ol: out.append("</ol>"); in_ol = False
        txt = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", line.strip())
        out.append(f"<p style='line-height:1.8'>{esc(txt)}</p>")
    if in_ul: out.append("</ul>")
    if in_ol: out.append("</ol>")
    body = "\n".join(out)
    return (f"<!DOCTYPE html><html lang='zh-CN'><head><meta charset='UTF-8'>"
            f"<style>body{{font-family:'Microsoft YaHei',sans-serif;max-width:780px;"
            f"margin:0 auto;padding:24px;color:#e2ecf7;background:#03060c;line-height:1.7}}</style>"
            f"</head><body>{body}</body></html>")


def page_list(slug: str) -> list[str]:
    d = PAGES / slug
    if not d.exists():
        return []
    return sorted(p.name for p in d.glob("p[0-9]*"))


# ================= 转换管线 =================

def _office(progid: str):
    """启动 Office COM。

    注意: pywin32 在 Python 3.14 下 ExportAsFixedFormat 报
    'The Python instance can not be converted to a COM object'(2026-09-07 实测),
    comtypes 走类型库正式调用无此问题。"""
    import comtypes.client
    return comtypes.client.CreateObject(progid)


def pptx_to_pdf(src: Path, pdf: Path) -> None:
    """PowerPoint COM 导出 PDF(保真路线)。"""
    print(f"[conv] PowerPoint 导出 PDF …", flush=True)
    app = _office("PowerPoint.Application")
    try:
        pres = app.Presentations.Open(FileName=str(src), ReadOnly=True, WithWindow=False)
        try:
            pres.ExportAsFixedFormat(str(pdf), 2)  # ppFixedFormatTypePDF = 2
        finally:
            pres.Close()
    finally:
        app.Quit()


def doc_to_pdf(src: Path, pdf: Path) -> None:
    """Word COM 另存 PDF(.doc/.docx 通用)。"""
    print(f"[conv] Word 导出 PDF …", flush=True)
    app = _office("Word.Application")
    app.Visible = False
    app.DisplayAlerts = 0
    try:
        doc = app.Documents.Open(FileName=str(src), ConfirmConversions=False, ReadOnly=True)
        try:
            doc.SaveAs2(FileName=str(pdf), FileFormat=17)  # wdFormatPDF = 17
        finally:
            doc.Close(False)
    finally:
        app.Quit()


def xlsx_to_pdf(src: Path, pdf: Path) -> None:
    """Excel COM 导出 PDF。注意首参名是 Filename(Word 是 FileName)。

    导出前把每张工作表设为"宽度压一页、高度不限": 否则 Excel 会把整表
    缩进一页(62 行表格挤成一张小字图), 纵向展开后每页约 30-40 行可读。
    """
    print(f"[conv] Excel 导出 PDF …", flush=True)
    app = _office("Excel.Application")
    app.Visible = False
    app.DisplayAlerts = False
    try:
        wb = app.Workbooks.Open(Filename=str(src), UpdateLinks=False, ReadOnly=True)
        try:
            for i in range(1, wb.Worksheets.Count + 1):
                ws = wb.Worksheets[i]
                ws.PageSetup.Zoom = False
                ws.PageSetup.FitToPagesWide = 1
                ws.PageSetup.FitToPagesTall = False
            wb.ExportAsFixedFormat(0, str(pdf))  # xlTypePDF = 0
        finally:
            wb.Close(False)
    finally:
        app.Quit()


def pdf_to_pages(pdf: Path, out_dir: Path, dpi: int) -> list[Path]:
    """pdftoppm 渲染 PDF 为 pNNN.png 序列。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["pdftoppm", "-png", "-r", str(dpi),
                        str(pdf), str(out_dir / "p")],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"pdftoppm 失败: {r.stderr[-500:]}")
    raws = sorted(out_dir.glob("p-*.png"), key=lambda p: int(p.stem.split("-")[1]))
    pages = []
    for i, p in enumerate(raws, 1):
        dst = out_dir / f"p{i:03d}.png"
        p.rename(dst)
        pages.append(dst)
    return pages


def pages_total_mb(pages: list[Path]) -> float:
    return sum(p.stat().st_size for p in pages) / 1024 / 1024


def to_jpeg(pages: list[Path], quality: int) -> list[Path]:
    """PNG 转 JPEG(文档截图无透明需求, 体积约 1/3)。"""
    from PIL import Image
    new = []
    for p in pages:
        dst = p.with_suffix(".jpg")
        Image.open(p).convert("RGB").save(dst, quality=quality)
        p.unlink()
        new.append(dst)
    return new


def shrink_pages(pdf: Path, out_dir: Path, pages: list[Path], dpi: int) -> list[Path]:
    """单条目渲染图超 PNG_BUDGET_MB 时两级降级: L1 PNG→JPEG, L2 60% DPI 重渲。

    入参必须是 PNG 列表(调用方别再预先 to_jpeg——对 JPG 再 to_jpeg 会自删源文件,
    2026-09-07 科学黄金时代 170 页入库踩过)。L2 重渲后同样转 JPEG, 输出统一 JPG。"""
    if pages_total_mb(pages) <= PNG_BUDGET_MB:
        return to_jpeg(pages, JPEG_QUALITY)
    pages = to_jpeg(pages, JPEG_QUALITY)
    print(f"[shrink] L1: PNG→JPEG q{JPEG_QUALITY}, 现 {pages_total_mb(pages):.1f} MB", flush=True)
    if pages_total_mb(pages) <= PNG_BUDGET_MB:
        return pages
    dpi2 = max(60, int(dpi * 0.6))
    for p in pages:
        p.unlink()
    pages = pdf_to_pages(pdf, out_dir, dpi2)
    pages = to_jpeg(pages, JPEG_QUALITY)
    print(f"[shrink] L2: {dpi2} DPI 重渲, 现 {pages_total_mb(pages):.1f} MB", flush=True)
    return pages


# ================= 入库 =================

def cmd_add(a) -> None:
    m = load_manifest()
    topic = find_topic(m, a.topic)
    if topic is None:
        print(f"[error] 主题不存在: {a.topic}")
        print("        先执行: py kb_ingest.py topic add <主题名> --slug <topic-slug>")
        sys.exit(1)
    if not a.slug:
        print("[error] --slug 必填(ASCII kebab-case, 如 debt-plan-internal-exchange)")
        sys.exit(1)
    slug = a.slug.strip().lower()
    if find_item(m, slug) and not a.force:
        print(f"[error] slug 已存在: {slug} (覆盖请加 --force)")
        sys.exit(1)

    target = a.target.strip()
    if target.startswith(("http://", "https://")):
        item = _add_link(a, slug, topic)
    else:
        item = _add_file(a, slug, topic)

    if find_item(m, slug):
        m["items"] = [x for x in m["items"] if x["slug"] != slug]
    m["items"].append(item)
    save_manifest(m)
    build_item_page(item, m)
    build_index(m)
    n = item["pages"] or 0
    print(f"[ok] 入库 {item['slug']} | {item['title']} | "
          f"{TYPE_LABEL[item['type']]} {n} 页 {human_size(item['size'])}")


def _add_link(a, slug: str, topic: dict) -> dict:
    print(f"[probe] 探测链接可达性 …", flush=True)
    if not url_ok(a.target):
        print(f"[error] 链接不可达: {a.target}")
        sys.exit(1)
    print("[probe] ok")
    return {"slug": slug, "topic": topic["slug"], "title": a.title,
            "type": "link", "date": a.date or date.today().isoformat(),
            "desc": a.desc or "", "tags": _parse_tags(a.tags),
            "original": "", "file": "", "size": 0, "pages": 0, "url": a.target}


def _parse_tags(s: str) -> list[str]:
    return [t.strip() for t in s.split(",") if t.strip()] if s else []


def _add_file(a, slug: str, topic: dict) -> dict:
    src = Path(a.target).resolve()
    if not src.exists():
        print(f"[error] 文件不存在: {src}")
        sys.exit(1)
    if src.is_dir():
        print(f"[error] 目标是目录不是文件: {src}")
        sys.exit(1)
    size = src.stat().st_size
    if size > MAX_FILE_MB * 1024 * 1024:
        print(f"[error] 文件 {human_size(size)} 超 GitHub {MAX_FILE_MB}MB 硬限, 拒绝入库")
        sys.exit(1)
    if size > WARN_FILE_MB * 1024 * 1024 and not a.force:
        print(f"[warn] 文件 {human_size(size)} 超 {WARN_FILE_MB}MB 建议线, 确认入库请加 --force")
        sys.exit(1)

    itype = EXT_TO_TYPE.get(src.suffix.lower())
    if itype is None:
        print(f"[error] 不支持的类型: {src.suffix} (支持 pptx/pdf/doc(x)/xls(x)/png/jpg/链接)")
        sys.exit(1)
    dpi = a.dpi or DPI_DEFAULT.get(itype, 140)

    wdir = WORK / slug
    if wdir.exists():
        shutil.rmtree(wdir)
    (wdir / "file").mkdir(parents=True)
    moved = []
    try:
        dst = wdir / "file" / src.name
        shutil.copy2(src, dst)
        os.chmod(dst, 0o644)  # 防微信只读属性传染

        pages_rendered = []
        if not a.no_render and (a.force_render or not (PAGES / slug).exists()):
            if itype == "pdf":
                pdf = src
            elif itype == "html":
                pages_rendered = []  # 网页类型不渲染图片页, 条目页 iframe 内嵌预览
            elif itype == "md":
                # md → 轻量 HTML 放 files/<slug>/<name>.html, 条目页 iframe 预览; 原 md 供下载
                html_path = wdir / "file" / (src.name + ".html")
                html_path.write_text(md_to_html_light(src.read_text(encoding="utf-8", errors="replace")),
                                     encoding="utf-8")
                pages_rendered = []
            elif itype == "ppt":
                pdf = wdir / "src.pdf"
                pptx_to_pdf(src, pdf)
            elif itype == "doc":
                pdf = wdir / "src.pdf"
                doc_to_pdf(src, pdf)
            elif itype == "xls":
                pdf = wdir / "src.pdf"
                xlsx_to_pdf(src, pdf)
            else:  # image
                (wdir / "pages").mkdir(parents=True)
                ip = wdir / "pages" / f"p001{src.suffix.lower()}"
                shutil.copy2(src, ip)
                pages_rendered = [ip]
            if itype in ("ppt", "doc", "xls", "pdf"):
                pages_rendered = pdf_to_pages(pdf, wdir / "pages", dpi)
                # shrink_pages 全权负责 PNG→JPEG 转换(别再预先 to_jpeg, 见其 docstring)
                pages_rendered = shrink_pages(pdf, wdir / "pages", pages_rendered, dpi)

        # 全部成功 → 目录级搬入(原子落库)
        if (FILES / slug).exists():
            shutil.rmtree(FILES / slug)
        os.replace(wdir / "file", FILES / slug)
        moved.append(FILES / slug)
        if pages_rendered:
            if (PAGES / slug).exists():
                shutil.rmtree(PAGES / slug)
            os.replace(wdir / "pages", PAGES / slug)
            moved.append(PAGES / slug)
        elif (PAGES / slug).exists():
            # 保留旧渲染页: 重新盘点页数(降级/重渲场景)
            pass
    except Exception as e:
        shutil.rmtree(wdir, ignore_errors=True)
        for p in moved:
            shutil.rmtree(p, ignore_errors=True)
        print(f"[error] 入库失败, 已回滚: {e}")
        sys.exit(1)
    finally:
        shutil.rmtree(wdir, ignore_errors=True)

    return {"slug": slug, "topic": topic["slug"], "title": a.title, "type": itype,
            "date": a.date or date.today().isoformat(), "desc": a.desc or "",
            "tags": _parse_tags(a.tags), "original": src.name, "file": src.name,
            "size": size, "pages": len(page_list(slug)), "url": None}


# ================= 页面生成 =================

VIEWER_JS = """<script>
const PAGES = __PAGES__;
let i = 0;
const img = document.getElementById('pg');
const ind = document.getElementById('ind');
const prevB = document.getElementById('prev');
const nextB = document.getElementById('next');
function go(n){
  if(n < 0 || n >= PAGES.length) return;
  i = n;
  img.src = PAGES[i];
  ind.textContent = (i+1) + ' / ' + PAGES.length;
  prevB.classList.toggle('off', i === 0);
  nextB.classList.toggle('off', i === PAGES.length-1);
  if(i+1 < PAGES.length){ new Image().src = PAGES[i+1]; }
  if(i-1 >= 0){ new Image().src = PAGES[i-1]; }
}
document.addEventListener('keydown', function(e){
  if(e.key === 'ArrowRight' || e.key === 'PageDown'){ go(i+1); }
  if(e.key === 'ArrowLeft' || e.key === 'PageUp'){ go(i-1); }
});
let tx = null;
document.addEventListener('touchstart', function(e){ tx = e.touches[0].clientX; }, {passive: true});
document.addEventListener('touchend', function(e){
  if(tx === null) return;
  const dx = e.changedTouches[0].clientX - tx; tx = null;
  if(Math.abs(dx) > 50){ go(i + (dx < 0 ? 1 : -1)); }
}, {passive: true});
</script>"""

FILTER_JS = """<script>
const q = document.getElementById('q');
const cards = Array.from(document.querySelectorAll('.kb-card'));
const n = document.getElementById('kb-count-n');
q.addEventListener('input', function(){
  const s = q.value.trim().toLowerCase();
  let vis = 0;
  cards.forEach(function(c){
    const hit = !s || c.dataset.search.includes(s);
    c.classList.toggle('hide', !hit);
    if(hit) vis++;
  });
  document.querySelectorAll('.kb-topic').forEach(function(t){
    const any = Array.from(t.querySelectorAll('.kb-card')).some(function(c){
      return !c.classList.contains('hide');
    });
    t.classList.toggle('hide', !any);
  });
  n.textContent = vis;
});
</script>"""


def _chips(tags: list[str]) -> str:
    return "".join(f'<span class="kb-chip">{esc(t)}</span>' for t in tags)


def item_card(it: dict, tname: str) -> str:
    slug = it["slug"]
    icon = TYPE_ICON.get(it["type"], "📦")
    label = TYPE_LABEL.get(it["type"], it["type"])
    pages = it.get("pages") or 0
    fname = it.get("file") or ""
    meta = []
    if it["type"] != "link" and pages:
        meta.append(f"{pages} 页")
    if it.get("size"):
        meta.append(human_size(it["size"]))
    meta.append(it.get("date", ""))
    dl = ""
    if fname:
        durl = f"files/{slug}/{urllib.parse.quote(fname)}"
        dl = (f'<a class="kb-dl" href="{durl}" download '
              f'onclick="event.stopPropagation()">⬇ 下载</a>')
    search = " ".join([it.get("title", ""), it.get("desc", ""),
                       " ".join(it.get("tags", [])), tname]).lower()
    fname_html = f'<div class="kb-fname">{esc(it.get("original") or "")}</div>' if fname else ""
    return (f'<div class="kb-card" onclick="location.href=\'{slug}/index.html\'" '
            f'data-search="{esc(search)}">'
            f'<div class="kb-top"><span class="kb-ico">{icon}</span>'
            f'<span class="kb-badge">{esc(label)}</span></div>'
            f'<div class="kb-t">{esc(it["title"])}</div>'
            f'{fname_html}'
            f'<div class="kb-m">{esc(it.get("desc") or "")}</div>'
            f'<div class="kb-chips">{_chips(it.get("tags", []))}</div>'
            f'<div class="kb-meta"><span>{" · ".join(meta)}</span>{dl}</div>'
            f'</div>')


def build_index(m: dict) -> None:
    topics = sorted(m.get("topics", []), key=lambda t: (t.get("order", 0), t["name"]))
    items = m.get("items", [])
    sections = []
    for t in topics:
        its = sorted((it for it in items if it["topic"] == t["slug"]),
                     key=lambda it: it.get("date", ""), reverse=True)
        cards = "".join(item_card(it, t["name"]) for it in its)
        closed_cls = " closed" if t.get("collapsed") else ""
        sections.append(
            f'<section class="kb-topic{closed_cls}">'
            f'<div class="kb-topic-head" onclick="toggleTopic(this)">'
            f'<span class="kb-topic-name">{esc(t["name"])}</span>'
            f'<span class="kb-topic-slug">{esc(t["slug"])}</span>'
            f'<span class="kb-topic-count">{len(its)} ITEMS</span>'
            f'<span class="kb-arrow">▸</span></div>'
            f'<div class="kb-grid">{cards}</div></section>')
    total = len(items)
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>stay hungry · EVERSTEAD</title>
<link rel="stylesheet" href="../zy-tech.css">
<style>
/* stay hungry 知识库: 主题分组默认折叠 */
.kb-topic-head{{cursor:pointer;user-select:none;display:flex;align-items:center;gap:10px}}
.kb-arrow{{margin-left:auto;font-size:13px;color:var(--muted);transition:transform .2s}}
.kb-topic.closed .kb-grid{{display:none}}
.kb-topic.closed .kb-arrow{{transform:rotate(0deg)}}
.kb-topic:not(.closed) .kb-arrow{{transform:rotate(90deg)}}
.kb-topic{{margin-bottom:26px}}
</style>
</head>
<body>
<div class="kb-topbar">
  <a class="kb-back" href="../index.html">← 成果站首页</a>
  <span class="kb-brand">stay hungry<span class="kb-en">KNOWLEDGE BASE · 求知若饥</span></span>
  <span class="kb-count" id="kb-count-n">{total} ITEMS</span>
</div>
<input class="kb-search" id="q" type="text" placeholder="搜索标题 / 描述 / 标签 …">
<div id="sections">
{"".join(sections) or '<div class="kb-note">暂无条目 — 用 kb_ingest.py add 入库</div>'}
</div>
<div class="kb-footer">stay hungry · 求知若饥 · 翻页预览 + 原文件下载 · 持续更新</div>
{FILTER_JS}
<script>
/* 主题分组折叠/展开 */
function toggleTopic(head){{
  head.parentElement.classList.toggle('closed');
}}
</script>
</body>
</html>"""
    (KB / "index.html").write_text(html, encoding="utf-8")
    print(f"[build] knowledge/index.html ({total} 条目)")


def build_item_page(it: dict, m: dict) -> None:
    slug = it["slug"]
    topic = find_topic(m, it["topic"])
    tname = topic["name"] if topic else it["topic"]
    pages = page_list(slug)
    rel_pages = [f"../pages/{slug}/{p}" for p in pages]
    fname = it.get("file") or ""
    label = TYPE_LABEL.get(it["type"], it["type"])

    dl = ""
    if fname:
        durl = f"../files/{slug}/{urllib.parse.quote(fname)}"
        dl = f'<a class="kb-btn" href="{durl}" download>⬇ 下载原文件</a>'
    meta_parts = [f'<a class="kb-chip" href="../index.html">{esc(tname)}</a>',
                  f'<span class="kb-chip">{esc(label)}</span>',
                  f'<span class="kb-chip">{esc(it.get("date", ""))}</span>']
    meta_parts += [f'<span class="kb-chip">{esc(t)}</span>' for t in it.get("tags", [])]
    fileline = ""
    if fname:
        size_txt = human_size(it.get("size") or 0)
        fileline = f'<div class="kb-fileline">{esc(it.get("original") or fname)} · {size_txt}</div>'

    if it["type"] == "link" and it.get("url"):
        body = (f'<div class="kb-linkpanel"><div class="kb-ico" style="margin:0 auto 12px">🔗</div>'
                f'<div class="u">{esc(it["url"])}</div>'
                f'<a class="kb-btn" href="{esc(it["url"])}" target="_blank" rel="noopener">↗ 打开链接</a>'
                f'</div>')
    elif it["type"] == "html" and fname:
        # 网页条目: iframe 内嵌原文件预览(单文件无依赖的页面)
        src_url = f"../files/{slug}/{urllib.parse.quote(fname)}"
        body = (f'<div class="kb-htmlpanel">'
                f'<iframe src="{src_url}" title="{esc(it["title"])}"></iframe>'
                f'</div>'
                f'<style>'
                f'.kb-htmlpanel{{border:1px solid var(--line);border-radius:10px;overflow:hidden;margin-top:14px}}'
                f'.kb-htmlpanel iframe{{width:100%;height:78vh;border:0;background:#fff}}'
                f'</style>')
    elif it["type"] == "md" and fname:
        # md 条目: 预览 files/<slug>/<原名>.html(入库时轻量转换), 原 md 供下载
        src_url = f"../files/{slug}/{urllib.parse.quote(fname)}.html"
        body = (f'<div class="kb-htmlpanel">'
                f'<iframe src="{src_url}" title="{esc(it["title"])}"></iframe>'
                f'</div>'
                f'<style>'
                f'.kb-htmlpanel{{border:1px solid var(--line);border-radius:10px;overflow:hidden;margin-top:14px}}'
                f'.kb-htmlpanel iframe{{width:100%;height:78vh;border:0}}'
                f'</style>')
    elif pages:
        first = rel_pages[0]
        body = (f'<div class="viewer"><img id="pg" src="{first}" alt="{esc(it["title"])}"></div>'
                f'<div class="viewer-nav">'
                f'<button class="viewer-btn" id="prev" onclick="go(i-1)">‹ 上一页</button>'
                f'<span class="viewer-pg" id="ind">1 / {len(rel_pages)}</span>'
                f'<button class="viewer-btn" id="next" onclick="go(i+1)">下一页 ›</button>'
                f'</div>'
                + VIEWER_JS.replace("__PAGES__", json.dumps(rel_pages)))
    else:
        body = ('<div class="kb-note">无在线预览, 请下载原文件查看</div>'
                if fname else
                '<div class="kb-note">无在线预览</div>')

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(it["title"])} · 知识库</title>
<link rel="stylesheet" href="../../zy-tech.css">
</head>
<body>
<div class="kb-bread"><a href="../../index.html">成果站</a> / <a href="../index.html">知识库</a> / 条目</div>
<h1 class="kb-h1">{esc(it["title"])}</h1>
<div class="kb-infoline">{"".join(meta_parts)}</div>
{fileline}
{dl}
{body}
</body>
</html>"""
    out_dir = KB / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(html, encoding="utf-8")


def build_all(m: dict) -> None:
    for it in m.get("items", []):
        build_item_page(it, m)
    build_index(m)


# ================= 子命令 =================

def cmd_topic(a) -> None:
    m = load_manifest()
    if a.topic_action == "ls":
        for t in m.get("topics", []):
            n = sum(1 for it in m.get("items", []) if it["topic"] == t["slug"])
            print(f"  {t['slug']:<28} {t['name']}  ({n} 条目)")
        if not m.get("topics"):
            print("  (空)")
        return
    if not a.slug:
        print("[error] --slug 必填(ASCII kebab-case, 如 insurance-debt)")
        sys.exit(1)
    slug = a.slug.strip().lower()
    if a.topic_action == "rm":
        if find_topic(m, slug) is None:
            print(f"[error] 主题不存在: {slug}")
            sys.exit(1)
        n = sum(1 for it in m.get("items", []) if it["topic"] == slug)
        if n:
            print(f"[error] 主题下还有 {n} 个条目, 先 rm 条目再删主题")
            sys.exit(1)
        m["topics"] = [t for t in m["topics"] if t["slug"] != slug]
        save_manifest(m)
        print(f"[ok] 主题已删除: {slug}")
        return
    if find_topic(m, slug):
        print(f"[error] 主题 slug 已存在: {slug}")
        sys.exit(1)
    m["topics"].append({"slug": slug, "name": a.name,
                        "desc": a.desc or "", "order": a.order or len(m["topics"]) + 1})
    save_manifest(m)
    print(f"[ok] 主题已添加: {slug} | {a.name}")


def cmd_rm(a) -> None:
    m = load_manifest()
    it = find_item(m, a.slug)
    if it is None:
        print(f"[error] 条目不存在: {a.slug}")
        sys.exit(1)
    m["items"] = [x for x in m["items"] if x["slug"] != a.slug]
    save_manifest(m)
    if not a.keep_files:
        for d in (FILES / a.slug, PAGES / a.slug, KB / a.slug):
            if d.exists():
                shutil.rmtree(d)
        print(f"[rm] 已删除 files/pages/页面: {a.slug}")
    build_index(m)
    print(f"[ok] 已移除条目: {a.slug}")


def cmd_ls() -> None:
    m = load_manifest()
    print(f"主题 {len(m['topics'])} 个 / 条目 {len(m['items'])} 个")
    for it in m.get("items", []):
        t = find_topic(m, it["topic"])
        print(f"  {it['slug']:<32} [{TYPE_LABEL.get(it['type'], it['type']):>2}] "
              f"{(it.get('date') or ''):<10} {it['title']}")


def cmd_build() -> None:
    m = load_manifest()
    build_all(m)
    print("[ok] 全量重建完成(未重渲图片)")


def main():
    ap = argparse.ArgumentParser(description="知识库入库与页面生成")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("topic", help="主题管理")
    sp = p.add_subparsers(dest="topic_action", required=True)
    tp = sp.add_parser("add", help="添加主题")
    tp.add_argument("name", help="主题中文名")
    tp.add_argument("--slug", help="主题 slug(必填)")
    tp.add_argument("--desc", default="")
    tp.add_argument("--order", type=int)
    sp.add_parser("ls", help="列出主题")
    rp = sp.add_parser("rm", help="删除主题(要求该主题下无条目)")
    rp.add_argument("slug")

    p = sub.add_parser("add", help="入库一个文件或链接")
    p.add_argument("target", help="文件路径或 http(s) 链接")
    p.add_argument("--title", required=True, help="条目标题")
    p.add_argument("--topic", required=True, help="所属主题 slug")
    p.add_argument("--slug", help="条目 slug(必填, ASCII)")
    p.add_argument("--desc", default="", help="一句话描述")
    p.add_argument("--tags", default="", help="逗号分隔标签")
    p.add_argument("--date", help="日期 YYYY-MM-DD(默认今天)")
    p.add_argument("--dpi", type=int, help="渲染 DPI(默认按类型)")
    p.add_argument("--no-render", action="store_true", help="跳过渲染, 只存原文件")
    p.add_argument("--force", action="store_true", help="覆盖同名 slug / 放行 >50MB 文件")
    p.add_argument("--force-render", action="store_true", help="强制重渲(重新转换+渲染, 默认跳过已有页面)")

    p = sub.add_parser("rm", help="移除条目")
    p.add_argument("slug")
    p.add_argument("--keep-files", action="store_true", help="保留 files/pages 目录")

    sub.add_parser("ls", help="列出条目")
    sub.add_parser("build", help="从 manifest 全量重建页面")

    a = ap.parse_args()
    if a.cmd == "topic":
        cmd_topic(a)
    elif a.cmd == "add":
        cmd_add(a)
    elif a.cmd == "rm":
        cmd_rm(a)
    elif a.cmd == "ls":
        cmd_ls()
    elif a.cmd == "build":
        cmd_build()


if __name__ == "__main__":
    main()

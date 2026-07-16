# ToolDiagram.py
import os
import re
import html
import threading
import tkinter as tk
from tkinter import filedialog
import customtkinter as ctk
import graphviz
import pypdf

from Config import *


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def esc(s):
    if s is None:
        return "?"
    s = str(s)
    # Strip XML-invalid control characters (causes Graphviz parse errors)
    s = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', s)
    return html.escape(s)

def html_label(*lines):
    return "<" + "<br/>".join(lines) + ">"

def _resolve(obj):
    return obj.get_object() if hasattr(obj, "get_object") else obj

def _res_key(raw_value, fallback):
    """Return a stable graphviz node-ID for a resource object.
    If it's an indirect reference, two pages that point at the same
    object will get the same key and share one node in the diagram."""
    if isinstance(raw_value, pypdf.generic.IndirectObject):
        return f"res_{raw_value.idnum}_{raw_value.generation}"
    return fallback

def _get_dict_keys(res_obj, key):
    """Safely retrieve a sub-dict from a resource dict and return its keys."""
    if res_obj is None:
        return []
    raw = res_obj.get(key)
    if raw is None:
        return []
    d = _resolve(raw)
    return sorted(str(k) for k in d.keys()) if hasattr(d, "keys") else []

def _get_basefonts(res_obj):
    """Return up to 6 BaseFont names from the /Font sub-dict."""
    if res_obj is None:
        return []
    raw = res_obj.get("/Font")
    if raw is None:
        return []
    font_dict = _resolve(raw)
    if not hasattr(font_dict, "items"):
        return []
    names = []
    for _, fref in font_dict.items():
        fobj = _resolve(fref)
        if hasattr(fobj, "get"):
            bf = fobj.get("/BaseFont")
            if bf:
                names.append(str(bf).lstrip("/"))
    return sorted(set(names))[:6]

def _get_procset(res_obj):
    """Return ProcSet entries as a list of strings."""
    if res_obj is None:
        return []
    raw = res_obj.get("/ProcSet")
    if raw is None:
        return []
    arr = _resolve(raw)
    return sorted(str(v).lstrip("/") for v in arr) if hasattr(arr, "__iter__") else []


# ---------------------------------------------------------------------------
# INFO EXTRACTION  (pypdf for per-page accuracy; regex for trailer stats)
# ---------------------------------------------------------------------------

def extract_info(pdf_path, raw_data):
    reader = pypdf.PdfReader(pdf_path)
    info = {}

    # ── Trailer stats (regex – pypdf doesn't expose these directly) ─────────
    info["linearized"]       = b"/Linearized" in raw_data
    info["objstm_count"]     = len(re.findall(rb"/Type\s*/ObjStm", raw_data))
    info["xref_stream_count"]= len(re.findall(rb"/Type\s*/XRef",   raw_data))
    info["obj_count"]        = len(re.findall(rb"\d+\s+0\s+obj",   raw_data))

    # ── Metadata ────────────────────────────────────────────────────────────
    meta = reader.metadata or {}
    info["producer"]       = str(meta.get("/Producer",      "")) or None
    info["creation_date"]  = str(meta.get("/CreationDate",  "")) or None
    info["mod_date"]       = str(meta.get("/ModDate",       "")) or None

    # ── Document ID from trailer ─────────────────────────────────────────────
    id_entry = reader.trailer.get("/ID")
    if id_entry:
        try:
            parts = []
            for v in id_entry:
                val = _resolve(v)
                try:
                    parts.append(bytes(val).hex()[:8])
                except Exception:
                    s = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', str(val))
                    parts.append(s[:8])
            info["id_pair"] = tuple(parts[:2]) if len(parts) >= 2 else None
        except Exception:
            info["id_pair"] = None
    else:
        info["id_pair"] = None

    # ── Per-page info ────────────────────────────────────────────────────────
    info["page_count"] = len(reader.pages)
    pages = []
    for i, page in enumerate(reader.pages):
        pd = {"index": i}

        # MediaBox
        try:
            mb = page.mediabox
            pd["mediabox"] = (
                f"{float(mb.left):.4g}, {float(mb.bottom):.4g}, "
                f"{float(mb.right):.4g}, {float(mb.top):.4g}"
            )
        except Exception:
            pd["mediabox"] = None

        pd["has_cropbox"] = "/CropBox" in page
        pd["rotate"]      = str(page.get("/Rotate", 0))

        # Resources – use raw_get so we can detect shared indirect references
        try:
            raw_res = page.raw_get("/Resources")
        except (KeyError, AttributeError):
            raw_res = None

        if raw_res is not None:
            res_obj   = _resolve(raw_res)
            pd["res_key"] = _res_key(raw_res, fallback=f"res_page_{i}")
            pd["font_names"]     = _get_dict_keys(res_obj, "/Font")
            pd["basefonts"]      = _get_basefonts(res_obj)
            pd["extgstate_names"]= _get_dict_keys(res_obj, "/ExtGState")
            pd["procset"]        = _get_procset(res_obj)
            pd["xobject_names"]  = _get_dict_keys(res_obj, "/XObject")
        else:
            pd["res_key"]        = None
            pd["font_names"]     = []
            pd["basefonts"]      = []
            pd["extgstate_names"]= []
            pd["procset"]        = []
            pd["xobject_names"]  = []

        pages.append(pd)
    info["pages"] = pages

    # ── Catalog-level features ───────────────────────────────────────────────
    try:
        catalog = _resolve(reader.trailer["/Root"])
        info["has_structtreeroot"] = "/StructTreeRoot" in catalog
        info["has_markinfo"]       = "/MarkInfo"       in catalog
        info["has_metadata_xml"]   = "/Metadata"       in catalog
        info["has_viewerprefs"]    = "/ViewerPreferences" in catalog

        struct = catalog.get("/StructTreeRoot")
        if struct:
            s = _resolve(struct)
            info["has_rolemap"]    = "/RoleMap"    in s if hasattr(s, "__contains__") else False
            info["has_parenttree"] = "/ParentTree" in s if hasattr(s, "__contains__") else False
        else:
            info["has_rolemap"] = info["has_parenttree"] = False
    except Exception:
        for k in ("has_structtreeroot","has_markinfo","has_metadata_xml",
                  "has_viewerprefs","has_rolemap","has_parenttree"):
            info[k] = False

    return info


# ---------------------------------------------------------------------------
# DIAGRAM BUILDER  (all pages, shared-resource deduplication)
# ---------------------------------------------------------------------------

def build_diagram(info, title):
    g = graphviz.Digraph("PDF_Structure", format="svg")
    g.attr(
        rankdir="TB", bgcolor="white", fontname="Helvetica",
        label=esc(title), labelloc="t", fontsize="20",
        pad="0.6", nodesep="0.5", ranksep="0.7",
    )
    g.attr("node", fontname="Helvetica", fontsize="11")
    g.attr("edge", color="#666666", arrowsize="0.7")

    # ── Trailer ─────────────────────────────────────────────────────────────
    trailer_lines = [
        "<b>Trailer</b>",
        f"Linearized: {esc(info['linearized'])}",
        f"Producer: {esc(info['producer'])}",
        f"CreationDate: {esc(info['creation_date'])}",
        f"ModDate: {esc(info['mod_date'])}",
    ]
    if info["id_pair"]:
        a, b = info["id_pair"]
        changed = "MODIFIED" if a != b else "unchanged"
        trailer_lines.append(f"ID: {a}... / {b}... ({changed})")
    trailer_lines.append(
        f"Objects: {info['obj_count']} loose, "
        f"{info['objstm_count']} ObjStm, "
        f"{info['xref_stream_count']} XRef stream(s)"
    )
    g.node("trailer", html_label(*trailer_lines),
           shape="box", style="filled", fillcolor="#2b2b2b",
           fontcolor="white", color="#2b2b2b")

    # ── Catalog ──────────────────────────────────────────────────────────────
    g.node("catalog", html_label("<b>Catalog</b>", "/Type /Catalog"),
           shape="box", style="filled", fillcolor="#4a6fa5", fontcolor="white")
    g.edge("trailer", "catalog", label="/Root")

    # ── Pages ────────────────────────────────────────────────────────────────
    g.node("pages",
           html_label("<b>Pages</b>", f"/Count {esc(info['page_count'])}"),
           shape="box", style="filled", fillcolor="#6b8cae", fontcolor="white")
    g.edge("catalog", "pages", label="/Pages")

    # ── All pages (shared resources deduplicated by res_key) ─────────────────
    added_res = set()   # res_key values already added as graphviz nodes

    for pg in info["pages"]:
        i     = pg["index"]
        pg_id = f"page_{i + 1}"

        pg_lines = [f"<b>Page {i + 1}</b>"]
        if pg["mediabox"]:
            pg_lines.append(f"MediaBox: [{esc(pg['mediabox'])}]")
        if pg["has_cropbox"]:
            pg_lines.append("CropBox: True")
        if pg["rotate"] not in ("0", "None"):
            pg_lines.append(f"Rotate: {esc(pg['rotate'])}")

        g.node(pg_id, html_label(*pg_lines),
               shape="box", style="filled", fillcolor="#8fa8c4", fontcolor="white")
        g.edge("pages", pg_id, label=f"/Kids[{i}]")

        # Contents
        cont_id = f"contents_{i + 1}"
        g.node(cont_id,
               html_label("<b>Contents</b>", "(content stream)"),
               shape="component", style="filled", fillcolor="#d9d9d9")
        g.edge(pg_id, cont_id, label="/Contents")

        # Resources
        rk = pg["res_key"]
        if rk is None:
            continue

        # Edge from page → resource node (always needed, even for shared nodes)
        g.edge(pg_id, rk, label="/Resources")

        if rk in added_res:
            continue   # node already built; just the edge above is enough
        added_res.add(rk)

        g.node(rk, html_label("<b>Resources</b>"),
               shape="box", style="filled", fillcolor="#c9d6e3")

        # Font
        if pg["font_names"] or pg["basefonts"]:
            fid = f"{rk}_font"
            fl = ["<b>Font</b>"]
            if pg["font_names"]:
                keys_str = ", ".join(pg["font_names"][:10])
                if len(pg["font_names"]) > 10:
                    keys_str += f" … (+{len(pg['font_names']) - 10})"
                fl.append("Keys: " + esc(keys_str))
            for bf in pg["basefonts"]:
                fl.append(esc(bf))
            g.node(fid, html_label(*fl),
                   shape="note", style="filled", fillcolor="#f4e3b2")
            g.edge(rk, fid, label="/Font")

        # ExtGState
        if pg["extgstate_names"]:
            gsid = f"{rk}_gs"
            gs_str = ", ".join(pg["extgstate_names"][:10])
            if len(pg["extgstate_names"]) > 10:
                gs_str += f" … (+{len(pg['extgstate_names']) - 10})"
            g.node(gsid, html_label("<b>ExtGState</b>", esc(gs_str)),
                   shape="note", style="filled", fillcolor="#f4e3b2")
            g.edge(rk, gsid, label="/ExtGState")

        # ProcSet
        if pg["procset"]:
            psid = f"{rk}_ps"
            g.node(psid,
                   html_label("<b>ProcSet</b>", esc(", ".join(pg["procset"]))),
                   shape="note", style="filled", fillcolor="#f4e3b2")
            g.edge(rk, psid, label="/ProcSet")

        # XObject
        if pg["xobject_names"]:
            xoid = f"{rk}_xo"
            xo_str = ", ".join(pg["xobject_names"][:10])
            if len(pg["xobject_names"]) > 10:
                xo_str += f" … (+{len(pg['xobject_names']) - 10})"
            g.node(xoid, html_label("<b>XObject</b>", esc(xo_str)),
                   shape="note", style="filled", fillcolor="#f4e3b2")
            g.edge(rk, xoid, label="/XObject")

    # ── Catalog-level optional nodes ─────────────────────────────────────────
    if info["has_structtreeroot"]:
        g.node("structroot", html_label("<b>StructTreeRoot</b>"),
               shape="box", style="filled", fillcolor="#7fa876", fontcolor="white")
        g.edge("catalog", "structroot", label="/StructTreeRoot")
        if info["has_rolemap"]:
            g.node("rolemap", html_label("<b>RoleMap</b>"),
                   shape="ellipse", style="filled", fillcolor="#bcd9b3")
            g.edge("structroot", "rolemap", label="/RoleMap")
        if info["has_parenttree"]:
            g.node("parenttree", html_label("<b>ParentTree</b>"),
                   shape="ellipse", style="filled", fillcolor="#bcd9b3")
            g.edge("structroot", "parenttree", label="/ParentTree")

    if info["has_markinfo"]:
        g.node("markinfo", html_label("<b>MarkInfo</b>", "Marked: true"),
               shape="ellipse", style="filled", fillcolor="#e3c9c9")
        g.edge("catalog", "markinfo", label="/MarkInfo")

    if info["has_metadata_xml"]:
        g.node("metadata", html_label("<b>Metadata</b>", "(XMP/XML stream)"),
               shape="ellipse", style="filled", fillcolor="#e3c9c9")
        g.edge("catalog", "metadata", label="/Metadata")

    if info["has_viewerprefs"]:
        g.node("viewerprefs", html_label("<b>ViewerPreferences</b>"),
               shape="ellipse", style="filled", fillcolor="#e3c9c9")
        g.edge("catalog", "viewerprefs", label="/ViewerPreferences")

    return g


# ---------------------------------------------------------------------------
# PROCESSOR
# ---------------------------------------------------------------------------

def process_diagram(pdf_path, output_dir, update_log, update_progress, finish_job):
    try:
        base_name = os.path.splitext(os.path.basename(pdf_path))[0]
        update_log(f"Reading: {base_name}.pdf", ACCENT_BLUE)
        update_progress(0.1)

        with open(pdf_path, "rb") as f:
            raw_data = f.read()

        update_log("Parsing PDF structure with pypdf...", TEXT_MAIN)
        update_progress(0.3)
        info = extract_info(pdf_path, raw_data)

        update_log(f"Found {info['page_count']} page(s). Building diagram...", TEXT_MAIN)
        update_progress(0.6)
        graph = build_diagram(info, title=base_name)

        outpath = os.path.join(output_dir, f"{base_name}_diagram")
        update_log("Rendering SVG and PNG...", TEXT_MAIN)
        update_progress(0.85)

        try:
            graph.render(outpath, format="svg", cleanup=True)
        except graphviz.backend.ExecutableNotFound:
            update_progress(0.0)
            update_log("\nERROR: Graphviz binary not found.", ACCENT_RED)
            update_log("Install the Graphviz system package to render images.", TEXT_MAIN)
            finish_job(False)
            return

        update_progress(1.0)
        update_log(f"\nDIAGRAMS RENDERED  ({info['page_count']} pages mapped)", ACCENT_GREEN)
        update_log(f"Saved to: {output_dir}", TEXT_MAIN)
        finish_job(True)

    except Exception as e:
        update_progress(0.0)
        update_log(f"\nERROR: {str(e)}", ACCENT_RED)
        finish_job(False)


# ---------------------------------------------------------------------------
# UI MODULE
# ---------------------------------------------------------------------------

class StructureDiagramModule(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)

        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(pady=(20, 10), padx=20, fill="x")
        ctk.CTkLabel(
            header_frame, text="VISUAL STRUCTURE MAP",
            font=ctk.CTkFont(size=24, weight="bold"), text_color=ACCENT_TEAL
        ).pack(anchor="w")
        ctk.CTkLabel(
            header_frame,
            text="Generate a full-document flowchart of the PDF's internal architecture.",
            font=ctk.CTkFont(size=14), text_color="gray"
        ).pack(anchor="w")

        card_files = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=15)
        card_files.pack(pady=10, padx=20, fill="x")

        in_row = ctk.CTkFrame(card_files, fg_color="transparent")
        in_row.pack(fill="x", padx=20, pady=(20, 10))
        self.input_entry = ctk.CTkEntry(
            in_row, placeholder_text="Step 1: Choose a PDF file...",
            height=40, corner_radius=8, fg_color=BG_MAIN
        )
        self.input_entry.pack(side="left", fill="x", expand=True, padx=(0, 15))
        self.input_btn = ctk.CTkButton(
            in_row, text="Browse", width=100, height=40,
            fg_color=ACCENT_TEAL, text_color=BG_MAIN, font=ctk.CTkFont(weight="bold"),
            command=self.pick_pdf
        )
        self.input_btn.pack(side="right")

        out_row = ctk.CTkFrame(card_files, fg_color="transparent")
        out_row.pack(fill="x", padx=20, pady=(0, 20))
        self.output_entry = ctk.CTkEntry(
            out_row, placeholder_text="Step 2: Choose output folder for diagrams...",
            height=40, corner_radius=8, fg_color=BG_MAIN
        )
        self.output_entry.pack(side="left", fill="x", expand=True, padx=(0, 15))
        self.output_btn = ctk.CTkButton(
            out_row, text="Select Folder", width=120, height=40,
            fg_color="#2A3441", text_color=TEXT_MAIN,
            command=self.pick_save_spot
        )
        self.output_btn.pack(side="right")

        card_logs = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=15)
        card_logs.pack(pady=10, padx=20, fill="both", expand=True)
        card_logs.grid_columnconfigure(0, weight=1)
        card_logs.grid_rowconfigure(0, weight=1)

        self.log_box = ctk.CTkTextbox(
            card_logs, fg_color=BG_MAIN, text_color=TEXT_MAIN, corner_radius=8
        )
        self.log_box.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="nsew")
        for tag, color in [
            (TEXT_MAIN, TEXT_MAIN), (ACCENT_BLUE, ACCENT_BLUE),
            (ACCENT_GREEN, ACCENT_GREEN), (ACCENT_RED, ACCENT_RED),
            (ACCENT_TEAL, ACCENT_TEAL),
        ]:
            self.log_box._textbox.tag_config(tag, foreground=color)

        self.progress_bar = ctk.CTkProgressBar(
            card_logs, progress_color=ACCENT_TEAL, fg_color=BG_MAIN, height=12
        )
        self.progress_bar.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="ew")
        self.progress_bar.set(0)

        self.run_btn = ctk.CTkButton(
            self, text="RENDER DIAGRAM",
            font=ctk.CTkFont(size=18, weight="bold"), height=50, corner_radius=15,
            fg_color=ACCENT_TEAL, text_color=BG_MAIN,
            command=self.start_render
        )
        self.run_btn.pack(pady=(10, 20), padx=20, fill="x")
        self.write_log("Module loaded. Select a PDF to chart.", TEXT_MAIN)

    def write_log(self, text, color):
        self.log_box.configure(state="normal")
        self.log_box._textbox.insert("end", text + "\n", color)
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def pick_pdf(self):
        file_path = filedialog.askopenfilename(filetypes=[("PDF Files", "*.pdf")])
        if file_path:
            self.input_entry.delete(0, tk.END)
            self.input_entry.insert(0, file_path)
            self.output_entry.delete(0, tk.END)
            self.output_entry.insert(0, os.path.dirname(file_path))
            self.write_log(f"Loaded: {os.path.basename(file_path)}", ACCENT_TEAL)

    def pick_save_spot(self):
        folder_path = filedialog.askdirectory()
        if folder_path:
            self.output_entry.delete(0, tk.END)
            self.output_entry.insert(0, folder_path)

    def freeze_screen(self, lock):
        state = "disabled" if lock else "normal"
        self.input_btn.configure(state=state)
        self.output_btn.configure(state=state)
        self.run_btn.configure(state=state)

    def job_done(self, success):
        self.freeze_screen(False)
        if success:
            self.run_btn.configure(text="SUCCESS! RENDER ANOTHER?", fg_color=ACCENT_GREEN)
        else:
            self.run_btn.configure(text="FAILED. TRY AGAIN?", fg_color=ACCENT_RED)
        self.after(3000, lambda: self.run_btn.configure(text="RENDER DIAGRAM", fg_color=ACCENT_TEAL))

    def start_render(self):
        pdf, out_folder = self.input_entry.get().strip(), self.output_entry.get().strip()
        if not pdf or not out_folder:
            self.write_log("Pick a PDF and an output folder first.", ACCENT_RED)
            return
        self.freeze_screen(True)
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", tk.END)
        self.log_box.configure(state="disabled")
        threading.Thread(
            target=process_diagram,
            args=(pdf, out_folder, self.write_log, self.progress_bar.set, self.job_done),
            daemon=True
        ).start()

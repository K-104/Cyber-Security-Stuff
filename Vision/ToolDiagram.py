# ToolDiagram.py
import os
import re
import html
import threading
import tkinter as tk
from tkinter import filedialog
import customtkinter as ctk
import graphviz

# Import our shared configs
from Config import *

# --- BACKGROUND LOGIC ---
def read_bytes(path):
    with open(path, "rb") as f:
        return f.read()

def decode_pdf_string(raw_bytes):
    if raw_bytes[:2] == b"\xfe\xff":
        try:
            return raw_bytes[2:].decode("utf-16-be", errors="replace")
        except Exception:
            return raw_bytes.decode("latin-1", errors="replace")
    return raw_bytes.decode("latin-1", errors="replace")

def extract_tree_info(data):
    info = {}

    def find_date(tag):
        mm = re.search(tag + rb"\s*\(([^)]*)\)", data)
        return decode_pdf_string(mm.group(1)) if mm else None

    info["creation_date"] = find_date(rb"/CreationDate")
    info["mod_date"] = find_date(rb"/ModDate")

    prod_m = re.search(rb"/Producer\s*\(((?:[^()\\]|\\.)*)\)", data)
    info["producer"] = decode_pdf_string(prod_m.group(1)).strip() if prod_m else None

    id_m = re.search(rb"/ID\s*\[\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*\]", data)
    info["id_pair"] = (id_m.group(1).decode(), id_m.group(2).decode()) if id_m else None

    info["linearized"] = b"/Linearized" in data

    count_m = re.search(rb"/Type\s*/Pages[^>]*?/Count\s+(\d+)", data)
    info["page_count"] = count_m.group(1).decode() if count_m else "?"

    mb_m = re.search(rb"/MediaBox\s*\[\s*([\d.\-]+)\s+([\d.\-]+)\s+([\d.\-]+)\s+([\d.\-]+)\s*\]", data)
    info["mediabox"] = ", ".join(g.decode() for g in mb_m.groups()) if mb_m else None

    info["has_cropbox"] = b"/CropBox" in data
    rot_m = re.search(rb"/Rotate\s+(\d+)", data)
    info["rotate"] = rot_m.group(1).decode() if rot_m else None

    font_names = re.findall(rb"/(F\d+|TT\d+|C2_\d+|T1_\d+)\s+\d+\s+0\s+R", data)
    info["font_resource_names"] = sorted(set(n.decode() for n in font_names))

    basefonts = re.findall(rb"/BaseFont\s*/([^\s/>\]]+)", data)
    info["basefonts"] = sorted(set(b.decode("latin-1") for b in basefonts))

    gs_names = re.findall(rb"/(GS\d+)\s+\d+\s+0\s+R", data)
    if not gs_names:
        gs_names = re.findall(rb"/(GS\d+)\s*<<", data)
    info["extgstate_names"] = sorted(set(n.decode() for n in gs_names))

    m = re.search(rb"/ProcSet\s*\[([^\]]*)\]", data)
    if m:
        procs = re.findall(rb"/(\w+)", m.group(1))
        info["procset"] = sorted(set(p.decode() for p in procs))
    else:
        info["procset"] = []

    info["has_structtreeroot"] = b"/StructTreeRoot" in data
    info["has_rolemap"] = b"/RoleMap" in data
    info["has_parenttree"] = b"/ParentTree" in data
    info["has_markinfo"] = b"/MarkInfo" in data
    info["has_metadata_xml"] = b"/Type/Metadata" in data or b"/Type /Metadata" in data
    info["has_viewerprefs"] = b"/ViewerPreferences" in data

    info["objstm_count"] = len(re.findall(rb"/Type\s*/ObjStm", data))
    info["xref_stream_count"] = len(re.findall(rb"/Type\s*/XRef", data))
    info["obj_count"] = len(re.findall(rb"\d+\s+0\s+obj", data))

    return info

def esc(s):
    return html.escape(str(s)) if s is not None else "?"

def html_label(*lines):
    return "<" + "<br/>".join(lines) + ">"

def build_diagram(info, title):
    g = graphviz.Digraph("PDF_Structure", format="svg")
    g.attr(rankdir="TB", bgcolor="white", fontname="Helvetica", label=title, labelloc="t", fontsize="20", pad="0.4")
    g.attr("node", fontname="Helvetica", fontsize="11")
    g.attr("edge", color="#666666", arrowsize="0.7")

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
        trailer_lines.append(f"ID: {a[:8]}... / {b[:8]}... ({changed})")
    trailer_lines.append(f"Objects: {info['obj_count']} loose, {info['objstm_count']} ObjStm, {info['xref_stream_count']} XRef stream(s)")
    g.node("trailer", html_label(*trailer_lines), shape="box", style="filled", fillcolor="#2b2b2b", fontcolor="white", color="#2b2b2b")

    g.node("catalog", html_label("<b>Catalog</b>", "/Type /Catalog"), shape="box", style="filled", fillcolor="#4a6fa5", fontcolor="white")
    g.edge("trailer", "catalog", label="/Root")

    g.node("pages", html_label("<b>Pages</b>", f"/Count {esc(info['page_count'])}"), shape="box", style="filled", fillcolor="#6b8cae", fontcolor="white")
    g.edge("catalog", "pages", label="/Pages")

    page_lines = ["<b>Page 1</b>"]
    if info["mediabox"]: page_lines.append(f"MediaBox: [{esc(info['mediabox'])}]")
    page_lines.append(f"CropBox: {esc(info['has_cropbox'])}")
    page_lines.append(f"Rotate: {esc(info['rotate'])}")
    g.node("page", html_label(*page_lines), shape="box", style="filled", fillcolor="#8fa8c4", fontcolor="white")
    g.edge("pages", "page", label="/Kids[0]")

    g.node("resources", html_label("<b>Resources</b>"), shape="box", style="filled", fillcolor="#c9d6e3")
    g.edge("page", "resources", label="/Resources")

    font_lines = ["<b>Font</b>"]
    if info["font_resource_names"]: font_lines.append("Resources: " + esc(", ".join(info["font_resource_names"])))
    if info["basefonts"]:
        for bf in info["basefonts"][:4]: font_lines.append(esc(bf))
    g.node("font", html_label(*font_lines), shape="note", style="filled", fillcolor="#f4e3b2")
    g.edge("resources", "font", label="/Font")

    gs_lines = ["<b>ExtGState</b>"]
    if info["extgstate_names"]: gs_lines.append(esc(", ".join(info["extgstate_names"])))
    else: gs_lines.append("(inside compressed ObjStm)")
    g.node("extgstate", html_label(*gs_lines), shape="note", style="filled", fillcolor="#f4e3b2")
    g.edge("resources", "extgstate", label="/ExtGState")

    ps_lines = ["<b>ProcSet</b>", esc(", ".join(info["procset"]) or "-")]
    g.node("procset", html_label(*ps_lines), shape="note", style="filled", fillcolor="#f4e3b2")
    g.edge("resources", "procset", label="/ProcSet")

    g.node("contents", html_label("<b>Contents</b>", "(page content stream)"), shape="component", style="filled", fillcolor="#d9d9d9")
    g.edge("page", "contents", label="/Contents")

    if info["has_structtreeroot"]:
        g.node("structroot", html_label("<b>StructTreeRoot</b>"), shape="box", style="filled", fillcolor="#7fa876", fontcolor="white")
        g.edge("catalog", "structroot", label="/StructTreeRoot")
        if info["has_rolemap"]:
            g.node("rolemap", html_label("<b>RoleMap</b>"), shape="ellipse", style="filled", fillcolor="#bcd9b3")
            g.edge("structroot", "rolemap", label="/RoleMap")
        if info["has_parenttree"]:
            g.node("parenttree", html_label("<b>ParentTree</b>"), shape="ellipse", style="filled", fillcolor="#bcd9b3")
            g.edge("structroot", "parenttree", label="/ParentTree")

    if info["has_markinfo"]:
        g.node("markinfo", html_label("<b>MarkInfo</b>", "Marked: true"), shape="ellipse", style="filled", fillcolor="#e3c9c9")
        g.edge("catalog", "markinfo", label="/MarkInfo")
    if info["has_metadata_xml"]:
        g.node("metadata", html_label("<b>Metadata</b>", "(XMP/XML stream)"), shape="ellipse", style="filled", fillcolor="#e3c9c9")
        g.edge("catalog", "metadata", label="/Metadata")
    if info["has_viewerprefs"]:
        g.node("viewerprefs", html_label("<b>ViewerPreferences</b>"), shape="ellipse", style="filled", fillcolor="#e3c9c9")
        g.edge("catalog", "viewerprefs", label="/ViewerPreferences")

    return g

def process_diagram(pdf_path, output_dir, update_log, update_progress, finish_job):
    try:
        base_name = os.path.splitext(os.path.basename(pdf_path))[0]
        update_log(f"Reading raw bytes from: {base_name}.pdf", ACCENT_BLUE)
        update_progress(0.2)
        
        data = read_bytes(pdf_path)
        
        update_log("Applying regex heuristics to map tree structure...", TEXT_MAIN)
        update_progress(0.5)
        info = extract_tree_info(data)
        
        update_log("Generating Graphviz nodes and edges...", TEXT_MAIN)
        update_progress(0.7)
        graph = build_diagram(info, title=base_name)
        
        outpath = os.path.join(output_dir, f"{base_name}_diagram")
        
        update_log("Rendering SVG and PNG files...", TEXT_MAIN)
        update_progress(0.9)
        
        try:
            graph.render(outpath, format="svg", cleanup=True)
            graph.render(outpath, format="png", cleanup=True)
        except graphviz.backend.ExecutableNotFound:
            update_progress(0.0)
            update_log("\n❌ GRAPHVIZ NOT FOUND!", ACCENT_RED)
            update_log("You must install the Graphviz system binary on your computer to render images.", TEXT_MAIN)
            finish_job(False)
            return

        update_progress(1.0)
        update_log(f"\n🎉 DIAGRAMS RENDERED!", ACCENT_GREEN)
        update_log(f"Saved to: {output_dir}", TEXT_MAIN)
        finish_job(True)

    except Exception as e:
        update_progress(0.0)
        update_log(f"\n❌ ERROR: {str(e)}", ACCENT_RED)
        finish_job(False)

# --- THE UI MODULE ---
class StructureDiagramModule(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)

        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(pady=(20, 10), padx=20, fill="x")
        ctk.CTkLabel(header_frame, text="VISUAL STRUCTURE MAP", font=ctk.CTkFont(size=24, weight="bold"), text_color=ACCENT_TEAL).pack(anchor="w")
        ctk.CTkLabel(header_frame, text="Generate a high-level flowchart of the PDF's internal architecture.", font=ctk.CTkFont(size=14), text_color="gray").pack(anchor="w")

        card_files = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=15)
        card_files.pack(pady=10, padx=20, fill="x")
        
        in_row = ctk.CTkFrame(card_files, fg_color="transparent")
        in_row.pack(fill="x", padx=20, pady=(20, 10))
        self.input_entry = ctk.CTkEntry(in_row, placeholder_text="Step 1: Choose a PDF file...", height=40, corner_radius=8, fg_color=BG_MAIN)
        self.input_entry.pack(side="left", fill="x", expand=True, padx=(0, 15))
        self.input_btn = ctk.CTkButton(in_row, text="Browse", width=100, height=40, fg_color=ACCENT_TEAL, text_color=BG_MAIN, font=ctk.CTkFont(weight="bold"), command=self.pick_pdf)
        self.input_btn.pack(side="right")

        out_row = ctk.CTkFrame(card_files, fg_color="transparent")
        out_row.pack(fill="x", padx=20, pady=(0, 20))
        self.output_entry = ctk.CTkEntry(out_row, placeholder_text="Step 2: Choose output folder for images...", height=40, corner_radius=8, fg_color=BG_MAIN)
        self.output_entry.pack(side="left", fill="x", expand=True, padx=(0, 15))
        self.output_btn = ctk.CTkButton(out_row, text="Select Folder", width=100, height=40, fg_color="#2A3441", text_color=TEXT_MAIN, command=self.pick_save_spot)
        self.output_btn.pack(side="right")

        card_logs = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=15)
        card_logs.pack(pady=10, padx=20, fill="both", expand=True)
        card_logs.grid_columnconfigure(0, weight=1)
        card_logs.grid_rowconfigure(0, weight=1)

        self.log_box = ctk.CTkTextbox(card_logs, fg_color=BG_MAIN, text_color=TEXT_MAIN, corner_radius=8)
        self.log_box.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="nsew")
        self.log_box._textbox.tag_config(TEXT_MAIN, foreground=TEXT_MAIN)
        self.log_box._textbox.tag_config(ACCENT_BLUE, foreground=ACCENT_BLUE)
        self.log_box._textbox.tag_config(ACCENT_GREEN, foreground=ACCENT_GREEN)
        self.log_box._textbox.tag_config(ACCENT_RED, foreground=ACCENT_RED)

        self.progress_bar = ctk.CTkProgressBar(card_logs, progress_color=ACCENT_TEAL, fg_color=BG_MAIN, height=12)
        self.progress_bar.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="ew")
        self.progress_bar.set(0)

        self.run_btn = ctk.CTkButton(self, text="RENDER DIAGRAMS", font=ctk.CTkFont(size=18, weight="bold"), height=50, corner_radius=15, fg_color=ACCENT_TEAL, text_color=BG_MAIN, command=self.start_extraction)
        self.run_btn.pack(pady=(10, 20), padx=20, fill="x")
        self.write_log("Graphviz module loaded. Select a PDF to chart.", TEXT_MAIN)

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
            self.output_entry.insert(0, os.path.dirname(file_path))  # Default to the same folder as the PDF
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
        self.after(3000, lambda: self.run_btn.configure(text="RENDER DIAGRAMS", fg_color=ACCENT_TEAL))

    def start_extraction(self):
        pdf, out_folder = self.input_entry.get().strip(), self.output_entry.get().strip()

        if not pdf or not out_folder:
            self.write_log("You need to pick a PDF and an output folder.", ACCENT_RED)
            return

        self.freeze_screen(True)
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", tk.END) 
        self.log_box.configure(state="disabled")
        
        threading.Thread(target=process_diagram, args=(pdf, out_folder, self.write_log, self.progress_bar.set, self.job_done), daemon=True).start()
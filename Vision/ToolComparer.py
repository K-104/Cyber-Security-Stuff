# ToolComparer.py
import os
import re
import threading
import customtkinter as ctk
from tkinter import filedialog
import pypdf
from Config import *

# --- FORENSIC LOGIC ---
def read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def extract_profile(data):
    """Extracts byte-level optimization heuristics."""
    profile = {}
    profile["linearized"] = b"/Linearized" in data
    profile["obj_count"] = len(re.findall(rb"\d+\s+0\s+obj", data))
    profile["objstm_count"] = len(re.findall(rb"/Type\s*/ObjStm", data))
    profile["xref_stream_count"] = len(re.findall(rb"/Type\s*/XRef", data))
    font_names = re.findall(rb"/(F\d+|TT\d+|C2_\d+|T1_\d+)\s+\d+\s+0\s+R", data)
    profile["font_resource_names"] = sorted(set(n.decode() for n in font_names))
    return profile


def calculate_tree_stats(pdf_path):
    """Mathematically calculates structural topology of the PDF tree."""
    try:
        with open(pdf_path, "rb") as f:
            reader = pypdf.PdfReader(f)
            root = reader.trailer["/Root"]

            visited = set()
            node_count = 0
            leaf_count = 0
            broken_refs = 0
            max_depth = 0
            max_fanout = 0

            # Stack elements: (object, depth)
            stack = [(root, 0)]

            while stack:
                curr, depth = stack.pop()

                # Resolve + dedupe indirect refs BEFORE counting anything,
                # so shared objects (fonts, ExtGStates, etc.) are only
                # counted once no matter how many parents point to them.
                if isinstance(curr, pypdf.generic.IndirectObject):
                    ref = (curr.idnum, curr.generation)
                    if ref in visited:
                        continue
                    visited.add(ref)
                    try:
                        curr = curr.get_object()
                    except Exception:
                        broken_refs += 1
                        continue

                node_count += 1
                if depth > max_depth:
                    max_depth = depth

                if isinstance(curr, pypdf.generic.DictionaryObject):
                    # Exclude parent pointers to prevent backward traversal
                    keys = [k for k in curr.keys() if k not in ("/W", "/Parent", "/P")]
                    fanout = len(keys)
                    if fanout > max_fanout:
                        max_fanout = fanout
                    if fanout:
                        stack.extend((curr[k], depth + 1) for k in keys)
                    else:
                        leaf_count += 1

                elif isinstance(curr, pypdf.generic.ArrayObject):
                    fanout = len(curr)
                    if fanout > max_fanout:
                        max_fanout = fanout
                    if fanout:
                        stack.extend((item, depth + 1) for item in curr)
                    else:
                        leaf_count += 1

                else:
                    # Primitive/leaf (e.g., string, integer, boolean)
                    leaf_count += 1

            return {
                "node_count": node_count,
                "leaf_count": leaf_count,
                "max_depth": max_depth,
                "max_fanout": max_fanout,
                "broken_refs": broken_refs,
            }
    except Exception:
        return {
            "node_count": 0,
            "leaf_count": 0,
            "max_depth": 0,
            "max_fanout": 0,
            "broken_refs": 0,
        }


# --- TABLE RENDERING ---
def _fmt_row(label, left, right, w_label, w_col):
    return f"│ {label:<{w_label}} │ {left:<{w_col}} │ {right:<{w_col}} │"


def _section_row(title, w_label, w_col):
    return f"│ {title:<{w_label}} │ {'':<{w_col}} │ {'':<{w_col}} │"


def build_comparison_table(orig, mod, orig_stats, mod_stats):
    """Builds a clean, aligned box-drawing table comparing two PDF profiles."""
    rows = [
        ("section", "Topology"),
        ("data", "Total Nodes", orig_stats["node_count"], mod_stats["node_count"]),
        ("data", "Leaf Nodes", orig_stats["leaf_count"], mod_stats["leaf_count"]),
        ("data", "Max Depth", orig_stats["max_depth"], mod_stats["max_depth"]),
        ("data", "Max Fanout", orig_stats["max_fanout"], mod_stats["max_fanout"]),
        ("data", "Broken Refs", orig_stats["broken_refs"], mod_stats["broken_refs"]),
        ("section", "Byte Artifacts"),
        ("data", "Linearized", orig["linearized"], mod["linearized"]),
        ("data", "Loose Objects", orig["obj_count"], mod["obj_count"]),
        ("data", "Object Streams", orig["objstm_count"], mod["objstm_count"]),
        ("data", "XRef Streams", orig["xref_stream_count"], mod["xref_stream_count"]),
    ]

    # Section titles render as "[ Title ]", so pad their width for that wrapping
    label_widths = [
        len(r[1]) + 4 if r[0] == "section" else len(r[1])
        for r in rows
    ]
    w_label = max(len("METRIC"), *label_widths)
    w_col = max(len("ORIGINAL"), len("MODIFIED"),
                *(len(str(r[2])) for r in rows if r[0] == "data"),
                *(len(str(r[3])) for r in rows if r[0] == "data"))

    top = f"┌{'─' * (w_label + 2)}┬{'─' * (w_col + 2)}┬{'─' * (w_col + 2)}┐"
    header = _fmt_row("METRIC", "ORIGINAL", "MODIFIED", w_label, w_col)
    header_sep = f"├{'─' * (w_label + 2)}┼{'─' * (w_col + 2)}┼{'─' * (w_col + 2)}┤"
    bottom = f"└{'─' * (w_label + 2)}┴{'─' * (w_col + 2)}┴{'─' * (w_col + 2)}┘"

    lines = [top, header, header_sep]
    for row in rows:
        if row[0] == "section":
            lines.append(_section_row(f"[ {row[1]} ]", w_label, w_col))
            lines.append(header_sep)
        else:
            _, label, left, right = row
            lines.append(_fmt_row(label, str(left), str(right), w_label, w_col))
    lines.append(bottom)

    return "\n".join(lines)


def process_comparison(orig_path, mod_path, update_log, update_progress, finish_job):
    try:
        update_log("Extracting byte profiles...", ACCENT_BLUE)
        update_progress(0.2)
        orig_data = read_bytes(orig_path)
        mod_data = read_bytes(mod_path)

        # 1. Get Byte Profiles
        orig = extract_profile(orig_data)
        mod = extract_profile(mod_data)
        update_progress(0.4)

        # 2. Get Mathematical Tree Stats
        update_log("Calculating mathematical topology...", ACCENT_BLUE)
        orig_stats = calculate_tree_stats(orig_path)
        mod_stats = calculate_tree_stats(mod_path)
        update_progress(0.6)

        # --- GENERATE THE SIDE-BY-SIDE TABLE ---
        table = build_comparison_table(orig, mod, orig_stats, mod_stats)
        update_log("\n" + table + "\n", TEXT_MAIN)
        update_log("HEURISTIC ANALYSIS:", ACCENT_TEAL)

        # --- HEURISTIC SCORING ---
        score = 0
        max_score = 7

        if mod["linearized"] and not orig["linearized"]:
            update_log("[MATCH] Linearization found (Adobe Fast Web View).", ACCENT_GREEN)
            score += 3
        else:
            update_log("[-] Linearization status unchanged.", TEXT_MAIN)

        if mod["objstm_count"] > orig["objstm_count"]:
            update_log("[MATCH] Objects repacked into streams (Optimization).", ACCENT_GREEN)
            score += 2
        else:
            update_log("[-] No significant object repacking.", TEXT_MAIN)

        if mod["font_resource_names"] != orig["font_resource_names"]:
            update_log("[MATCH] Font resource naming style changed.", ACCENT_GREEN)
            score += 2
        else:
            update_log("[-] Font naming style consistent.", TEXT_MAIN)

        # Topology Anomaly Detection
        if mod_stats["max_depth"] > orig_stats["max_depth"] + 2:
            update_log("[ANOMALY] Max tree depth increased drastically. Possible payload injection.", ACCENT_RED)
        if mod_stats["max_fanout"] > orig_stats["max_fanout"] + 5:
            update_log("[ANOMALY] Node fanout increased abnormally. Structural tampering likely.", ACCENT_RED)
        if mod_stats["broken_refs"] > orig_stats["broken_refs"]:
            update_log("[ANOMALY] New unresolved object references detected. Possible corruption from editing.", ACCENT_RED)

        update_progress(1.0)
        pct = (score / max_score) * 100
        update_log(f"\nLikelihood of Adobe Edit: {pct:.1f}%", ACCENT_TEAL)
        finish_job(True)

    except Exception as e:
        update_progress(0.0)
        update_log(f"\n❌ ERROR: {str(e)}", ACCENT_RED)
        finish_job(False)


# --- THE UI MODULE ---
class ForensicTriageModule(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)

        header = ctk.CTkLabel(self, text="FORENSIC TRIAGE", font=ctk.CTkFont(size=24, weight="bold"), text_color=ACCENT_TEAL)
        header.pack(pady=20, padx=20, anchor="w")

        card = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=15)
        card.pack(pady=10, padx=20, fill="x")

        self.in_orig = ctk.CTkEntry(card, placeholder_text="Original PDF...", height=40, fg_color=BG_MAIN)
        self.in_orig.pack(fill="x", padx=20, pady=10)
        self.in_mod = ctk.CTkEntry(card, placeholder_text="Modified PDF...", height=40, fg_color=BG_MAIN)
        self.in_mod.pack(fill="x", padx=20, pady=10)

        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=10)
        ctk.CTkButton(btn_row, text="Browse Original", command=lambda: self.browse(self.in_orig)).pack(side="left", padx=5)
        ctk.CTkButton(btn_row, text="Browse Modified", command=lambda: self.browse(self.in_mod)).pack(side="left", padx=5)

        # Monospace font is required for the box-drawing table to line up correctly
        self.log_box = ctk.CTkTextbox(self, fg_color=BG_CARD, height=280, font=ctk.CTkFont(family="Consolas", size=13))
        self.log_box.pack(pady=10, padx=20, fill="both", expand=True)

        # --- IMPORTANT: Register the color tags ---
        self.log_box._textbox.tag_config(TEXT_MAIN, foreground=TEXT_MAIN)
        self.log_box._textbox.tag_config(ACCENT_BLUE, foreground=ACCENT_BLUE)
        self.log_box._textbox.tag_config(ACCENT_GREEN, foreground=ACCENT_GREEN)
        self.log_box._textbox.tag_config(ACCENT_RED, foreground=ACCENT_RED)
        self.log_box._textbox.tag_config(ACCENT_TEAL, foreground=ACCENT_TEAL)

        self.run_btn = ctk.CTkButton(self, text="COMPARE DOCUMENTS", height=50, fg_color=ACCENT_TEAL, text_color=BG_MAIN, command=self.start)
        self.run_btn.pack(pady=10, padx=20, fill="x")

    def browse(self, entry):
        path = filedialog.askopenfilename(filetypes=[("PDF", "*.pdf")])
        if path:
            entry.delete(0, "end")
            entry.insert(0, path)

    def log(self, text, color=TEXT_MAIN):
        self.log_box.configure(state="normal")
        # --- IMPORTANT: Use the color tag here ---
        self.log_box.insert("end", text + "\n", color)
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def start(self):
        self.run_btn.configure(state="disabled")
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")
        threading.Thread(
            target=process_comparison,
            args=(self.in_orig.get(), self.in_mod.get(), self.log, lambda x: None, self.done),
            daemon=True,
        ).start()

    def done(self, success):
        self.run_btn.configure(state="normal")
# ToolTree.py
import os
import threading
import tkinter as tk
from tkinter import filedialog
import customtkinter as ctk
import pypdf
from typing import Any, Optional, Set, Tuple, Dict

# Import our shared colors and dictionary (Updated to capital C)
from Config import *

MAX_DEPTH = 50


# --- BACKGROUND LOGIC ---
def object_description(obj: Any) -> str:
    return type(obj).__name__.replace("Object", "")


def _is_binary(obj: Any) -> bool:
    """
    Returns True for anything that should be displayed as hex rather than decoded text.
    ByteStringObject IS a bytes subclass, but calling str() on it decodes the raw
    bytes using the platform encoding and produces garbled output (e.g. '\ub299\ud4c3').
    Checking the class name catches that case regardless of MRO order.
    """
    return isinstance(obj, (bytes, bytearray)) or type(obj).__name__ == "ByteStringObject"


def _is_binary(obj) -> bool:
    """Returns True for any binary PDF object that should be shown as hex.
    ByteStringObject IS bytes but str() decodes raw bytes via platform encoding,
    producing garbled output. Checking class name guarantees hex regardless of MRO."""
    return isinstance(obj, (bytes, bytearray)) or type(obj).__name__ == "ByteStringObject"


def format_leaf_value(obj) -> str:
    """Binary objects are hex-encoded; everything else keeps its normal repr()."""
    if _is_binary(obj):
        return bytes(obj).hex()
    return repr(obj)


def format_metadata_value(value) -> str:
    """Same binary-safety as format_leaf_value, but unquoted for table cells."""
    if _is_binary(value):
        return bytes(value).hex()
    return str(value)


def write_line(output_file, prefix: str, connector: str, text: str, name: str = "") -> None:
    output_file.write(prefix + connector + text + "\n")


def draw_tree(
    obj: Any,
    output_file,
    name: str = "/Root",
    prefix: str = "",
    is_last: bool = True,
    visited: Optional[Set[Tuple[int, int]]] = None,
    depth: int = 0,
    stats: Optional[Dict[str, int]] = None,
) -> None:
    if visited is None:
        visited = set()
    if stats is None:
        stats = {"nodes": 0, "leaves": 0, "max_depth": 0}

    connector = "└── " if is_last else "├── "
    stats["nodes"] += 1
    if depth > stats["max_depth"]:
        stats["max_depth"] = depth

    if depth > MAX_DEPTH:
        write_line(output_file, prefix, connector, "... Maximum recursion depth reached", name)
        stats["leaves"] += 1
        return

    object_ref = ""
    if isinstance(obj, pypdf.generic.IndirectObject):
        object_ref = f"({obj.idnum},{obj.generation})"
        ref = (obj.idnum, obj.generation)
        if ref in visited:
            write_line(output_file, prefix, connector, f"{name} {object_ref} [Already Expanded]", name)
            stats["leaves"] += 1
            return
        visited.add(ref)
        try:
            obj = obj.get_object()
        except Exception as error:
            write_line(output_file, prefix, connector, f"{name} {object_ref} [ERROR: {error}]", name)
            stats["leaves"] += 1
            return

    obj_type = object_description(obj)

    if isinstance(obj, pypdf.generic.StreamObject):
        write_line(output_file, prefix, connector, f"{name} [{obj_type}] {object_ref}", name)
        new_prefix = prefix + ("    " if is_last else "│   ")
        stream_keys = [k for k in ("/Length", "/Subtype", "/Filter", "/Width", "/Height") if k in obj]
        for i, key in enumerate(stream_keys):
            is_last_key = i == len(stream_keys) - 1
            write_line(output_file, new_prefix, "└── " if is_last_key else "├── ", f"{key}: {format_leaf_value(obj[key])}", key)
        return

    if isinstance(obj, pypdf.generic.DictionaryObject):
        write_line(output_file, prefix, connector, f"{name} [{obj_type}] {object_ref}", name)
        new_prefix = prefix + ("    " if is_last else "│   ")
        # Sorted alphabetically so the same PDF always produces the same
        # tree ordering, regardless of how the objects happen to be laid
        # out on disk -- makes trees comparable across runs/files.
        items = sorted(
            ((k, v) for k, v in obj.items() if k not in ("/W", "/Parent")),
            key=lambda kv: kv[0],
        )
        if not items:
            stats["leaves"] += 1
        for i, (key, value) in enumerate(items):
            draw_tree(value, output_file, name=str(key), prefix=new_prefix, is_last=(i == len(items) - 1), visited=visited, depth=depth + 1, stats=stats)
        return

    if isinstance(obj, pypdf.generic.ArrayObject):
        write_line(output_file, prefix, connector, f"{name} [{obj_type}]", name)
        new_prefix = prefix + ("    " if is_last else "│   ")
        if len(obj) == 0:
            stats["leaves"] += 1
        for i, value in enumerate(obj):
            draw_tree(value, output_file, name=f"[{i}]", prefix=new_prefix, is_last=(i == len(obj) - 1), visited=visited, depth=depth + 1, stats=stats)
        return

    write_line(output_file, prefix, connector, f"{name}: {format_leaf_value(obj)} [{obj_type}]", name)
    stats["leaves"] += 1


# --- TABLE RENDERING ---
def _box_table(headers, rows, max_col_width=50):
    """Generic aligned box-drawing table renderer used by both tables below."""
    def clip(s, w):
        s = str(s)
        return s if len(s) <= w else s[: w - 3] + "..."

    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))
    widths = [min(w, max_col_width) for w in widths]

    def border(left, mid, right):
        return left + mid.join("─" * (w + 2) for w in widths) + right

    def line(cells):
        return "│ " + " │ ".join(f"{clip(c, w):<{w}}" for c, w in zip(cells, widths)) + " │"

    lines = [border("┌", "┬", "┐"), line(headers), border("├", "┼", "┤")]
    for row in rows:
        lines.append(line(row))
    lines.append(border("└", "┴", "┘"))
    return "\n".join(lines)


def build_metadata_table(reader) -> str:
    """Builds a sorted, aligned FIELD | VALUE | MEANING table from document metadata + the trailer /ID."""
    rows = []

    if reader.metadata:
        for key, value in reader.metadata.items():
            rows.append((str(key), format_metadata_value(value)))

    # The /ID pair lives in the trailer, not the Info dict, and is raw bytes --
    # surface it explicitly, hex-encoded, instead of leaving it out entirely.
    id_entry = reader.trailer.get("/ID")
    if id_entry:
        try:
            parts = []
            for v in id_entry:
                if isinstance(v, pypdf.generic.IndirectObject):
                    v = v.get_object()
                parts.append(format_metadata_value(v))
            rows.append(("/ID", " / ".join(parts)))
        except Exception:
            pass

    if not rows:
        return "No metadata found.\n"

    rows.sort(key=lambda r: r[0])
    rows_with_meaning = [(field, value, PDF_EXPLANATIONS.get(field, "-")) for field, value in rows]
    return _box_table(("FIELD", "VALUE", "MEANING"), rows_with_meaning)


def build_summary_table(stats: Dict[str, int], unique_objects: int) -> str:
    rows = [
        ("Nodes Mapped", stats["nodes"]),
        ("Leaf Nodes", stats["leaves"]),
        ("Max Depth", stats["max_depth"]),
        ("Unique Objects", unique_objects),
    ]
    return _box_table(("METRIC", "VALUE"), rows)


def process_tree(pdf_path, txt_path, update_log, update_progress, finish_job):
    try:
        update_log(f"Opening PDF: {pdf_path}", ACCENT_BLUE)
        update_progress(0.1)
        visited: Set[Tuple[int, int]] = set()
        stats: Dict[str, int] = {"nodes": 0, "leaves": 0, "max_depth": 0}

        with open(pdf_path, "rb") as pdf_file, open(txt_path, "w", encoding="utf-8") as out_file:
            reader = pypdf.PdfReader(pdf_file)

            update_log("Building metadata table...", TEXT_MAIN)
            update_progress(0.25)
            metadata_table = build_metadata_table(reader)

            out_file.write("=" * 80 + "\nPDF METADATA\n" + "=" * 80 + "\n\n")
            out_file.write(
                "This block contains the document's metadata — information embedded in the PDF\n"
                "about the file itself rather than its visual content. Fields such as /Author,\n"
                "/Creator, and /Producer reveal who wrote the document and which software saved\n"
                "it. The /ID field is a pair of raw hex fingerprints that uniquely identify this\n"
                "specific PDF instance; the first value is assigned when the file is created and\n"
                "the second is updated every time the file is resaved.\n\n"
            )
            out_file.write(metadata_table + "\n")
            update_log("\n" + metadata_table, TEXT_MAIN)

            update_log("Generating ASCII Object Tree (sorted)...", TEXT_MAIN)
            update_progress(0.5)

            out_file.write("\n" + "=" * 80 + "\nPDF OBJECT TREE\n" + "=" * 80 + "\n\n")
            out_file.write(
                "This block maps the internal object graph of the PDF, starting from the document\n"
                "root (/Root). Each indented node is a PDF object — dictionaries, arrays, streams,\n"
                "or primitive values — connected by the references that link them together. Reading\n"
                "top-to-bottom traces the document's structure: the catalog leads to the page tree\n"
                "(/Pages), each page carries its /Resources (fonts, images), and /Contents streams\n"
                "hold the actual drawing instructions. Objects marked [Already Expanded] are\n"
                "cross-references seen earlier in the tree and are not repeated to prevent loops.\n\n"
            )
            draw_tree(reader.trailer["/Root"], out_file, visited=visited, stats=stats)

            update_progress(0.8)
            summary_table = build_summary_table(stats, len(visited))
            out_file.write("\n" + "=" * 80 + "\nSUMMARY\n" + "=" * 80 + "\n\n")
            out_file.write(
                "This block provides a statistical overview of the object tree traversal above.\n"
                "Nodes Mapped is the total count of every object visited during the walk.\n"
                "Leaf Nodes are terminal values with no children — strings, numbers, booleans.\n"
                "Max Depth shows the deepest nesting level reached in the object graph.\n"
                "Unique Objects reflects how many distinct indirect references were resolved,\n"
                "giving a sense of the PDF's overall complexity.\n\n"
            )
            out_file.write(summary_table + "\n")
            update_log("\n" + summary_table, ACCENT_TEAL)

        update_progress(1.0)
        update_log(f"\n🎉 ALL DONE! Tree saved here:\n{txt_path}", ACCENT_GREEN)
        finish_job(True)
    except Exception as e:
        update_progress(0.0)
        update_log(f"\n❌ ERROR: {str(e)}", ACCENT_RED)
        finish_job(False)


# --- THE UI MODULE ---
class TreeGeneratorModule(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)

        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(pady=(20, 10), padx=20, fill="x")
        ctk.CTkLabel(header_frame, text="ASCII TREE GENERATOR", font=ctk.CTkFont(size=24, weight="bold"), text_color=ACCENT_TEAL).pack(anchor="w")
        ctk.CTkLabel(header_frame, text="Map your PDF into a highly readable text diagram.", font=ctk.CTkFont(size=14), text_color="gray").pack(anchor="w")

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
        self.output_entry = ctk.CTkEntry(out_row, placeholder_text="Step 2: Where should we save the TXT file?", height=40, corner_radius=8, fg_color=BG_MAIN)
        self.output_entry.pack(side="left", fill="x", expand=True, padx=(0, 15))
        self.output_btn = ctk.CTkButton(out_row, text="Save As", width=100, height=40, fg_color="#2A3441", text_color=TEXT_MAIN, command=self.pick_save_spot)
        self.output_btn.pack(side="right")

        card_logs = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=15)
        card_logs.pack(pady=10, padx=20, fill="both", expand=True)
        card_logs.grid_columnconfigure(0, weight=1)
        card_logs.grid_rowconfigure(0, weight=1)

        # Monospace font so the box-drawn tables actually line up
        self.log_box = ctk.CTkTextbox(card_logs, fg_color=BG_MAIN, text_color=TEXT_MAIN, corner_radius=8, font=ctk.CTkFont(family="Consolas", size=13))
        self.log_box.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="nsew")
        self.log_box._textbox.tag_config(TEXT_MAIN, foreground=TEXT_MAIN)
        self.log_box._textbox.tag_config(ACCENT_BLUE, foreground=ACCENT_BLUE)
        self.log_box._textbox.tag_config(ACCENT_GREEN, foreground=ACCENT_GREEN)
        self.log_box._textbox.tag_config(ACCENT_RED, foreground=ACCENT_RED)
        # ACCENT_TEAL was used by pick_pdf()'s "Loaded:" log line but was
        # never registered as a tag -- it silently rendered in the default
        # color instead of teal. Fixed here.
        self.log_box._textbox.tag_config(ACCENT_TEAL, foreground=ACCENT_TEAL)

        self.progress_bar = ctk.CTkProgressBar(card_logs, progress_color=ACCENT_TEAL, fg_color=BG_MAIN, height=12)
        self.progress_bar.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="ew")
        self.progress_bar.set(0)

        self.run_btn = ctk.CTkButton(self, text="GENERATE ASCII TREE", font=ctk.CTkFont(size=18, weight="bold"), height=50, corner_radius=15, fg_color=ACCENT_TEAL, text_color=BG_MAIN, command=self.start_reading)
        self.run_btn.pack(pady=(10, 20), padx=20, fill="x")
        self.write_log("Module loaded. Select a PDF to begin.", TEXT_MAIN)

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
            self.output_entry.insert(0, os.path.splitext(file_path)[0] + "_Tree.txt")
            self.write_log(f"Loaded: {os.path.basename(file_path)}", ACCENT_TEAL)

    def pick_save_spot(self):
        file_path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text Files", "*.txt")])
        if file_path:
            self.output_entry.delete(0, tk.END)
            self.output_entry.insert(0, file_path)

    def freeze_screen(self, lock):
        state = "disabled" if lock else "normal"
        self.input_btn.configure(state=state)
        self.output_btn.configure(state=state)
        self.run_btn.configure(state=state)

    def job_done(self, success):
        self.freeze_screen(False)
        if success:
            self.run_btn.configure(text="SUCCESS! RUN ANOTHER?", fg_color=ACCENT_GREEN)
        else:
            self.run_btn.configure(text="FAILED. TRY AGAIN?", fg_color=ACCENT_RED)
        self.after(3000, lambda: self.run_btn.configure(text="GENERATE ASCII TREE", fg_color=ACCENT_TEAL))

    def start_reading(self):
        pdf, txt_file = self.input_entry.get().strip(), self.output_entry.get().strip()
        if not pdf or not txt_file:
            self.write_log("You need to pick a PDF and a place to save it.", ACCENT_RED)
            return

        self.freeze_screen(True)
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", tk.END)
        self.log_box.configure(state="disabled")
        self.write_log("Building the ASCII Tree...", ACCENT_TEAL)

        threading.Thread(target=process_tree, args=(pdf, txt_file, self.write_log, self.progress_bar.set, self.job_done), daemon=True).start()
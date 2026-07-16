import threading
import customtkinter as ctk
from tkinter import filedialog
import pypdf
from Config import *

# --- FORENSIC LOGIC ---

def format_id_field(id_obj):
    """
    Forces ID fields (which are raw byte arrays in PDFs) 
    into clean, readable Hex strings, stripping pypdf wrappers.
    """
    if not id_obj: return "None"
    formatted = []
    for item in id_obj:
        # If it's an indirect object, resolve it
        val = item.get_object() if hasattr(item, 'get_object') else item
        # If it's bytes/bytestring, convert to hex. Otherwise, stringify.
        if isinstance(val, (bytes, bytearray)):
            formatted.append(val.hex())
        else:
            formatted.append(str(val))
    return " / ".join(formatted)

def get_tree_dict(obj, depth=0, max_depth=50):
    """Recursively converts PDF objects to dicts with a safety depth limit."""
    if depth > max_depth: return "<MAX_DEPTH_REACHED>"
    
    # Resolve indirect objects
    if hasattr(obj, 'get_object'):
        obj = obj.get_object()

    if isinstance(obj, pypdf.generic.DictionaryObject):
        return {str(k): get_tree_dict(v, depth + 1) for k, v in obj.items() if k not in ("/W", "/Parent")}
    if isinstance(obj, pypdf.generic.ArrayObject):
        return [get_tree_dict(v, depth + 1) for v in obj]
    return str(obj)

def get_metadata(reader):
    """Extracts metadata and formats IDs to be human-readable."""
    meta = reader.metadata or {}
    # Extract /ID and force format to clean Hex strings
    raw_id = reader.trailer.get("/ID", [])
    
    return {
        "/Creator": meta.get("/Creator", "Not Set"),
        "/Producer": meta.get("/Producer", "Not Set"),
        "/CreationDate": meta.get("/CreationDate", "Not Set"),
        "/ModDate": meta.get("/ModDate", "Not Set"),
        "/ID": format_id_field(raw_id)
    }

def compare_dicts(d1, d2):
    """Compares two dictionaries for structural changes."""
    diff = {}
    all_keys = set(d1.keys()) | set(d2.keys())
    for k in all_keys:
        if k not in d1: diff[k] = {"status": "added", "val": d2[k]}
        elif k not in d2: diff[k] = {"status": "removed", "val": d1[k]}
        elif d1[k] != d2[k]:
            if isinstance(d1[k], dict) and isinstance(d2[k], dict):
                diff[k] = {"status": "modified", "val": compare_dicts(d1[k], d2[k])}
            else:
                diff[k] = {"status": "modified", "old": d1[k], "new": d2[k]}
    return diff

def format_report(diff, indent=""):
    """Turns the difference dictionary into a human-readable text block."""
    report = ""
    for k, v in diff.items():
        if v["status"] == "modified":
            report += f"{indent}[MODIFIED] {k} | Old: {v.get('old', '...')} -> New: {v.get('new', '...')}\n"
            if isinstance(v.get("val"), dict): report += format_report(v["val"], indent + "    ")
        elif v["status"] == "added":
            report += f"{indent}[ADDED] {k}: {v.get('val')}\n"
        elif v["status"] == "removed":
            report += f"{indent}[REMOVED] {k}: {v.get('val')}\n"
    return report

# --- PROCESSOR ---

def process_comparison(orig_path, mod_path, update_log, finish_job):
    try:
        update_log("Analyzing PDF Documents...", ACCENT_BLUE)
        r1, r2 = pypdf.PdfReader(orig_path), pypdf.PdfReader(mod_path)
        
        # 1. Metadata Audit
        m1, m2 = get_metadata(r1), get_metadata(r2)
        meta_diff = compare_dicts(m1, m2)
        
        # 2. Structural Tree Audit
        t1, t2 = get_tree_dict(r1.trailer["/Root"]), get_tree_dict(r2.trailer["/Root"])
        tree_diff = compare_dicts(t1, t2)
        
        # 3. Compile Report
        report_text = f"--- FORENSIC AUDIT REPORT ---\n"
        report_text += f"File A: {orig_path}\nFile B: {mod_path}\n\n"
        
        report_text += "=== 1. METADATA & ID AUDIT ===\n"
        report_text += format_report(meta_diff) if meta_diff else "[-] No metadata differences found.\n"
        
        report_text += "\n=== 2. STRUCTURAL TREE AUDIT ===\n"
        report_text += format_report(tree_diff) if tree_diff else "[-] No structural differences found.\n"
        
        finish_job(True, report_text)
    except Exception as e:
        finish_job(False, str(e))

# --- UI MODULE ---

class ForensicComparerModule(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.report_text = ""
        
        ctk.CTkLabel(self, text="PDF FORENSIC AUDITOR", font=ctk.CTkFont(size=24, weight="bold"), text_color=ACCENT_TEAL).pack(pady=20, padx=20, anchor="w")
        
        card = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=15)
        card.pack(pady=10, padx=20, fill="x")
        
        self.in1 = ctk.CTkEntry(card, placeholder_text="Original PDF...", height=40, fg_color=BG_MAIN)
        self.in1.pack(fill="x", padx=20, pady=10)
        self.in2 = ctk.CTkEntry(card, placeholder_text="Modified PDF...", height=40, fg_color=BG_MAIN)
        self.in2.pack(fill="x", padx=20, pady=10)
        
        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=10)
        ctk.CTkButton(btn_row, text="Browse Original", command=lambda: self.browse_file(self.in1)).pack(side="left", padx=5)
        ctk.CTkButton(btn_row, text="Browse Modified", command=lambda: self.browse_file(self.in2)).pack(side="left", padx=5)

        self.log_box = ctk.CTkTextbox(self, fg_color=BG_CARD, height=300, font=ctk.CTkFont(family="Consolas", size=13))
        self.log_box.pack(pady=10, padx=20, fill="both", expand=True)
        
        # Color tags
        for tag, color in [("TEXT", TEXT_MAIN), ("BLUE", ACCENT_BLUE), ("GREEN", ACCENT_GREEN), ("RED", ACCENT_RED), ("TEAL", ACCENT_TEAL)]:
            self.log_box._textbox.tag_config(tag, foreground=color)

        action_row = ctk.CTkFrame(self, fg_color="transparent")
        action_row.pack(pady=10, padx=20, fill="x")
        
        self.run_btn = ctk.CTkButton(action_row, text="RUN AUDIT", height=50, fg_color=ACCENT_TEAL, text_color=BG_MAIN, command=self.start)
        self.run_btn.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        self.dl_btn = ctk.CTkButton(action_row, text="DOWNLOAD REPORT", height=50, fg_color="#34495e", state="disabled", command=self.download)
        self.dl_btn.pack(side="right", fill="x", expand=True, padx=(5, 0))

    def browse_file(self, entry):
        path = filedialog.askopenfilename(filetypes=[("PDF", "*.pdf")])
        if path: entry.delete(0, "end"); entry.insert(0, path)

    def log(self, text, color="TEXT"):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", text + "\n", color)
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def download(self):
        file = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text File", "*.txt")])
        if file:
            with open(file, "w", encoding="utf-8") as f:
                f.write(self.report_text)
            self.log(f"Report saved to: {file}", "GREEN")

    def start(self):
        self.run_btn.configure(state="disabled")
        self.dl_btn.configure(state="disabled")
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")
        self.log("Starting analysis...", "BLUE")
        threading.Thread(target=process_comparison, args=(self.in1.get(), self.in2.get(), self.log, self.done), daemon=True).start()
    
    def done(self, success, result):
        self.run_btn.configure(state="normal")
        if success:
            self.report_text = result
            self.dl_btn.configure(state="normal")
            self.log("\n✅ Audit complete.", "GREEN")
        else:
            self.log(f"\n❌ ERROR: {result}", "RED")
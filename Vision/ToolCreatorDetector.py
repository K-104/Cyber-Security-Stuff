# ToolCreatorDetector.py
import re
import os 
import threading
import customtkinter as ctk
from tkinter import filedialog
import pypdf
from Config import *

# --- FORENSIC LOGIC ---
def read_bytes(path):
    with open(path, "rb") as f:
        return f.read()

def process_detection(pdf_path, update_log, update_progress, finish_job):
    try:
        update_log(f"Analyzing: {os.path.basename(pdf_path)}", ACCENT_BLUE)
        update_progress(0.2)
        
        # 1. Standard Dictionary Metadata
        reader = pypdf.PdfReader(pdf_path)
        meta = reader.metadata or {}
        creator = meta.get("/Creator", "Unknown / Stripped")
        producer = meta.get("/Producer", "Unknown / Stripped")
        
        update_progress(0.5)
        
        # 2. Hidden XMP Streams & Byte Fingerprints
        raw_data = read_bytes(pdf_path)
        
        xmp_creator = re.search(rb"<xmp:CreatorTool>(.*?)</xmp:CreatorTool>", raw_data)
        xmp_producer = re.search(rb"<pdf:Producer>(.*?)</pdf:Producer>", raw_data)
        
        x_creator_str = xmp_creator.group(1).decode('utf-8', 'ignore') if xmp_creator else "Not found"
        x_producer_str = xmp_producer.group(1).decode('utf-8', 'ignore') if xmp_producer else "Not found"
        
        # Adobe Structural Markers
        is_linearized = b"/Linearized" in raw_data
        has_acrobat_namespace = b"xmlns:acrobat=" in raw_data
        
        update_progress(0.8)
        
        # --- GENERATE REPORT ---
        report = "\n" + "="*60 + "\n"
        report += f"{'CREATOR TOOL & PRODUCER ANALYSIS':^60}\n"
        report += "="*60 + "\n\n"
        
        update_log(report, ACCENT_TEAL)
        
        update_log("[ STANDARD DICTIONARY ]", ACCENT_BLUE)
        update_log(f"Authoring App (/Creator): {creator}", TEXT_MAIN)
        update_log(f"PDF Engine    (/Producer): {producer}\n", TEXT_MAIN)
        
        update_log("[ HIDDEN XMP METADATA ]", ACCENT_BLUE)
        update_log(f"XMP CreatorTool: {x_creator_str}", TEXT_MAIN)
        update_log(f"XMP Producer:    {x_producer_str}\n", TEXT_MAIN)
        
        update_log("[ FORENSIC CONCLUSION ]", ACCENT_TEAL)
        
        # Heuristic Evaluation
        producer_str = str(producer).lower()
        if "adobe" in producer_str or "acrobat" in producer_str:
            update_log("-> Explicit Match: Document explicitly declares Adobe as the generating engine.", ACCENT_GREEN)
        elif is_linearized or has_acrobat_namespace:
            update_log("-> SUSPICIOUS MODIFICATION DETECTED:", ACCENT_RED)
            update_log("   Standard metadata does not report Adobe, but structural Adobe fingerprints", ACCENT_RED)
            update_log("   (like Linearization or Acrobat namespaces) were found deep in the file bytes.", ACCENT_RED)
            update_log("   This document was likely re-saved or optimized by Adobe Acrobat post-creation.", ACCENT_RED)
        else:
            update_log("-> Consistent: No hidden Adobe fingerprints detected. Output matches the declared engine.", TEXT_MAIN)
            
        update_progress(1.0)
        update_log("\nAnalysis complete.", ACCENT_GREEN)
        finish_job(True)

    except Exception as e:
        update_progress(0.0)
        update_log(f"\n❌ ERROR: {str(e)}", ACCENT_RED)
        finish_job(False)


# --- THE UI MODULE ---
class CreatorDetectorModule(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)

        header = ctk.CTkLabel(self, text="CREATOR TOOL DETECTOR", font=ctk.CTkFont(size=24, weight="bold"), text_color=ACCENT_TEAL)
        header.pack(pady=20, padx=20, anchor="w")
        
        ctk.CTkLabel(self, text="Cross-reference standard metadata against hidden XMP streams and byte-level signatures.", font=ctk.CTkFont(size=14), text_color="gray").pack(padx=20, anchor="w", pady=(0, 10))

        card = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=15)
        card.pack(pady=10, padx=20, fill="x")

        self.input_entry = ctk.CTkEntry(card, placeholder_text="Choose a PDF file...", height=40, fg_color=BG_MAIN)
        self.input_entry.pack(side="left", fill="x", expand=True, padx=(20, 10), pady=20)
        
        self.input_btn = ctk.CTkButton(card, text="Browse", width=100, height=40, fg_color=ACCENT_TEAL, text_color=BG_MAIN, font=ctk.CTkFont(weight="bold"), command=self.browse)
        self.input_btn.pack(side="right", padx=(0, 20), pady=20)

        self.log_box = ctk.CTkTextbox(self, fg_color=BG_CARD, height=250)
        self.log_box.pack(pady=10, padx=20, fill="both", expand=True)
        
        # Register color tags
        self.log_box._textbox.tag_config(TEXT_MAIN, foreground=TEXT_MAIN)
        self.log_box._textbox.tag_config(ACCENT_BLUE, foreground=ACCENT_BLUE)
        self.log_box._textbox.tag_config(ACCENT_GREEN, foreground=ACCENT_GREEN)
        self.log_box._textbox.tag_config(ACCENT_RED, foreground=ACCENT_RED)
        self.log_box._textbox.tag_config(ACCENT_TEAL, foreground=ACCENT_TEAL)
        
        self.run_btn = ctk.CTkButton(self, text="DETECT CREATOR TOOL", height=50, fg_color=ACCENT_TEAL, text_color=BG_MAIN, font=ctk.CTkFont(size=18, weight="bold"), command=self.start)
        self.run_btn.pack(pady=10, padx=20, fill="x")

    def browse(self):
        path = filedialog.askopenfilename(filetypes=[("PDF Files", "*.pdf")])
        if path:
            self.input_entry.delete(0, "end")
            self.input_entry.insert(0, path)

    def log(self, text, color=TEXT_MAIN):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", text + "\n", color)
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def start(self):
        pdf_path = self.input_entry.get().strip()
        if not pdf_path:
            self.log("Please select a PDF file first.", ACCENT_RED)
            return
            
        self.run_btn.configure(state="disabled")
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")
        
        threading.Thread(target=process_detection, args=(pdf_path, self.log, lambda x: None, self.done), daemon=True).start()
    
    def done(self, success):
        self.run_btn.configure(state="normal")
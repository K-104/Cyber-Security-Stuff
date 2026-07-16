# ToolExtractor.py
import hashlib
import json
import os
import threading
import tkinter as tk
from datetime import datetime, timezone
from tkinter import filedialog

import customtkinter as ctk
import pypdf

from Config import *


# ---------------------------------------------------------------------------
# SNAPSHOT HELPERS
# These functions produce the exact same data the Forensics Auditor needs so
# it can load a forensic_snapshot.json directly instead of re-parsing the PDF.
# Keep in sync with the extraction logic in ToolDifference.py.
# ---------------------------------------------------------------------------

def _format_id_field(id_obj):
    """Converts the raw /ID byte arrays to clean hex strings."""
    if not id_obj:
        return "None"
    parts = []
    for item in id_obj:
        val = item.get_object() if hasattr(item, "get_object") else item
        if isinstance(val, (bytes, bytearray)) or type(val).__name__ == "ByteStringObject":
            parts.append(bytes(val).hex())
        else:
            parts.append(str(val))
    return " / ".join(parts)


def _get_tree_dict(obj, depth=0, max_depth=50):
    """Recursively converts a PDF object graph to a plain dict (mirrors ToolDifference)."""
    if depth > max_depth:
        return "<MAX_DEPTH_REACHED>"
    if hasattr(obj, "get_object"):
        obj = obj.get_object()
    if isinstance(obj, pypdf.generic.DictionaryObject):
        return {str(k): _get_tree_dict(v, depth + 1) for k, v in obj.items()
                if k not in ("/W", "/Parent")}
    if isinstance(obj, pypdf.generic.ArrayObject):
        return [_get_tree_dict(v, depth + 1) for v in obj]
    # Hex-encode binary values so JSON can serialise them
    if isinstance(obj, (bytes, bytearray)) or type(obj).__name__ == "ByteStringObject":
        return bytes(obj).hex()
    return str(obj)


def _get_metadata(reader):
    """Extracts the key metadata fields (mirrors ToolDifference.get_metadata)."""
    meta = reader.metadata or {}
    return {
        "/Creator":      str(meta.get("/Creator",      "Not Set")),
        "/Producer":     str(meta.get("/Producer",     "Not Set")),
        "/CreationDate": str(meta.get("/CreationDate", "Not Set")),
        "/ModDate":      str(meta.get("/ModDate",      "Not Set")),
        "/ID":           _format_id_field(reader.trailer.get("/ID", [])),
    }


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# EXTRACTION LOGIC
# ---------------------------------------------------------------------------

def process_extraction(pdf_path, output_dir, update_log, update_progress, finish_job):
    try:
        update_log(f"Opening: {os.path.basename(pdf_path)}", ACCENT_BLUE)
        update_progress(0.05)

        # Sub-folder for images keeps the root folder clean
        images_dir = os.path.join(output_dir, "images")
        os.makedirs(images_dir, exist_ok=True)

        # Hash the source file before opening so we capture the unmodified bytes
        update_log("Hashing source file...", TEXT_MAIN)
        source_hash = _sha256(pdf_path)
        update_progress(0.1)

        with open(pdf_path, "rb") as file:
            reader = pypdf.PdfReader(file)

            if reader.is_encrypted:
                update_log("Document is password-protected — extraction may be incomplete.", ACCENT_RED)

            num_pages = len(reader.pages)
            update_log(f"Found {num_pages} page(s). Extracting text and images...", TEXT_MAIN)

            full_text = ""
            image_paths = []

            for i, page in enumerate(reader.pages):
                # Text
                text = page.extract_text()
                if text:
                    full_text += f"\n{'='*40}\nPAGE {i+1}\n{'='*40}\n{text}\n"

                # Images → images/ subfolder
                for img_idx, image_file_object in enumerate(page.images):
                    safe_name = f"Page_{i+1}_{image_file_object.name}"
                    image_path = os.path.join(images_dir, safe_name)
                    with open(image_path, "wb") as img_out:
                        img_out.write(image_file_object.data)
                    image_paths.append(os.path.join("images", safe_name))

                update_progress(0.1 + 0.55 * ((i + 1) / num_pages))

            # ---- Extracted_Text.txt ----------------------------------------
            update_log("Saving extracted text...", TEXT_MAIN)
            text_out_path = os.path.join(output_dir, "Extracted_Text.txt")
            with open(text_out_path, "w", encoding="utf-8") as text_file:
                if full_text.strip():
                    text_file.write(full_text)
                else:
                    text_file.write(
                        "No readable text found.\n"
                        "This PDF may consist entirely of scanned images."
                    )
            update_progress(0.70)

            # ---- forensic_snapshot.json ------------------------------------
            update_log("Building forensic snapshot...", TEXT_MAIN)
            snapshot = {
                "snapshot_version": "1.0",
                "source_file":      os.path.basename(pdf_path),
                "source_sha256":    source_hash,
                "extracted_at":     datetime.now(timezone.utc).isoformat(),
                "page_count":       num_pages,
                "image_count":      len(image_paths),
                "images":           image_paths,
                "metadata":         _get_metadata(reader),
                "object_tree":      _get_tree_dict(reader.trailer["/Root"]),
            }
            snapshot_path = os.path.join(output_dir, "forensic_snapshot.json")
            with open(snapshot_path, "w", encoding="utf-8") as snap_file:
                json.dump(snapshot, snap_file, indent=2, ensure_ascii=False)
            update_progress(0.90)

            # ---- manifest.txt ----------------------------------------------
            manifest_lines = [
                "EXTRACTION MANIFEST",
                "=" * 40,
                f"Source file : {os.path.basename(pdf_path)}",
                f"SHA-256     : {source_hash}",
                f"Extracted at: {snapshot['extracted_at']}",
                f"Pages       : {num_pages}",
                f"Images found: {len(image_paths)}",
                "",
                "FILES IN THIS FOLDER",
                "-" * 40,
                "  Extracted_Text.txt      — full page text",
                "  forensic_snapshot.json  — machine-readable snapshot for the Forensics Auditor",
                "  images/                 — extracted image files",
            ]
            for img in image_paths:
                manifest_lines.append(f"    {img}")
            with open(os.path.join(output_dir, "manifest.txt"), "w", encoding="utf-8") as mf:
                mf.write("\n".join(manifest_lines) + "\n")

        update_progress(1.0)
        update_log(f"\nEXTRACTION COMPLETE", ACCENT_GREEN)
        update_log(f"Pages       : {num_pages}", TEXT_MAIN)
        update_log(f"Images      : {len(image_paths)}", TEXT_MAIN)
        update_log(f"SHA-256     : {source_hash[:16]}...", TEXT_MAIN)
        update_log(f"Snapshot    : forensic_snapshot.json", ACCENT_TEAL)
        update_log(f"Folder ready for Forensics Auditor comparison.", ACCENT_TEAL)
        finish_job(True)

    except Exception as e:
        update_progress(0.0)
        update_log(f"\nERROR: {str(e)}", ACCENT_RED)
        finish_job(False)


# ---------------------------------------------------------------------------
# UI MODULE
# ---------------------------------------------------------------------------

class DataExtractorModule(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)

        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(pady=(20, 10), padx=20, fill="x")
        ctk.CTkLabel(
            header_frame, text="DATA EXTRACTOR",
            font=ctk.CTkFont(size=24, weight="bold"), text_color=ACCENT_TEAL
        ).pack(anchor="w")
        ctk.CTkLabel(
            header_frame,
            text="Extracts text, images, and a forensic snapshot ready for the Auditor.",
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
            out_row, placeholder_text="Step 2: Choose a folder to save the extraction...",
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
            self, text="EXTRACT DATA",
            font=ctk.CTkFont(size=18, weight="bold"), height=50, corner_radius=15,
            fg_color=ACCENT_TEAL, text_color=BG_MAIN,
            command=self.start_extraction
        )
        self.run_btn.pack(pady=(10, 20), padx=20, fill="x")
        self.write_log("Extractor loaded. Select a PDF and an output folder.", TEXT_MAIN)

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
            base_dir = os.path.dirname(file_path)
            pdf_name = os.path.splitext(os.path.basename(file_path))[0]
            self.output_entry.delete(0, tk.END)
            self.output_entry.insert(0, os.path.join(base_dir, f"{pdf_name}_Extracted"))
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
            self.run_btn.configure(text="SUCCESS! RUN ANOTHER?", fg_color=ACCENT_GREEN)
        else:
            self.run_btn.configure(text="FAILED. TRY AGAIN?", fg_color=ACCENT_RED)
        self.after(3000, lambda: self.run_btn.configure(text="EXTRACT DATA", fg_color=ACCENT_TEAL))

    def start_extraction(self):
        pdf = self.input_entry.get().strip()
        out_folder = self.output_entry.get().strip()

        if not pdf or not out_folder:
            self.write_log("Pick a PDF and an output folder first.", ACCENT_RED)
            return

        if not os.path.exists(out_folder):
            try:
                os.makedirs(out_folder)
            except Exception as e:
                self.write_log(f"Could not create folder: {str(e)}", ACCENT_RED)
                return

        self.freeze_screen(True)
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", tk.END)
        self.log_box.configure(state="disabled")
        self.write_log(f"Extracting to: {out_folder}", ACCENT_TEAL)

        threading.Thread(
            target=process_extraction,
            args=(pdf, out_folder, self.write_log, self.progress_bar.set, self.job_done),
            daemon=True
        ).start()

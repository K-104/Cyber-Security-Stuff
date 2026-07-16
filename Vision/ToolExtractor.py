# ToolExtractor.py
import os
import threading
import tkinter as tk
from tkinter import filedialog
import customtkinter as ctk
import pypdf

# Import our shared colors
from Config import *

# --- BACKGROUND LOGIC ---
def process_extraction(pdf_path, output_dir, update_log, update_progress, finish_job):
    try:
        update_log(f"Opening PDF: {os.path.basename(pdf_path)}", ACCENT_BLUE)
        update_progress(0.1)

        with open(pdf_path, "rb") as file:
            reader = pypdf.PdfReader(file)
            
            if reader.is_encrypted:
                update_log("Document is password protected. Extraction may fail.", ACCENT_RED)

            num_pages = len(reader.pages)
            full_text = ""
            image_count = 0

            update_log(f"Found {num_pages} pages. Starting extraction...", TEXT_MAIN)
            
            for i, page in enumerate(reader.pages):
                # 1. Extract Text
                text = page.extract_text()
                if text:
                    full_text += f"\n{'='*40}\nPAGE {i+1}\n{'='*40}\n{text}\n"

                # 2. Extract Images
                # pypdf's page.images returns a list of ImageFile objects
                for img_idx, image_file_object in enumerate(page.images):
                    # Clean up the name and add the page number so we know where it came from
                    safe_name = f"Page_{i+1}_{image_file_object.name}"
                    image_path = os.path.join(output_dir, safe_name)
                    
                    with open(image_path, "wb") as img_out:
                        img_out.write(image_file_object.data)
                    image_count += 1

                # Update progress bar (scales from 10% to 90%)
                progress = 0.1 + (0.8 * ((i + 1) / num_pages))
                update_progress(progress)

            # 3. Save the master text file
            update_log("Compiling extracted text...", TEXT_MAIN)
            text_out_path = os.path.join(output_dir, "Extracted_Text.txt")
            with open(text_out_path, "w", encoding="utf-8") as text_file:
                if full_text.strip():
                    text_file.write(full_text)
                else:
                    text_file.write("No readable text found. This PDF might be entirely scanned images.")

        update_progress(1.0)
        update_log(f"\n🎉 EXTRACTION COMPLETE!", ACCENT_GREEN)
        update_log(f"Text saved to: Extracted_Text.txt", TEXT_MAIN)
        update_log(f"Images recovered: {image_count}", ACCENT_TEAL)
        finish_job(True)

    except Exception as e:
        update_progress(0.0)
        update_log(f"\n❌ ERROR: {str(e)}", ACCENT_RED)
        finish_job(False)


# --- THE UI MODULE ---
class DataExtractorModule(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)

        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(pady=(20, 10), padx=20, fill="x")
        ctk.CTkLabel(header_frame, text="DATA EXTRACTOR", font=ctk.CTkFont(size=24, weight="bold"), text_color=ACCENT_TEAL).pack(anchor="w")
        ctk.CTkLabel(header_frame, text="Rip text and images out of a PDF and save them to a folder.", font=ctk.CTkFont(size=14), text_color="gray").pack(anchor="w")

        card_files = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=15)
        card_files.pack(pady=10, padx=20, fill="x")
        
        # Input PDF
        in_row = ctk.CTkFrame(card_files, fg_color="transparent")
        in_row.pack(fill="x", padx=20, pady=(20, 10))
        self.input_entry = ctk.CTkEntry(in_row, placeholder_text="Step 1: Choose a PDF file...", height=40, corner_radius=8, fg_color=BG_MAIN)
        self.input_entry.pack(side="left", fill="x", expand=True, padx=(0, 15))
        self.input_btn = ctk.CTkButton(in_row, text="Browse", width=100, height=40, fg_color=ACCENT_TEAL, text_color=BG_MAIN, font=ctk.CTkFont(weight="bold"), command=self.pick_pdf)
        self.input_btn.pack(side="right")

        # Output Folder (Note the change from file to folder)
        out_row = ctk.CTkFrame(card_files, fg_color="transparent")
        out_row.pack(fill="x", padx=20, pady=(0, 20))
        self.output_entry = ctk.CTkEntry(out_row, placeholder_text="Step 2: Choose a folder to dump the files...", height=40, corner_radius=8, fg_color=BG_MAIN)
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

        self.run_btn = ctk.CTkButton(self, text="EXTRACT DATA", font=ctk.CTkFont(size=18, weight="bold"), height=50, corner_radius=15, fg_color=ACCENT_TEAL, text_color=BG_MAIN, command=self.start_extraction)
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
            
            # Auto-suggest a folder named after the PDF in the same directory
            base_dir = os.path.dirname(file_path)
            pdf_name = os.path.splitext(os.path.basename(file_path))[0]
            suggested_folder = os.path.join(base_dir, f"{pdf_name}_Extracted")
            
            self.output_entry.delete(0, tk.END)
            self.output_entry.insert(0, suggested_folder)
            self.write_log(f"Loaded: {os.path.basename(file_path)}", ACCENT_TEAL)

    def pick_save_spot(self):
        # We ask for a Directory here, not a File
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
            self.write_log("You need to pick a PDF and an output folder.", ACCENT_RED)
            return

        # Create the folder if it doesn't exist yet
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
        self.write_log(f"Extracting data to: {out_folder}", ACCENT_TEAL)

        threading.Thread(target=process_extraction, args=(pdf, out_folder, self.write_log, self.progress_bar.set, self.job_done), daemon=True).start()
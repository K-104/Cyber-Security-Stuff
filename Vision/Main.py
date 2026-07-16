# Main.py
import customtkinter as ctk

from Config import *
from ToolTree import TreeGeneratorModule
from ToolDiagram import StructureDiagramModule
from ToolComparer import ForensicTriageModule
from ToolDifference import ForensicComparerModule
from ToolCreatorDetector import CreatorDetectorModule
from ToolExtractor import DataExtractorModule
from ToolPlaceholders import PlaceholderModule
ctk.set_appearance_mode("dark")

# --- TOOL REGISTRY ---

# To add a new tool: add one entry here. No other code needs to change.
TOOLS = [
    {"id": "tree",     "label": "ASCII Tree Generator",         "cls": TreeGeneratorModule},
    {"id": "diagram",  "label": "Visual Structure Map",         "cls": StructureDiagramModule},
    {"id": "compare",  "label": "Structural Triage (Compare)",  "cls": PlaceholderModule},
    {"id": "diff",     "label": "Forensics Auditor",            "cls": PlaceholderModule},
    {"id": "creator",  "label": "Creator Detector",             "cls": CreatorDetectorModule},
    {"id": "extract",  "label": "Data Extractor",                "cls": DataExtractorModule},
]


class UltimatePDFSuite(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("PDF Forensic Suite")
        self.geometry("1000x750")
        self.configure(fg_color=BG_MAIN)

        # Configure columns: Sidebar (col 0) and Main Content (col 1)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # --- SIDEBAR ---
        self.sidebar = ctk.CTkFrame(self, fg_color=BG_SIDEBAR, corner_radius=0, width=220)
        self.sidebar.grid(row=0, column=0, sticky="nsew")

        # Title
        ctk.CTkLabel(self.sidebar, text="PDF SUITE", font=ctk.CTkFont(size=22, weight="bold"), text_color="white").pack(pady=(30, 30), padx=20)

        # --- BUILD BUTTONS + MODULES FROM THE REGISTRY ---
        # buttons and modules are both keyed by the same plain-string tool id,
        # so there's exactly one place (TOOLS) that ever needs editing.
        self.buttons = {}
        self.modules = {}

        for tool in TOOLS:
            tool_id = tool["id"]

            btn = ctk.CTkButton(
                self.sidebar,
                text=tool["label"],
                anchor="w",
                fg_color="transparent",
                hover_color=BG_CARD,
                command=lambda tid=tool_id: self.show_module(tid),
            )
            btn.pack(fill="x", padx=10, pady=5)
            self.buttons[tool_id] = btn

            self.modules[tool_id] = tool["cls"](self)
            # --- THE FIX ---
            if tool["cls"] == PlaceholderModule:
                self.modules[tool_id] = tool["cls"](self, title=tool["label"])
            else:
                self.modules[tool_id] = tool["cls"](self)

        # Version label pushed to bottom
        ctk.CTkLabel(self.sidebar, text="v1.0 Alpha", text_color="gray").pack(side="bottom", pady=20)

        # Select the first module by default
        self.show_module(TOOLS[0]["id"])

    def show_module(self, module_id):
        """Hides all modules and shows the selected one, by plain-string id."""
        if module_id not in self.modules:
            raise ValueError(f"Unknown tool id: {module_id!r}")

        # Reset all button colors, then highlight only the active one
        for tid, btn in self.buttons.items():
            btn.configure(fg_color=BG_CARD if tid == module_id else "transparent")

        # Hide all frames, then show the requested one
        for frame in self.modules.values():
            frame.grid_forget()
        self.modules[module_id].grid(row=0, column=1, sticky="nsew")


if __name__ == "__main__":
    app = UltimatePDFSuite()
    app.mainloop()
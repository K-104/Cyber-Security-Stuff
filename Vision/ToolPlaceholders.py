# ToolPlaceholders.py
import customtkinter as ctk

# Import our shared configs 
from Config import *

class PlaceholderModule(ctk.CTkFrame):
    def __init__(self, master, title, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        
        ctk.CTkLabel(self, text=title, font=ctk.CTkFont(size=24, weight="bold"), text_color=ACCENT_TEAL).pack(pady=40)
        ctk.CTkLabel(self, text="This tool is currently under construction.", text_color="gray").pack()
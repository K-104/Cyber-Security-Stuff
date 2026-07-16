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


def format_leaf_value(obj: Any) -> str:
    """
    Renders a leaf value for display. Binary objects (ByteStringObject, bytes,
    bytearray) are hex-encoded. Everything else keeps its normal repr().
    """
    if _is_binary(obj):
        return bytes(obj).hex()
    return repr(obj)


def format_metadata_value(value: Any) -> str:
    """Same binary-safety as format_leaf_value, but unquoted for table cells."""
    if _is_binary(value):
        return bytes(value).hex()
    return str(value)


def write_line(output_file, prefix: str, connector: str, text: str, name: str = "") -> None:
    output_file.write(f"{prefix}{connector}{text}\n"))
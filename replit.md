# PDF Forensic Suite

A desktop GUI application for analyzing and inspecting PDF file internals, built with Python and customtkinter.

## How to run

The app starts automatically via the **Start application** workflow (`bash run.sh`), which runs `Vision/Main.py` with a VNC virtual display.

Switch the preview pane to **VNC** to see and interact with the GUI.

## Stack

- **Python 3.12**
- **customtkinter** — dark-themed GUI framework
- **pypdf** — PDF parsing
- **graphviz** — diagram/tree rendering

## Tools

| Tool | Status | Description |
|------|--------|-------------|
| ASCII Tree Generator | ✅ | Renders the PDF object tree as ASCII |
| Visual Structure Map | ✅ | Graphviz diagram of PDF structure |
| Creator Detector | ✅ | Identifies the software that created the PDF |
| Data Extractor | ✅ | Extracts embedded data from PDFs |
| Structural Triage | 🚧 Placeholder | Not yet implemented |
| Forensics Auditor | 🚧 Placeholder | Not yet implemented |

## Project structure

```
Vision/
  Main.py          # App entry point & tool registry
  Config.py        # Color palette & PDF key dictionary
  ToolTree.py      # ASCII Tree Generator
  ToolDiagram.py   # Visual Structure Map
  ToolComparer.py  # Structural Triage (unused — placeholder)
  ToolDifference.py# Forensics Auditor (unused — placeholder)
  ToolCreatorDetector.py
  ToolExtractor.py
  ToolPlaceholders.py
run.sh             # Workflow entry point
```

## User preferences

_No preferences recorded yet._

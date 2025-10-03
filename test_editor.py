import tkinter as tk
from tkinter import simpledialog, messagebox
from pathlib import Path

class TestEditorDialog(simpledialog.Dialog):
    def __init__(self, parent, test_dir: Path):
        self.test_dir = test_dir
        super().__init__(parent, title="New/Edit Test")

    def body(self, master):
        tk.Label(master, text="Test Filename:").grid(row=0, column=0, sticky="w")
        self.filename_entry = tk.Entry(master, width=40)
        self.filename_entry.grid(row=0, column=1, padx=6, pady=4)

        tk.Label(master, text="Prompt:").grid(row=1, column=0, sticky="nw")
        self.prompt_text = tk.Text(master, width=60, height=10)
        self.prompt_text.grid(row=1, column=1, padx=6, pady=4)

        tk.Label(master, text="Expected Output:").grid(row=2, column=0, sticky="nw")
        self.output_text = tk.Text(master, width=60, height=10)
        self.output_text.grid(row=2, column=1, padx=6, pady=4)
        return self.filename_entry

    def apply(self):
        filename = self.filename_entry.get().strip()
        prompt = self.prompt_text.get("1.0", "end").strip()
        output = self.output_text.get("1.0", "end").strip()
        if not filename or not prompt:
            messagebox.showerror("Error", "Filename and prompt are required.")
            return
        file_path = self.test_dir / filename
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(f"PROMPT:\n{prompt}\n\nEXPECTED:\n{output}\n")
        messagebox.showinfo("Saved", f"Test saved as {file_path.name}")

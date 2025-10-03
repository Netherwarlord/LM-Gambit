import tkinter as tk
from tkinter import ttk
import difflib

class DiffViewerDialog(tk.Toplevel):
    def __init__(self, parent, expected: str, actual: str, title: str = "Output Diff"):
        super().__init__(parent)
        self.title(title)
        self.geometry("900x600")
        self.transient(parent)
        self.grab_set()

        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill="both", expand=True, padx=10, pady=10)

        left_frame = ttk.Frame(paned)
        right_frame = ttk.Frame(paned)
        paned.add(left_frame, weight=1)
        paned.add(right_frame, weight=1)

        ttk.Label(left_frame, text="Expected Output", font=("Helvetica", 12, "bold")).pack(anchor="w")
        self.expected_text = tk.Text(left_frame, wrap="word", bg="#f8f8f8")
        self.expected_text.pack(fill="both", expand=True)
        self.expected_text.insert("1.0", expected)
        self.expected_text.configure(state="disabled")

        ttk.Label(right_frame, text="Actual Output", font=("Helvetica", 12, "bold")).pack(anchor="w")
        self.actual_text = tk.Text(right_frame, wrap="word", bg="#f8f8f8")
        self.actual_text.pack(fill="both", expand=True)
        self.actual_text.insert("1.0", actual)
        self.actual_text.configure(state="disabled")

        # Diff summary at the bottom
        diff = list(difflib.unified_diff(
            expected.splitlines(), actual.splitlines(), lineterm='', n=3,
            fromfile='expected', tofile='actual'))
        diff_str = '\n'.join(diff) if diff else 'No differences.'
        ttk.Label(self, text="Diff Summary", font=("Helvetica", 11, "bold")).pack(anchor="w", padx=10)
        diff_box = tk.Text(self, height=8, wrap="none", bg="#f0f0f0")
        diff_box.pack(fill="x", padx=10, pady=(0,10))
        diff_box.insert("1.0", diff_str)
        diff_box.configure(state="disabled")

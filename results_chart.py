import tkinter as tk
from tkinter import ttk
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import re

def parse_report(report_path: Path):
    # Simple parser for markdown report: looks for lines like 'Pass: 8/10', 'Fail: 2/10', etc.
    pass_count = 0
    fail_count = 0
    total = 0
    with open(report_path, 'r', encoding='utf-8') as f:
        for line in f:
            m = re.match(r'Pass: (\d+)/(\d+)', line)
            if m:
                pass_count = int(m.group(1))
                total = int(m.group(2))
            m = re.match(r'Fail: (\d+)/(\d+)', line)
            if m:
                fail_count = int(m.group(1))
    return pass_count, fail_count, total

class ResultsChartDialog(tk.Toplevel):
    def __init__(self, parent, report_path: Path):
        super().__init__(parent)
        self.title(f"Test Results Chart: {report_path.name}")
        self.geometry("600x500")
        self.transient(parent)
        self.grab_set()

        pass_count, fail_count, total = parse_report(report_path)
        fig, ax = plt.subplots(figsize=(5,4))
        ax.bar(['Pass', 'Fail'], [pass_count, fail_count], color=['#4caf50', '#f44336'])
        ax.set_ylabel('Count')
        ax.set_title(f"Test Results ({pass_count+fail_count}/{total} completed)")
        for i, v in enumerate([pass_count, fail_count]):
            ax.text(i, v + 0.1, str(v), ha='center', va='bottom', fontweight='bold')
        fig.tight_layout()

        canvas = FigureCanvasTkAgg(fig, master=self)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)
        ttk.Button(self, text="Close", command=self.destroy).pack(pady=8)

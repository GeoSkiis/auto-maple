import tkinter as tk
from src.gui.interfaces import LabelFrame


class Status(LabelFrame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, 'Status', **kwargs)

        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(3, weight=1)

        self.curr_cb = tk.StringVar()
        self.curr_routine = tk.StringVar()
        self.curr_minimap = tk.StringVar(value='(none)')

        self.cb_label = tk.Label(self, text='Command Book:')
        self.cb_label.grid(row=0, column=1, padx=5, pady=(5, 0), sticky=tk.E)
        self.cb_entry = tk.Entry(self, textvariable=self.curr_cb, state=tk.DISABLED)
        self.cb_entry.grid(row=0, column=2, padx=(0, 5), pady=(5, 0), sticky=tk.EW)

        self.r_label = tk.Label(self, text='Routine:')
        self.r_label.grid(row=1, column=1, padx=5, pady=0, sticky=tk.E)
        self.r_entry = tk.Entry(self, textvariable=self.curr_routine, state=tk.DISABLED)
        self.r_entry.grid(row=1, column=2, padx=(0, 5), pady=0, sticky=tk.EW)

        self.mm_label = tk.Label(self, text='Minimap:')
        self.mm_label.grid(row=2, column=1, padx=5, pady=(0, 5), sticky=tk.E)
        self.mm_entry = tk.Entry(self, textvariable=self.curr_minimap, state=tk.DISABLED, width=50)
        self.mm_entry.grid(row=2, column=2, padx=(0, 5), pady=(0, 5), sticky=tk.EW)

    def set_cb(self, string):
        self.curr_cb.set(string)

    def set_routine(self, string):
        self.curr_routine.set(string)

    def set_minimap(self, string):
        """Set the displayed minimap filename. Use '(none)' when no minimap is selected."""
        self.curr_minimap.set(string or '(none)')

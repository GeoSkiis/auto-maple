"""Item buff and familiar pot cooldown settings."""

import tkinter as tk
from tkinter import ttk
from src.gui.interfaces import LabelFrame, Frame
from src.common.interfaces import Configurable


# Item buff 1-4: Never, 10/15/20/30/60 min, 2 hrs. Familiar: Never, 1 hr
# Timed options add 60s to the nominal duration (labels unchanged).
_BUFF_INTERVAL_PAD = 60
ITEM_BUFF_OPTIONS = [
    ('Never', 0),
    ('10 min', 600 + _BUFF_INTERVAL_PAD),
    ('15 min', 900 + _BUFF_INTERVAL_PAD),
    ('20 min', 1200 + _BUFF_INTERVAL_PAD),
    ('30 min', 1800 + _BUFF_INTERVAL_PAD),
    ('60 min', 3600 + _BUFF_INTERVAL_PAD),
    ('2 hrs', 7200 + _BUFF_INTERVAL_PAD),
]
FAMILIAR_OPTIONS = [
    ('Never', 0),
    ('1 hr', 3600 + _BUFF_INTERVAL_PAD),
]

# Saved configs from before the pad used exact second counts; map to padded values.
_LEGACY_ITEM_BUFF_SEC = {
    600: 600 + _BUFF_INTERVAL_PAD,
    900: 900 + _BUFF_INTERVAL_PAD,
    1200: 1200 + _BUFF_INTERVAL_PAD,
    1800: 1800 + _BUFF_INTERVAL_PAD,
    3600: 3600 + _BUFF_INTERVAL_PAD,
    7200: 7200 + _BUFF_INTERVAL_PAD,
}
_LEGACY_FAMILIAR_1HR = 3600


def _seconds_to_label(seconds, options):
    for label, sec in options:
        if sec == seconds:
            return label
    if options is ITEM_BUFF_OPTIONS and seconds in _LEGACY_ITEM_BUFF_SEC:
        return _seconds_to_label(_LEGACY_ITEM_BUFF_SEC[seconds], options)
    if options is FAMILIAR_OPTIONS and seconds == _LEGACY_FAMILIAR_1HR:
        return _seconds_to_label(_LEGACY_FAMILIAR_1HR + _BUFF_INTERVAL_PAD, options)
    return options[0][0]


class ItemBuffs(LabelFrame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, 'Item Buffs', **kwargs)

        self.settings = ItemBuffSettings('item_buffs')

        self.item_vars = []
        self.familiar_var = tk.StringVar(value=_seconds_to_label(
            self.settings.get('Familiar pot'), FAMILIAR_OPTIONS))

        for i in range(1, 5):
            key = f'Item buff {i}'
            sec = self.settings.get(key)
            var = tk.StringVar(value=_seconds_to_label(sec, ITEM_BUFF_OPTIONS))
            self.item_vars.append(var)

            row = Frame(self)
            row.pack(side=tk.TOP, fill='x', expand=True, pady=2, padx=5)
            label = tk.Label(row, text=f'{key}:', width=12, anchor='w')
            label.pack(side=tk.LEFT, padx=(0, 5))
            opts = [x[0] for x in ITEM_BUFF_OPTIONS]
            om = ttk.OptionMenu(row, var, var.get(), *opts, command=lambda v, k=key: self._on_item_change(k))
            om.pack(side=tk.LEFT)

        fam_row = Frame(self)
        fam_row.pack(side=tk.TOP, fill='x', expand=True, pady=(2, 5), padx=5)
        tk.Label(fam_row, text='Familiar pot:', width=12, anchor='w').pack(side=tk.LEFT, padx=(0, 5))
        fam_opts = [x[0] for x in FAMILIAR_OPTIONS]
        ttk.OptionMenu(
            fam_row, self.familiar_var, self.familiar_var.get(), *fam_opts,
            command=lambda v: self._on_familiar_change()
        ).pack(side=tk.LEFT)

    def _on_item_change(self, key):
        idx = int(key.split()[-1]) - 1
        label = self.item_vars[idx].get()
        sec = next((s for lb, s in ITEM_BUFF_OPTIONS if lb == label), 0)
        self.settings.set(key, sec)
        self.settings.save_config()

    def _on_familiar_change(self):
        label = self.familiar_var.get()
        sec = next((s for lb, s in FAMILIAR_OPTIONS if lb == label), 0)
        self.settings.set('Familiar pot', sec)
        self.settings.save_config()

    def get_interval_seconds(self, key):
        """Return interval in seconds for 'Item buff 1'..'Item buff 4' or 'Familiar pot'."""
        return self.settings.get(key)


class ItemBuffSettings(Configurable):
    DEFAULT_CONFIG = {
        'Item buff 1': 0,      # Never default
        'Item buff 2': 0,
        'Item buff 3': 0,
        'Item buff 4': 0,
        'Familiar pot': 0,     # Never default
    }

    def get(self, key):
        v = self.config.get(key, self.DEFAULT_CONFIG.get(key))
        if key.startswith('Item buff'):
            return _LEGACY_ITEM_BUFF_SEC.get(v, v)
        if key == 'Familiar pot' and v == _LEGACY_FAMILIAR_1HR:
            return v + _BUFF_INTERVAL_PAD
        return v

    def set(self, key, value):
        if key in self.DEFAULT_CONFIG:
            self.config[key] = value

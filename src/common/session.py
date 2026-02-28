"""Persist and restore command book, routine, and minimap selection across app restarts."""

import json
import os


SESSION_FILE = os.path.join('.settings', 'session.json')


def save(command_book_path=None, routine_path=None, minimap_path=None):
    """Update and save session. Pass only paths you want to update; others are preserved."""
    data = {}
    if os.path.isfile(SESSION_FILE):
        try:
            with open(SESSION_FILE, 'r') as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass

    if command_book_path is not None:
        data['command_book'] = command_book_path
    if routine_path is not None:
        data['routine'] = routine_path
    if minimap_path is not None:
        data['minimap'] = minimap_path

    os.makedirs(os.path.dirname(SESSION_FILE), exist_ok=True)
    with open(SESSION_FILE, 'w') as f:
        json.dump(data, f, indent=2)


def load():
    """Load saved session paths. Returns dict with keys command_book, routine, minimap (or empty string if missing)."""
    if not os.path.isfile(SESSION_FILE):
        return {}
    try:
        with open(SESSION_FILE, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}

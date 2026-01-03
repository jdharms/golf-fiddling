"""
NES Open Tournament Golf - File Dialogs

Tkinter-based file dialog utilities for loading and saving files.
"""



def open_file_dialog(title: str, filetypes: list[tuple[str, str]]) -> str | None:
    """
    Display an 'Open File' dialog and return the selected path.

    Args:
        title: Dialog window title
        filetypes: List of (description, pattern) tuples, e.g. [("JSON files", "*.json")]

    Returns:
        Selected file path, or None if canceled or tkinter unavailable
    """
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        path = filedialog.askopenfilename(title=title, filetypes=filetypes)
        root.destroy()
        return path if path else None
    except ImportError:
        print("tkinter not available for file dialog")
        return None


def save_file_dialog(
    title: str, default_extension: str, filetypes: list[tuple[str, str]]
) -> str | None:
    """
    Display a 'Save File' dialog and return the selected path.

    Args:
        title: Dialog window title
        default_extension: Default file extension (e.g., ".json")
        filetypes: List of (description, pattern) tuples, e.g. [("JSON files", "*.json")]

    Returns:
        Selected file path, or None if canceled or tkinter unavailable
    """
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        path = filedialog.asksaveasfilename(
            title=title, defaultextension=default_extension, filetypes=filetypes
        )
        root.destroy()
        return path if path else None
    except ImportError:
        print("tkinter not available for file dialog")
        return None

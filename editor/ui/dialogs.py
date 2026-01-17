"""
NES Open Tournament Golf - File Dialogs

Cross-platform file dialog utilities using plyer with tkinter fallback.
"""

from plyer import filechooser


def _open_file_tkinter(title: str, filetypes: list[tuple[str, str]]) -> str | None:
    """Tkinter fallback for open file dialog."""
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


def _save_file_tkinter(
    title: str, default_extension: str, filetypes: list[tuple[str, str]]
) -> str | None:
    """Tkinter fallback for save file dialog."""
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


def open_file_dialog(title: str, filetypes: list[tuple[str, str]]) -> str | None:
    """
    Display an 'Open File' dialog and return the selected path.

    Args:
        title: Dialog window title
        filetypes: List of (description, pattern) tuples, e.g. [("JSON files", "*.json")]

    Returns:
        Selected file path, or None if canceled
    """
    try:
        result = filechooser.open_file(title=title, filters=filetypes)
        if result:
            return result[0]  # plyer returns a list, we want single path
        return None
    except (OSError, NotImplementedError):
        # plyer backend not available, fall back to tkinter
        return _open_file_tkinter(title, filetypes)


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
        Selected file path, or None if canceled
    """
    try:
        result = filechooser.save_file(title=title, filters=filetypes)
        if result:
            path = result[0]  # plyer returns a list
            # Ensure default extension is applied if not present
            if default_extension and not path.endswith(default_extension):
                path += default_extension
            return path
        return None
    except (OSError, NotImplementedError):
        # plyer backend not available, fall back to tkinter
        return _save_file_tkinter(title, default_extension, filetypes)

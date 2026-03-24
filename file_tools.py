"""
File processing tools.
"""

import os
from typing import Optional


def _ensure_directory_exists(path: str) -> bool:
    """Ensure the directory for the given file path exists; create if needed."""
    directory = os.path.dirname(path)
    if directory and not os.path.exists(directory):
        try:
            os.makedirs(directory, exist_ok=True)
            return True
        except OSError as e:
            return False
    return True


def file_write(path: str, content: str, mode: Optional[str] = None) -> str:
    """
    Write content to a file.

    Args:
        path: Absolute or relative path to the file.
        content: String content to write.
        mode: Write mode ('overwrite', 'append', or None).
    Returns:
        String with success or error message, including absolute path.
    """
    # Convert to absolute path
    abs_path = os.path.abspath(path)

    # Ensure directory exists
    if not _ensure_directory_exists(abs_path):
        return f"Error: Could not create directory for {abs_path}"

    # Determine mode if not specified
    if mode is None:
        mode = "overwrite"

    try:
        if mode == "overwrite":
            with open(abs_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return f"Successfully wrote to {abs_path}"
        elif mode == "append":
            with open(abs_path, 'a', encoding='utf-8') as f:
                f.write(content)
            return f"Successfully appended to {abs_path}"
        else:
            return f"Error: Invalid mode '{mode}'. Must be 'overwrite', 'append', or None."
    except Exception as e:
        return f"Error writing to file: {str(e)}"


def file_replace(path: str, old: str, new: str, replace_all: bool = False) -> str:
    """
    Replace occurrences of a substring in a file.

    Args:
        path: Absolute or relative path to the file.
        old: Substring to replace.
        new: Replacement substring.
        replace_all: If True, replace all occurrences; otherwise replace only the first.

    Returns:
        String with success or error message, including absolute path.
    """
    # Convert to absolute path
    abs_path = os.path.abspath(path)

    # Check file existence
    if not os.path.exists(abs_path):
        return f"Error: File not found: {abs_path}"

    if not os.path.isfile(abs_path):
        return f"Error: Path is not a file: {abs_path}"

    try:
        with open(abs_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Perform replacement
        if replace_all:
            new_content = content.replace(old, new)
        else:
            new_content = content.replace(old, new, 1)

        # Write back only if changes were made
        if new_content != content:
            with open(abs_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            return f"Successfully replaced in {abs_path}"
        else:
            return f"No occurrences found to replace in {abs_path}"

    except Exception as e:
        return f"Error processing file: {str(e)}"


FILE_TOOLS = {
    "file_write": file_write,
    "file_replace": file_replace,
}
"""
Image processing tools.
"""

import base64
import mimetypes
import os
import re
from typing import Optional

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


def _is_url(string: str) -> bool:
    """Check if the string is a URL"""
    url_pattern = re.compile(
        r'^https?://'
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'
        r'localhost|'
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
        r'(?::\d+)?'
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    return bool(url_pattern.match(string))


def _encode_image_to_data_url(image_data: bytes, mime_type: Optional[str] = None) -> str:
    """Encode image bytes to a base64 data URL"""
    base64_data = base64.b64encode(image_data).decode('utf-8')
    return f"data:{mime_type};base64,{base64_data}"


def read_image(path: str):
    """
    Read an image from the file system or URL and return it in Kimi vision API format.

    Args:
        path: Absolute or relative path to the image file, or a URL to the image.

    Returns:
        List with image content in format: [{"type": "image_url", "image_url": {"url": "data:..."}}]
    """
    if _is_url(path):
        if not REQUESTS_AVAILABLE:
            return [{"type": "text", "text": "Error: requests library not available for URL fetching"}]

        try:
            response = requests.get(path, timeout=30)
            response.raise_for_status()

            mime_type = response.headers.get('Content-Type', '')
            if not mime_type or not mime_type.startswith('image/'):
                mime_type, _ = mimetypes.guess_type(path)
            if not mime_type or not mime_type.startswith('image/'):
                return [{"type": "text", "text": f"Error: The URL does not point to a valid image file (detected MIME type: {mime_type or 'unknown'})"}]

            image_data = response.content
            data_url = _encode_image_to_data_url(image_data, mime_type)
            return [{"type": "image_url", "image_url": {"url": data_url}}]
        except requests.RequestException as e:
            return [{"type": "text", "text": f"Error downloading image from URL: {str(e)}"}]
    else:
        if not os.path.exists(path):
            return [{"type": "text", "text": f"Error: File not found: {path}"}]

        if not os.path.isfile(path):
            return [{"type": "text", "text": f"Error: Path is not a file: {path}"}]

        mime_type, _ = mimetypes.guess_type(path)
        if not mime_type or not mime_type.startswith('image/'):
            return [{"type": "text", "text": f"Error: The file is not a valid image file (detected MIME type: {mime_type or 'unknown'})"}]

        try:
            with open(path, 'rb') as f:
                image_data = f.read()
            data_url = _encode_image_to_data_url(image_data, mime_type)
            return [{"type": "image_url", "image_url": {"url": data_url}}]
        except Exception as e:
            return [{"type": "text", "text": f"Error reading image: {str(e)}"}]


IMAGE_TOOLS = {
    "read_image": read_image,
}

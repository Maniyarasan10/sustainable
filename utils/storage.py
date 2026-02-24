import os
from typing import Optional

import cloudinary
import cloudinary.uploader


def _configure():
    # Allow full CLOUDINARY_URL env or individual components
    cloud_name = os.getenv('CLOUDINARY_CLOUD_NAME')
    api_key = os.getenv('CLOUDINARY_API_KEY')
    api_secret = os.getenv('CLOUDINARY_API_SECRET')
    cloudinary_url = os.getenv('CLOUDINARY_URL')

    if cloudinary_url:
        cloudinary.config(cloudinary_url=cloudinary_url)
    else:
        if cloud_name and api_key and api_secret:
            cloudinary.config(cloud_name=cloud_name, api_key=api_key, api_secret=api_secret)


def upload_file(upload_file, folder: str = "sustainable", public_id: Optional[str] = None) -> dict:
    """
    Upload a FastAPI `UploadFile` (or file-like/bytes) to Cloudinary.

    Returns the Cloudinary response dict (contains `secure_url`, `url`, `public_id`, `resource_type`, etc.).
    """
    _configure()

    # read bytes
    try:
        data = upload_file.file.read()
    except Exception:
        # If something unexpected, try treating upload_file as raw content
        data = upload_file

    opts = {"folder": folder}
    if public_id:
        opts['public_id'] = public_id

    # attempt to infer resource type from content-type if available
    content_type = getattr(upload_file, 'content_type', None)
    if content_type and content_type.startswith('video'):
        opts['resource_type'] = 'video'

    # Use uploader; Cloudinary can detect images/video automatically when resource_type is provided
    result = cloudinary.uploader.upload(data, **opts)
    return result


def build_url_from_response(resp: dict) -> str:
    return resp.get('secure_url') or resp.get('url')

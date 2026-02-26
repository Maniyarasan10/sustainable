import os
from typing import Optional

import cloudinary
import cloudinary.uploader


import logging

logger = logging.getLogger("storage")

def _configure():
    # Allow full CLOUDINARY_URL env or individual components
    cloudinary_url = os.getenv('CLOUDINARY_URL')
    cloud_name = os.getenv('CLOUDINARY_CLOUD_NAME')
    api_key = os.getenv('CLOUDINARY_API_KEY')
    api_secret = os.getenv('CLOUDINARY_API_SECRET')

    if cloudinary_url:
        logger.info("Configuring Cloudinary using CLOUDINARY_URL (manual parse)")
        import re
        # Format: cloudinary://api_key:api_secret@cloud_name
        match = re.search(r"cloudinary://([^:]+):([^@]+)@(.+)", cloudinary_url)
        if match:
            cloudinary.config(
                api_key=match.group(1),
                api_secret=match.group(2),
                cloud_name=match.group(3),
                secure=True
            )
        else:
            logger.error("CLOUDINARY_URL format is invalid. Expected cloudinary://key:secret@name")
    elif cloud_name and api_key and api_secret:
        logger.info("Configuring Cloudinary using individual components")
        cloudinary.config(cloud_name=cloud_name, api_key=api_key, api_secret=api_secret, secure=True)
    else:
        logger.warning("Cloudinary configuration missing! Check CLOUDINARY_URL or components in .env")


def upload_file(upload_file, folder: str = "sustainable", public_id: Optional[str] = None) -> dict:
    """
    Upload a FastAPI `UploadFile` (or file-like/bytes) to Cloudinary.

    Returns the Cloudinary response dict (contains `secure_url`, `url`, `public_id`, `resource_type`, etc.).
    """
    _configure()

    # read bytes
    try:
        # Check if it has a .file attribute (FastAPI UploadFile)
        if hasattr(upload_file, 'file'):
            data = upload_file.file.read()
        else:
            data = upload_file
    except Exception as e:
        logger.error(f"Failed to read upload file data: {e}")
        raise

    opts = {"folder": folder}
    if public_id:
        opts['public_id'] = public_id

    # attempt to infer resource type from content-type if available
    content_type = getattr(upload_file, 'content_type', None)
    if content_type and content_type.startswith('video'):
        opts['resource_type'] = 'video'

    # Use uploader
    try:
        logger.info(f"Uploading file to Cloudinary folder: {folder}")
        result = cloudinary.uploader.upload(data, **opts)
        return result
    except Exception as e:
        logger.error(f"Cloudinary upload failed: {e}")
        raise


def build_url_from_response(resp: dict) -> str:
    return resp.get('secure_url') or resp.get('url')

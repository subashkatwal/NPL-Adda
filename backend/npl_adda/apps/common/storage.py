"""
Cloudinary storage for uploaded and rendered images (memes, avatars).

Enabled from settings when CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET are set;
otherwise media stays on the local filesystem. Stored names keep Django's upload_to folders plus the file
extension (``memes/uploads/2026/10/photo_a1b2c3d4.jpg``); the Cloudinary public_id is the name without it.
"""
import os
import secrets

import cloudinary
import cloudinary.uploader
import cloudinary.utils
import requests
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible


@deconstructible
class CloudinaryMediaStorage(Storage):
    def __init__(self):
        cloudinary.config(
            cloud_name=settings.CLOUDINARY_CLOUD_NAME,
            api_key=settings.CLOUDINARY_API_KEY,
            api_secret=settings.CLOUDINARY_API_SECRET,
            secure=True,
        )

    @staticmethod
    def _split(name):
        public_id, ext = os.path.splitext(name.replace("\\", "/"))
        return public_id, ext.lstrip(".").lower()

    def _save(self, name, content):
        public_id, ext = self._split(name)
        # A random suffix keeps names unique without an Admin API lookup per upload (see exists()).
        public_id = f"{public_id}_{secrets.token_hex(4)}"
        content.seek(0)
        result = cloudinary.uploader.upload(content, public_id=public_id, resource_type="image", overwrite=False)
        return f"{result['public_id']}.{ext or result['format']}"

    def _open(self, name, mode="rb"):
        response = requests.get(self.url(name), timeout=15)
        response.raise_for_status()
        return ContentFile(response.content, name=name)

    def exists(self, name):
        return False  # _save always picks a fresh public_id

    def url(self, name):
        public_id, ext = self._split(name)
        return cloudinary.utils.cloudinary_url(public_id, format=ext or None, resource_type="image", secure=True)[0]

    def delete(self, name):
        if name:
            cloudinary.uploader.destroy(self._split(name)[0], resource_type="image", invalidate=True)

    def size(self, name):
        return len(self._open(name).read())

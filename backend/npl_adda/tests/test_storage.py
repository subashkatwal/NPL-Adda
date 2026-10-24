from unittest import mock

from django.core.files.base import ContentFile
from django.test import override_settings

from apps.common.storage import CloudinaryMediaStorage


@override_settings(CLOUDINARY_CLOUD_NAME="demo", CLOUDINARY_API_KEY="key", CLOUDINARY_API_SECRET="secret")
def test_cloudinary_storage_saves_under_unique_public_id_and_builds_url():
    storage = CloudinaryMediaStorage()
    with mock.patch("cloudinary.uploader.upload") as upload:
        upload.side_effect = lambda content, public_id, **kw: {"public_id": public_id, "format": "jpg"}
        name = storage.save("memes/rendered/abc.jpg", ContentFile(b"img"))

    public_id = upload.call_args.kwargs["public_id"]
    assert public_id.startswith("memes/rendered/abc_") and name == f"{public_id}.jpg"
    url = storage.url(name)
    assert url.startswith("https://res.cloudinary.com/demo/image/upload/") and url.endswith(f"/{public_id}.jpg")

    with mock.patch("cloudinary.uploader.destroy") as destroy:
        storage.delete(name)
    destroy.assert_called_once_with(public_id, resource_type="image", invalidate=True)

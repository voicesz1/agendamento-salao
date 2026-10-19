from hashlib import sha256
from io import BytesIO
import warnings

from fastapi import UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError

from app.models import Service

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000


def read_service_image(upload: UploadFile | None) -> bytes | None:
    if not upload or not upload.filename:
        return None
    payload = upload.file.read(MAX_IMAGE_BYTES + 1)
    if not payload or len(payload) > MAX_IMAGE_BYTES:
        raise ValueError("A imagem deve ter até 5 MB.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(payload)) as source:
                if source.format not in {"JPEG", "PNG", "WEBP"}:
                    raise ValueError("Use uma foto JPG, PNG ou WebP.")
                if source.width * source.height > MAX_IMAGE_PIXELS or getattr(source, "is_animated", False):
                    raise ValueError("Escolha uma foto estática de até 20 megapixels.")
                source.load()
                photo = ImageOps.exif_transpose(source)
                photo.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
                # Flatten transparency and strip metadata, including camera location.
                rgba = photo.convert("RGBA")
                clean = Image.new("RGB", rgba.size, "white")
                clean.paste(rgba, mask=rgba.getchannel("A"))
                output = BytesIO()
                clean.save(output, format="JPEG", quality=85, optimize=True)
                return output.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError("Não foi possível ler essa imagem.") from exc


def set_service_image(service: Service, image_data: bytes | None) -> None:
    service.image_data = image_data
    service.image_revision = sha256(image_data).hexdigest() if image_data else ""

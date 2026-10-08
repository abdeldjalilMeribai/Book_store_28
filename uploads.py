"""Envoi d'images sécurisé : validation Pillow, ré-encodage (supprime EXIF et charges cachées), nom aléatoire."""
import io
import os
import uuid

from PIL import Image, ImageFile, UnidentifiedImageError

Image.MAX_IMAGE_PIXELS = 40_000_000   # garde-fou « decompression bomb »
ImageFile.LOAD_TRUNCATED_IMAGES = True


class InvalidImageError(ValueError):
    pass


def save_image(file_storage, upload_folder, allowed_ext, max_dim=1600) -> str:
    name = (file_storage.filename or "").lower()
    ext = name.rsplit(".", 1)[-1] if "." in name else ""
    if ext not in allowed_ext:
        raise InvalidImageError("Format non accepté : utilisez JPG, PNG, WEBP ou JFIF.")
    raw = file_storage.read()
    file_storage.seek(0)
    if not raw:
        raise InvalidImageError("Le fichier est vide.")
    try:
        with Image.open(io.BytesIO(raw)) as probe:
            probe.verify()
        with Image.open(io.BytesIO(raw)) as img:
            img.load()
            fmt = (img.format or "").upper()
            if fmt not in {"JPEG", "PNG", "WEBP", "MPO", "GIF", "AVIF"}:
                raise InvalidImageError("Format d'image non pris en charge.")
            if img.mode in ("RGBA", "LA", "P"):
                rgba = img.convert("RGBA")
                flat = Image.new("RGB", rgba.size, (255, 255, 255))
                flat.paste(rgba, mask=rgba.getchannel("A"))
                img = flat
            else:
                img = img.convert("RGB")
            img.thumbnail((max_dim, max_dim), Image.LANCZOS)
            os.makedirs(upload_folder, exist_ok=True)
            filename = f"{uuid.uuid4().hex}.jpg"
            img.save(os.path.join(upload_folder, filename), format="JPEG", quality=86, optimize=True, progressive=True)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise InvalidImageError("Ce fichier n'est pas une image valide.") from exc
    return f"/static/uploads/{filename}"


def delete_upload(url, upload_folder):
    """Supprime le fichier seulement s'il vient du dossier d'envois (jamais les images du thème)."""
    if not url or not url.startswith("/static/uploads/"):
        return
    path = os.path.join(upload_folder, os.path.basename(url))
    if os.path.isfile(path):
        try:
            os.remove(path)
        except OSError:
            pass

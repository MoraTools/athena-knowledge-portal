"""Private, immutable article images. Article saves and GC share SQLite's write transaction."""
import hashlib
from html import unescape
from html.parser import HTMLParser
from io import BytesIO
import os
from pathlib import Path
import re
import subprocess
import sys
from datetime import timedelta
from urllib.parse import unquote, urlsplit
from uuid import UUID
import warnings

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from markdown_it import MarkdownIt
from PIL import Image, ImageOps, UnidentifiedImageError

from .models import Article, ManagedImage, visible_articles


MAX_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 20_000_000
MAX_GIF_FRAMES = 2_000
MAX_GIF_PIXELS = 2_000_000_000
GRACE = timedelta(hours=24)
IMAGE_PATH = re.compile(r'/article-images/([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})/?')
GENERATED_FILE = re.compile(r'[0-9a-f]{32}\.(?:png|jpg|webp|gif)')
MARKDOWN = MarkdownIt('commonmark', {'html': True}).enable(['table', 'strikethrough'])


def image_id_from_url(url):
    """Only this portal's absolute URLs and root-relative URLs identify a managed image."""
    try:
        parts = urlsplit(unescape(url))
        origin = urlsplit(settings.PUBLIC_ORIGIN)
        if parts.netloc and (parts.netloc.lower() != origin.netloc.lower() or parts.username or parts.password):
            return None
        if parts.scheme and (not parts.netloc or parts.scheme.lower() != origin.scheme.lower()):
            return None
        match = IMAGE_PATH.fullmatch(unquote(parts.path))
        return UUID(match[1]) if match else None
    except (ValueError, TypeError):
        return None


class ImageSources(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.urls = []

    def handle_starttag(self, tag, attrs):
        if tag == 'img':
            self.urls.extend(value for name, value in attrs if name == 'src' and value)


def referenced_image_ids(body, *, conservative=False):
    parser = ImageSources()
    parser.feed(MARKDOWN.render(body))
    ids = {image_id for url in parser.urls if (image_id := image_id_from_url(url))}
    if conservative:
        # Protect code examples, unused reference definitions and unusual Markdown too. False positives retain files.
        ids.update(UUID(match[1]) for match in IMAGE_PATH.finditer(unquote(unescape(body))))
    return ids


def all_references():
    # ponytail: full scan of this small KB; add a reference index if article volume makes scans expensive.
    ids = set()
    for body in Article.objects.values_list('body', flat=True):
        ids.update(referenced_image_ids(body, conservative=True))
    return ids


def image_path(image):
    if image.format not in ('png', 'jpg', 'webp', 'gif'):
        raise ValidationError('Formato de imagen no permitido.')
    root = Path(settings.MEDIA_ROOT) / 'article-images'
    path = root / image.filename
    # Generated basenames only; symlinks must never expose another local file.
    if root.is_symlink() or path.is_symlink() or path.parent.resolve() != root.resolve():
        raise ValidationError('Archivo de imagen no permitido.')
    return path


def check_references(body, *, actor=None):
    ids = referenced_image_ids(body)
    images = {image.pk: image for image in ManagedImage.objects.filter(pk__in=ids)}
    if ids != images.keys() or any(not image_path(image).is_file() for image in images.values()):
        raise ValidationError({'body': 'Una imagen del artículo ya no está disponible. Vuelva a insertarla antes de guardar.'})
    if actor:
        foreign = {image.pk for image in images.values() if image.uploader_id != actor.pk}
        attached = set()
        if foreign:
            for saved_body in visible_articles(actor, include_drafts=True).values_list('body', flat=True):
                attached.update(referenced_image_ids(saved_body))
        if foreign - attached:
            raise ValidationError({'body': 'Solo puede insertar sus imágenes sin guardar. Vuelva a subir la imagen con su cuenta.'})


def sync_image_usage():
    ids = all_references()
    ManagedImage.objects.filter(pk__in=ids).exclude(unused_since=None).update(unused_since=None)
    ManagedImage.objects.exclude(pk__in=ids).filter(unused_since=None).update(unused_since=timezone.now())


def can_upload(user):
    return user.is_authenticated and user.is_active and (
        user.has_perm('athena.add_article') or user.has_perm('athena.change_article'))


def clean_gif(raw):
    """Keep GIF rendering blocks, strip metadata, then decode one frame at a time."""
    position = 0

    def take(length):
        nonlocal position
        end = position + length
        if end > len(raw):
            raise ValueError('Truncated GIF block')
        block = raw[position:end]
        position = end
        return block

    def subblocks():
        start = position
        while length := take(1)[0]:
            take(length)
        return raw[start:position]

    header = take(13)
    if header[:6] not in (b'GIF87a', b'GIF89a'):
        raise ValueError('Invalid GIF header')
    width, height = int.from_bytes(header[6:8], 'little'), int.from_bytes(header[8:10], 'little')
    pixels = width * height
    if not pixels or pixels > MAX_PIXELS:
        raise ValidationError('Use una imagen de hasta 20 millones de píxeles.')
    output = bytearray(header)
    global_colors = 2 ** ((header[10] & 7) + 1) if header[10] & 128 else 0
    if global_colors:
        output.extend(take(3 * global_colors))
    frames = 0
    control = b''
    loop = False
    while True:
        marker = take(1)
        if marker == b';':
            if not frames or control:
                raise ValueError('Invalid GIF trailer')
            output.extend(marker)
            break  # Bytes after the GIF trailer are not image data.
        if marker == b'!':
            label = take(1)
            if label == b'\xf9':
                block = take(6)
                if control or block[0] != 4 or block[-1] or block[1] & 224 or ((block[1] >> 2) & 7) > 3:
                    raise ValueError('Invalid GIF graphic control')
                control = marker + label + block
            elif label == b'\xfe':
                subblocks()  # Comments never affect rendering.
            elif label == b'\xff':
                if take(1) != b'\x0b':
                    raise ValueError('Invalid GIF application header')
                application, data = take(11), subblocks()
                if application in (b'NETSCAPE2.0', b'ANIMEXTS1.0'):
                    if loop or data[:2] != b'\x03\x01' or len(data) != 5:
                        raise ValueError('Invalid GIF loop extension')
                    output.extend(marker + label + b'\x0b' + application + data)
                    loop = True
            else:
                raise ValueError('Unsupported GIF extension')
        elif marker == b',':
            descriptor = take(9)
            left, top, frame_width, frame_height = (int.from_bytes(descriptor[n:n + 2], 'little') for n in (0, 2, 4, 6))
            if (not frame_width or not frame_height or left + frame_width > width or top + frame_height > height
                    or descriptor[8] & 24):
                raise ValueError('Invalid GIF frame dimensions')
            frames += 1
            if frames > MAX_GIF_FRAMES or frames * pixels > MAX_GIF_PIXELS:
                raise ValidationError('El GIF es demasiado largo o grande. Reduzca la duración o la resolución.')
            local_colors = 2 ** ((descriptor[8] & 7) + 1) if descriptor[8] & 128 else 0
            palette = take(3 * local_colors) if local_colors else b''
            colors = local_colors or global_colors
            if not colors or (control and control[3] & 1 and control[6] >= colors):
                raise ValueError('Invalid GIF palette')
            code_size = take(1)
            if not 2 <= code_size[0] <= 8:
                raise ValueError('Invalid GIF LZW code size')
            compressed = subblocks()
            if compressed == b'\x00':
                raise ValueError('Empty GIF frame')
            output.extend(control + marker + descriptor + palette + code_size + compressed)
            control = b''
        else:
            raise ValueError('Invalid GIF block')
    data = bytes(output)
    # WeasyPrint enables truncated Pillow images globally. Validate in an isolated strict, bounded worker.
    try:
        subprocess.run([sys.executable, str(Path(__file__).with_name('gif_validation.py')), str(frames)],
                       input=data, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=12, check=True)
    except subprocess.TimeoutExpired as error:
        raise ValidationError('El GIF es demasiado largo o grande. Reduzca la duración o la resolución.') from error
    except subprocess.CalledProcessError as error:
        if error.returncode < 0:
            raise ValidationError('El GIF es demasiado largo o grande. Reduzca la duración o la resolución.') from error
        raise OSError('Invalid GIF frame pixels') from error
    return data, width, height


def create_image(upload, user):
    if upload.size > MAX_BYTES:
        raise ValidationError('Use una imagen PNG, JPEG, WebP o GIF de hasta 10 MiB.')
    raw = upload.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValidationError('La imagen supera 10 MiB.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as source:
                fmt = {'PNG': 'png', 'JPEG': 'jpg', 'WEBP': 'webp', 'GIF': 'gif'}.get(source.format)
                if not fmt or source.width * source.height > MAX_PIXELS:
                    raise ValidationError('Use una imagen PNG, JPEG, WebP o GIF de hasta 20 millones de píxeles.')
                if fmt != 'gif' and getattr(source, 'n_frames', 1) != 1:
                    raise ValidationError('Use una imagen sin animación.')
                if fmt != 'gif':
                    source.verify()
            if fmt == 'gif':
                data, width, height = clean_gif(raw)
            else:
                with Image.open(BytesIO(raw)) as source:
                    source.load()
                    clean = ImageOps.exif_transpose(source).convert('RGBA' if 'A' in source.getbands() or 'transparency' in source.info else 'RGB')
                    if fmt == 'jpg':
                        clean = clean.convert('RGB')
                    output = BytesIO()
                    # Re-encode actual pixels to discard metadata and any appended HTML or other data.
                    clean.save(output, format={'png': 'PNG', 'jpg': 'JPEG', 'webp': 'WEBP'}[fmt])
                    data = output.getvalue()
                    width, height = clean.size
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, EOFError, Image.DecompressionBombWarning, Image.DecompressionBombError) as error:
        raise ValidationError('La imagen no es válida. Use PNG, JPEG, WebP o GIF.') from error
    if len(data) > MAX_BYTES:
        raise ValidationError('La imagen procesada supera 10 MiB. Reduzca su tamaño e intente de nuevo.')
    image = ManagedImage(uploader=user, format=fmt, size=len(data), sha256=hashlib.sha256(data).hexdigest(),
                         width=width, height=height)
    path = image_path(image)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    written = False
    try:
        with transaction.atomic():
            with path.open('xb') as file:
                written = True
                os.chmod(path, 0o600)
                file.write(data)
            image.save(force_insert=True)
    except Exception:
        if written:
            path.unlink(missing_ok=True)
        raise
    return image


def image_data(image):
    url = image.get_absolute_url()
    return {'id': str(image.pk), 'url': url, 'markdown': f'![Imagen]({url})', 'content_type': image.content_type,
            'size': image.size, 'width': image.width, 'height': image.height, 'sha256': image.sha256}


def collect_images(*, dry_run=False, now=None):
    """No unrelated media paths are examined. Unlink only after metadata deletion commits."""
    now = now or timezone.now()
    report = {'referenced': 0, 'grace': 0, 'images': [], 'orphans': []}
    with transaction.atomic():
        ids = all_references()
        images = list(ManagedImage.objects.all())
        names = {image.filename for image in images}
        for image in images:
            if image.pk in ids:
                report['referenced'] += 1
                if not dry_run and image.unused_since is not None:
                    ManagedImage.objects.filter(pk=image.pk).update(unused_since=None)
                continue
            if image.unused_since is None:
                if not dry_run:
                    ManagedImage.objects.filter(pk=image.pk).update(unused_since=now)
                report['grace'] += 1
                continue
            if image.unused_since > now - GRACE or image.created_at > now - GRACE:
                report['grace'] += 1
                continue
            path = image_path(image)
            report['images'].append(str(image.pk))
            if not dry_run:
                image.delete()
                transaction.on_commit(lambda path=path: path.unlink(missing_ok=True))
        root = Path(settings.MEDIA_ROOT) / 'article-images'
        if root.is_dir() and not root.is_symlink():
            for path in root.iterdir():
                if (path.name not in names and GENERATED_FILE.fullmatch(path.name) and not path.is_symlink()
                        and path.is_file() and path.stat().st_mtime <= (now - GRACE).timestamp()):
                    # A conservative saved reference also protects an orphan with missing metadata.
                    if UUID(path.name.split('.')[0]) in ids:
                        continue
                    report['orphans'].append(path.name)
                    if not dry_run:
                        transaction.on_commit(lambda path=path: path.unlink(missing_ok=True))
    return report

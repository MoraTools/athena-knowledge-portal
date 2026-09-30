"""Strict GIF pixel validation, isolated from the web process and PDF library."""
from io import BytesIO
import resource
import sys

from PIL import Image, ImageFile


if __name__ == '__main__':
    resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
    ImageFile.LOAD_TRUNCATED_IMAGES = False
    data = sys.stdin.buffer.read(10 * 1024 * 1024 + 1)
    if len(data) > 10 * 1024 * 1024:
        raise ValueError('GIF exceeds the upload limit')
    # Never collect frames: only the current composite and disposal state are retained.
    with Image.open(BytesIO(data)) as source:
        for frame in range(int(sys.argv[1])):
            source.seek(frame)
            source.load()

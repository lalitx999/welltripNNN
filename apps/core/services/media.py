"""
Secure Media Handling Service for WellTrip.
Enforces Security Requirement #3 and #9:
1. Path traversal prevention: Generates media/<model>/<yyyy>/<mm>/<uuid>.<ext>.
2. Magic bytes validation: Verifies actual file signature, not trusting user's Content-Type.
3. EXIF stripping & Re-encoding: Strips all EXIF geolocation metadata and hidden web shells via Pillow.
4. File size limits: Max 10MB for images, 20MB for documents.
5. Allowed extensions: jpg, jpeg, png, webp, pdf only.
"""
import io
import os
import uuid
from datetime import datetime
from PIL import Image
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import InMemoryUploadedFile

ALLOWED_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp'}
ALLOWED_DOC_EXTENSIONS = {'pdf'}
MAX_IMAGE_SIZE = 10 * 1024 * 1024       # 10MB
MAX_DOC_SIZE = 20 * 1024 * 1024         # 20MB

MAGIC_BYTES = {
    'jpg': b'\xff\xd8\xff',
    'jpeg': b'\xff\xd8\xff',
    'png': b'\x89PNG\r\n\x1a\n',
    'webp': b'RIFF',   # Starts with RIFF and has WEBP at offset 8
    'pdf': b'%PDF-',
}


def secure_upload_path(instance, filename, model_subdir=None):
    """
    Generates a secure, non-guessable, path-traversal-free file path:
    media/<model>/<yyyy>/<mm>/<uuid>.<ext>
    """
    ext = filename.split('.')[-1].lower() if '.' in filename else 'jpg'
    if ext not in (ALLOWED_IMAGE_EXTENSIONS | ALLOWED_DOC_EXTENSIONS):
        ext = 'jpg'

    now = datetime.now()
    subdir = model_subdir or instance.__class__.__name__.lower()
    unique_filename = f"{uuid.uuid4().hex}.{ext}"
    return os.path.join(subdir, now.strftime('%Y'), now.strftime('%m'), unique_filename)


def validate_magic_bytes(file_obj, ext):
    """
    Validates actual binary file signature (Magic Bytes).
    Prevents attackers from disguising PHP/JS files as images.
    """
    file_obj.seek(0)
    header = file_obj.read(16)
    file_obj.seek(0)

    if ext in ('jpg', 'jpeg'):
        if not header.startswith(MAGIC_BYTES['jpg']):
            raise ValidationError("รูปแบบไฟล์ JPEG ไม่ถูกต้อง (Magic Byte Mismatch)")
    elif ext == 'png':
        if not header.startswith(MAGIC_BYTES['png']):
            raise ValidationError("รูปแบบไฟล์ PNG ไม่ถูกต้อง (Magic Byte Mismatch)")
    elif ext == 'webp':
        if not (header.startswith(b'RIFF') and b'WEBP' in header[:16]):
            raise ValidationError("รูปแบบไฟล์ WEBP ไม่ถูกต้อง (Magic Byte Mismatch)")
    elif ext == 'pdf':
        if not header.startswith(MAGIC_BYTES['pdf']):
            raise ValidationError("รูปแบบไฟล์ PDF ไม่ถูกต้อง (Magic Byte Mismatch)")


def sanitize_and_strip_image(uploaded_file):
    """
    Re-encodes image using Pillow to:
    1. Strip all EXIF metadata (GPS location, camera serial, etc.).
    2. Nullify any polyglot shell scripts embedded in image comments.
    3. Return a clean, re-encoded InMemoryUploadedFile.
    """
    ext = uploaded_file.name.split('.')[-1].lower() if '.' in uploaded_file.name else 'jpg'

    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValidationError(f"นามสกุลไฟล์ไม่ได้รับอนุญาต (อนุญาตเฉพาะ: {', '.join(ALLOWED_IMAGE_EXTENSIONS)})")

    if uploaded_file.size > MAX_IMAGE_SIZE:
        raise ValidationError(f"ขนาดไฟล์รูปภาพเกินกำหนด (สูงสุด {MAX_IMAGE_SIZE // (1024*1024)}MB)")

    # Validate Magic Bytes first
    validate_magic_bytes(uploaded_file, ext)

    try:
        # Open through Pillow to verify it's a valid image
        image = Image.open(uploaded_file)
        image.verify()

        # Re-open for processing because verify() corrupts image data stream
        uploaded_file.seek(0)
        image = Image.open(uploaded_file)

        # Convert to RGB (or RGBA for PNG) to sanitize
        if ext in ('jpg', 'jpeg'):
            if image.mode in ('RGBA', 'P', 'LA'):
                image = image.convert('RGB')
            output_format = 'JPEG'
            content_type = 'image/jpeg'
        elif ext == 'png':
            output_format = 'PNG'
            content_type = 'image/png'
        elif ext == 'webp':
            output_format = 'WEBP'
            content_type = 'image/webp'
        else:
            image = image.convert('RGB')
            output_format = 'JPEG'
            content_type = 'image/jpeg'

        # Save into a clean in-memory buffer without EXIF data
        buffer = io.BytesIO()
        image.save(buffer, format=output_format, quality=85, optimize=True)
        buffer.seek(0)

        # Generate a safe random name
        clean_filename = f"{uuid.uuid4().hex}.{ext}"

        return InMemoryUploadedFile(
            file=buffer,
            field_name=uploaded_file.field_name if hasattr(uploaded_file, 'field_name') else None,
            name=clean_filename,
            content_type=content_type,
            size=buffer.getbuffer().nbytes,
            charset=None,
        )
    except Exception as e:
        raise ValidationError(f"ไม่สามารถประมวลผลรูปภาพได้ รูปภาพอาจชำรุดหรือมีรูปแบบผิดปกติ: {str(e)}")

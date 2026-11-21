"""Deterministic image processing; generative edits require a separate configured model."""
from io import BytesIO
from PIL import Image, ImageEnhance, ImageDraw, ImageFont, ImageFilter, ImageOps
import numpy as np
import cv2


def read_image(data: bytes) -> Image.Image:
    img = Image.open(BytesIO(data))
    img.load()
    img = ImageOps.exif_transpose(img)
    if img.width * img.height > 24_000_000:
        raise ValueError("Imagem muito grande (limite: 24 megapixels).")
    return img.convert("RGBA")


def remove_background(img: Image.Image) -> Image.Image:
    from rembg import remove, new_session
    # First call downloads the selected segmentation model (~hundreds of MB).
    session = new_session("u2net")
    return remove(img, session=session).convert("RGBA")


def apply_background(img: Image.Image, color: str) -> Image.Image:
    bg = Image.new("RGBA", img.size, color)
    return Image.alpha_composite(bg, img)


def adjust(img: Image.Image, brightness: float, contrast: float, saturation: float, sharpness: float) -> Image.Image:
    alpha = img.getchannel("A")
    rgb = img.convert("RGB")
    for enhancer, factor in [(ImageEnhance.Brightness, brightness), (ImageEnhance.Contrast, contrast),
                              (ImageEnhance.Color, saturation), (ImageEnhance.Sharpness, sharpness)]:
        rgb = enhancer(rgb).enhance(factor)
    rgb.putalpha(alpha)
    return rgb


def shadow(img: Image.Image, blur=18, offset=12, opacity=85) -> Image.Image:
    alpha = img.getchannel("A")
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    black = Image.new("RGBA", img.size, (0, 0, 0, opacity))
    shifted = Image.new("L", img.size, 0)
    shifted.paste(alpha, (offset, offset))
    black.putalpha(shifted.point(lambda x: int(x * opacity / 255)))
    sh = Image.alpha_composite(sh, black.filter(ImageFilter.GaussianBlur(blur)))
    return Image.alpha_composite(sh, img)


def add_text(img: Image.Image, text: str, x: int, y: int, size: int, color: str) -> Image.Image:
    result = img.copy()
    draw = ImageDraw.Draw(result)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)
    except OSError:
        font = ImageFont.load_default()
    draw.multiline_text((x, y), text[:500], fill=color, font=font, spacing=4)
    return result


def inpaint_mask(img: Image.Image, mask: Image.Image, radius: int = 5) -> Image.Image:
    """OpenCV classical inpainting for small removals, not AI semantic reconstruction."""
    rgb = np.array(img.convert("RGB"))
    m = np.array(mask.convert("L"))
    if m.shape != rgb.shape[:2]:
        mask = mask.resize(img.size, Image.Resampling.NEAREST)
        m = np.array(mask.convert("L"))
    m = np.where(m > 32, 255, 0).astype(np.uint8)
    result = cv2.inpaint(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), m, radius, cv2.INPAINT_TELEA)
    return Image.fromarray(cv2.cvtColor(result, cv2.COLOR_BGR2RGB)).convert("RGBA")


def upscale(img: Image.Image, factor: int = 2) -> Image.Image:
    """High-quality interpolation; not generative super-resolution."""
    return img.resize((img.width * factor, img.height * factor), Image.Resampling.LANCZOS)


def as_png(img: Image.Image) -> bytes:
    output = BytesIO()
    img.save(output, format="PNG")
    return output.getvalue()

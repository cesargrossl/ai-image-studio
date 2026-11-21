"""Motor de edição: operações locais + serviços GPU acionados pelo chat."""
import base64
import io
import os
import re
from typing import Any

import cv2
import numpy as np
import requests
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

GENERATOR_URL = os.getenv("GENERATOR_URL", "http://generator:8001").rstrip("/")
SEGMENTER_URL = os.getenv("SEGMENTER_URL", "http://segmenter:8002").rstrip("/")
MAX_SIDE = int(os.getenv("MAX_IMAGE_SIDE", "3072"))


class EditError(Exception):
    pass


def image_to_b64(im: Image.Image):
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def from_b64(data: str):
    return Image.open(io.BytesIO(base64.b64decode(data))).copy()


def open_uploaded(payload: bytes):
    try:
        with Image.open(io.BytesIO(payload)) as source:
            source.load()
            if source.width * source.height > 30_000_000:
                raise EditError("Imagem grande demais (limite de 30 megapixels)")
            img = ImageOps.exif_transpose(source).copy()
            img.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
            return img.convert("RGBA")
    except EditError:
        raise
    except Exception as exc:
        raise EditError("Arquivo não é uma imagem válida") from exc


def as_rgb(img: Image.Image, bg=(255, 255, 255)):
    if img.mode not in ("RGBA", "LA"):
        return img.convert("RGB")
    layer = Image.new("RGBA", img.size, (*bg, 255))
    layer.alpha_composite(img.convert("RGBA"))
    return layer.convert("RGB")


def clamp(value, low, high, default):
    try:
        return max(low, min(high, float(value)))
    except (ValueError, TypeError):
        return default


def to_int(value, default, low, high):
    try:
        return max(low, min(high, int(value)))
    except (ValueError, TypeError):
        return default


def parse_color(value: str, default="#ffffff"):
    named = {
        "branco": "#ffffff", "white": "#ffffff", "preto": "#000000", "black": "#000000",
        "bege": "#e9dcc5", "beige": "#e9dcc5", "cinza": "#dedede", "gray": "#dedede",
        "azul": "#729fcf", "blue": "#729fcf", "rosa": "#f3bdd4", "pink": "#f3bdd4",
        "verde": "#a8cba6", "green": "#a8cba6",
    }
    word = (value or "").strip().lower()
    c = named.get(word, word)
    return c if re.fullmatch(r"#[0-9a-fA-F]{6}", c) else default


def rembg_cutout(image: Image.Image):
    # Não rode a segmentação de novo se o usuário já possui um PNG com transparência.
    if image.mode == "RGBA" and image.getchannel("A").getextrema()[0] < 255:
        return image.copy()
    try:
        from rembg import new_session, remove
        # A sessão/modelo são reutilizados enquanto o processo está ativo.
        global _REMBG_SESSION
        if _REMBG_SESSION is None:
            _REMBG_SESSION = new_session("u2net")
        result = remove(image.convert("RGB"), session=_REMBG_SESSION)
        return result.convert("RGBA")
    except Exception as exc:
        raise EditError(f"Falha no rembg: {exc}. Verifique download do modelo e logs do app.") from exc


_REMBG_SESSION = None


def http_service(url, route: str, payload: dict, title: str, timeout: int):
    try:
        response = requests.post(url + route, json=payload, timeout=(8, timeout))
    except requests.RequestException as exc:
        raise EditError(f"Serviço {title} indisponível. Inicie o perfil Docker correspondente. Detalhes: {exc}") from exc
    if response.status_code != 200:
        try:
            msg = response.json().get("detail", response.text[:300])
        except Exception:
            msg = response.text[:300]
        raise EditError(f"Erro em {title} (HTTP {response.status_code}): {msg}")
    return response.json()


def generator(mode: str, prompt: str, image: Image.Image | None = None,
              mask: Image.Image | None = None, *, strength=0.5, steps=25, seed=42,
              width=1024, height=1024):
    payload = {
        "mode": mode, "prompt": prompt, "strength": strength,
        "steps": steps, "seed": seed, "width": width, "height": height,
        "negative_prompt": "blurry, distorted, deformed fabric, duplicate products, watermark, text, bad quality"
    }
    if image is not None:
        payload["image_b64"] = image_to_b64(as_rgb(image))
    if mask is not None:
        payload["mask_b64"] = image_to_b64(mask.convert("L"))
    data = http_service(GENERATOR_URL, "/generate", payload, "gerador GPU (profile gpu)", timeout=1800)
    return from_b64(data["image_b64"]).convert("RGB")


def get_mask(image: Image.Image, step: dict, custom_mask: Image.Image | None):
    if custom_mask is not None:
        mask = custom_mask.convert("L").resize(image.size, Image.Resampling.NEAREST)
        # Áreas brancas = editar, pretas = preservar.
        return mask.point(lambda v: 255 if v > 127 else 0)
    target = str(step.get("target_en", "") or step.get("target", "")).strip()
    if not target:
        raise EditError("Informe qual objeto selecionar. Exemplo: 'remova a toalha azul'.")
    data = http_service(SEGMENTER_URL, "/segment",
                        {"image_b64": image_to_b64(as_rgb(image)), "target_en": target},
                        "segmentação automática (profile objects)", timeout=900)
    return from_b64(data["mask_b64"]).convert("L").resize(image.size)


def inpaint_local(image: Image.Image, mask: Image.Image):
    rgb = np.array(as_rgb(image))
    m = np.array(mask.convert("L"))
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    result = cv2.inpaint(bgr, m, 5, cv2.INPAINT_TELEA)
    return Image.fromarray(cv2.cvtColor(result, cv2.COLOR_BGR2RGB)).convert("RGBA")


def composite_bg(image: Image.Image, background: Image.Image):
    cutout = rembg_cutout(image)
    bg = ImageOps.fit(background.convert("RGB"), image.size, method=Image.Resampling.LANCZOS).convert("RGBA")
    bg.alpha_composite(cutout)
    return bg


def add_shadow(image: Image.Image, blur=18, offset=16, opacity=95):
    cutout = image.convert("RGBA")
    if cutout.getextrema()[3] == (255, 255):
        cutout = rembg_cutout(image)
    shadow_alpha = cutout.getchannel("A").filter(ImageFilter.GaussianBlur(blur)).point(lambda n: int(n * opacity / 255))
    shadow = Image.new("RGBA", cutout.size, (0, 0, 0, 0))
    shadow.putalpha(shadow_alpha)
    stage = Image.new("RGBA", cutout.size, "white")
    stage.alpha_composite(shadow, (0, offset))
    stage.alpha_composite(cutout)
    return stage


def font(size):
    paths = ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"]
    for path in paths:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def draw_text(image: Image.Image, text: str, color: str, position: str, size: int):
    result = image.convert("RGBA").copy()
    d = ImageDraw.Draw(result)
    f = font(size)
    bounds = d.multiline_textbbox((0, 0), text, font=f, spacing=6)
    tw, th = bounds[2] - bounds[0], bounds[3] - bounds[1]
    margin = max(10, int(min(result.size) * 0.03))
    x = margin if "left" in position else (result.width - tw - margin if "right" in position else (result.width - tw) // 2)
    y = margin if "top" in position else (result.height - th - margin if "bottom" in position else (result.height - th) // 2)
    d.multiline_text((max(0, x), max(0, y)), text, font=f, fill=parse_color(color, "#111111"), spacing=6,
                     stroke_width=1, stroke_fill="#ffffff")
    return result


def apply_one(image: Image.Image, step: dict, *, manual_mask=None, background_image=None):
    """Uma etapa; retorna (imagem editada, observação)."""
    action = step["action"]
    value = clamp(step.get("value"), 0.1, 5, 1.2)
    note = ""
    if action == "remove_background":
        return rembg_cutout(image), "Fundo removido; resultado com transparência."
    if action == "background_color":
        color = parse_color(str(step.get("color", "branco")))
        cut = rembg_cutout(image)
        bg = Image.new("RGBA", image.size, color)
        bg.alpha_composite(cut)
        return bg, f"Fundo alterado para {color}."
    if action == "background_upload":
        if background_image is None:
            raise EditError("Envie uma foto de fundo na barra lateral para utilizá-la aqui.")
        return composite_bg(image, background_image), "Fundo substituído pela imagem enviada."
    if action == "background_scene":
        scene = str(step.get("prompt_en") or step.get("prompt") or "elegant hotel bedroom, natural light")
        bg = generator("text2img", f"photorealistic empty background: {scene}. No towels, no foreground product.",
                       steps=to_int(step.get("steps"), 25, 5, 60), width=image.width, height=image.height)
        return composite_bg(image, bg), "Cenário gerado com IA; produto original recortado e preservado na frente."
    if action == "brightness":
        return ImageEnhance.Brightness(image).enhance(value), f"Brilho ×{value:.2f}."
    if action == "contrast":
        return ImageEnhance.Contrast(image).enhance(value), f"Contraste ×{value:.2f}."
    if action == "saturation":
        return ImageEnhance.Color(image).enhance(value), f"Saturação ×{value:.2f}."
    if action == "sharpness":
        return ImageEnhance.Sharpness(image).enhance(value), f"Nitidez ×{value:.2f}."
    if action == "autocorrect":
        rgb = ImageOps.autocontrast(as_rgb(image), cutoff=0.5)
        rgb = ImageEnhance.Sharpness(rgb).enhance(1.18)
        return rgb.convert("RGBA"), "Contraste e nitidez corrigidos automaticamente (sem geração)."
    if action == "white_balance":
        arr = np.array(as_rgb(image), dtype=np.float32)
        avgs = np.mean(arr, axis=(0, 1))
        balance = np.mean(avgs) / np.maximum(avgs, 1)
        corrected = np.clip(arr * balance, 0, 255).astype("uint8")
        return Image.fromarray(corrected).convert("RGBA"), "Balanço de branco ajustado."
    if action == "denoise":
        bgr = cv2.cvtColor(np.array(as_rgb(image)), cv2.COLOR_RGB2BGR)
        strength = to_int(step.get("value", 10), 10, 1, 30)
        clean = cv2.fastNlMeansDenoisingColored(bgr, None, strength, strength, 7, 21)
        return Image.fromarray(cv2.cvtColor(clean, cv2.COLOR_BGR2RGB)).convert("RGBA"), "Ruído reduzido."
    if action == "grayscale":
        return ImageOps.grayscale(image).convert("RGBA"), "Convertida para preto e branco."
    if action == "rotate":
        deg = clamp(step.get("value"), -360, 360, 90)
        return image.rotate(-deg, expand=True, fillcolor=(255, 255, 255, 0)), f"Rotacionada {deg:.0f}°."
    if action == "flip":
        direction = str(step.get("position", "horizontal"))
        return (ImageOps.flip(image) if "vertical" in direction else ImageOps.mirror(image)), "Imagem espelhada."
    if action == "upscale":
        factor = to_int(step.get("value"), 2, 2, 4)
        if image.width * image.height * factor * factor > 50_000_000:
            raise EditError("Ampliação ultrapassaria 50 megapixels")
        return image.resize((image.width * factor, image.height * factor), Image.Resampling.LANCZOS), "Ampliação por interpolação Lanczos (não é super-resolução neural)."
    if action == "resize":
        w, h = to_int(step.get("width"), image.width, 64, 6000), to_int(step.get("height"), image.height, 64, 6000)
        return image.resize((w, h), Image.Resampling.LANCZOS), f"Redimensionada para {w} × {h}."
    if action == "crop":
        pct = clamp(step.get("value"), 0.01, 0.45, 0.1)
        dx, dy = int(image.width * pct), int(image.height * pct)
        return image.crop((dx, dy, image.width - dx, image.height - dy)), f"Recorte de {pct:.0%} em cada borda."
    if action == "shadow":
        return add_shadow(image), "Sombra suave adicionada."
    if action == "blur_background":
        cut = rembg_cutout(image)
        bg = as_rgb(image).filter(ImageFilter.GaussianBlur(15)).convert("RGBA")
        bg.alpha_composite(cut)
        return bg, "Fundo desfocado preservando o objeto principal (sujeito à qualidade da máscara)."
    if action == "text":
        content = str(step.get("text") or "").strip()
        if not content:
            raise EditError("Diga qual texto deseja inserir.")
        pos = str(step.get("position") or "bottom-right")
        size = to_int(step.get("font_size"), max(20, image.width // 24), 12, 250)
        return draw_text(image, content, str(step.get("color", "#111111")), pos, size), "Texto inserido."
    if action in {"remove_object", "replace_object", "edit_region"}:
        mask = get_mask(image, step, manual_mask)
        # Suaviza as bordas e cobre pequenas sobras do objeto.
        m = np.array(mask.convert("L"))
        m = cv2.dilate(m, np.ones((9, 9), np.uint8), iterations=1)
        mask = Image.fromarray(m).convert("L")
        if action == "remove_object" and bool(step.get("fast_mode")):
            return inpaint_local(image, mask), "Objeto removido com OpenCV; resultados em regiões grandes podem ser ruins."
        target = str(step.get("target_en") or "object")
        if action == "remove_object":
            prompt = f"photorealistic clean natural background behind the removed {target}, seamlessly continue existing environment, no {target}"
        else:
            prompt = str(step.get("prompt_en") or step.get("prompt") or "").strip()
            if not prompt:
                raise EditError("Especifique o objeto ou aparência desejada para substituir a região.")
        gen = generator("inpaint", prompt, image, mask, strength=0.98,
                        steps=to_int(step.get("steps"), 30, 5, 60))
        gen = gen.resize(image.size, Image.Resampling.LANCZOS).convert("RGBA")
        feather = mask.filter(ImageFilter.GaussianBlur(radius=max(2, image.width // 350)))
        output = Image.composite(gen, image.convert("RGBA"), feather)
        return output, "Região alterada por inpainting. Revise o resultado antes de publicar."
    if action == "enhance_ai":
        prompt = str(step.get("prompt_en") or step.get("prompt") or "high-quality detailed professional product photography")
        strength = clamp(step.get("value"), 0.1, 0.8, 0.25)
        gen = generator("img2img", prompt, image, strength=strength,
                        steps=to_int(step.get("steps"), 25, 5, 60))
        return gen.resize(image.size, Image.Resampling.LANCZOS).convert("RGBA"), "Imagem reinterpretada por IA; confira fidelidade do produto."
    if action == "expand":
        pct = clamp(step.get("value"), 0.1, 0.5, 0.25)
        pad_x, pad_y = int(image.width * pct), int(image.height * pct)
        canvas = Image.new("RGBA", (image.width + 2 * pad_x, image.height + 2 * pad_y), "white")
        canvas.alpha_composite(image.convert("RGBA"), (pad_x, pad_y))
        mask = Image.new("L", canvas.size, 255)
        ImageDraw.Draw(mask).rectangle((pad_x, pad_y, pad_x + image.width - 1, pad_y + image.height - 1), fill=0)
        prompt = str(step.get("prompt_en") or "extend surrounding photorealistic environment without changing center")
        gen = generator("inpaint", prompt, canvas, mask, strength=0.99, steps=30)
        gen = gen.resize(canvas.size, Image.Resampling.LANCZOS).convert("RGBA")
        gen.alpha_composite(image.convert("RGBA"), (pad_x, pad_y))
        return gen, "Bordas expandidas por IA, mantendo a região central original."
    raise EditError(f"Ação não reconhecida: {action}")


def apply_plan(image: Image.Image, steps: list[dict[str, Any]], *, manual_mask=None, background_image=None):
    if not steps or len(steps) > 8:
        raise EditError("Peça entre 1 e 8 alterações por mensagem.")
    result = image.copy()
    notes = []
    for i, step in enumerate(steps, 1):
        try:
            result, note = apply_one(result, step, manual_mask=manual_mask, background_image=background_image)
            if max(result.size) > 9000:
                raise EditError("O resultado ultrapassou a dimensão máxima permitida")
            notes.append(f"{i}. {note}")
        except EditError as exc:
            raise EditError(f"Etapa {i} ({step.get('action', '?')}): {exc}") from exc
    return result, notes

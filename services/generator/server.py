"""API local de geração. Modelos baixados da Hugging Face na primeira solicitação."""
import base64
import gc
import io
import os
import threading
from typing import Literal

import torch
from diffusers import AutoPipelineForImage2Image, AutoPipelineForInpainting, AutoPipelineForText2Image
from fastapi import FastAPI, HTTPException
from PIL import Image, ImageOps
from pydantic import BaseModel, Field

app = FastAPI(title="AI Image Studio - GPU")
LOCK = threading.Lock()
PIPE = None
PIPE_KIND = None

BASE_MODEL = os.getenv("SDXL_BASE_MODEL", "stabilityai/stable-diffusion-xl-base-1.0")
INPAINT_MODEL = os.getenv("SDXL_INPAINT_MODEL", "diffusers/stable-diffusion-xl-1.0-inpainting-0.1")
LOW_VRAM = os.getenv("GEN_LOW_VRAM", "0") == "1"
MAX_SIDE = max(512, min(1536, int(os.getenv("GEN_MAX_SIDE", "1024"))))


class Job(BaseModel):
    mode: Literal["text2img", "img2img", "inpaint"]
    prompt: str = Field(min_length=3, max_length=3000)
    negative_prompt: str = "blurry, distorted, extra objects, watermark, text, low quality"
    image_b64: str | None = None
    mask_b64: str | None = None
    steps: int = Field(default=25, ge=5, le=60)
    guidance: float = Field(default=7.0, ge=1, le=15)
    strength: float = Field(default=0.45, ge=0.05, le=1)
    seed: int = Field(default=42, ge=0, le=4294967295)
    width: int = Field(default=1024, ge=512, le=1536)
    height: int = Field(default=1024, ge=512, le=1536)


def from_b64(encoded: str) -> Image.Image:
    try:
        data = base64.b64decode(encoded, validate=True)
        if len(data) > 40_000_000:
            raise ValueError("Imagem excede 40 MB")
        im = Image.open(io.BytesIO(data))
        im.load()
        return ImageOps.exif_transpose(im)
    except Exception as exc:
        raise HTTPException(400, f"Imagem inválida: {exc}") from exc


def to_b64(image: Image.Image) -> str:
    out = io.BytesIO()
    image.save(out, "PNG")
    return base64.b64encode(out.getvalue()).decode("ascii")


def nearest8(value: int) -> int:
    return max(512, min(MAX_SIDE, int(round(value / 8)) * 8))


def scale_size(size: tuple[int, int]):
    w, h = size
    factor = min(1.0, MAX_SIDE / max(w, h))
    return max(512, round(w * factor / 8) * 8), max(512, round(h * factor / 8) * 8)


def pipeline_for(kind: str):
    global PIPE, PIPE_KIND
    if PIPE is not None and PIPE_KIND == kind:
        return PIPE
    if PIPE is not None:
        del PIPE
        PIPE = None
        PIPE_KIND = None
        gc.collect()
        torch.cuda.empty_cache()
    model = INPAINT_MODEL if kind == "inpaint" else BASE_MODEL
    cls = {"text2img": AutoPipelineForText2Image,
           "img2img": AutoPipelineForImage2Image,
           "inpaint": AutoPipelineForInpainting}[kind]
    # Sem variante forçada: permite configurar checkpoints compatíveis com o Diffusers.
    pipe = cls.from_pretrained(model, torch_dtype=torch.float16, use_safetensors=True)
    if LOW_VRAM:
        pipe.enable_model_cpu_offload()
    else:
        pipe.to("cuda")
    pipe.set_progress_bar_config(disable=True)
    PIPE = pipe
    PIPE_KIND = kind
    return pipe


@app.get("/health")
def health():
    return {"ok": True, "cuda": torch.cuda.is_available(), "model_loaded": PIPE_KIND}


@app.post("/generate")
def generate(job: Job):
    if not torch.cuda.is_available():
        raise HTTPException(503, "GPU NVIDIA/CUDA indisponível neste contêiner")
    if job.mode != "text2img" and not job.image_b64:
        raise HTTPException(400, "O modo solicitado precisa de uma imagem de entrada")
    if job.mode == "inpaint" and not job.mask_b64:
        raise HTTPException(400, "Inpainting precisa de uma máscara de seleção")
    with LOCK:
        try:
            pipe = pipeline_for(job.mode)
            args = dict(prompt=job.prompt, negative_prompt=job.negative_prompt,
                        guidance_scale=job.guidance, num_inference_steps=job.steps,
                        generator=torch.Generator(device="cuda").manual_seed(job.seed))
            if job.mode == "text2img":
                w, h = nearest8(job.width), nearest8(job.height)
                args.update(width=w, height=h)
            else:
                original = from_b64(job.image_b64).convert("RGB")
                size = scale_size(original.size)
                args["image"] = original.resize(size, Image.Resampling.LANCZOS)
                if job.mode == "inpaint":
                    mask = from_b64(job.mask_b64).convert("L")
                    if mask.size != original.size:
                        mask = mask.resize(original.size, Image.Resampling.NEAREST)
                    args["mask_image"] = mask.resize(size, Image.Resampling.NEAREST)
                    args["strength"] = job.strength
                else:
                    args["strength"] = job.strength
            output = pipe(**args).images[0]
            return {"image_b64": to_b64(output), "width": output.width, "height": output.height}
        except torch.cuda.OutOfMemoryError as exc:
            torch.cuda.empty_cache()
            raise HTTPException(507, "GPU sem VRAM suficiente; reduza GEN_MAX_SIDE ou use GEN_LOW_VRAM=1") from exc
        except Exception as exc:
            raise HTTPException(500, f"Falha no modelo generativo: {type(exc).__name__}: {exc}") from exc

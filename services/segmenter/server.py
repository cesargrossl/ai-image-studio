"""Detecção de objetos em inglês via Grounding DINO e segmentação SAM."""
import base64
import io
import os
import threading

import numpy as np
import torch
from fastapi import FastAPI, HTTPException
from PIL import Image, ImageOps
from pydantic import BaseModel, Field
from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor, SamModel, SamProcessor

app = FastAPI(title="AI Image Studio - máscaras automáticas")
LOCK = threading.Lock()
LOADED = None


class SegmentJob(BaseModel):
    image_b64: str
    target_en: str = Field(min_length=2, max_length=160)
    threshold: float = Field(default=0.28, ge=0.05, le=0.9)


def load_models():
    global LOADED
    if LOADED is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        detector_id = os.getenv("DINO_MODEL", "IDEA-Research/grounding-dino-tiny")
        sam_id = os.getenv("SAM_MODEL", "facebook/sam-vit-base")
        dino_processor = AutoProcessor.from_pretrained(detector_id)
        dino = AutoModelForZeroShotObjectDetection.from_pretrained(detector_id).to(device).eval()
        sam_processor = SamProcessor.from_pretrained(sam_id)
        sam = SamModel.from_pretrained(sam_id).to(device).eval()
        LOADED = (device, dino_processor, dino, sam_processor, sam)
    return LOADED


def png_b64(image: Image.Image) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


@app.get("/health")
def health():
    return {"ok": True, "cuda": torch.cuda.is_available(), "models_loaded": LOADED is not None}


@app.post("/segment")
def segment(job: SegmentJob):
    with LOCK:
        try:
            data = base64.b64decode(job.image_b64, validate=True)
            if len(data) > 40_000_000:
                raise HTTPException(400, "Imagem excede 40 MB")
            image = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
            device, dp, dm, sp, sm = load_models()
            target = job.target_en.strip().rstrip(".") + "."
            inputs = dp(images=image, text=target, return_tensors="pt").to(device)
            with torch.inference_mode():
                detections = dm(**inputs)
            found = dp.post_process_grounded_object_detection(
                detections, inputs.input_ids,
                threshold=job.threshold, text_threshold=0.24,
                target_sizes=[(image.height, image.width)]
            )[0]
            boxes = found["boxes"].detach().cpu()
            if len(boxes) == 0:
                raise HTTPException(422, f"Não identifiquei '{job.target_en}' na foto. Tente outra descrição ou envie uma máscara.")
            # Apenas o objeto mais confiante; mais seguro para não remover vários produtos.
            best = int(found["scores"].argmax().item())
            box = boxes[best].tolist()
            sam_inputs = sp(image, input_boxes=[[box]], return_tensors="pt").to(device)
            with torch.inference_mode():
                result = sm(**sam_inputs, multimask_output=True)
            masks = sp.image_processor.post_process_masks(
                result.pred_masks.detach().cpu(),
                sam_inputs["original_sizes"].detach().cpu(),
                sam_inputs["reshaped_input_sizes"].detach().cpu()
            )
            choice = int(result.iou_scores[0, 0].argmax().item())
            mask = np.asarray(masks[0][0, choice], dtype=np.uint8) * 255
            return {"mask_b64": png_b64(Image.fromarray(mask, mode="L")),
                    "box": box, "score": round(float(found["scores"][best].item()), 3)}
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(500, f"Falha na segmentação: {type(exc).__name__}: {exc}") from exc

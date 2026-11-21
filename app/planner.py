"""Traduz pedidos em português para planos de edição validados (Ollama ou regras locais)."""
import json
import os
import re
import unicodedata
from dataclasses import dataclass

import requests

ACTIONS = [
    "remove_background", "background_color", "background_upload", "background_scene",
    "brightness", "contrast", "saturation", "sharpness", "autocorrect",
    "white_balance", "denoise", "grayscale", "rotate", "flip", "upscale",
    "resize", "crop", "shadow", "blur_background", "text",
    "remove_object", "replace_object", "edit_region", "enhance_ai", "expand",
]

SCHEMA = {
    "type": "object",
    "properties": {
        "steps": {
            "type": "array", "maxItems": 8,
            "items": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ACTIONS},
                    "value": {"type": "number"},
                    "color": {"type": "string"},
                    "text": {"type": "string"},
                    "position": {"type": "string"},
                    "font_size": {"type": "integer"},
                    "width": {"type": "integer"},
                    "height": {"type": "integer"},
                    "prompt_en": {"type": "string"},
                    "target_en": {"type": "string"},
                    "steps": {"type": "integer"},
                    "fast_mode": {"type": "boolean"}
                },
                "required": ["action"],
            }
        },
        "question": {"type": "string"},
        "explanation": {"type": "string"}
    },
    "required": ["steps", "question", "explanation"]
}

SYSTEM = """You are an image-editing ACTION PLANNER, not an image editor. User speaks Brazilian Portuguese.
Return ONLY valid JSON matching schema. Do not claim an edit was applied.
Make action steps in the natural requested order, MAXIMUM 8, from this whitelist:
remove_background: remove entire background, return transparent image (not a specific object).
background_color: remove background and fill solid color; color named Portuguese/English or #RRGGBB.
background_upload: use the background photo uploaded in sidebar.
background_scene: generate a new photographic SCENE background, then place original cutout product on top. prompt_en MUST be detailed English description of EMPTY scene without subject.
brightness, contrast, saturation, sharpness: value is multiplier 1 normal, 1.20 +20%, 0.80 -20%. Range 0.1..5.
autocorrect: basic improvements preserving image fidelity.
white_balance, denoise (value is strength from 1 to 30), grayscale.
rotate: value is clockwise degrees. flip: position horizontal or vertical.
upscale: value 2, 3 or 4, only interpolation (not neural).
resize: width/height absolute pixels.
crop: value = fraction to remove on every border (0.1 means 10%).
shadow, blur_background, text (text exact user wording; position top-left/top-right/bottom-left/bottom-right/center, color and optional font_size).
remove_object: user wants to delete a SPECIFIC object. Provide target_en in ENGLISH (e.g. 'white bath towel'), do NOT use remove_background.
replace_object: user wants to replace one object. target_en (original object to detect) and prompt_en (new object's realistic English description).
edit_region: change an object/region. target_en and prompt_en English.
enhance_ai: generatively revise photograph, but may change product identity. prompt_en detailed in English; value strength 0.1..0.8.
expand: extend canvas around the photo, value fraction, prompt_en environment.
When removing a particular object automatically, the detector selects ONE detected object. If target unclear, ask in question, steps empty.
For regular enhancement: prefer autocorrect/brightness/etc (no generator). When creating scene or changing objects, plan GPU generation actions.
Do not invent additional features or actions. Do not ask if clear. Keep explanation short Portuguese, leave question empty when clear.
Examples:
'Remova o fundo e coloque um fundo branco' -> [{action:'background_color',color:'branco'}].
'Remova uma toalha azul da foto' -> [{action:'remove_object',target_en:'blue towel'}].
'Coloque a toalha em um banheiro de luxo' -> [{action:'background_scene',prompt_en:'luxury bathroom with marble vanity and daylight, empty foreground area'}].
'Aumente brilho 20% e contraste 10%' -> [{action:'brightness',value:1.2},{action:'contrast',value:1.1}].
'Troque a toalha azul por uma branca' -> [{action:'replace_object',target_en:'blue towel',prompt_en:'a single white cotton bath towel matching existing perspective and lighting'}].
"""


@dataclass
class Plan:
    steps: list[dict]
    explanation: str = ""
    question: str = ""
    source: str = ""


def clean_text(s: str):
    return "".join(c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c))


def validate(raw: dict):
    if not isinstance(raw, dict) or not isinstance(raw.get("steps"), list):
        raise ValueError("Plano de edição inválido")
    steps = raw["steps"]
    if len(steps) > 8:
        raise ValueError("Pedido contém mais de 8 etapas")
    result = []
    for s in steps:
        if not isinstance(s, dict) or s.get("action") not in ACTIONS:
            raise ValueError("Ação de edição inválida")
        result.append({k: v for k, v in s.items() if k in SCHEMA["properties"]["steps"]["items"]["properties"]})
    return Plan(result, str(raw.get("explanation") or ""), str(raw.get("question") or ""), "Ollama")


def ollama_plan(text: str, recent_messages=None):
    url = os.getenv("OLLAMA_URL", "http://ollama:11434").rstrip("/")
    model = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
    messages = [{"role": "system", "content": SYSTEM}]
    # Somente contexto de instruções, nunca o conteúdo de imagens.
    for m in (recent_messages or [])[-6:]:
        if m.get("role") == "user":
            messages.append({"role": "user", "content": str(m.get("content", ""))[:500]})
    messages.append({"role": "user", "content": text[:2000]})
    response = requests.post(url + "/api/chat", json={
        "model": model, "stream": False, "format": SCHEMA, "messages": messages,
        "options": {"temperature": 0.0, "num_ctx": 4096}}, timeout=(5, 180))
    response.raise_for_status()
    answer = response.json()["message"]["content"]
    return validate(json.loads(answer))


def extract_target(s: str):
    plain = clean_text(s)
    translations = {
        "toalha": "towel", "roupao": "bathrobe", "lencol": "bed sheet", "travesseiro": "pillow",
        "almofada": "cushion", "cobertor": "blanket", "colcha": "bedspread",
        "pessoa": "person", "copo": "glass", "vaso": "vase", "cadeira": "chair",
        "mesa": "table", "cama": "bed", "flor": "flower", "quadro": "picture frame",
        "etiqueta": "label", "logo": "logo",
    }
    for k, v in translations.items():
        if k in plain:
            color = next((en for pt, en in [("branca", "white"), ("branco", "white"), ("azul", "blue"), ("vermelha", "red"), ("preta", "black"), ("preto", "black")] if pt in plain), "")
            return (color + " " + v).strip()
    return ""


def amount_for(s: str, base=1.2, variants=None):
    """Extrai percentual próximo da propriedade; evita repetir o % do brilho no contraste."""
    segment = s
    prefix = ""
    if variants:
        places = [s.find(word) for word in variants if word in s]
        if places:
            start = min(i for i in places if i >= 0)
            # Percorre até a próxima instrução de edição.
            prefix = s[max(0, start-32):start].split(" e ")[-1].split(", ")[-1]
            tail = s[start:]
            next_action = re.search(r"\b(?:e |depois |, )?(?:brilho|contraste|saturacao|nitidez)\b", tail[2:])
            if next_action:
                segment = tail[:next_action.start() + 2]
            else:
                segment = tail
    m = re.search(r"(\d+(?:[,.]\d+)?)\s*%", segment)
    if not m:
        return base
    pct = min(100, float(m.group(1).replace(",", "."))) / 100
    negative = any(word in segment or word in prefix for word in ["reduz", "dimin", "menos", "abaix"])
    return max(0.1, 1 - pct) if negative else 1 + pct


def fallback_plan(text: str):
    """Modo limitado sem Ollama: reconhece instruções comuns sem fingir entender todos os pedidos."""
    s = clean_text(text)
    result = []
    def add(action, **params):
        result.append({"action": action, **params})
    if "fundo" in s and any(w in s for w in ["remov", "retir", "apag", "tirar"]):
        if any(c in s for c in ["branco", "bege", "preto", "cinza", "azul", "rosa"]):
            color = next(c for c in ["branco", "bege", "preto", "cinza", "azul", "rosa"] if c in s)
            add("background_color", color=color)
        else:
            add("remove_background")
    elif "fundo" in s and any(w in s for w in ["troqu", "substit", "coloqu", "muda", "deix", "altere"]):
        color = next((c for c in ["branco", "bege", "preto", "cinza", "azul", "rosa"] if c in s), "")
        if color:
            add("background_color", color=color)
        elif any(w in s for w in ["enviada", "upload", "anexada"]):
            add("background_upload")
        elif any(w in s for w in ["quarto", "banheiro", "hotel", "praia", "cozinha"]):
            place = next(p for p in ["quarto", "banheiro", "hotel", "praia", "cozinha"] if p in s)
            en = {"quarto": "bright elegant bedroom", "banheiro": "luxury bathroom", "hotel": "boutique hotel room", "praia": "sunny beach", "cozinha": "modern kitchen"}[place]
            add("background_scene", prompt_en=f"photorealistic {en}, clean empty foreground, natural lighting")
    # Intencionalmente não converte 'remova uma toalha' em remoção de fundo.
    if not result and any(w in s for w in ["remova", "remover", "retire", "retirar", "apague", "tirar"]):
        target = extract_target(s)
        if target:
            add("remove_object", target_en=target)
    for name, variants in [
        ("brightness", ["brilho", "clarear", "clareie", "iluminacao"]),
        ("contrast", ["contraste"]),
        ("saturation", ["saturacao", "vibrancia"]),
        ("sharpness", ["nitidez", "nítida", "nitida"]),
    ]:
        if any(k in s for k in variants):
            add(name, value=amount_for(s, variants=variants))
    if any(k in s for k in ["melhore a imagem", "melhorar imagem", "melhore a foto", "melhorar foto", "corrija automaticamente"]):
        add("autocorrect")
    if "preto e branco" in s:
        add("grayscale")
    if "sombra" in s:
        add("shadow")
    if any(k in s for k in ["desfoque o fundo", "desfocar fundo", "fundo desfocado"]):
        add("blur_background")
    if "ampli" in s or "aumente a resolucao" in s:
        add("upscale", value=2)
    if any(k in s for k in ["inserir texto", "adicione o texto", "escreva"]):
        match = re.search(r'["“](.+?)["”]', text)
        if match:
            add("text", text=match.group(1), position="bottom-right")
    if "troque" in s and "toalha" in s and not result:
        return Plan([], question="Qual toalha deseja substituir e qual deve ficar no lugar?", source="regras locais")
    if not result:
        return Plan([], question="Não consegui interpretar este pedido sem o Ollama. Descreva uma edição mais específica ou ative o modelo.", source="regras locais")
    return Plan(result[:8], explanation="Plano interpretado por regras locais (Ollama indisponível).", source="regras locais")


def build_plan(text: str, messages=None):
    if len(text.strip()) < 3:
        return Plan([], question="Descreva a alteração que deseja fazer.")
    try:
        plan = ollama_plan(text, messages)
        if not plan.steps and not plan.question:
            return Plan([], question="Descreva com mais detalhes o que deseja alterar.", source="Ollama")
        return plan
    except (ValueError, KeyError, json.JSONDecodeError, requests.RequestException):
        return fallback_plan(text)

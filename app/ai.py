import os
import json
import requests

OLLAMA = os.getenv("OLLAMA_URL", "http://ollama:11434")
MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")


def parse_instruction(text: str) -> dict:
    """Constrained extraction; app asks user to confirm before running an action."""
    schema = '''Return ONLY valid JSON with keys: action (one of remove_background, background_white, background_beige, brightness, contrast, remove_object, generative, unknown), amount (number 0..100), explanation (short Portuguese text). Do not output Markdown. For removing a named object choose remove_object. For replacing a scene choose generative. For a background removal choose remove_background.'''
    r = requests.post(f"{OLLAMA}/api/chat", json={"model": MODEL, "stream": False, "format": "json", "messages": [
        {"role": "system", "content": schema}, {"role": "user", "content": text[:1500]}]}, timeout=180)
    r.raise_for_status()
    obj = json.loads(r.json()["message"]["content"])
    if obj.get("action") not in {"remove_background", "background_white", "background_beige", "brightness", "contrast", "remove_object", "generative", "unknown"}:
        obj["action"] = "unknown"
    return obj

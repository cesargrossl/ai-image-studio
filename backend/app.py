import io
import os
import re
import requests
import streamlit as st
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter
from rembg import remove

st.set_page_config(page_title="AI Image Studio", page_icon="🖼️", layout="wide")
st.title("AI Image Studio — edição de imagens")
password = os.getenv("APP_PASSWORD", "troque-esta-senha")
if not password or password == "troque-esta-senha":
    st.error("Configure APP_PASSWORD no arquivo .env antes de utilizar.")
    st.stop()
if not st.session_state.get("authenticated"):
    with st.form("login"):
        pwd = st.text_input("Senha", type="password")
        if st.form_submit_button("Entrar"):
            if pwd == password:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Senha incorreta")
    st.stop()

uploaded = st.file_uploader("Envie uma imagem", type=["png", "jpg", "jpeg", "webp"])
prompt = st.text_area("Descreva a edição", placeholder="Remova o fundo, coloque fundo branco, adicione sombra e o texto Promoção")

def parse_instruction(text):
    # A interpretação local funciona mesmo sem LLM; o modelo é opcional.
    t = text.lower()
    cfg = {"remove_background": any(x in t for x in ["remova o fundo", "remover fundo", "retire o fundo", "sem fundo", "fundo transparente", "fundo branco", "fundo bege"]),
           "background": "transparent", "shadow": "sombra" in t,
           "brightness": "clarear" in t or "mais brilho" in t,
           "text": ""}
    if "fundo branco" in t: cfg["background"] = "white"
    elif "fundo bege" in t: cfg["background"] = "beige"
    m = re.search(r'(?:texto|escreva|adicione a frase|inserir texto)\s*[:\-]?\s*["“](.+?)["”]', text, re.I)
    if not m:
        m = re.search(r'(?:texto|escreva)\s*:\s*(.+)', text, re.I)
    if m: cfg["text"] = m.group(1).strip()
    return cfg

def edit_image(img, cfg):
    img = img.convert("RGBA")
    if cfg["remove_background"]:
        img = remove(img)
    if cfg["brightness"]:
        rgb = ImageEnhance.Brightness(img.convert("RGB")).enhance(1.2)
        rgb.putalpha(img.getchannel("A"))
        img = rgb
    w, h = img.size
    if cfg["background"] != "transparent":
        color = (255,255,255,255) if cfg["background"] == "white" else (240,230,210,255)
        base = Image.new("RGBA", (w,h), color)
    else:
        base = Image.new("RGBA", (w,h), (0,0,0,0))
    if cfg["shadow"]:
        alpha = img.getchannel("A")
        shadow = Image.new("RGBA", (w,h), (0,0,0,0))
        shadow.putalpha(alpha.point(lambda a: int(a*0.32)))
        shadow = shadow.filter(ImageFilter.GaussianBlur(max(3,w//65)))
        base.alpha_composite(shadow, (min(12,w//40), min(12,h//40)))
    base.alpha_composite(img)
    if cfg["text"]:
        draw = ImageDraw.Draw(base)
        try: font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", max(16,w//20))
        except OSError: font = ImageFont.load_default()
        draw.text((max(10,w//25), max(10,h//25)), cfg["text"], fill=(25,25,25,255), font=font, stroke_width=1, stroke_fill=(255,255,255,255))
    return base

if uploaded:
    try:
        original = Image.open(uploaded)
        if original.width * original.height > 25_000_000:
            st.error("Imagem muito grande: máximo de 25 megapixels")
            st.stop()
        st.image(original, caption="Original", width=450)
        if st.button("Aplicar edição", type="primary"):
            if not prompt.strip():
                st.warning("Descreva a edição desejada")
            else:
                with st.spinner("Processando imagem (o primeiro uso pode baixar o modelo U²-Net)..."):
                    cfg = parse_instruction(prompt)
                    output = edit_image(original, cfg)
                    st.session_state.result = output
                    st.session_state.cfg = cfg
        if "result" in st.session_state:
            st.image(st.session_state.result, caption="Resultado", width=450)
            b = io.BytesIO()
            st.session_state.result.save(b, format="PNG")
            st.download_button("Baixar PNG", b.getvalue(), file_name="imagem_editada.png", mime="image/png")
            st.caption("Recursos deste MVP: remoção de fundo, fundo branco/bege, sombra, brilho e texto. Não inclui edição generativa por prompt.")
    except Exception as e:
        st.error(f"Erro ao processar imagem: {e}")

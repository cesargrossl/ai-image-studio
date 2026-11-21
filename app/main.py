import os
import hmac
import json
from pathlib import Path
from datetime import datetime, timezone
from io import BytesIO
import streamlit as st
from PIL import Image, ImageDraw
from processing import read_image, remove_background, apply_background, adjust, shadow, add_text, inpaint_mask, upscale, as_png

st.set_page_config(page_title="AI Image Studio", page_icon="🖼️", layout="wide")
DATA = Path(os.getenv("DATA_DIR", "/data"))
for folder in ("originals", "edited", "masks"):
    (DATA / folder).mkdir(parents=True, exist_ok=True)


def authenticated():
    expected = os.getenv("APP_PASSWORD", "")
    if not expected or expected == "troque-esta-senha-forte":
        st.error("Configure uma senha forte em APP_PASSWORD no .env e recrie o contêiner.")
        st.stop()
    if st.session_state.get("logged_in"):
        return True
    st.title("🔒 AI Image Studio")
    pwd = st.text_input("Senha de acesso", type="password")
    if st.button("Entrar", type="primary"):
        if hmac.compare_digest(pwd, expected):
            st.session_state.logged_in = True
            st.rerun()
        else:
            st.error("Senha incorreta")
    st.stop()


authenticated()
st.title("🖼️ AI Image Studio")
st.caption("Edição local de imagens · ferramentas tradicionais e segmentação por IA · Ollama opcional")

with st.sidebar:
    st.header("Projeto")
    st.write("Ajustes, fundo, sombra, texto, remoção com máscara e histórico.")
    if st.button("Sair"):
        st.session_state.logged_in = False
        st.rerun()
    st.warning("A remoção de objetos por máscara usa OpenCV e funciona melhor em áreas pequenas. Cenários gerados por IA requerem workflow/modelo adicional.")

upload = st.file_uploader("Envie sua imagem", type=["png", "jpg", "jpeg", "webp"])
if upload is not None:
    file_bytes = upload.getvalue()
    import hashlib
    signature = hashlib.sha256(file_bytes).hexdigest()
    if st.session_state.get("signature") != signature:
        try:
            image = read_image(file_bytes)
        except Exception as exc:
            st.error(f"Arquivo inválido: {exc}")
            st.stop()
        st.session_state.signature = signature
        st.session_state.original = image
        st.session_state.image = image.copy()
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        st.session_state.session_file = f"{stamp}_{signature[:10]}"
        (DATA / "originals" / f"{st.session_state.session_file}.png").write_bytes(as_png(image))

if "image" not in st.session_state:
    st.info("Selecione uma imagem para começar. Depois use as abas para editar.")
    st.stop()

image = st.session_state.image
original = st.session_state.original
left, right = st.columns(2)
with left:
    st.subheader("Original")
    st.image(original, use_container_width=True)
with right:
    st.subheader("Resultado")
    st.image(image, use_container_width=True)

if st.button("↩️ Restaurar original"):
    st.session_state.image = original.copy()
    st.rerun()

tabs = st.tabs(["🎨 Ajustes", "🧼 Fundo", "✂️ Remover objeto", "📝 Texto", "🔎 Ampliar", "💬 Comandos", "📁 Histórico"])
with tabs[0]:
    brightness = st.slider("Brilho", 0.2, 3.0, 1.0, 0.05)
    contrast = st.slider("Contraste", 0.2, 3.0, 1.0, 0.05)
    saturation = st.slider("Saturação", 0.0, 3.0, 1.0, 0.05)
    sharpness = st.slider("Nitidez", 0.0, 3.0, 1.0, 0.05)
    if st.button("Aplicar ajustes"):
        st.session_state.image = adjust(image, brightness, contrast, saturation, sharpness)
        st.rerun()
with tabs[1]:
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Remover fundo com IA"):
            with st.spinner("Processando (primeira execução pode baixar o modelo)..."):
                try:
                    st.session_state.image = remove_background(image)
                    st.rerun()
                except Exception as exc:
                    st.error(f"Falha na remoção do fundo: {exc}")
    with col2:
        bg_color = st.color_picker("Cor do novo fundo", "#FFFFFF")
        if st.button("Aplicar cor de fundo"):
            st.session_state.image = apply_background(image, bg_color)
            st.rerun()
    if st.button("Adicionar sombra"):
        st.session_state.image = shadow(image)
        st.rerun()
with tabs[2]:
    st.write("Desenhe sobre o objeto que deseja remover. Para áreas grandes ou fundos complexos, o resultado pode ser limitado.")
    try:
        from streamlit_drawable_canvas import st_canvas
        preview = image.convert("RGB")
        w, h = preview.size
        scale = min(1.0, 700 / max(w, 1))
        sw, sh = max(1, int(w * scale)), max(1, int(h * scale))
        resized = preview.resize((sw, sh))
        brush = st.slider("Espessura do pincel", 5, 90, 25)
        canvas = st_canvas(fill_color="rgba(255,0,0,0.35)", stroke_width=brush,
                           stroke_color="#FF0000", background_image=resized,
                           update_streamlit=True, height=sh, width=sw, drawing_mode="freedraw", key=f"mask_{st.session_state.signature}")
        if st.button("Remover área marcada"):
            if canvas.image_data is None:
                st.warning("Desenhe primeiro sobre o objeto.")
            else:
                import numpy as np
                # Canvas alpha can contain background; use red-dominant pixels as mask.
                arr = canvas.image_data.astype("int16")
                selected = ((arr[:, :, 0] > arr[:, :, 1] + 70) & (arr[:, :, 0] > arr[:, :, 2] + 70)).astype("uint8") * 255
                if selected.max() == 0:
                    st.warning("Nenhuma marcação vermelha encontrada.")
                else:
                    mask = Image.fromarray(selected, mode="L").resize(image.size, Image.Resampling.NEAREST)
                    (DATA / "masks" / f"{st.session_state.session_file}.png").write_bytes(as_png(mask.convert("RGBA")))
                    st.session_state.image = inpaint_mask(image, mask)
                    st.rerun()
    except Exception as exc:
        st.error(f"Editor de máscara indisponível: {exc}")
with tabs[3]:
    text = st.text_input("Texto a inserir", "")
    size = st.slider("Tamanho da fonte", 12, 150, 32)
    color = st.color_picker("Cor do texto", "#000000")
    x = st.number_input("Posição X", 0, image.width, 20)
    y = st.number_input("Posição Y", 0, image.height, 20)
    if st.button("Inserir texto") and text:
        st.session_state.image = add_text(image, text, x, y, size, color)
        st.rerun()
with tabs[4]:
    st.caption("Ampliação Lanczos (não é super-resolução generativa).")
    if st.button("Ampliar 2×"):
        if image.width * image.height * 4 > 24_000_000:
            st.error("Ampliação excederia 24 megapixels.")
        else:
            st.session_state.image = upscale(image)
            st.rerun()
with tabs[5]:
    st.write("O Ollama pode interpretar o pedido e sugerir uma operação. Confirme antes de aplicar.")
    command = st.text_area("Seu pedido", placeholder="Ex.: aumente o brilho em 20%")
    if st.button("Interpretar com Ollama") and command:
        try:
            from ai import parse_instruction
            with st.spinner("Consultando Ollama..."):
                st.session_state.proposal = parse_instruction(command)
        except Exception as exc:
            st.error(f"Ollama indisponível ou modelo não baixado: {exc}")
    proposal = st.session_state.get("proposal")
    if proposal:
        st.json(proposal)
        action = proposal.get("action")
        if action in {"remove_object", "generative"}:
            st.info("Para remoção de objetos, use a aba de máscara. Para cenas generativas, configure um workflow no ComfyUI.")
        elif action in {"remove_background", "background_white", "background_beige", "brightness", "contrast"}:
            if st.button("Confirmar e aplicar comando"):
                try:
                    amount = min(100, max(0, float(proposal.get("amount") or 20)))
                    if action == "remove_background": result = remove_background(image)
                    elif action == "background_white": result = apply_background(image, "white")
                    elif action == "background_beige": result = apply_background(image, "#E8DCC8")
                    elif action == "brightness": result = adjust(image, 1 + amount/100, 1, 1, 1)
                    else: result = adjust(image, 1, 1 + amount/100, 1, 1)
                    st.session_state.image = result
                    st.session_state.proposal = None
                    st.rerun()
                except Exception as exc:
                    st.error(f"Falha na operação: {exc}")
with tabs[6]:
    files = sorted((DATA / "edited").glob("*.png"), reverse=True)[:30]
    st.write(f"Últimas {len(files)} edições salvas")
    for f in files:
        st.text(f.name)

st.divider()
if st.button("💾 Salvar edição no histórico"):
    name = f"{st.session_state.session_file}_{datetime.now(timezone.utc).strftime('%H%M%S%f')}.png"
    (DATA / "edited" / name).write_bytes(as_png(st.session_state.image))
    st.success(f"Salvo: {name}")
st.download_button("⬇️ Baixar imagem PNG", data=as_png(st.session_state.image), file_name="imagem_editada.png", mime="image/png", type="primary")

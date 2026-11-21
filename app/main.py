"""AI Image Studio — tudo começa no chat, inclusive o envio de fotos."""
import io
import os
from pathlib import Path

import requests
import streamlit as st
from PIL import Image

import db
from planner import build_plan
from processor import EditError, apply_plan, open_uploaded

st.set_page_config(page_title="AI Image Studio • Chat", page_icon="🖼️", layout="wide")
st.markdown("""<style>
.block-container{padding-top:1.6rem;max-width:1250px}
[data-testid="stChatMessage"]{border-radius:12px}
small{color:#778}
</style>""", unsafe_allow_html=True)


@st.cache_resource
def initialize():
    db.init_db()
    return True


try:
    initialize()
except Exception as exc:
    st.error(f"Configuração inicial inválida: {exc}")
    st.info("Edite o arquivo .env com APP_PASSWORD e recrie o contêiner: docker compose up -d --force-recreate")
    st.stop()


def service_status(url: str):
    try:
        result = requests.get(url + "/health", timeout=2)
        if result.ok:
            info = result.json()
            if "cuda" in info and not info["cuda"]:
                return "🟠 Serviço online, mas sem GPU CUDA"
            return "🟢 Online"
        return "🔴 Indisponível"
    except requests.RequestException:
        return "⚪ Não iniciado"


def login():
    st.title("🖼️ AI Image Studio")
    st.caption("Editor de imagens por conversação • Docker local")
    with st.form("login"):
        username = st.text_input("Usuário", value=os.getenv("APP_ADMIN_USER", "admin"))
        password = st.text_input("Senha", type="password")
        submit = st.form_submit_button("Entrar", type="primary")
        if submit:
            if db.authenticate(username.strip(), password):
                st.session_state["username"] = username.strip()
                st.rerun()
            else:
                st.error("Usuário ou senha incorretos. Confira APP_ADMIN_USER/APP_PASSWORD no .env e recrie o contêiner.")
    st.caption("O administrador é configurado no .env. Senhas dos demais usuários são criadas pelo administrador.")
    st.stop()


if "username" not in st.session_state:
    login()

username = st.session_state["username"]
if not db.list_projects(username) and "active_project" not in st.session_state:
    st.session_state.active_project = None

with st.sidebar:
    st.header("🖼️ AI Image Studio")
    st.caption(f"Conectado: **{username}**")
    if st.button("Sair", use_container_width=True):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()

    st.divider()
    st.subheader("Projetos")
    projects = db.list_projects(username)
    selected_project = st.session_state.get("active_project")
    if selected_project and selected_project not in {p["id"] for p in projects}:
        selected_project = None
    if st.button("＋ Novo projeto", use_container_width=True):
        st.session_state.active_project = None
        st.rerun()
    if projects:
        options = [p["id"] for p in projects]
        if selected_project is None and not st.session_state.get("new_project_open"):
            # Em modo novo, o usuário ainda pode enviar um novo arquivo via chat.
            pass
        selected = st.selectbox("Abrir projeto existente", options=[""] + options,
                                format_func=lambda i: "Selecione..." if i == "" else next(p["name"] for p in projects if p["id"] == i),
                                index=(options.index(selected_project) + 1) if selected_project in options else 0,
                                key=f"choose_project_{selected_project or 'new'}")
        if selected and selected != selected_project:
            st.session_state.active_project = selected
            st.rerun()

    st.divider()
    st.subheader("Edição avançada (opcional)")
    uploaded_mask = st.file_uploader("Máscara PNG (branco = editar, preto = manter)", type=["png"], key="mask")
    uploaded_bg = st.file_uploader("Foto de fundo para substituir cenário", type=["png", "jpg", "jpeg", "webp"], key="bg")
    manual_mask = None
    bg_image = None
    if uploaded_mask:
        try:
            manual_mask = Image.open(io.BytesIO(uploaded_mask.getvalue())).convert("L")
            st.caption("Máscara carregada: será usada nos comandos de remover/trocar objetos.")
        except Exception:
            st.error("Máscara PNG inválida")
    if uploaded_bg:
        try:
            bg_image = open_uploaded(uploaded_bg.getvalue())
            st.caption("Fundo enviado: peça 'troque pelo fundo que enviei'.")
        except Exception:
            st.error("Imagem de fundo inválida")
    st.divider()
    with st.expander("Serviços de IA"):
        st.caption("Os serviços opcionais são carregados somente quando usados.")
        st.write("Geração:", service_status(os.getenv("GENERATOR_URL", "http://generator:8001")))
        st.write("Seleção de objetos:", service_status(os.getenv("SEGMENTER_URL", "http://segmenter:8002")))
        st.caption("Ollama: use `docker compose exec ollama ollama list` para confirmar os modelos baixados.")
    if db.is_admin(username):
        with st.expander("Administrar usuários"):
            with st.form("new_user", clear_on_submit=True):
                new_user = st.text_input("Novo nome de usuário")
                new_pass = st.text_input("Senha inicial (mín. 10 caracteres)", type="password")
                if st.form_submit_button("Criar usuário"):
                    try:
                        db.create_user(new_user, new_pass)
                        st.success(f"Usuário {new_user} criado")
                    except Exception as exc:
                        st.error(f"Não foi possível criar: {exc}")
            st.caption("Usuários: " + ", ".join(db.list_users()))

st.title("💬 AI Image Studio")
st.caption("Anexe uma foto ao chat e peça qualquer alteração. Cada nova imagem abre um projeto com histórico próprio.")

with st.expander("Exemplos de comandos que você pode pedir", expanded=False):
    st.markdown("""- Remova o fundo e coloque um fundo branco.
- Aumente o brilho 20%, o contraste 10% e melhore a nitidez.
- Remova a toalha azul e reconstrua o fundo.
- Troque a toalha azul por uma toalha branca.
- Coloque o produto em um quarto de hotel moderno com iluminação natural.
- Coloque o fundo enviado e adicione uma sombra suave.
- Desfoque o fundo e insira o texto \"Linha Premium\".
- Melhore a fotografia e corrija o balanço de branco.
- Amplie a resolução duas vezes.
- Expanda as bordas da foto para caber em formato horizontal.""")

project_id = st.session_state.get("active_project")
if project_id:
    versions = db.versions(project_id, username)
    if versions:
        left, right = st.columns(2)
        original = Image.open(versions[0]["file_path"])
        latest = Image.open(versions[-1]["file_path"])
        with left:
            st.subheader("Original")
            st.image(original, use_container_width=True)
        with right:
            st.subheader(f"Resultado • versão {versions[-1]['version_num']}")
            st.image(latest, use_container_width=True)
            buf = io.BytesIO()
            latest.save(buf, "PNG")
            st.download_button("⬇️ Baixar imagem PNG", buf.getvalue(),
                               file_name=f"imagem_editada_v{versions[-1]['version_num']}.png", mime="image/png")
        with st.expander("Histórico de versões / restaurar"):
            if len(versions) > 1:
                numbers = [v["version_num"] for v in versions]
                choice = st.select_slider("Ver versão", options=numbers, value=numbers[-1])
                item = next(v for v in versions if v["version_num"] == choice)
                st.image(item["file_path"], width=350)
                st.caption(item["instruction"])
                if st.button("Restaurar esta versão como nova edição"):
                    restore = Image.open(item["file_path"]).copy()
                    db.write_version(project_id, username, restore, f"Restauração da versão {choice}")
                    st.rerun()
            else:
                st.caption("O projeto ainda contém somente a foto original.")
        st.divider()
        for m in db.chat_history(project_id, username):
            with st.chat_message(m["role"]):
                st.markdown(m["content"])
else:
    st.info("📎 Para começar, clique no ícone de anexo do campo de chat, escolha sua foto e escreva uma instrução. Também pode anexar só a foto.")

input_value = st.chat_input("Ex.: remova a toalha azul e coloque outra branca...", accept_file=True,
                            file_type=["jpg", "jpeg", "png", "webp"], key="main_chat")

if input_value:
    prompt = (input_value.text or "").strip()
    images = list(input_value.files or [])
    if images:
        selected_img = images[0]
        max_mb = int(os.getenv("MAX_IMAGE_MB", "20"))
        if len(selected_img.getvalue()) > max_mb * 1024 * 1024:
            st.error(f"Imagem excede o limite de {max_mb} MB")
            st.stop()
        try:
            photo = open_uploaded(selected_img.getvalue())
            name = Path(selected_img.name).stem[:80] or "Nova fotografia"
            project_id = db.create_project(username, name)
            db.write_version(project_id, username, photo, "Imagem original enviada pelo chat")
            st.session_state.active_project = project_id
            st.success(f"Foto '{selected_img.name}' recebida. Novo projeto criado.")
        except Exception as exc:
            st.error(f"Não foi possível receber a foto: {exc}")
            st.stop()
    if not project_id:
        st.warning("Primeiro anexe a imagem na conversa usando o ícone de anexo do chat.")
        st.stop()
    if not prompt:
        db.add_message(project_id, username, "assistant", "Imagem recebida. Qual alteração você deseja fazer?")
        st.rerun()
    db.add_message(project_id, username, "user", prompt)
    current_version = db.versions(project_id, username)[-1]
    current = Image.open(current_version["file_path"]).copy()
    with st.chat_message("assistant"):
        with st.spinner("Interpretando o comando e processando a imagem..."):
            prior = db.chat_history(project_id, username)
            plan = build_plan(prompt, prior[:-1])
            if not plan.steps:
                reply = plan.question or "Não consegui montar um plano de edição para esse pedido."
                st.info(reply)
                db.add_message(project_id, username, "assistant", reply)
            else:
                st.caption("Plano: " + " → ".join(s["action"] for s in plan.steps))
                try:
                    processed, notes = apply_plan(current, plan.steps,
                                                  manual_mask=manual_mask, background_image=bg_image)
                    db.write_version(project_id, username, processed, prompt)
                    answer = "✅ **Edição aplicada**\n\n" + "\n\n".join(notes)
                    if plan.source == "regras locais":
                        answer += "\n\n*O modelo Ollama não respondeu; usei o interpretador local limitado.*"
                    db.add_message(project_id, username, "assistant", answer)
                    st.success("Imagem editada. Veja a comparação e baixe o PNG acima.")
                except EditError as exc:
                    answer = f"❌ **Edição não concluída:** {exc}\n\nA imagem anterior foi preservada."
                    db.add_message(project_id, username, "assistant", answer)
                    st.error(answer)
                except Exception as exc:
                    # Nunca dizer que a operação ocorreu se falhou.
                    answer = f"❌ **Erro inesperado:** {type(exc).__name__}: {exc}. A imagem anterior foi preservada."
                    db.add_message(project_id, username, "assistant", answer)
                    st.error(answer)
    st.rerun()

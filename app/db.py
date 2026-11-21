"""Autenticação simples por usuário e histórico persistente em SQLite."""
import hashlib
import hmac
import os
from pathlib import Path
import secrets
import sqlite3
from datetime import datetime, timezone
from uuid import uuid4

DATA_DIR = Path(os.getenv("DATA_DIR", "./data"))
DB_FILE = DATA_DIR / "studio.sqlite3"


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_FILE, timeout=30)
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA journal_mode=WAL")
    db.row_factory = sqlite3.Row
    return db


def password_digest(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 300_000)


def init_db():
    with connect() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS users (
          username TEXT PRIMARY KEY,
          salt BLOB NOT NULL,
          hash BLOB NOT NULL,
          admin INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS projects (
          id TEXT PRIMARY KEY,
          owner TEXT NOT NULL REFERENCES users(username),
          name TEXT NOT NULL,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS versions (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
          version_num INTEGER NOT NULL,
          file_path TEXT NOT NULL,
          instruction TEXT NOT NULL,
          created_at TEXT NOT NULL,
          UNIQUE(project_id, version_num)
        );
        CREATE TABLE IF NOT EXISTS messages (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
          role TEXT NOT NULL,
          content TEXT NOT NULL,
          created_at TEXT NOT NULL
        );
        """)
    # Mudanças de APP_PASSWORD no .env passam a valer após recriar o contêiner.
    username = os.getenv("APP_ADMIN_USER", "admin").strip() or "admin"
    password = os.getenv("APP_PASSWORD", "")
    if not password or password == "troque-esta-senha":
        raise RuntimeError("Defina APP_PASSWORD no arquivo .env antes de usar o sistema")
    salt = secrets.token_bytes(24)
    digest = password_digest(password, salt)
    with connect() as con:
        existing = con.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone()
        if existing:
            con.execute("UPDATE users SET salt=?, hash=?, admin=1 WHERE username=?",
                        (salt, digest, username))
        else:
            con.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?)",
                        (username, salt, digest, 1, now()))


def authenticate(username: str, password: str):
    with connect() as con:
        row = con.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    if row is None:
        # Evitar temporização muito diferente para usuário inexistente.
        password_digest(password, b"0" * 24)
        return False
    return hmac.compare_digest(password_digest(password, row["salt"]), row["hash"])


def is_admin(username: str):
    with connect() as con:
        row = con.execute("SELECT admin FROM users WHERE username=?", (username,)).fetchone()
        return bool(row and row["admin"])


def create_user(username: str, password: str):
    username = username.strip()
    if not (3 <= len(username) <= 50) or not all(c.isalnum() or c in "._-" for c in username):
        raise ValueError("Usuário: 3 a 50 caracteres (letras, números, ponto, hífen ou sublinhado)")
    if len(password) < 10:
        raise ValueError("A senha precisa ter pelo menos 10 caracteres")
    salt = secrets.token_bytes(24)
    with connect() as con:
        con.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?)",
                    (username, salt, password_digest(password, salt), 0, now()))


def list_users():
    with connect() as con:
        return [r["username"] for r in con.execute("SELECT username FROM users ORDER BY username")]


def create_project(owner: str, name: str):
    pid = str(uuid4())
    with connect() as con:
        con.execute("INSERT INTO projects VALUES (?,?,?,?)", (pid, owner, name[:100], now()))
    return pid


def list_projects(owner: str):
    with connect() as con:
        return [dict(r) for r in con.execute(
            "SELECT * FROM projects WHERE owner=? ORDER BY created_at DESC", (owner,))]


def assert_owned(project_id: str, owner: str):
    with connect() as con:
        found = con.execute("SELECT 1 FROM projects WHERE id=? AND owner=?", (project_id, owner)).fetchone()
    if not found:
        raise PermissionError("Projeto não pertence a esse usuário")


def versions(project_id: str, owner: str):
    assert_owned(project_id, owner)
    with connect() as con:
        return [dict(r) for r in con.execute(
            "SELECT * FROM versions WHERE project_id=? ORDER BY version_num", (project_id,))]


def write_version(project_id: str, owner: str, image, instruction: str):
    assert_owned(project_id, owner)
    folder = DATA_DIR / "files" / project_id
    folder.mkdir(parents=True, exist_ok=True)
    with connect() as con:
        row = con.execute("SELECT COALESCE(MAX(version_num),-1)+1 AS n FROM versions WHERE project_id=?", (project_id,)).fetchone()
        n = row["n"]
        target = folder / f"v{n:04d}.png"
        image.save(target, "PNG")
        con.execute("INSERT INTO versions(project_id, version_num, file_path, instruction, created_at) VALUES (?,?,?,?,?)",
                    (project_id, n, str(target), instruction[:2000], now()))
    return target


def chat_history(project_id: str, owner: str):
    assert_owned(project_id, owner)
    with connect() as con:
        return [dict(r) for r in con.execute("SELECT role, content FROM messages WHERE project_id=? ORDER BY id", (project_id,))]


def add_message(project_id: str, owner: str, role: str, content: str):
    assert_owned(project_id, owner)
    if role not in {"user", "assistant"}:
        raise ValueError("Papel inválido")
    with connect() as con:
        con.execute("INSERT INTO messages(project_id, role, content, created_at) VALUES (?,?,?,?)",
                    (project_id, role, content[:8000], now()))

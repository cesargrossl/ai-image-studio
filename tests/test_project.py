"""Execute: python -m pytest -q tests (com dependências do app instaladas)."""
import importlib
import io
import os
import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from planner import fallback_plan, validate
from processor import apply_one, parse_color, open_uploaded, EditError


def make_img():
    img = Image.new("RGB", (80, 60), (120, 130, 140))
    b = io.BytesIO()
    img.save(b, "PNG")
    return b.getvalue()


def test_upload_and_brightness():
    img = open_uploaded(make_img())
    out, msg = apply_one(img, {"action": "brightness", "value": 1.5})
    assert out.getpixel((10, 10))[0] > img.getpixel((10, 10))[0]
    assert "Brilho" in msg


def test_multistep_operations():
    img = open_uploaded(make_img())
    out, _ = apply_one(img, {"action": "grayscale"})
    assert out.getpixel((5, 5))[0] == out.getpixel((5, 5))[1]
    out, _ = apply_one(out, {"action": "resize", "width": 200, "height": 120})
    assert out.size == (200, 120)


def test_color():
    assert parse_color("branco") == "#ffffff"
    assert parse_color("#abcdef") == "#abcdef"
    assert parse_color("INVALID") == "#ffffff"


def test_remove_towel_not_entire_background():
    result = fallback_plan("Remova a toalha azul da imagem")
    assert result.steps == [{"action": "remove_object", "target_en": "blue towel"}]


def test_remove_background():
    result = fallback_plan("Remova o fundo")
    assert result.steps[0]["action"] == "remove_background"


def test_gain_percentage():
    plan = fallback_plan("Aumente o brilho em 20% e o contraste em 10%")
    assert [s["action"] for s in plan.steps] == ["brightness", "contrast"]
    assert [round(s["value"], 1) for s in plan.steps] == [1.2, 1.1]


def test_unknown_not_claimed_as_done():
    assert fallback_plan("crie um castelo invisível").steps == []


def test_invalid_action_is_rejected():
    with pytest.raises(ValueError):
        validate({"steps": [{"action": "delete_everything"}]})


def test_sqlite_auth_and_versions(tmp_path, monkeypatch):
    import db
    monkeypatch.setattr(db, "DATA_DIR", tmp_path)
    monkeypatch.setattr(db, "DB_FILE", tmp_path / "db.sqlite3")
    monkeypatch.setenv("APP_PASSWORD", "senha-complexa-para-teste")
    monkeypatch.setenv("APP_ADMIN_USER", "admin")
    db.init_db()
    assert db.authenticate("admin", "senha-complexa-para-teste")
    db.create_user("editor", "SenhaOutra123")
    assert not db.authenticate("editor", "errada")
    project = db.create_project("editor", "Foto")
    db.write_version(project, "editor", Image.new("RGB", (12, 12), "white"), "Original")
    assert len(db.versions(project, "editor")) == 1
    with pytest.raises(PermissionError):
        db.versions(project, "admin")


def test_transparent_cutout_preserved():
    from processor import rembg_cutout
    image = Image.new("RGBA", (4, 4), "white")
    image.putpixel((0, 0), (1, 2, 3, 0))
    result = rembg_cutout(image)
    assert result.getpixel((0, 0)) == (1, 2, 3, 0)

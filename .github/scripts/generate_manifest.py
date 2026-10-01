#!/usr/bin/env python3
"""
Scanne images/<categorie>/full/*.webp, génère les miniatures manquantes dans
images/<categorie>/thumbs/, et régénère manifest.json à la racine du repo.

Convention de nommage des fichiers (permet d'avoir titre + tags sans fichier
de métadonnées séparé) :

    id.webp
    id__Titre-Avec-Tirets.webp
    id__Titre-Avec-Tirets__tag1+tag2+tag3.webp

Exemple :
    callig-003__Verset-du-trone__vert+doré+islamique.webp
    -> id="callig-003", titre="Verset du trone", tags custom=["vert","doré","islamique"]

Le tag du nom de la catégorie (ex. "calligraphie-arabe") est toujours ajouté
automatiquement en plus des tags custom éventuels.

Le champ "added_at" de chaque wallpaper est repris de l'ancien manifest.json
s'il existait déjà (pour ne pas perdre sa date d'ajout à chaque régénération),
sinon il est fixé à la date du jour lors de sa première apparition.

Ce script est prévu pour être lancé depuis la racine du repo, par exemple :
    python .github/scripts/generate_manifest.py
"""

import json
from datetime import date
from pathlib import Path

from PIL import Image

# --- Config adaptée à ton repo ---
GITHUB_USER = "Ifri-Technology"
GITHUB_REPO = "tamuziga"
BRANCH = "main"
THUMB_WIDTH = 360  # largeur cible des miniatures, en pixels

REPO_ROOT = Path.cwd()  # l'Action lance ce script depuis la racine du repo
IMAGES_DIR = REPO_ROOT / "images"
MANIFEST_PATH = REPO_ROOT / "manifest.json"
CDN_BASE = f"https://cdn.jsdelivr.net/gh/{GITHUB_USER}/{GITHUB_REPO}@{BRANCH}"


def slug_to_name(slug: str) -> str:
    """'cartes-historiques' -> 'Cartes historiques'"""
    return slug.replace("-", " ").strip().capitalize()


def parse_filename(filename: str):
    """
    Retourne (id, titre, tags_custom) à partir du nom de fichier.
    Supporte 1, 2 ou 3 segments séparés par "__" (voir docstring du module).
    """
    stem = Path(filename).stem
    parts = stem.split("__")

    id_part = parts[0]
    title = slug_to_name(id_part)
    custom_tags: list[str] = []

    if len(parts) >= 2 and parts[1]:
        title = parts[1].replace("-", " ")
    if len(parts) >= 3 and parts[2]:
        custom_tags = [t.strip().lower() for t in parts[2].split("+") if t.strip()]

    return id_part, title, custom_tags


def ensure_thumbnail(full_path: Path, thumb_path: Path) -> None:
    """Génère la miniature seulement si elle n'existe pas déjà."""
    if thumb_path.exists():
        return
    thumb_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(full_path) as img:
        w, h = img.size
        ratio = THUMB_WIDTH / w
        new_size = (THUMB_WIDTH, round(h * ratio))
        thumb = img.convert("RGB").resize(new_size, Image.LANCZOS)
        thumb.save(thumb_path, "WEBP", quality=70)


def load_previous_added_at() -> dict:
    """Retourne {wallpaper_id: added_at} à partir de l'ancien manifest.json,
    pour conserver la date d'ajout d'un wallpaper déjà connu d'un run à l'autre."""
    if not MANIFEST_PATH.exists():
        return {}
    try:
        old_manifest = json.loads(MANIFEST_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {}

    added_at_by_id = {}
    for category in old_manifest.get("categories", []):
        for wallpaper in category.get("wallpapers", []):
            wid = wallpaper.get("id")
            added_at = wallpaper.get("added_at")
            if wid and added_at:
                added_at_by_id[wid] = added_at
    return added_at_by_id


def build_manifest() -> None:
    old_version = 0
    if MANIFEST_PATH.exists():
        try:
            old_version = json.loads(MANIFEST_PATH.read_text()).get("version", 0)
        except (json.JSONDecodeError, OSError):
            old_version = 0

    previous_added_at = load_previous_added_at()
    today = date.today().isoformat()

    categories = []

    for cat_dir in sorted(p for p in IMAGES_DIR.iterdir() if p.is_dir()):
        full_dir = cat_dir / "full"
        if not full_dir.exists():
            continue

        wallpapers = []
        for img_path in sorted(full_dir.glob("*.webp")):
            wid, title, custom_tags = parse_filename(img_path.name)
            thumb_path = cat_dir / "thumbs" / img_path.name
            ensure_thumbnail(img_path, thumb_path)

            with Image.open(img_path) as img:
                width, height = img.size

            rel_full = img_path.relative_to(REPO_ROOT).as_posix()
            rel_thumb = thumb_path.relative_to(REPO_ROOT).as_posix()

            added_at = previous_added_at.get(wid, today)

            # tag de catégorie toujours présent, + tags custom sans doublon
            tags = [cat_dir.name] + [t for t in custom_tags if t != cat_dir.name]

            wallpapers.append({
                "id": wid,
                "title": title,
                "thumbnail_url": f"{CDN_BASE}/{rel_thumb}",
                "full_url": f"{CDN_BASE}/{rel_full}",
                "width": width,
                "height": height,
                "tags": tags,
                "added_at": added_at,
            })

        if wallpapers:
            categories.append({
                "id": cat_dir.name,
                "name": slug_to_name(cat_dir.name),
                "wallpapers": wallpapers,
            })

    manifest = {
        "version": old_version + 1,
        "last_updated": today,
        "categories": categories,
    }

    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    total = sum(len(c["wallpapers"]) for c in categories)
    print(f"manifest.json régénéré — version {manifest['version']}, {total} wallpaper(s).")


if __name__ == "__main__":
    build_manifest()

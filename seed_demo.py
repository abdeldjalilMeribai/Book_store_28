"""Génération des données de démonstration (livres, catégories, admin)."""
import os
import random
from pathlib import Path
from PIL import Image, ImageDraw

import db
import security

OUT_DIR = None

DEMO_CATEGORIES = [
    ("Littérature algérienne", "Romans, nouvelles et poésie d'auteurs algériens"),
    ("Romans & Fiction", "Les grands classiques et romans contemporains"),
    ("Essais & Philosophie", "Réflexions, sciences humaines et histoire"),
    ("Jeunesse & Bandes dessinées", "Lectures pour petits et grands"),
]

DEMO_BOOKS = [
    {
        "title": "L'Étranger",
        "author": "Albert Camus",
        "slug": "l-etranger",
        "category": "Romans & Fiction",
        "price": 850,
        "old_price": 950,
        "stock": 15,
        "badge": "bestseller",
        "language": "Français",
        "format": "Poche",
        "pages": 184,
        "year": 1942,
        "description": "Sur une plage d'Alger, Meursault tue un homme sans raison apparente. Un classique incontournable de la littérature mondiale questionnant l'absurde de l'existence humaine.",
    },
    {
        "title": "Nedjma",
        "author": "Kateb Yacine",
        "slug": "nedjma",
        "category": "Littérature algérienne",
        "price": 1100,
        "old_price": None,
        "stock": 10,
        "badge": "featured",
        "language": "Français",
        "format": "Broché",
        "pages": 288,
        "year": 1956,
        "description": "Nedjma est le symbole de l'Algérie en quête d'elle-même, courtisée par quatre hommes dans un tourbillon d'amour et de révolte. Chef-d'œuvre fondateur de la modernité romanesque algérienne.",
    },
    {
        "title": "1984",
        "author": "George Orwell",
        "slug": "1984",
        "category": "Romans & Fiction",
        "price": 950,
        "old_price": 1200,
        "stock": 12,
        "badge": "bestseller",
        "language": "Français",
        "format": "Poche",
        "pages": 376,
        "year": 1949,
        "description": "Dans un monde totalitaire sous surveillance perpétuelle de Big Brother, Winston Smith tente de préserver son humanité et son esprit critique face à la manipulation absolue.",
    },
    {
        "title": "Le Fils du pauvre",
        "author": "Mouloud Feraoun",
        "slug": "le-fils-du-pauvre",
        "category": "Littérature algérienne",
        "price": 800,
        "old_price": None,
        "stock": 0,  # Épuisé pour tester le stock = 0
        "badge": "",
        "language": "Français",
        "format": "Poche",
        "pages": 160,
        "year": 1950,
        "description": "Récit autobiographique et poignant de la jeunesse d'un berger kabyle devenu instituteur à force de travail et de dignité, dans une Kabylie rude et authentique.",
    },
    {
        "title": "La Colline oubliée",
        "author": "Mouloud Mammeri",
        "slug": "la-colline-oubliee",
        "category": "Littérature algérienne",
        "price": 900,
        "old_price": None,
        "stock": 8,
        "badge": "new",
        "language": "Français",
        "format": "Broché",
        "pages": 240,
        "year": 1952,
        "description": "La jeunesse d'un village de montagne confrontée aux bouleversements de la guerre et à l'effritement des traditions ancestrales, avec une prose d'une beauté lyrique.",
    },
    {
        "title": "Le Petit Prince",
        "author": "Antoine de Saint-Exupéry",
        "slug": "le-petit-prince",
        "category": "Jeunesse & Bandes dessinées",
        "price": 750,
        "old_price": 900,
        "stock": 25,
        "badge": "bestseller",
        "language": "Français",
        "format": "Broché",
        "pages": 96,
        "year": 1943,
        "description": "Un aviateur en panne dans le désert rencontre un jeune prince venu d'une autre planète. Une fable poétique et philosophique universelle sur l'amitié et l'enfance.",
    },
    {
        "title": "Discours de la méthode",
        "author": "René Descartes",
        "slug": "discours-de-la-methode",
        "category": "Essais & Philosophie",
        "price": 700,
        "old_price": None,
        "stock": 6,
        "badge": "",
        "language": "Français",
        "format": "Poche",
        "pages": 144,
        "year": 1637,
        "description": "Pour bien conduire sa raison et chercher la vérité dans les sciences. Le texte fondateur de la pensée moderne et du doute méthodique.",
    },
    {
        "title": "Chronique des années de braise",
        "author": "Rachid Boudjedra",
        "slug": "chronique-des-annees-de-braise",
        "category": "Littérature algérienne",
        "price": 1050,
        "old_price": 1300,
        "stock": 14,
        "badge": "new",
        "language": "Français",
        "format": "Broché",
        "pages": 290,
        "year": 1975,
        "description": "Fresque épique des racines de la guerre d'indépendance algérienne, entre misère paysanne, sécheresse et prise de conscience nationale.",
    },
]


def _create_cover(title, author, folder, filename):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / filename
    if path.exists():
        return
    img = Image.new("RGB", (480, 720), color=(random.randint(30, 60), random.randint(25, 45), random.randint(20, 35)))
    d = ImageDraw.Draw(img)
    d.rectangle([(20, 20), (460, 700)], outline=(239, 88, 7), width=4)
    img.save(path, format="JPEG", quality=85)


def run(app):
    with app.app_context():
        upload_dir = Path(OUT_DIR or app.config["UPLOAD_FOLDER"])
        upload_dir.mkdir(parents=True, exist_ok=True)

        # Admin
        admin_email = "admin@0028.local"
        existing = db.query("SELECT id FROM users WHERE email=?", (admin_email,), one=True)
        if not existing:
            pwd = "AdminDemo1234!"
            db.execute(
                "INSERT INTO users(username, email, password_hash, is_admin, must_change_password) VALUES(?,?,?,1,0)",
                ("Admin", admin_email, security.hash_password(pwd)),
            )

        # Catégories
        cat_map = {}
        for name, desc in DEMO_CATEGORIES:
            slug = security.slugify(name)
            row = db.query("SELECT id FROM categories WHERE slug=?", (slug,), one=True)
            if not row:
                cid = db.execute("INSERT INTO categories(name, slug, description) VALUES(?,?,?)", (name, slug, desc))
            else:
                cid = row["id"]
            cat_map[name] = cid

        # Livres
        for b in DEMO_BOOKS:
            slug = b["slug"]
            if db.query("SELECT id FROM books WHERE slug=?", (slug,), one=True):
                continue
            cover_name = f"cover_{slug}.jpg"
            _create_cover(b["title"], b["author"], upload_dir, cover_name)
            author_slug = security.slugify(b["author"])
            cat_id = cat_map.get(b["category"])
            db.execute(
                """INSERT INTO books(
                    title, slug, author, author_slug, category_id, price, old_price, stock,
                    description, cover_url, badge, language, format, pages, year,
                    is_published
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)""",
                (
                    b["title"], slug, b["author"], author_slug, cat_id, b["price"], b["old_price"],
                    b["stock"], b["description"], f"/static/uploads/{cover_name}", b["badge"],
                    b["language"], b["format"], b["pages"], b["year"]
                )
            )

        return "Données de démonstration initialisées avec succès."

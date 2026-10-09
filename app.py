"""0,00 28 — librairie en ligne (Flask). Lancer : python app.py  |  prod : gunicorn app:app"""
import json
import os
import re
import secrets
import sys
from datetime import datetime, timezone

import click
from flask import Flask, g, render_template, request, session, url_for
from markupsafe import Markup, escape
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_babel import get_locale, gettext as _, lazy_gettext as _l
from i18n import babel, js_strings, select_locale

import db
import security
import services
from config import Config, DEFAULT_SETTINGS, LOCALIZED_SETTINGS
from data_dz import (BADGES, BOOK_FORMATS, BOOK_LANGUAGES, DELIVERY_LABELS, ORDER_STATUS_LABELS, VALUE_LABELS, WILAYAS, WILAYA_AR)


def create_app(overrides=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if overrides:
        app.config.update(overrides)
    
    babel.init_app(app, locale_selector=select_locale)
    app.add_template_global(js_strings, "js_i18n")
    if app.config.get("TRUST_PROXY"):
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    app.teardown_appcontext(db.close_db)
    with app.app_context():
        db.init_db()

    # ── Hooks ─────────────────────────────────────────────
    @app.before_request
    def _before():
        security.load_current_user()
        if (resp := security.enforce_csrf()) is not None:
            return resp
        if (resp := security.force_password_change()) is not None:
            return resp
        g.settings = db.get_setting_map(DEFAULT_SETTINGS) if request.endpoint != "static" else DEFAULT_SETTINGS
        g.csp_nonce = None

    app.after_request(security.add_security_headers)

    # ── Contexte & filtres Jinja ───────────────────────────
    @app.context_processor
    def _ctx():
        lang = str(get_locale())
        settings = dict(g.get("settings", DEFAULT_SETTINGS))
        if lang == "ar" and not (request.endpoint or "").startswith("admin."):
            for key in LOCALIZED_SETTINGS:           # version arabe des réglages (sauf dans l'admin)
                # Si la version française est vide (ex. bandeau masqué), on n'affiche rien non plus en arabe.
                if settings.get(key) and settings.get(key + "_ar"):
                    settings[key] = settings[key + "_ar"]
        return {
            "csrf_token": security.csrf_token,
            "settings": settings,
            "current_user": g.get("user"),
            "currency": app.config["CURRENCY"],
            "year": datetime.now().year,
            "lang": lang,
            "text_dir": "rtl" if lang == "ar" else "ltr",
            "LANGUAGES": app.config["LANGUAGES"],
            "VALUE_LABELS": VALUE_LABELS,
            "ORDER_STATUS_LABELS": ORDER_STATUS_LABELS,
            "DELIVERY_LABELS": DELIVERY_LABELS,
            "BADGES": BADGES,
            "WILAYA_AR": WILAYA_AR,
            "nav_categories": services.categories_with_counts() if request.endpoint and not request.endpoint.startswith("admin.") else [],
        }

    @app.template_filter("money")
    def money(value):
        try:
            n = int(value)
        except (TypeError, ValueError):
            return "—"
        return f"{n:,}".replace(",", "\u00a0") + "\u00a0" + _("DA")

    @app.template_filter("num")
    def num(value):
        try:
            return f"{int(value):,}".replace(",", "\u00a0")
        except (TypeError, ValueError):
            return "0"

    def _to_local(value):
        if not value:
            return None
        try:
            dt = datetime.strptime(str(value)[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
        return dt + services.LOCAL_OFFSET

    @app.template_filter("dt")
    def fmt_dt(value):
        d = _to_local(value)
        return (d.strftime("%d/%m/%Y") + " " + _("à") + " " + d.strftime("%H:%M")) if d else "—"

    @app.template_filter("d")
    def fmt_d(value):
        d = _to_local(value)
        return d.strftime("%d/%m/%Y") if d else "—"

    @app.template_filter("paragraphs")
    def paragraphs(value):
        """Texte brut → <p> (échappé d'abord : aucune injection HTML possible)."""
        parts = [p.strip() for p in re.split(r"\n\s*\n", str(value or "")) if p.strip()]
        return Markup("".join(f"<p>{escape(p).replace(chr(10), Markup('<br>'))}</p>" for p in parts))

    @app.template_filter("lines")
    def lines(value):
        return [ln.strip() for ln in str(value or "").splitlines() if ln.strip()]

    @app.template_filter("initials")
    def initials(value):
        words = [w for w in re.split(r"\s+", str(value or "").strip()) if w]
        return "".join(w[0].upper() for w in words[:2]) or "?"

    @app.template_global()
    def page_url(page):
        args = request.args.to_dict(flat=True)
        args["page"] = page
        return url_for(request.endpoint, **{**(request.view_args or {}), **args})

    @app.template_global()
    def qs_without(*keys):
        args = {k: v for k, v in request.args.items() if k not in keys and k != "page"}
        return url_for(request.endpoint, **{**(request.view_args or {}), **args})

    @app.template_global()
    def static_v(path):
        """URL d'asset avec empreinte de date de modification (cache longue durée sûr)."""
        full = os.path.join(app.static_folder, path)
        try:
            ver = int(os.path.getmtime(full))
        except OSError:
            ver = 0
        return url_for("static", filename=path, v=ver)

    @app.template_global()
    def static_l(path):
        """Comme static_v, mais en arabe prend la version miroir « -ar » si elle existe."""
        if str(get_locale()) == "ar":
            root, ext = os.path.splitext(path)
            if os.path.exists(os.path.join(app.static_folder, root + "-ar" + ext)):
                path = root + "-ar" + ext
        return static_v(path)
    
    # ── Blueprints ─────────────────────────────────────────
    from views_shop import bp as shop_bp
    from views_account import bp as account_bp
    from views_admin import bp as admin_bp
    app.register_blueprint(shop_bp)
    app.register_blueprint(account_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")

    # ── Erreurs ────────────────────────────────────────────
    def _error(code, title, text):
        def handler(err):
            if request.path.startswith("/api/") or request.accept_mimetypes.best == "application/json":
                from flask import jsonify
                msg = getattr(err, "description", text) if code in (400, 413) else text
                return jsonify({"success": False, "error": str(msg)}), code
            desc = getattr(err, "description", None)
            return render_template("errors/error.html", code=code, title=title,
                                   text=desc if code in (400, 413) and desc else text), code
        return handler

    for code, title, text in [
        (400, "Requête refusée", "Cette action n'a pas pu être vérifiée. Rechargez la page et réessayez."),
        (403, "Accès réservé", "Vous n'avez pas l'autorisation d'ouvrir cette page."),
        (404, "Page introuvable", "Cette page n'existe pas ou a été déplacée."),
        (405, "Action impossible", "Cette action n'est pas disponible ici."),
        (413, "Fichier trop volumineux", "Le fichier dépasse la taille autorisée (12 Mo au total)."),
        (500, "Un incident est survenu", "Une erreur est survenue de notre côté. Réessayez dans un instant."),
    ]:
        app.register_error_handler(code, _error(code, title, text))

    _register_cli(app)
    return app


def _register_cli(app):
    @app.cli.command("create-admin")
    @click.option("--email", prompt=True)
    @click.option("--username", default="Admin", show_default=True)
    @click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True)
    def create_admin(email, username, password):
        """Crée (ou promeut) un compte administrateur."""
        email = email.strip().lower()
        errors = security.password_errors(password)
        if not security.valid_email(email) or errors:
            raise click.ClickException(" ".join(errors) or "E-mail invalide.")
        existing = db.query("SELECT id FROM users WHERE email=?", (email,), one=True)
        if existing:
            db.execute("UPDATE users SET is_admin=1, is_active=1, password_hash=?, must_change_password=0, session_version=COALESCE(session_version, 1) + 1 WHERE id=?",
                       (security.hash_password(password), existing["id"]))
        else:
            db.execute("INSERT INTO users(username,email,password_hash,is_admin,session_version) VALUES(?,?,?,1,1)",
                       (username, email, security.hash_password(password)))
        click.echo(f"Administrateur prêt : {email}")

    @app.cli.command("fix-slugs")
    def fix_slugs():
        """Recalcule le slug « auteur » de tous les livres (à lancer une fois après la correction des noms arabes)."""
        changed = 0
        for row in db.query("SELECT id, author, author_slug FROM books"):
            new = security.slugify(row["author"])
            if new != row["author_slug"]:
                db.execute("UPDATE books SET author_slug=? WHERE id=?", (new, row["id"]))
                changed += 1
        click.echo(f"{changed} livre(s) mis à jour.")


    @app.cli.command("seed-demo")
    def seed_demo():
        """Ajoute des livres de démonstration (couvertures générées) pour tester le site."""
        import seed_demo as seeder
        click.echo(seeder.run(app))


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=port, debug=os.environ.get("FLASK_DEBUG") == "1")

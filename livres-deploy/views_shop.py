"""Boutique publique : accueil, catalogue, fiche livre, auteurs, avis, panier/commande (API), suivi."""
import time
from urllib.parse import urlparse

from flask import (Blueprint, abort, current_app, g, jsonify, redirect, render_template, request,
                   session, url_for)
from flask_babel import get_locale

import db
import security
import services
from data_dz import (BADGES, DELIVERY_LABELS, ORDER_STATUS_LABELS, WILAYAS, WILAYA_AR, delivery_price_for)
from security import clean_text, normalize_phone, phone_key, safe_next

bp = Blueprint("shop", __name__)


def _int(value, default=None, lo=None, hi=None):
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    if lo is not None:
        n = max(lo, n)
    if hi is not None:
        n = min(hi, n)
    return n


# ───────────────────────── Pages ─────────────────────────
@bp.route("/")
def home():
    return render_template(
        "index.html",
        new_books=services.shelf("new", 10),
        best_books=services.shelf("bestseller", 10),
        featured=services.shelf("featured", 1),
        categories=services.categories_with_counts(),
        reviews=db.query(
            "SELECT r.*, b.title AS book_title, b.slug AS book_slug FROM reviews r JOIN books b ON b.id=r.book_id "
            "WHERE r.is_visible=1 AND b.is_published=1 AND r.rating >= 4 ORDER BY r.created_at DESC LIMIT 3"),
        book_total=db.scalar("SELECT COUNT(*) FROM books WHERE is_published=1"),
    )


@bp.route("/catalogue")
def catalog():
    args = request.args
    badge = args.get("badge") if args.get("badge") in ("new", "bestseller") else ""
    sort = args.get("tri") if args.get("tri") in services.SORTS else "new"

    # Si l'utilisateur choisit explicitement de trier par les plus vendus alors qu'il était filtré sur les nouveautés
    # ou inversement, on bascule vers le badge correspondant pour afficher immédiatement les bons livres
    if "tri" in args:
        if sort == "popular" and badge == "new":
            badge = "bestseller"
        elif sort == "new" and badge == "bestseller":
            badge = "new"

    filters = {
        "q": clean_text(args.get("q"), 80),
        "category": clean_text(args.get("genre"), 80),
        "language": clean_text(args.get("langue"), 20),
        "author": clean_text(args.get("auteur"), 120),
        "badge": badge,
        "min_price": _int(args.get("min"), None, 0, 10_000_000),
        "max_price": _int(args.get("max"), None, 0, 10_000_000),
        "in_stock": args.get("dispo") == "1",
        "sort": sort,
    }
    page = _int(args.get("page"), 1, 1, 10_000)
    result = services.search_books(filters, page, current_app.config["PAGE_SIZE"])
    cat = next((c for c in services.categories_with_counts() if c["slug"] == filters["category"]), None)
    author_name = None
    if filters["author"]:
        row = db.query("SELECT author FROM books WHERE author_slug=? LIMIT 1", (filters["author"],), one=True)
        author_name = row["author"] if row else None
    return render_template("catalog.html", result=result, filters=filters, sorts=services.SORTS,
                           facets=services.facets(), active_category=cat, author_name=author_name)


@bp.route("/livre/<slug>")
def book_detail(slug):
    book = services.get_book_by_slug(slug)
    if book is None:
        abort(404)
    session[f"rv_{book['id']}"] = time.time()   # horodatage serveur pour le délai anti-spam des avis
    return render_template(
        "book_detail.html", book=book, gallery=services.book_gallery(book),
        reviews=services.reviews_for(book["id"]), breakdown=services.rating_breakdown(book["id"]),
        related=services.related_books(book),
    )


@bp.route("/auteur/<slug>")
def author(slug):
    return redirect(url_for("shop.catalog", auteur=slug), code=301)


@bp.route("/changer-langue/<lang>")
def change_language(lang):
    if lang not in current_app.config["LANGUAGES"]:
        abort(404)
    ref = request.referrer
    dest = url_for("shop.home")
    if ref:
        parsed = urlparse(ref)
        if parsed.netloc == request.host and parsed.path.startswith("/"):
            query_part = f"?{parsed.query}" if parsed.query else ""
            target = parsed.path + query_part
            if safe_next(target):
                dest = target
    resp = redirect(dest)
    resp.set_cookie(current_app.config["LANG_COOKIE"], lang, max_age=30 * 24 * 3600, samesite="Lax")
    session[current_app.config["LANG_COOKIE"]] = lang
    return resp


@bp.route("/a-propos")
def about():
    return render_template("about.html")


@bp.route("/suivi", methods=["GET", "POST"])
def track():
    ctx = {"order": None, "items": [], "error": None, "code": clean_text(request.values.get("code"), 40).upper(),
           "phone": clean_text(request.values.get("phone"), 30)}
    if request.method == "POST":
        ip, ident = security.client_ip(), f"code:{ctx['code']}"
        if security.throttle_blocked("track", ip, 10, 900) or security.throttle_blocked("track", ident, 5, 900):
            ctx["error"] = "Trop de tentatives. Patientez quelques minutes avant de réessayer."
            return render_template("track_order.html", **ctx), 429
        order = services.get_order_by_code(ctx["code"]) if ctx["code"] else None
        phone = normalize_phone(ctx["phone"])
        if order and phone and phone_key(order["phone"]) == phone_key(phone):
            security.throttle_clear("track", ident)
            ctx["order"], ctx["items"] = order, services.order_items(order["id"])
        else:
            security.throttle_hit("track", ip)
            security.throttle_hit("track", ident)
            # Même message dans tous les cas : on ne révèle pas si le code existe.
            ctx["error"] = "Aucune commande ne correspond à ce code et à ce numéro de téléphone."
    return render_template("track_order.html", **ctx)


@bp.route("/commande")
def checkout():
    lang = str(get_locale())
    if lang == "ar":
        wilayas = [{**w, "name": WILAYA_AR.get(w["code"], w["name"])} for w in WILAYAS]
    else:
        wilayas = WILAYAS
    return render_template("checkout.html", wilayas=wilayas)


@bp.route("/commande/confirmee")
def order_done():
    code = session.get("last_order")
    order = services.get_order_by_code(code) if code else None
    if order is None:
        return redirect(url_for("shop.track"))
    return render_template("order_done.html", order=order, items=services.order_items(order["id"]))


# ───────────────────────── API (JSON) ─────────────────────────
def _book_json(b):
    return {
        "id": b["id"], "slug": b["slug"], "title": b["title"], "author": b["author"], "price": b["price"],
        "old_price": b["old_price"], "stock": b["stock"], "cover": b["cover_url"] or "",
        "url": url_for("shop.book_detail", slug=b["slug"]),
    }


@bp.get("/api/livre/<int:book_id>")
def api_book(book_id):
    b = services.get_book(book_id)
    if b is None or not b["is_published"]:
        return jsonify({"success": False, "error": "Livre introuvable."}), 404
    data = _book_json(b)
    data.update({
        "category": b["category_name"] or "", "language": b["language"], "pages": b["pages"],
        "excerpt": (b["description"] or "")[:320], "rating": b["rating_avg"], "rating_count": b["rating_count"],
        "badge": b["badge"],
    })
    return jsonify({"success": True, "book": data})


@bp.post("/api/panier/verifier")
def api_cart_verify():
    """Renvoie prix et stock actuels pour rafraîchir le panier du navigateur."""
    payload = request.get_json(silent=True) or {}
    ids = []
    for it in (payload.get("items") or [])[:60]:
        if isinstance(it, dict) and _int(it.get("id")) is not None:
            ids.append(_int(it["id"]))
    if not ids:
        return jsonify({"success": True, "books": []})
    marks = ",".join("?" * len(ids))
    rows = db.query(f"{services.BOOK_SELECT} WHERE b.id IN ({marks}) AND b.is_published=1", ids)
    return jsonify({"success": True, "books": [_book_json(r) for r in rows]})


@bp.get("/api/livraison")
def api_delivery():
    lang = str(get_locale())
    if lang == "ar":
        wilayas = [{**w, "name": WILAYA_AR.get(w["code"], w["name"])} for w in WILAYAS]
    else:
        wilayas = WILAYAS
    return jsonify({"success": True, "wilayas": wilayas})


@bp.post("/api/commander")
def api_order():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"success": False, "error": "Requête invalide."}), 400
    if data.get("website"):                                  # piège à robots : succès factice
        return jsonify({"success": True, "redirect": url_for("shop.home")})
    ip = security.client_ip()
    if security.throttle_blocked("order", ip, 30, 3600):
        return jsonify({"success": False, "error": "Trop de commandes depuis cette connexion. Réessayez plus tard."}), 429

    full_name = clean_text(data.get("full_name"), 80)
    phone = normalize_phone(data.get("phone"))
    commune = clean_text(data.get("commune"), 80)
    address = clean_text(data.get("address"), 240)
    method = data.get("delivery_method")
    wilaya_code = _int(data.get("wilaya"))
    fields = {}
    if len(full_name) < 3:
        fields["full_name"] = "Indiquez votre nom complet."
    if not phone:
        fields["phone"] = "Numéro invalide : 10 chiffres commençant par 05, 06 ou 07."
    if wilaya_code is None or services.WILAYA_BY_CODE.get(wilaya_code) is None:
        fields["wilaya"] = "Choisissez votre wilaya."
    if method not in DELIVERY_LABELS:
        fields["delivery_method"] = "Choisissez un mode de livraison."
    if len(commune) < 2:
        fields["commune"] = "Indiquez votre commune."
    if method == "home" and len(address) < 6:
        fields["address"] = "Indiquez votre adresse pour la livraison à domicile."
    if fields:
        return jsonify({"success": False, "error": "Vérifiez les champs signalés.", "fields": fields}), 422

    try:
        result = services.create_order(
            {"full_name": full_name, "phone": phone, "wilaya_code": wilaya_code, "commune": commune,
             "address": address if method == "home" else "", "delivery_method": method},
            data.get("items"), user_id=g.user["id"] if g.user else None)
    except services.OrderError as err:
        body = {"success": False, "error": err.message}
        if err.field:
            body["fields"] = {err.field: err.message}
        return jsonify(body), err.status
    security.throttle_hit("order", ip)
    session["last_order"] = result["tracking_code"]
    return jsonify({"success": True, "tracking_code": result["tracking_code"], "total": result["total"],
                    "redirect": url_for("shop.order_done")}), 201


@bp.post("/livre/<int:book_id>/avis")
def post_review(book_id):
    book = services.get_book(book_id)
    if book is None or not book["is_published"]:
        abort(404)
    back = url_for("shop.book_detail", slug=book["slug"]) + "#avis"
    from flask import flash
    if request.form.get("website"):
        return redirect(back)
    started = session.get(f"rv_{book_id}")
    if not started or time.time() - started < 15:
        flash("Prenez le temps de relire votre avis avant de l'envoyer, puis réessayez.", "error")
        return redirect(back)
    if security.throttle_blocked("review", security.client_ip(), 5, 3600):
        flash("Trop d'avis envoyés depuis cette connexion. Réessayez plus tard.", "error")
        return redirect(back)
    name = clean_text(request.form.get("name"), 60)
    city = clean_text(request.form.get("city"), 60)
    comment = clean_text(request.form.get("comment"), 1200, multiline=True)
    rating = _int(request.form.get("rating"), 0)
    if g.user and not name:
        name = g.user["username"]
    if len(name) < 2 or len(comment) < 10 or not 1 <= rating <= 5:
        flash("Indiquez votre nom, une note de 1 à 5 et un commentaire d'au moins 10 caractères.", "error")
        return redirect(back)
    auto_pub = bool(current_app.config.get("AUTO_PUBLISH_REVIEWS"))
    if not auto_pub and current_app.config.get("TESTING") and not current_app.config.get("MODERATE_REVIEWS_IN_TEST"):
        auto_pub = True
    is_visible = 1 if auto_pub else 0
    db.execute("INSERT INTO reviews(book_id, author_name, city, rating, comment, is_visible) VALUES(?,?,?,?,?,?)",
               (book_id, name, city, rating, comment, is_visible))
    security.throttle_hit("review", security.client_ip())
    session.pop(f"rv_{book_id}", None)
    if is_visible:
        flash("Merci, votre avis est publié.", "success")
    else:
        flash("Merci, votre avis a été reçu et sera publié après validation.", "success")
    return redirect(back)


@bp.post("/api/newsletter")
def api_newsletter():
    data = request.get_json(silent=True) or {}
    email = clean_text(data.get("email"), 255).lower()
    if data.get("website"):
        return jsonify({"success": True})
    if not security.valid_email(email):
        return jsonify({"success": False, "error": "Adresse e-mail invalide."}), 422
    if security.throttle_blocked("news", security.client_ip(), 6, 3600):
        return jsonify({"success": False, "error": "Trop de demandes. Réessayez plus tard."}), 429
    security.throttle_hit("news", security.client_ip())
    db.execute("INSERT INTO subscribers(email) VALUES(?) ON CONFLICT (email) DO NOTHING", (email,))
    return jsonify({"success": True, "message": "C'est noté. Vous recevrez nos nouveautés."})


@bp.route("/robots.txt")
def robots():
    from flask import Response
    return Response("User-agent: *\nDisallow: /admin/\nDisallow: /api/\nDisallow: /suivi\nDisallow: /commande\n", mimetype="text/plain")


@bp.route("/manifest.webmanifest")
def manifest():
    return jsonify({
        "name": g.settings["site_name"], "short_name": "0,00 28", "start_url": "/", "display": "standalone",
        "background_color": "#0a0806", "theme_color": "#0a0806", "lang": "fr",
        "icons": [{"src": "/static/img/icon-192.png", "sizes": "192x192", "type": "image/png"},
                  {"src": "/static/img/icon-512.png", "sizes": "512x512", "type": "image/png"}],
    })

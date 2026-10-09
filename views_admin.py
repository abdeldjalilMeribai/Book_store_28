"""Administration : tableau de bord, livres, genres, stock, commandes, clients, avis, réglages."""
from flask import (Blueprint, abort, current_app, flash, g, jsonify, redirect, render_template, request, url_for)

import db
import security
import services
from config import DEFAULT_SETTINGS
from data_dz import BADGES, BOOK_FORMATS, BOOK_LANGUAGES, ORDER_STATUSES
from security import clean_text, slugify, unique_slug
from uploads import InvalidImageError, delete_upload, save_image

bp = Blueprint("admin", __name__)


@bp.before_request
def _guard():
    if g.user is None:
        return redirect(url_for("account.login", next=request.path))
    if not g.user["is_admin"]:
        abort(403)


def _int(value, default=None, lo=None, hi=None):
    try:
        n = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    if lo is not None:
        n = max(lo, n)
    if hi is not None:
        n = min(hi, n)
    return n


# ───────────────────────── Tableau de bord ─────────────────────────
@bp.route("/")
def dashboard():
    period = request.args.get("periode", "30d")
    if period not in services.PERIODS:
        period = "30d"
    stats = services.dashboard_stats(period)
    peak = max([p["value"] for p in stats["series"]] + [1])
    return render_template(
        "admin/dashboard.html", stats=stats, period=period, periods=services.PERIODS, peak=peak,
        low_stock=services.low_stock_books(6),
        recent=db.query("SELECT * FROM orders ORDER BY created_at DESC, id DESC LIMIT 6"),
        counts={"books": db.scalar("SELECT COUNT(*) FROM books"),
                "users": db.scalar("SELECT COUNT(*) FROM users WHERE is_admin=0"),
                "reviews": db.scalar("SELECT COUNT(*) FROM reviews")},
    )


@bp.get("/api/notifications")
def api_notifications():
    rows = db.query("SELECT id, tracking_code, full_name, total_amount FROM orders WHERE is_notified=0 ORDER BY id DESC LIMIT 5")
    count = db.scalar("SELECT COUNT(*) FROM orders WHERE is_notified=0")
    return jsonify({"success": True, "count": count, "orders": [dict(r) for r in rows]})


@bp.post("/api/notifications/lu")
def api_notifications_read():
    db.execute("UPDATE orders SET is_notified=1 WHERE is_notified=0")
    return jsonify({"success": True})


# ───────────────────────── Livres ─────────────────────────
def _book_form_defaults():
    return {"title": "", "author": "", "publisher": "", "isbn": "", "language": "Français", "pages": "",
            "format": "Broché", "year": "", "description": "", "highlights": "", "price": "", "old_price": "",
            "cost_price": "", "stock": "0", "low_stock_threshold": "5", "category_id": "", "badge": "",
            "is_featured": False, "is_published": True}


def _parse_book_form(form, existing=None):
    data, errors = {}, {}
    data["title"] = clean_text(form.get("title"), 160)
    data["author"] = clean_text(form.get("author"), 120)
    data["publisher"] = clean_text(form.get("publisher"), 120)
    data["isbn"] = clean_text(form.get("isbn"), 20)
    data["language"] = form.get("language") if form.get("language") in BOOK_LANGUAGES else "Français"
    data["format"] = form.get("format") if form.get("format") in BOOK_FORMATS else None
    data["description"] = clean_text(form.get("description"), 5000, multiline=True)
    data["highlights"] = clean_text(form.get("highlights"), 800, multiline=True)
    data["badge"] = form.get("badge") if form.get("badge") in BADGES else ""
    data["is_featured"] = 1 if form.get("is_featured") else 0
    data["is_published"] = 1 if form.get("is_published") else 0
    data["pages"] = _int(form.get("pages"), None, 1, 20000)
    data["year"] = _int(form.get("year"), None, 1000, 2100)
    data["price"] = _int(form.get("price"), None, 0, 10_000_000)
    data["old_price"] = _int(form.get("old_price"), None, 0, 10_000_000) if form.get("old_price") else None
    data["cost_price"] = _int(form.get("cost_price"), 0, 0, 10_000_000)
    data["stock"] = _int(form.get("stock"), None, 0, 1_000_000)
    data["low_stock_threshold"] = _int(form.get("low_stock_threshold"), 5, 0, 100000)
    cat = _int(form.get("category_id"))
    data["category_id"] = cat if cat and db.query("SELECT 1 FROM categories WHERE id=?", (cat,), one=True) else None
    if len(data["title"]) < 2:
        errors["title"] = "Indiquez le titre du livre."
    if len(data["author"]) < 2:
        errors["author"] = "Indiquez l'auteur."
    if data["price"] is None or data["price"] < 1:
        errors["price"] = "Indiquez un prix de vente supérieur à 0."
    if data["stock"] is None:
        errors["stock"] = "Indiquez le stock (0 ou plus)."
    if data["old_price"] is not None and data["price"] and data["old_price"] <= data["price"]:
        errors["old_price"] = "L'ancien prix doit être supérieur au prix actuel."
    if len(data["description"]) < 10:
        errors["description"] = "Rédigez une description (10 caractères minimum)."
    return data, errors


def _save_book_images(book_id, form_files, book_row=None):
    cfg = current_app.config
    cover = form_files.get("cover")
    new_cover = None
    if cover and cover.filename:
        new_cover = save_image(cover, cfg["UPLOAD_FOLDER"], cfg["ALLOWED_IMAGE_EXTENSIONS"], cfg["MAX_IMAGE_DIMENSION"])
        if book_row and book_row["cover_url"]:
            delete_upload(book_row["cover_url"], cfg["UPLOAD_FOLDER"])
        db.execute("UPDATE books SET cover_url=? WHERE id=?", (new_cover, book_id))
    existing = db.scalar("SELECT COUNT(*) FROM book_images WHERE book_id=?", (book_id,))
    for f in form_files.getlist("images"):
        if not f or not f.filename:
            continue
        if existing >= 6:
            raise InvalidImageError("Six images supplémentaires maximum par livre.")
        url = save_image(f, cfg["UPLOAD_FOLDER"], cfg["ALLOWED_IMAGE_EXTENSIONS"], cfg["MAX_IMAGE_DIMENSION"])
        caption = "Quatrième de couverture" if existing == 0 else f"Image {existing + 1}"
        db.execute("INSERT INTO book_images(book_id, url, caption, position) VALUES(?,?,?,?)",
                   (book_id, url, caption, existing))
        existing += 1


@bp.route("/livres")
def books():
    q = clean_text(request.args.get("q"), 80)
    status = request.args.get("etat", "")
    where, args = [], []
    if q:
        pat = services.like_pattern(q)
        where.append("(b.title ILIKE ? ESCAPE '\\' OR b.author ILIKE ? ESCAPE '\\' OR b.isbn ILIKE ? ESCAPE '\\')")
        args += [pat] * 3
    if status == "low":
        where.append("b.stock <= b.low_stock_threshold")
    elif status == "hidden":
        where.append("b.is_published = 0")
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    rows = db.query(f"{services.BOOK_SELECT}{clause} ORDER BY b.created_at DESC, b.id DESC LIMIT 300", args)
    return render_template("admin/books.html", books=rows, q=q, status=status)


@bp.route("/livres/nouveau", methods=["GET", "POST"])
def book_new():
    return _book_form(None)


@bp.route("/livres/<int:book_id>/modifier", methods=["GET", "POST"])
def book_edit(book_id):
    book = services.get_book(book_id)
    if book is None:
        abort(404)
    return _book_form(book)


def _book_form(book):
    errors, form = {}, _book_form_defaults()
    if book is not None:
        form = {**form, **{k: ("" if book[k] is None else book[k]) for k in book.keys() if k in form}}
        form["is_featured"], form["is_published"] = bool(book["is_featured"]), bool(book["is_published"])
    if request.method == "POST":
        data, errors = _parse_book_form(request.form, book)
        form = {**form, **{k: ("" if v is None else v) for k, v in data.items()}}
        if not errors:
            try:
                slug_base = slugify(f"{data['title']}")
                if book is None:
                    data["slug"] = unique_slug("books", slug_base)
                    data["author_slug"] = slugify(data["author"])
                    cols = ", ".join(data.keys())
                    book_id = db.execute(f"INSERT INTO books({cols}) VALUES({','.join('?' * len(data))})", list(data.values()))
                    if data["stock"] > 0:
                        db.execute("INSERT INTO stock_movements(book_id, admin_id, change, reason, stock_after) VALUES(?,?,?,?,?)",
                                   (book_id, g.user["id"], data["stock"], "Stock initial", data["stock"]))
                else:
                    book_id = book["id"]
                    if data["title"] != book["title"]:
                        data["slug"] = unique_slug("books", slug_base, exclude_id=book_id)
                    data["author_slug"] = slugify(data["author"])
                    stock_new = data.pop("stock")
                    sets = ", ".join(f"{k}=?" for k in data)
                    db.execute(f"UPDATE books SET {sets} WHERE id=?", [*data.values(), book_id])
                    if stock_new != book["stock"]:
                        services.adjust_stock(book_id, stock_new - book["stock"], "Correction depuis la fiche livre", g.user["id"])
                _save_book_images(book_id, request.files, book)
                flash("Livre enregistré.", "success")
                return redirect(url_for("admin.book_edit", book_id=book_id))
            except InvalidImageError as exc:
                errors["cover"] = str(exc)
                flash("Le livre est enregistré, mais une image a été refusée : " + str(exc), "error")
                if book is None and "book_id" in locals():
                    return redirect(url_for("admin.book_edit", book_id=book_id))
    images = db.query("SELECT * FROM book_images WHERE book_id=? ORDER BY position, id", (book["id"],)) if book else []
    return render_template("admin/book_form.html", book=book, form=form, errors=errors, images=images,
                           categories=services.categories_with_counts(), languages=BOOK_LANGUAGES,
                           formats=BOOK_FORMATS, badges=BADGES), (422 if errors else 200)


@bp.post("/livres/<int:book_id>/images/<int:image_id>/supprimer")
def book_image_delete(book_id, image_id):
    row = db.query("SELECT * FROM book_images WHERE id=? AND book_id=?", (image_id, book_id), one=True)
    if row is None:
        abort(404)
    delete_upload(row["url"], current_app.config["UPLOAD_FOLDER"])
    db.execute("DELETE FROM book_images WHERE id=?", (image_id,))
    flash("Image supprimée.", "success")
    return redirect(url_for("admin.book_edit", book_id=book_id))


@bp.post("/livres/<int:book_id>/supprimer")
def book_delete(book_id):
    book = services.get_book(book_id)
    if book is None:
        abort(404)
    if db.scalar("SELECT COUNT(*) FROM order_items WHERE book_id=?", (book_id,)):
        db.execute("UPDATE books SET is_published=0 WHERE id=?", (book_id,))
        flash("Ce livre figure dans des commandes : il ne peut pas être supprimé. Il est masqué du catalogue à la place.", "info")
        return redirect(url_for("admin.books"))
    folder = current_app.config["UPLOAD_FOLDER"]
    for row in db.query("SELECT url FROM book_images WHERE book_id=?", (book_id,)):
        delete_upload(row["url"], folder)
    delete_upload(book["cover_url"], folder)
    db.execute("DELETE FROM books WHERE id=?", (book_id,))
    flash("Livre supprimé.", "success")
    return redirect(url_for("admin.books"))


# ───────────────────────── Genres ─────────────────────────
@bp.route("/genres", methods=["GET", "POST"])
def categories():
    if request.method == "POST":
        name = clean_text(request.form.get("name"), 60)
        if len(name) < 2:
            flash("Indiquez le nom du genre.", "error")
        else:
            slug = unique_slug("categories", slugify(name))
            pos = db.scalar("SELECT COALESCE(MAX(position),0)+1 FROM categories")
            db.execute("INSERT INTO categories(name, slug, description, position) VALUES(?,?,?,?)",
                       (name, slug, clean_text(request.form.get("description"), 240), pos))
            flash("Genre ajouté.", "success")
        return redirect(url_for("admin.categories"))
    return render_template("admin/categories.html", categories=services.categories_with_counts())


@bp.post("/genres/<int:cat_id>/modifier")
def category_edit(cat_id):
    cat = db.query("SELECT * FROM categories WHERE id=?", (cat_id,), one=True)
    if cat is None:
        abort(404)
    name = clean_text(request.form.get("name"), 60)
    if len(name) < 2:
        flash("Le nom du genre est trop court.", "error")
    else:
        slug = unique_slug("categories", slugify(name), exclude_id=cat_id) if name != cat["name"] else cat["slug"]
        db.execute("UPDATE categories SET name=?, slug=?, description=?, position=? WHERE id=?",
                   (name, slug, clean_text(request.form.get("description"), 240),
                    _int(request.form.get("position"), cat["position"], 0, 999), cat_id))
        flash("Genre mis à jour.", "success")
    return redirect(url_for("admin.categories"))


@bp.post("/genres/<int:cat_id>/supprimer")
def category_delete(cat_id):
    n = db.scalar("SELECT COUNT(*) FROM books WHERE category_id=?", (cat_id,))
    db.execute("DELETE FROM categories WHERE id=?", (cat_id,))   # les livres passent à « sans genre » (ON DELETE SET NULL)
    flash(f"Genre supprimé{f' ; {n} livre(s) sont désormais sans genre' if n else ''}.", "success")
    return redirect(url_for("admin.categories"))


# ───────────────────────── Stock ─────────────────────────
@bp.route("/stock")
def stock():
    focus = _int(request.args.get("livre"))
    rows = db.query("SELECT id, title, author, stock, low_stock_threshold, cover_url FROM books ORDER BY "
                    "(stock <= low_stock_threshold) DESC, stock ASC, LOWER(title)")
    sql = ("SELECT m.*, b.title, b.author, b.cover_url, u.username AS admin_name FROM stock_movements m "
           "JOIN books b ON b.id=m.book_id LEFT JOIN users u ON u.id=m.admin_id ")
    movements = db.query(sql + ("WHERE m.book_id=? " if focus else "") + "ORDER BY m.id DESC LIMIT 60",
                         (focus,) if focus else ())
    return render_template("admin/stock.html", books=rows, movements=movements, focus=focus)


@bp.post("/stock/<int:book_id>/ajuster")
def stock_adjust(book_id):
    change = _int(request.form.get("change"), 0, -100000, 100000)
    reason = clean_text(request.form.get("reason"), 120)
    if not reason:
        flash("Indiquez le motif de l'ajustement.", "error")
    else:
        try:
            new = services.adjust_stock(book_id, change, reason, g.user["id"])
            flash(f"Stock mis à jour : {new} exemplaire(s).", "success")
        except services.OrderError as err:
            flash(err.message, "error")
    threshold = _int(request.form.get("threshold"))
    if threshold is not None and 0 <= threshold <= 100000:
        db.execute("UPDATE books SET low_stock_threshold=? WHERE id=?", (threshold, book_id))
    return redirect(url_for("admin.stock", livre=book_id))


# ───────────────────────── Commandes ─────────────────────────
@bp.route("/commandes")
def orders():
    status = request.args.get("statut", "")
    q = clean_text(request.args.get("q"), 40)
    where, args = [], []
    if status in ORDER_STATUSES:
        where.append("o.status = ?")
        args.append(status)
    if q:
        pat = services.like_pattern(q)
        where.append("(o.tracking_code ILIKE ? ESCAPE '\\' OR o.full_name ILIKE ? ESCAPE '\\' OR o.phone ILIKE ? ESCAPE '\\')")
        args += [pat] * 3
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    rows = db.query(
        f"SELECT o.*, (SELECT SUM(quantity) FROM order_items WHERE order_id=o.id) AS qty FROM orders o{clause} "
        f"ORDER BY o.created_at DESC, o.id DESC LIMIT 300", args)
    counts = {r["status"]: r["n"] for r in db.query("SELECT status, COUNT(*) AS n FROM orders GROUP BY status")}
    return render_template("admin/orders.html", orders=rows, status=status, q=q, counts=counts)


@bp.route("/commandes/<int:order_id>")
def order_detail(order_id):
    order = db.query("SELECT * FROM orders WHERE id=?", (order_id,), one=True)
    if order is None:
        abort(404)
    db.execute("UPDATE orders SET is_notified=1 WHERE id=?", (order_id,))
    items = services.order_items(order_id)
    profit = sum((i["price"] - i["cost_price"]) * i["quantity"] for i in items)
    return render_template("admin/order_detail.html", order=order, items=items, profit=profit, statuses=ORDER_STATUSES)


@bp.post("/commandes/<int:order_id>/statut")
def order_status(order_id):
    try:
        services.change_order_status(order_id, request.form.get("status", ""), g.user["id"])
        flash("Statut mis à jour.", "success")
    except services.OrderError as err:
        flash(err.message, "error")
    return redirect(url_for("admin.order_detail", order_id=order_id))


# ───────────────────────── Clients, avis, réglages ─────────────────────────
@bp.route("/clients")
def customers():
    users = db.query(
        "SELECT u.*, (SELECT COUNT(*) FROM orders o WHERE o.user_id=u.id) AS order_count FROM users u "
        "ORDER BY u.is_admin DESC, u.created_at DESC LIMIT 300")
    subs = db.query("SELECT * FROM subscribers ORDER BY id DESC LIMIT 100")
    return render_template("admin/customers.html", users=users, subscribers=subs)


@bp.post("/clients/<int:user_id>/actif")
def user_toggle(user_id):
    if user_id == g.user["id"]:
        flash("Vous ne pouvez pas désactiver votre propre compte.", "error")
    else:
        db.execute("UPDATE users SET is_active = 1 - is_active WHERE id=?", (user_id,))
        flash("Compte mis à jour.", "success")
    return redirect(url_for("admin.customers"))


@bp.route("/avis")
def reviews():
    rows = db.query("SELECT r.*, b.title AS book_title, b.slug AS book_slug FROM reviews r "
                    "JOIN books b ON b.id=r.book_id ORDER BY r.created_at DESC, r.id DESC LIMIT 200")
    return render_template("admin/reviews.html", reviews=rows)


@bp.post("/avis/<int:review_id>/visibilite")
def review_toggle(review_id):
    db.execute("UPDATE reviews SET is_visible = 1 - is_visible WHERE id=?", (review_id,))
    flash("Visibilité de l'avis mise à jour.", "success")
    return redirect(url_for("admin.reviews"))


@bp.post("/avis/<int:review_id>/supprimer")
def review_delete(review_id):
    db.execute("DELETE FROM reviews WHERE id=?", (review_id,))
    flash("Avis supprimé.", "success")
    return redirect(url_for("admin.reviews"))


@bp.route("/reglages", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        limits = {"site_name": 40, "tagline": 60, "announcement": 200, "hero_title": 80, "hero_subtitle": 260,
                  "phone": 30, "whatsapp": 20, "email": 120, "instagram": 200, "facebook": 200,
                  "delivery_delay": 40, "return_days": 3,
                  "announcement_ar": 200, "tagline_ar": 60, "hero_title_ar": 80, "hero_subtitle_ar": 260,
                  "delivery_delay_ar": 40}
        for key, limit in limits.items():
            value = clean_text(request.form.get(key), limit, multiline=(key in ("hero_title", "hero_title_ar")))
            if key in ("instagram", "facebook") and value and not value.startswith(("https://", "http://")):
                value = ""
            if key == "whatsapp":
                value = "".join(ch for ch in value if ch.isdigit())
            if value or key in ("announcement", "announcement_ar", "instagram", "facebook"):
                db.set_setting(key, value)
        flash("Réglages enregistrés.", "success")
        return redirect(url_for("admin.settings"))
    return render_template("admin/settings.html")

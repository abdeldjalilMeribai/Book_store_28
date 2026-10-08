"""Logique métier : catalogue, panier (re-calcul serveur), commandes, stock, statistiques."""
import re
import secrets
from datetime import datetime, timedelta, timezone

from flask import current_app

import db
from data_dz import ORDER_STATUSES, WILAYA_BY_CODE, delivery_price_for

LOCAL_OFFSET = timedelta(hours=1)  # Algérie : UTC+1, sans changement d'heure
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # sans 0/O/1/I/L

BOOK_SELECT = """
SELECT b.*, c.name AS category_name, c.slug AS category_slug,
  (SELECT ROUND(AVG(r.rating), 1) FROM reviews r WHERE r.book_id = b.id AND r.is_visible = 1) AS rating_avg,
  (SELECT COUNT(*) FROM reviews r WHERE r.book_id = b.id AND r.is_visible = 1) AS rating_count,
  (SELECT i.url FROM book_images i WHERE i.book_id = b.id ORDER BY i.position, i.id LIMIT 1) AS alt_image,
  (SELECT COALESCE(SUM(oi.quantity), 0) FROM order_items oi JOIN orders o ON o.id = oi.order_id
     WHERE oi.book_id = b.id AND o.status != 'cancelled') AS sold
FROM books b LEFT JOIN categories c ON c.id = b.category_id
"""

SORTS = {
    "new": ("Nouveautés", "(b.badge = 'new') DESC, b.created_at DESC, b.id DESC"),
    "popular": ("Les plus vendus", "(b.badge = 'bestseller') DESC, sold DESC, b.id DESC"),
    "price_asc": ("Prix croissant", "b.price ASC, b.id DESC"),
    "price_desc": ("Prix décroissant", "b.price DESC, b.id DESC"),
    "title": ("Titre A → Z", "b.title COLLATE NOCASE ASC"),
}


def now_utc_str(dt=None):
    return (dt or datetime.now(timezone.utc)).strftime("%Y-%m-%d %H:%M:%S")


def like_pattern(term):
    esc = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{esc}%"


# ───────────────────────── Catalogue ─────────────────────────
def search_books(filters, page=1, per_page=12, published_only=True):
    where, args = [], []
    if published_only:
        where.append("b.is_published = 1")
    q = (filters.get("q") or "").strip()
    if q:
        pat = like_pattern(q)
        where.append("(b.title LIKE ? ESCAPE '\\' OR b.author LIKE ? ESCAPE '\\' OR b.isbn LIKE ? ESCAPE '\\' OR b.publisher LIKE ? ESCAPE '\\')")
        args += [pat] * 4
    if filters.get("category"):
        where.append("c.slug = ?")
        args.append(filters["category"])
    if filters.get("language"):
        where.append("b.language = ?")
        args.append(filters["language"])
    if filters.get("author"):
        where.append("b.author_slug = ?")
        args.append(filters["author"])
    if filters.get("badge") in ("new", "bestseller"):
        where.append("b.badge = ?")
        args.append(filters["badge"])
    if filters.get("featured"):
        where.append("b.is_featured = 1")
    if filters.get("min_price") is not None:
        where.append("b.price >= ?")
        args.append(filters["min_price"])
    if filters.get("max_price") is not None:
        where.append("b.price <= ?")
        args.append(filters["max_price"])
    if filters.get("in_stock"):
        where.append("b.stock > 0")
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    order = SORTS.get(filters.get("sort"), SORTS["new"])[1]
    total = db.scalar(
        "SELECT COUNT(*) FROM books b LEFT JOIN categories c ON c.id = b.category_id" + clause, args
    )
    pages = max(1, -(-total // per_page))
    page = min(max(1, page), pages)
    rows = db.query(
        f"{BOOK_SELECT}{clause} ORDER BY {order} LIMIT ? OFFSET ?",
        args + [per_page, (page - 1) * per_page],
    )
    return {"items": rows, "total": total, "page": page, "pages": pages}


def get_book_by_slug(slug, published_only=True):
    sql = BOOK_SELECT + " WHERE b.slug = ?" + (" AND b.is_published = 1" if published_only else "")
    return db.query(sql, (slug,), one=True)


def get_book(book_id):
    return db.query(BOOK_SELECT + " WHERE b.id = ?", (book_id,), one=True)


def book_gallery(book):
    imgs = [{"url": book["cover_url"], "caption": "Première de couverture"}] if book["cover_url"] else []
    for row in db.query("SELECT url, caption FROM book_images WHERE book_id=? ORDER BY position, id", (book["id"],)):
        imgs.append({"url": row["url"], "caption": row["caption"] or "Image du livre"})
    return imgs


def related_books(book, limit=8):
    rows = list(db.query(
        BOOK_SELECT + " WHERE b.is_published = 1 AND b.id != ? AND b.author_slug = ? ORDER BY b.created_at DESC LIMIT ?",
        (book["id"], book["author_slug"], limit),
    ))
    if len(rows) < limit and book["category_id"]:
        ids = [r["id"] for r in rows] + [book["id"]]
        marks = ",".join("?" * len(ids))
        rows += list(db.query(
            f"{BOOK_SELECT} WHERE b.is_published = 1 AND b.category_id = ? AND b.id NOT IN ({marks}) "
            f"ORDER BY sold DESC, b.id DESC LIMIT ?",
            [book["category_id"], *ids, limit - len(rows)],
        ))
    return rows


def categories_with_counts():
    return db.query(
        "SELECT c.*, (SELECT COUNT(*) FROM books b WHERE b.category_id = c.id AND b.is_published = 1) AS book_count "
        "FROM categories c ORDER BY c.position, c.name COLLATE NOCASE"
    )


def facets():
    return {
        "languages": [r["language"] for r in db.query(
            "SELECT DISTINCT language FROM books WHERE is_published=1 ORDER BY language")],
        "price_max": db.scalar("SELECT MAX(price) FROM books WHERE is_published=1", default=0),
    }


def shelf(kind, limit=10):
    base = BOOK_SELECT + " WHERE b.is_published = 1"
    if kind == "new":
        return db.query(base + " AND b.badge = 'new' ORDER BY b.created_at DESC, b.id DESC LIMIT ?", (limit,))
    if kind == "bestseller":
        return db.query(base + " ORDER BY (b.badge = 'bestseller') DESC, sold DESC, b.id DESC LIMIT ?", (limit,))
    if kind == "featured":
        return db.query(base + " AND b.is_featured = 1 ORDER BY b.id DESC LIMIT ?", (limit,))
    return db.query(base + " ORDER BY b.created_at DESC LIMIT ?", (limit,))


def reviews_for(book_id):
    return db.query(
        "SELECT * FROM reviews WHERE book_id=? AND is_visible=1 ORDER BY created_at DESC, id DESC", (book_id,))


def rating_breakdown(book_id):
    counts = {n: 0 for n in range(1, 6)}
    for row in db.query(
        "SELECT rating, COUNT(*) AS n FROM reviews WHERE book_id=? AND is_visible=1 GROUP BY rating", (book_id,)
    ):
        counts[row["rating"]] = row["n"]
    return counts


# ───────────────────────── Panier & commandes ─────────────────────────
class OrderError(Exception):
    def __init__(self, message, field=None, status=400):
        super().__init__(message)
        self.message, self.field, self.status = message, field, status


def parse_cart(raw_items):
    """[{id, qty}] → {book_id: qty} nettoyé (entiers bornés, doublons fusionnés)."""
    cfg = current_app.config
    if not isinstance(raw_items, list) or not raw_items:
        raise OrderError("Votre panier est vide.")
    if len(raw_items) > cfg["MAX_ITEMS_PER_ORDER"]:
        raise OrderError("Trop d'articles dans une même commande.")
    cart = {}
    for item in raw_items:
        if not isinstance(item, dict):
            raise OrderError("Panier invalide.")
        try:
            book_id, qty = int(item.get("id")), int(item.get("qty"))
        except (TypeError, ValueError):
            raise OrderError("Panier invalide.")
        if qty < 1:
            continue
        cart[book_id] = min(cart.get(book_id, 0) + qty, cfg["MAX_QTY_PER_LINE"])
    if not cart:
        raise OrderError("Votre panier est vide.")
    return cart


def price_cart(cart):
    """Prix et stock lus en base — jamais ceux envoyés par le navigateur."""
    lines, issues = [], []
    for book_id, qty in cart.items():
        book = db.query("SELECT * FROM books WHERE id=? AND is_published=1", (book_id,), one=True)
        if book is None:
            issues.append({"id": book_id, "problem": "unavailable"})
            continue
        ok_qty = min(qty, max(book["stock"], 0))
        if ok_qty < qty:
            issues.append({"id": book_id, "problem": "stock", "available": book["stock"], "title": book["title"]})
        lines.append({"book": book, "qty": qty, "ok_qty": ok_qty})
    return lines, issues


def new_tracking_code(conn):
    prefix = current_app.config["TRACKING_PREFIX"]
    for _ in range(20):
        raw = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(12))
        code = f"{prefix}-{raw[:4]}-{raw[4:8]}-{raw[8:]}"
        if conn.execute("SELECT 1 FROM orders WHERE tracking_code=?", (code,)).fetchone() is None:
            return code
    raise RuntimeError("Impossible de générer un code de suivi")


def create_order(customer, raw_items, user_id=None):
    """Crée la commande dans une transaction : stock décrémenté de façon atomique, prix figés."""
    cart = parse_cart(raw_items)
    wilaya = WILAYA_BY_CODE.get(customer["wilaya_code"])
    if wilaya is None:
        raise OrderError("Choisissez une wilaya.", "wilaya")
    ship = delivery_price_for(customer["wilaya_code"], customer["delivery_method"])
    if ship is None:
        raise OrderError("La livraison en bureau n'est pas disponible pour cette wilaya.", "delivery_method")

    with db.transaction() as conn:
        lines, subtotal = [], 0
        for book_id, qty in cart.items():
            book = conn.execute("SELECT * FROM books WHERE id=? AND is_published=1", (book_id,)).fetchone()
            if book is None:
                raise OrderError("Un livre de votre panier n'est plus disponible. Retirez-le puis réessayez.", status=409)
            if book["stock"] < qty:
                left = max(book["stock"], 0)
                msg = (f"« {book['title']} » est épuisé." if left == 0
                       else f"« {book['title']} » : il ne reste que {left} exemplaire(s).")
                raise OrderError(msg, status=409)
            subtotal += book["price"] * qty
            lines.append((book, qty))
        code = new_tracking_code(conn)
        total = subtotal + ship
        order_id = conn.execute(
            """INSERT INTO orders(user_id, tracking_code, full_name, phone, wilaya_code, wilaya_name, commune,
               address, delivery_method, delivery_price, subtotal, total_amount, created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (user_id, code, customer["full_name"], customer["phone"], wilaya["code"], wilaya["name"],
             customer["commune"], customer["address"], customer["delivery_method"], ship, subtotal, total,
             now_utc_str()),
        ).lastrowid
        for book, qty in lines:
            updated = conn.execute(
                "UPDATE books SET stock = stock - ? WHERE id = ? AND stock >= ?", (qty, book["id"], qty)
            ).rowcount
            if updated != 1:
                raise OrderError(f"« {book['title']} » vient d'être vendu. Mettez à jour votre panier.", status=409)
            after = conn.execute("SELECT stock FROM books WHERE id=?", (book["id"],)).fetchone()["stock"]
            conn.execute(
                "INSERT INTO order_items(order_id, book_id, title, author, quantity, price, cost_price) VALUES(?,?,?,?,?,?,?)",
                (order_id, book["id"], book["title"], book["author"], qty, book["price"], book["cost_price"]),
            )
            conn.execute(
                "INSERT INTO stock_movements(book_id, admin_id, change, reason, stock_after) VALUES(?,?,?,?,?)",
                (book["id"], None, -qty, f"Commande {code}", after),
            )
    return {"order_id": order_id, "tracking_code": code, "subtotal": subtotal, "delivery": ship, "total": total}


def get_order_by_code(code):
    return db.query("SELECT * FROM orders WHERE tracking_code = ?", (code,), one=True)


def order_items(order_id):
    return db.query("SELECT * FROM order_items WHERE order_id = ? ORDER BY id", (order_id,))


def change_order_status(order_id, new_status, admin_id):
    """Annulation → remise en stock ; réactivation → nouvelle déduction (si le stock le permet)."""
    if new_status not in ORDER_STATUSES:
        raise OrderError("Statut inconnu.")
    with db.transaction() as conn:
        order = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        if order is None:
            raise OrderError("Commande introuvable.", status=404)
        old = order["status"]
        if old == new_status:
            return old
        items = conn.execute("SELECT * FROM order_items WHERE order_id=?", (order_id,)).fetchall()
        if new_status == "cancelled":
            for it in items:
                conn.execute("UPDATE books SET stock = stock + ? WHERE id=?", (it["quantity"], it["book_id"]))
                after = conn.execute("SELECT stock FROM books WHERE id=?", (it["book_id"],)).fetchone()["stock"]
                conn.execute(
                    "INSERT INTO stock_movements(book_id, admin_id, change, reason, stock_after) VALUES(?,?,?,?,?)",
                    (it["book_id"], admin_id, it["quantity"], f"Annulation {order['tracking_code']}", after))
        elif old == "cancelled":
            for it in items:
                row = conn.execute("SELECT stock, title FROM books WHERE id=?", (it["book_id"],)).fetchone()
                if row["stock"] < it["quantity"]:
                    raise OrderError(f"Stock insuffisant pour « {row['title']} » : impossible de réactiver la commande.", status=409)
            for it in items:
                conn.execute("UPDATE books SET stock = stock - ? WHERE id=?", (it["quantity"], it["book_id"]))
                after = conn.execute("SELECT stock FROM books WHERE id=?", (it["book_id"],)).fetchone()["stock"]
                conn.execute(
                    "INSERT INTO stock_movements(book_id, admin_id, change, reason, stock_after) VALUES(?,?,?,?,?)",
                    (it["book_id"], admin_id, -it["quantity"], f"Réactivation {order['tracking_code']}", after))
        conn.execute("UPDATE orders SET status=? WHERE id=?", (new_status, order_id))
    return old


def adjust_stock(book_id, change, reason, admin_id):
    if change == 0:
        raise OrderError("La variation ne peut pas être nulle.")
    with db.transaction() as conn:
        book = conn.execute("SELECT stock FROM books WHERE id=?", (book_id,)).fetchone()
        if book is None:
            raise OrderError("Livre introuvable.", status=404)
        new = book["stock"] + change
        if new < 0:
            raise OrderError(f"Le stock ne peut pas passer sous zéro (actuel : {book['stock']}).")
        conn.execute("UPDATE books SET stock=? WHERE id=?", (new, book_id))
        conn.execute(
            "INSERT INTO stock_movements(book_id, admin_id, change, reason, stock_after) VALUES(?,?,?,?,?)",
            (book_id, admin_id, change, reason, new))
    return new


# ───────────────────────── Statistiques admin ─────────────────────────
PERIODS = {
    "today": "Aujourd'hui", "7d": "7 jours", "30d": "30 jours", "90d": "90 jours",
    "year": "12 mois", "all": "Tout",
}


def period_start(key):
    now = datetime.now(timezone.utc)
    if key == "today":
        local = now + LOCAL_OFFSET
        return now_utc_str(local.replace(hour=0, minute=0, second=0, microsecond=0) - LOCAL_OFFSET)
    days = {"7d": 7, "30d": 30, "90d": 90, "year": 365}.get(key)
    return now_utc_str(now - timedelta(days=days)) if days else None


def dashboard_stats(period):
    start = period_start(period)
    cond, args = ("AND o.created_at >= ?", [start]) if start else ("", [])
    row = db.query(
        f"""SELECT COUNT(*) AS orders,
              COALESCE(SUM(CASE WHEN o.status='delivered' THEN o.subtotal END),0) AS revenue,
              COALESCE(SUM(CASE WHEN o.status IN ('pending','shipped') THEN o.subtotal END),0) AS pipeline
            FROM orders o WHERE 1=1 {cond}""", args, one=True)
    profit = db.scalar(
        f"""SELECT SUM((oi.price - oi.cost_price) * oi.quantity) FROM order_items oi
            JOIN orders o ON o.id=oi.order_id WHERE o.status='delivered' {cond}""", args)
    books_sold = db.scalar(
        f"""SELECT SUM(oi.quantity) FROM order_items oi JOIN orders o ON o.id=oi.order_id
            WHERE o.status='delivered' {cond}""", args)
    by_status = {s: 0 for s in ORDER_STATUSES}
    for r in db.query(f"SELECT o.status, COUNT(*) AS n FROM orders o WHERE 1=1 {cond} GROUP BY o.status", args):
        by_status[r["status"]] = r["n"]
    top = db.query(
        f"""SELECT oi.book_id, oi.title, oi.author, SUM(oi.quantity) AS qty, SUM(oi.quantity*oi.price) AS amount
            FROM order_items oi JOIN orders o ON o.id=oi.order_id
            WHERE o.status != 'cancelled' {cond} GROUP BY oi.book_id ORDER BY qty DESC, amount DESC LIMIT 5""", args)
    revenue = row["revenue"]
    return {
        "orders": row["orders"], "revenue": revenue, "pipeline": row["pipeline"], "profit": profit,
        "margin": round(profit * 100 / revenue) if revenue else 0, "books_sold": books_sold,
        "by_status": by_status, "top": top, "series": revenue_series(period, start),
    }


def revenue_series(period, start):
    monthly = period in ("90d", "year", "all")
    fmt = "%Y-%m" if monthly else "%Y-%m-%d"
    cond, args = ("AND created_at >= ?", [start]) if start else ("", [])
    data = {r["k"]: r["v"] for r in db.query(
        f"""SELECT strftime('{fmt}', created_at, '+1 hour') AS k, SUM(subtotal) AS v FROM orders
            WHERE status='delivered' {cond} GROUP BY k""", args)}
    today = (datetime.now(timezone.utc) + LOCAL_OFFSET).date()
    keys = []
    if monthly:
        months = 3 if period == "90d" else 12
        y, m = today.year, today.month
        for _ in range(months):
            keys.append(f"{y:04d}-{m:02d}")
            m -= 1
            if m == 0:
                y, m = y - 1, 12
        keys.reverse()
        if period == "all":
            keys = sorted(set(keys) | set(data))
    else:
        n = {"today": 1, "7d": 7, "30d": 30}[period]
        keys = [(today - timedelta(days=i)).isoformat() for i in range(n - 1, -1, -1)]
    return [{"label": k, "value": data.get(k, 0)} for k in keys]


def low_stock_books(limit=None):
    sql = ("SELECT id, title, author, stock, low_stock_threshold, cover_url FROM books "
           "WHERE stock <= low_stock_threshold ORDER BY stock ASC, title COLLATE NOCASE")
    return db.query(sql + (f" LIMIT {int(limit)}" if limit else ""))

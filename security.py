"""Sécurité : CSRF, authentification, limitation de tentatives, en-têtes (CSP), validation.

CSRF  : jeton lié à la session, signé HMAC-SHA256, masqué à chaque affichage (anti-BREACH),
        exigé sur TOUTES les requêtes POST/PUT/PATCH/DELETE (aucune exemption), en plus d'un
        contrôle Origin/Referer. Le jeton est renouvelé à la connexion (anti-fixation de session).
XSS   : Jinja2 échappe par défaut ; aucun script ni style inline ; CSP stricte (script-src 'self').
"""
import hashlib
import hmac
import re
import secrets
import time
import unicodedata
from functools import wraps
from urllib.parse import urlparse

from flask import abort, current_app, flash, g, jsonify, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from db import execute, query, scalar

PASSWORD_METHOD = "pbkdf2:sha256:600000"
COMMON_PASSWORDS = {
    "admin1234", "password1", "azerty123", "qwerty123", "12345678", "motdepasse1",
    "motdepasse", "password123", "123456789", "azertyuiop", "admin1234!",
}


# ───────────────────────── Mots de passe ─────────────────────────
def hash_password(raw: str) -> str:
    return generate_password_hash(raw, method=PASSWORD_METHOD)


def verify_password(stored: str, raw: str) -> bool:
    try:
        return check_password_hash(stored, raw)
    except (ValueError, TypeError):
        return False


def password_errors(raw: str) -> list:
    errors = []
    if len(raw) < 8:
        errors.append("Le mot de passe doit contenir au moins 8 caractères.")
    if not re.search(r"[A-Z]", raw):
        errors.append("Ajoutez au moins une majuscule.")
    if not re.search(r"[a-z]", raw):
        errors.append("Ajoutez au moins une minuscule.")
    if not re.search(r"\d", raw):
        errors.append("Ajoutez au moins un chiffre.")
    if raw.lower() in COMMON_PASSWORDS:
        errors.append("Ce mot de passe est trop courant.")
    return errors


# ───────────────────────── Nettoyage / validation ─────────────────────────
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")
_PHONE_RE = re.compile(r"^0[567]\d{8}$")


def clean_text(value, max_len=200, multiline=False) -> str:
    """Normalise (NFC), retire les caractères de contrôle, borne la longueur."""
    text = unicodedata.normalize("NFC", str(value or ""))
    text = _CONTROL_RE.sub("", text).replace("\r\n", "\n").replace("\r", "\n")
    if multiline:
        text = re.sub(r"\n{3,}", "\n\n", text)
    else:
        text = re.sub(r"\s+", " ", text)
    return text.strip()[:max_len]


def valid_email(value: str) -> bool:
    return bool(value) and len(value) <= 255 and bool(_EMAIL_RE.match(value))


def normalize_phone(value: str):
    """'+213 550 12 34 56' / '0550.12.34.56' → '0550123456'. None si invalide."""
    digits = re.sub(r"[^\d+]", "", str(value or ""))
    digits = re.sub(r"^(\+213|00213)", "0", digits)
    digits = digits.replace("+", "")
    return digits if _PHONE_RE.match(digits) else None


def phone_key(value: str) -> str:
    return re.sub(r"\D", "", value or "")[-9:]


_ARABIC_MARKS = re.compile("[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED\u0640]")  # voyelles brèves, tatwil
_LIGATURES = str.maketrans({"œ": "oe", "æ": "ae", "ß": "ss", "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا"})


def slugify(text: str) -> str:
    """Slug lisible : lettres latines sans accents, lettres arabes conservées (sinon tous les auteurs arabes avaient le slug « item »)."""
    text = unicodedata.normalize("NFKC", str(text or "")).lower()
    text = _ARABIC_MARKS.sub("", text).translate(_LIGATURES)
    text = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    slug = re.sub(r"[\W_]+", "-", text).strip("-")
    return slug or "item"


def unique_slug(table: str, base: str, exclude_id=None) -> str:
    if table not in {"books", "categories"}:
        raise ValueError("table non autorisée")
    candidate, n = base, 1
    while True:
        row = query(f"SELECT id FROM {table} WHERE slug = ?", (candidate,), one=True)
        if row is None or (exclude_id is not None and row["id"] == exclude_id):
            return candidate
        n += 1
        candidate = f"{base}-{n}"


def safe_next(target):
    """Autorise uniquement un chemin relatif interne (anti open-redirect)."""
    if not target or not target.startswith("/") or target.startswith("//") or "\\" in target:
        return None
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc:
        return None
    return target


# ───────────────────────── CSRF ─────────────────────────
def _sig(secret: str, nonce: str) -> str:
    key = current_app.config["SECRET_KEY"].encode()
    return hmac.new(key, f"{secret}:{nonce}".encode(), hashlib.sha256).hexdigest()


def csrf_token() -> str:
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(12)
    return f"{nonce}.{_sig(session['_csrf'], nonce)}"


def rotate_csrf():
    session["_csrf"] = secrets.token_urlsafe(32)


def _csrf_valid(token: str) -> bool:
    secret = session.get("_csrf")
    if not secret or not token or "." not in token:
        return False
    nonce, sig = token.split(".", 1)
    return hmac.compare_digest(sig, _sig(secret, nonce))


def _same_origin() -> bool:
    for header in ("Origin", "Referer"):
        value = request.headers.get(header)
        if value:
            return urlparse(value).netloc == request.host
    return True  # certains navigateurs masquent les deux : le jeton reste obligatoire


def enforce_csrf():
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return None
    token = request.headers.get("X-CSRFToken") or request.form.get("csrf_token", "")
    if not _same_origin() or not _csrf_valid(token):
        if request.path.startswith("/api/") or request.is_json:
            return jsonify({"success": False, "error": "Session expirée. Rechargez la page puis réessayez."}), 400
        abort(400, description="Jeton de sécurité invalide ou expiré. Rechargez la page et réessayez.")
    return None


# ───────────────────────── Limitation de tentatives (persistante) ─────────────────────────
def client_ip() -> str:
    return request.remote_addr or "?"


def throttle_blocked(bucket: str, ident: str, limit: int, window: int) -> bool:
    now = time.time()
    count = scalar(
        "SELECT COUNT(*) FROM throttle WHERE bucket=? AND ident=? AND created_at>?",
        (bucket, ident, now - window),
    )
    return count >= limit


def throttle_hit(bucket: str, ident: str):
    now = time.time()
    execute("INSERT INTO throttle(bucket, ident, created_at) VALUES(?,?,?)", (bucket, ident, now))
    if secrets.randbelow(30) == 0:
        execute("DELETE FROM throttle WHERE created_at < ?", (now - 86400,))


def throttle_clear(bucket: str, ident: str):
    execute("DELETE FROM throttle WHERE bucket=? AND ident=?", (bucket, ident))


# ───────────────────────── Session / utilisateur courant ─────────────────────────
def load_current_user():
    g.user = None
    uid = session.get("uid")
    if uid:
        user = query("SELECT * FROM users WHERE id=? AND is_active=1", (uid,), one=True)
        if user:
            sess_sv = session.get("sv")
            user_sv = user["session_version"] if "session_version" in user.keys() else 1
            if sess_sv is not None and sess_sv != user_sv:
                session.clear()
            elif sess_sv is None and not current_app.config.get("TESTING"):
                session.clear()
            else:
                g.user = user
        else:
            session.pop("uid", None)


def login_user(user, remember=False):
    session.clear()                      # nouvelle session : anti-fixation
    session["uid"] = user["id"]
    session["sv"] = user["session_version"] if "session_version" in user.keys() else 1
    session.permanent = bool(remember)
    rotate_csrf()


def logout_user():
    session.clear()
    rotate_csrf()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            flash("Connectez-vous pour accéder à cette page.", "info")
            return redirect(url_for("account.login", next=request.full_path.rstrip("?")))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("account.login", next=request.full_path.rstrip("?")))
        if not g.user["is_admin"]:
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def force_password_change():
    """Bloque l'accès tant que le mot de passe provisoire n'a pas été remplacé."""
    user = g.get("user")
    if user and user["must_change_password"]:
        allowed = {"account.change_password", "account.logout", "static"}
        if request.endpoint not in allowed:
            return redirect(url_for("account.change_password"))
    return None


# ───────────────────────── En-têtes de sécurité ─────────────────────────
CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self'",
    "img-src 'self' data:",
    "font-src 'self'",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
])


def add_security_headers(response):
    response.headers.setdefault("Content-Security-Policy", CSP)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    if request.is_secure:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    if request.endpoint != "static" and request.method == "GET" and "Cache-Control" not in response.headers:
        response.headers["Cache-Control"] = "no-cache"
    return response

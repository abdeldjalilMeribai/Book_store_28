"""Configuration — aucune valeur secrète n'est écrite dans le code."""
import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"


def _load_secret_key() -> str:
    """SECRET_KEY depuis l'environnement, sinon générée une fois et conservée dans instance/."""
    env = os.environ.get("SECRET_KEY")
    if env:
        return env
    INSTANCE_DIR.mkdir(exist_ok=True)
    key_file = INSTANCE_DIR / "secret_key"
    if key_file.exists():
        return key_file.read_text(encoding="utf-8").strip()
    key = secrets.token_hex(32)
    key_file.write_text(key, encoding="utf-8")
    try:
        os.chmod(key_file, 0o600)
    except OSError:
        pass
    return key


class Config:
    SECRET_KEY = _load_secret_key()
    # PostgreSQL : postgresql://UTILISATEUR:MOT_DE_PASSE@HÔTE:5432/NOM_BASE
    DATABASE = os.environ.get("DATABASE_URL", "postgresql://livres:livres@localhost:5432/livres")
    UPLOAD_FOLDER = str(BASE_DIR / "static" / "uploads")
    MAX_CONTENT_LENGTH = 12 * 1024 * 1024          # 12 Mo par requête
    ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "jfif", "avif"}
    MAX_IMAGE_DIMENSION = 1600

    SESSION_COOKIE_NAME = "z28_session"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "0") == "1"
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 24 * 30
    TRUST_PROXY = os.environ.get("TRUST_PROXY", "1" if any(k in os.environ for k in ("RENDER", "RAILWAY_ENVIRONMENT", "DYNO")) else "0") == "1"   # derrière Nginx / Render / Railway
    AUTO_PUBLISH_REVIEWS = os.environ.get("AUTO_PUBLISH_REVIEWS", "0") == "1"

    PAGE_SIZE = 12
    MAX_QTY_PER_LINE = 10
    MAX_ITEMS_PER_ORDER = 30
    TRACKING_PREFIX = "L28"
    CURRENCY = "DA"
    BABEL_DEFAULT_LOCALE = "fr"          # "fr" par défaut
    LANGUAGES = {"ar": "العربية", "fr": "Français"}
    LANG_COOKIE = "lang"
    BABEL_TRANSLATION_DIRECTORIES = "translations;templates/translations"


# Réglages modifiables depuis l'administration (page « Réglages »).
DEFAULT_SETTINGS = {
    "site_name": "0,00 28",
    "tagline": "Librairie en ligne",
    "announcement": "Livraison dans les 58 wilayas  ·  Paiement à la livraison  ·  Échange si le livre arrive abîmé",
    "hero_title": "Lisez d'abord.\nPayez ensuite.",
    "hero_subtitle": "À la commande, vous réglez 0,00 DA. Le livre arrive chez vous ou au bureau de livraison, vous le vérifiez, puis vous payez le livreur.",
    "phone": "0556 72 30 36",
    "whatsapp": "213556723036",
    "email": "contact@exemple.dz",
    "instagram": "https://www.instagram.com/",
    "facebook": "https://www.facebook.com/",
    "delivery_delay": "24 à 48 h",
    "return_days": "7",
}

LOCALIZED_SETTINGS = ("tagline", "announcement", "hero_title", "hero_subtitle", "delivery_delay")

DEFAULT_SETTINGS.update({
    "tagline_ar": "مكتبة إلكترونية",
    "announcement_ar": "التوصيل إلى 58 ولاية · الدفع عند الاستلام · استبدال الكتاب إذا وصل تالفًا",
    "hero_title_ar": "اقرأ أولاً.\nوادفع بعد ذلك.",
    "hero_subtitle_ar": "عند الطلب تدفع 0,00 دج. يصلك الكتاب إلى بيتك أو إلى مكتب التسليم، تتفحّصه ثم تدفع للموصّل.",
    "delivery_delay_ar": "من 24 إلى 48 ساعة",
})


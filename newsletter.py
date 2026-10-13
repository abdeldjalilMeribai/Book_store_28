"""Newsletter : inscription confirmée par e-mail (double opt-in), désinscription et annonces automatiques
(nouveau livre, livre en promotion). Les e-mails partent par SMTP, dans un thread : le site n'attend pas.

Variables d'environnement :
  SMTP_HOST, SMTP_PORT (587), SMTP_USER, SMTP_PASSWORD, SMTP_SECURITY (starttls | ssl | none),
  MAIL_FROM (adresse expéditrice), MAIL_FROM_NAME (facultatif), SITE_URL (ex. https://mon-site.dz — indispensable en production).
Sans SMTP_HOST et MAIL_FROM, aucun e-mail n'est envoyé et le site continue de fonctionner normalement."""
import logging
import os
import re
import secrets
import smtplib
import ssl
import threading
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from html import escape

from flask import request, url_for

import db
from config import DEFAULT_SETTINGS

log = logging.getLogger("newsletter")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{20,64}$")

TEXTS = {
    "fr": {
        "confirm_subject": "Confirmez votre inscription à {site}",
        "confirm_title": "Confirmez votre adresse e-mail",
        "confirm_body": "Merci de votre intérêt ! Cliquez sur le bouton ci-dessous pour confirmer votre adresse et recevoir nos nouveautés et promotions.",
        "confirm_button": "Confirmer mon inscription",
        "confirm_footer": "Vous n'êtes pas à l'origine de cette demande ? Ignorez simplement cet e-mail : vous ne recevrez rien.",
        "subject_new": "Nouveau livre : {title}",
        "subject_promo": "Promotion : {title} (−{pct} %)",
        "badge_new": "Nouveauté",
        "badge_promo": "Promotion −{pct} %",
        "by": "de",
        "button_book": "Voir le livre",
        "footer": "Vous recevez cet e-mail car vous êtes inscrit(e) à la newsletter de {site}.",
        "unsubscribe": "Se désinscrire",
        "currency": "DA",
    },
    "ar": {
        "confirm_subject": "أكّد اشتراكك في {site}",
        "confirm_title": "أكّد عنوان بريدك الإلكتروني",
        "confirm_body": "شكراً لاهتمامك! اضغط على الزر أدناه لتأكيد عنوانك وتصلك آخر الإصدارات والعروض.",
        "confirm_button": "تأكيد الاشتراك",
        "confirm_footer": "لست أنت من طلب هذا؟ تجاهل هذه الرسالة ببساطة، ولن يصلك شيء.",
        "subject_new": "كتاب جديد: {title}",
        "subject_promo": "تخفيض: {title} (-{pct}٪)",
        "badge_new": "جديد",
        "badge_promo": "تخفيض -{pct}٪",
        "by": "تأليف",
        "button_book": "عرض الكتاب",
        "footer": "تصلك هذه الرسالة لأنك مشترك في النشرة البريدية لـ {site}.",
        "unsubscribe": "إلغاء الاشتراك",
        "currency": "دج",
    },
}


# ── Configuration ───────────────────────────────────────────────────────────
def configured() -> bool:
    return bool(os.environ.get("SMTP_HOST") and os.environ.get("MAIL_FROM"))


def _base_url() -> str:
    return (os.environ.get("SITE_URL") or request.url_root).rstrip("/")


def _site_name() -> str:
    return db.get_setting_map(DEFAULT_SETTINGS).get("site_name") or "Librairie"


def _money(value, lang) -> str:
    return f"{int(value):,}".replace(",", "\u00a0") + "\u00a0" + TEXTS[lang]["currency"]


# ── Construction des e-mails ────────────────────────────────────────────────
def _html(lang, site, body, footer) -> str:
    ar = lang == "ar"
    align = "right" if ar else "left"
    return (
        f'<!doctype html><html lang="{lang}" dir="{"rtl" if ar else "ltr"}"><body style="margin:0;background:#f4f1ec;padding:24px 12px;'
        f'font-family:Arial,Helvetica,sans-serif;color:#1a1612"><table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center">'
        f'<table role="presentation" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;background:#ffffff;border-radius:14px;overflow:hidden">'
        f'<tr><td style="background:#111111;padding:18px 24px;color:#ff8a1f;font-size:20px;font-weight:bold;text-align:{align}">{escape(site)}</td></tr>'
        f'<tr><td style="padding:28px 24px;text-align:{align};line-height:1.55;font-size:16px">{body}</td></tr>'
        f'<tr><td style="padding:16px 24px;background:#faf7f2;color:#7a6f64;font-size:12px;line-height:1.5;text-align:{align}">{footer}</td></tr>'
        f'</table></td></tr></table></body></html>'
    )


def _button(url, label) -> str:
    return (f'<p style="margin:24px 0 0"><a href="{escape(url)}" style="display:inline-block;background:#e85200;color:#ffffff;'
            f'text-decoration:none;font-weight:bold;padding:13px 26px;border-radius:10px">{escape(label)}</a></p>')


def _message(to, subject, text, html, unsubscribe_url=None) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = formataddr((os.environ.get("MAIL_FROM_NAME") or _site_name(), os.environ["MAIL_FROM"]))
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=False)
    msg["Message-ID"] = make_msgid()
    if unsubscribe_url:
        msg["List-Unsubscribe"] = f"<{unsubscribe_url}>"
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    return msg


def _confirmation_message(email, token, lang, base, site) -> EmailMessage:
    t = TEXTS[lang]
    link = f"{base}{url_for('shop.newsletter_confirm', token=token)}"
    body = f'<h1 style="margin:0 0 12px;font-size:22px">{escape(t["confirm_title"])}</h1><p style="margin:0">{escape(t["confirm_body"])}</p>{_button(link, t["confirm_button"])}'
    text = f'{t["confirm_title"]}\n\n{t["confirm_body"]}\n\n{link}\n\n{t["confirm_footer"]}'
    return _message(email, t["confirm_subject"].format(site=site), text, _html(lang, site, body, escape(t["confirm_footer"])))


def _book_message(book, sub, kind, base, site) -> EmailMessage:
    lang = sub["lang"] if sub["lang"] in TEXTS else "fr"
    t = TEXTS[lang]
    link = f"{base}{url_for('shop.book_detail', slug=book['slug'])}"
    unsub = f"{base}{url_for('shop.newsletter_unsubscribe', token=sub['token'])}"
    price, old = book["price"], book["old_price"]
    promo = bool(old and old > price)
    pct = round((old - price) * 100 / old) if promo else 0
    badge = t["badge_promo"].format(pct=pct) if kind == "promo" and promo else t["badge_new"]
    subject = t["subject_promo" if kind == "promo" and promo else "subject_new"].format(title=book["title"], pct=pct)
    cover = book["cover_url"] or ""
    if cover and not cover.startswith("http"):
        cover = base + cover
    price_html = f'<span style="font-size:22px;font-weight:bold;color:#e85200">{escape(_money(price, lang))}</span>'
    if promo:
        price_html += f' <span style="color:#7a6f64;text-decoration:line-through;margin-inline-start:8px">{escape(_money(old, lang))}</span>'
    img = f'<p style="margin:0 0 16px"><img src="{escape(cover)}" alt="" width="160" style="max-width:100%;height:auto;border-radius:6px"></p>' if cover else ""
    body = (f'{img}<p style="margin:0 0 6px;color:#e85200;font-weight:bold;text-transform:uppercase;font-size:13px;letter-spacing:.04em">{escape(badge)}</p>'
            f'<h1 style="margin:0 0 4px;font-size:22px;line-height:1.3">{escape(book["title"])}</h1>'
            f'<p style="margin:0 0 14px;color:#7a6f64">{escape(t["by"])} {escape(book["author"])}</p><p style="margin:0">{price_html}</p>{_button(link, t["button_book"])}')
    footer = f'{escape(t["footer"].format(site=site))} <a href="{escape(unsub)}" style="color:#7a6f64">{escape(t["unsubscribe"])}</a>'
    text = (f'{badge}\n{book["title"]} — {t["by"]} {book["author"]}\n{_money(price, lang)}'
            + (f' ({_money(old, lang)})' if promo else '') + f'\n\n{link}\n\n{t["unsubscribe"]} : {unsub}')
    return _message(sub["email"], subject, text, _html(lang, site, body, footer), unsub)


# ── Envoi (SMTP, en arrière-plan) ───────────────────────────────────────────
def _send_all(messages):
    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT") or 587)
    security = (os.environ.get("SMTP_SECURITY") or ("ssl" if port == 465 else "starttls")).lower()
    sent = 0
    try:
        ctx = ssl.create_default_context()
        smtp = smtplib.SMTP_SSL(host, port, timeout=30, context=ctx) if security == "ssl" else smtplib.SMTP(host, port, timeout=30)
        with smtp:
            if security == "starttls":
                smtp.starttls(context=ctx)
            if os.environ.get("SMTP_USER") and os.environ.get("SMTP_PASSWORD"):
                smtp.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
            for msg in messages:
                try:
                    smtp.send_message(msg)
                    sent += 1
                except smtplib.SMTPException:
                    log.exception("E-mail non envoyé à %s", msg["To"])
    except Exception:
        log.exception("Connexion SMTP impossible (%s:%s)", host, port)
    log.info("Newsletter : %d/%d e-mail(s) envoyé(s)", sent, len(messages))


def _dispatch(messages):
    if messages:
        threading.Thread(target=_send_all, args=(messages,), daemon=True, name="newsletter-mail").start()


# ── Inscription / confirmation / désinscription ─────────────────────────────
def subscribe(email, lang):
    """Crée (ou relance) une inscription non confirmée et envoie l'e-mail de confirmation."""
    lang = lang if lang in TEXTS else "fr"
    row = db.query("SELECT confirmed_at FROM subscribers WHERE email=?", (email,), one=True)
    if row is not None and row["confirmed_at"]:
        return  # déjà confirmée : rien à envoyer (la réponse du site reste la même)
    token = secrets.token_urlsafe(24)
    db.execute(
        "INSERT INTO subscribers(email, token, lang) VALUES(?,?,?) "
        "ON CONFLICT (email) DO UPDATE SET token=EXCLUDED.token, lang=EXCLUDED.lang WHERE subscribers.confirmed_at IS NULL",
        (email, token, lang))
    if not configured():
        log.warning("SMTP non configuré (SMTP_HOST / MAIL_FROM) : e-mail de confirmation non envoyé à %s", email)
        return
    _dispatch([_confirmation_message(email, token, lang, _base_url(), _site_name())])


def confirm(token) -> bool:
    if not _TOKEN_RE.match(token or ""):
        return False
    row = db.query("SELECT id, confirmed_at FROM subscribers WHERE token=?", (token,), one=True)
    if row is None:
        return False
    if not row["confirmed_at"]:
        db.execute("UPDATE subscribers SET confirmed_at = to_char(timezone('utc', now()), 'YYYY-MM-DD HH24:MI:SS') WHERE id=?", (row["id"],))
    return True


def unsubscribe(token) -> bool:
    if not _TOKEN_RE.match(token or ""):
        return False
    row = db.query("SELECT id FROM subscribers WHERE token=?", (token,), one=True)
    if row is None:
        return False
    db.execute("DELETE FROM subscribers WHERE id=?", (row["id"],))
    return True


# ── Annonces automatiques ───────────────────────────────────────────────────
def announce_book(book, kind) -> int:
    """kind = 'new' (nouveau livre) ou 'promo' (livre qui passe en promotion). Retourne le nombre d'e-mails préparés."""
    subs = db.query("SELECT email, token, lang FROM subscribers WHERE confirmed_at IS NOT NULL AND token IS NOT NULL ORDER BY id")
    if not subs:
        return 0
    if not configured():
        log.warning("SMTP non configuré : %d abonné(s) non prévenu(s) pour « %s »", len(subs), book["title"])
        return 0
    base, site = _base_url(), _site_name()
    messages = [_book_message(book, s, kind, base, site) for s in subs]
    _dispatch(messages)
    return len(messages)
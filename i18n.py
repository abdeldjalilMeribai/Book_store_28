"""Langue de l'interface : cookie « lang » (arabe RTL / français)."""
from flask import current_app, has_request_context, request, session
from flask_babel import Babel, gettext as _, lazy_gettext as _l

babel = Babel()


def select_locale():
    cfg = current_app.config
    if has_request_context():                      # la CLI (create-admin) n'a pas de requête
        code = request.cookies.get(cfg["LANG_COOKIE"])
        if not code:
            code = session.get(cfg["LANG_COOKIE"])
        if code in cfg["LANGUAGES"]:
            return code
    return cfg["BABEL_DEFAULT_LOCALE"]


def js_strings():
    """Textes utilisés par le JavaScript. Ta CSP interdit les scripts inline : on les passe en JSON."""
    return {
        "currency": _("DA"),
        "sold_out": _("Ce livre est épuisé."),
        "sold_out_short": _("Épuisé"),
        "qty_limited": _("Quantité limitée à {n} pour ce livre."),
        "added_cart": _("Ajouté au panier"),
        "add_to_cart": _("Ajouter au panier"),
        "qty_of": _("Quantité de {title}"),
        "line_soldout_cart": _("Épuisé : retirez ce livre pour commander"),
        "line_soldout_checkout": _("Épuisé : retirez-le du panier"),
        "removed_wish": _("Retiré des favoris"),
        "added_wish": _("Ajouté aux favoris"),
        "cart_updated": _("Votre panier a été mis à jour (prix ou stock)."),
        "cart_empty": _("Votre panier est vide"),
        "cart_empty_hint": _("Ajoutez un livre : vous ne payez rien avant la livraison."),
        "wish_empty": _("Aucun favori"),
        "wish_empty_hint": _("Touchez le cœur d'un livre pour le retrouver ici."),
        "cover_of": _("Couverture de {title}"),
        "preview_unavailable": _("Aperçu indisponible pour le moment."),
        "copied": _("Code copié"),
        "copy_failed": _("Copie impossible"),
        "thanks": _("Merci !"),
        "generic_error": _("Une erreur est survenue."),
        "unavailable": _("Indisponible"),
        "stock_blocked": _("Un livre de votre panier est épuisé : retirez-le pour continuer."),
        "phone_invalid": _("Numéro invalide : 10 chiffres commençant par 05, 06 ou 07."),
        "address_required": _("Indiquez votre adresse pour la livraison à domicile."),
        "sending": _("Envoi en cours…"),
        "order_failed": _("La commande n'a pas pu être enregistrée."),
        "network": _("Connexion impossible. Vérifiez votre réseau puis réessayez."),
        "cover_preview": _("Aperçu de la couverture"),
        "decrease": _("Diminuer"),
        "increase": _("Augmenter"),
        "remove": _("Retirer"),
        "more_than_stock": _("Plus que {n} en stock"),
        "browse_catalog": _("Parcourir le catalogue"),
        "open_menu": _("Ouvrir le menu"),
        "close": _("Fermer"),
        "view_detail": _("Voir la fiche"),
        "choose_wilaya": _("Choisissez une wilaya"),
        "name_required": _("Indiquez votre nom complet."),
        "wilaya_required": _("Choisissez votre wilaya."),
        "commune_required": _("Indiquez votre commune."),
    }
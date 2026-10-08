from flask_babel import lazy_gettext as _l
"""Données de livraison Algérie : 58 wilayas et tarifs (DA). Modifiez ici pour ajuster les prix."""

WILAYAS = [
    {"code": 1,  "name": "Adrar",              "home_price": 1100, "office_price": 600},
    {"code": 2,  "name": "Chlef",              "home_price": 700,  "office_price": 400},
    {"code": 3,  "name": "Laghouat",           "home_price": 900,  "office_price": 500},
    {"code": 4,  "name": "Oum El Bouaghi",     "home_price": 800,  "office_price": 400},
    {"code": 5,  "name": "Batna",              "home_price": 800,  "office_price": 400},
    {"code": 6,  "name": "Béjaïa",             "home_price": 700,  "office_price": 400},
    {"code": 7,  "name": "Biskra",             "home_price": 900,  "office_price": 500},
    {"code": 8,  "name": "Béchar",             "home_price": 1100, "office_price": 600},
    {"code": 9,  "name": "Blida",              "home_price": 500,  "office_price": 250},
    {"code": 10, "name": "Bouira",             "home_price": 650,  "office_price": 400},
    {"code": 11, "name": "Tamanrasset",        "home_price": 1300, "office_price": 800},
    {"code": 12, "name": "Tébessa",            "home_price": 800,  "office_price": 500},
    {"code": 13, "name": "Tlemcen",            "home_price": 800,  "office_price": 400},
    {"code": 14, "name": "Tiaret",             "home_price": 800,  "office_price": 400},
    {"code": 15, "name": "Tizi Ouzou",         "home_price": 650,  "office_price": 400},
    {"code": 16, "name": "Alger",              "home_price": 400,  "office_price": 200},
    {"code": 17, "name": "Djelfa",             "home_price": 900,  "office_price": 500},
    {"code": 18, "name": "Jijel",              "home_price": 700,  "office_price": 400},
    {"code": 19, "name": "Sétif",              "home_price": 700,  "office_price": 400},
    {"code": 20, "name": "Saïda",              "home_price": 800,  "office_price": 400},
    {"code": 21, "name": "Skikda",             "home_price": 700,  "office_price": 400},
    {"code": 22, "name": "Sidi Bel Abbès",     "home_price": 700,  "office_price": 400},
    {"code": 23, "name": "Annaba",             "home_price": 700,  "office_price": 400},
    {"code": 24, "name": "Guelma",             "home_price": 800,  "office_price": 400},
    {"code": 25, "name": "Constantine",        "home_price": 700,  "office_price": 400},
    {"code": 26, "name": "Médéa",              "home_price": 600,  "office_price": 400},
    {"code": 27, "name": "Mostaganem",         "home_price": 700,  "office_price": 400},
    {"code": 28, "name": "M'Sila",             "home_price": 800,  "office_price": 500},
    {"code": 29, "name": "Mascara",            "home_price": 700,  "office_price": 400},
    {"code": 30, "name": "Ouargla",            "home_price": 1000, "office_price": 500},
    {"code": 31, "name": "Oran",               "home_price": 700,  "office_price": 400},
    {"code": 32, "name": "El Bayadh",          "home_price": 1000, "office_price": 500},
    {"code": 33, "name": "Illizi",             "home_price": 1300, "office_price": 600},
    {"code": 34, "name": "Bordj Bou Arreridj", "home_price": 700,  "office_price": 400},
    {"code": 35, "name": "Boumerdès",          "home_price": 600,  "office_price": 350},
    {"code": 36, "name": "El Tarf",            "home_price": 800,  "office_price": 400},
    {"code": 37, "name": "Tindouf",            "home_price": 1300, "office_price": 600},
    {"code": 38, "name": "Tissemsilt",         "home_price": 800,  "office_price": 400},
    {"code": 39, "name": "El Oued",            "home_price": 900,  "office_price": 500},
    {"code": 40, "name": "Khenchela",          "home_price": 800,  "office_price": 500},
    {"code": 41, "name": "Souk Ahras",         "home_price": 800,  "office_price": 500},
    {"code": 42, "name": "Tipaza",             "home_price": 600,  "office_price": 350},
    {"code": 43, "name": "Mila",               "home_price": 700,  "office_price": 400},
    {"code": 44, "name": "Aïn Defla",          "home_price": 600,  "office_price": 400},
    {"code": 45, "name": "Naâma",              "home_price": 1000, "office_price": 500},
    {"code": 46, "name": "Aïn Témouchent",     "home_price": 700,  "office_price": 400},
    {"code": 47, "name": "Ghardaïa",           "home_price": 1000, "office_price": 500},
    {"code": 48, "name": "Relizane",           "home_price": 700,  "office_price": 400},
    {"code": 49, "name": "Timimoun",           "home_price": 1300, "office_price": 600},
    {"code": 51, "name": "Ouled Djellal",      "home_price": 900,  "office_price": 500},
    {"code": 52, "name": "Béni Abbès",         "home_price": 1300, "office_price": None},
    {"code": 53, "name": "In Salah",           "home_price": 1300, "office_price": 600},
    {"code": 55, "name": "Touggourt",          "home_price": 900,  "office_price": 500},
    {"code": 57, "name": "El M'Ghair",         "home_price": 900,  "office_price": None},
    {"code": 58, "name": "El Meniaa",          "home_price": 1000, "office_price": 500},
]
WILAYA_BY_CODE = {w["code"]: w for w in WILAYAS}

DELIVERY_METHODS = ("home", "office")


ORDER_STATUSES = ("pending", "shipped", "delivered", "cancelled")
DELIVERY_LABELS = {"home": _l("À domicile"), "office": _l("Bureau de livraison")}

ORDER_STATUS_LABELS = {
    "pending": _l("En préparation"), "shipped": _l("Expédiée"),
    "delivered": _l("Livrée"), "cancelled": _l("Annulée"),
}

BADGES = {"": _l("Aucun"), "new": _l("Nouveauté"), "bestseller": _l("Best-seller")}

# Libellés d'affichage : les valeurs stockées en base (« Français », « Poche »…) ne changent pas.
VALUE_LABELS = {
    "Français": _l("Français"), "Arabe": _l("Arabe"), "Anglais": _l("Anglais"),
    "Amazigh": _l("Amazigh"), "Autre": _l("Autre"),
    "Poche": _l("Poche"), "Broché": _l("Broché"), "Relié": _l("Relié"), "Beau livre": _l("Beau livre"),
}

BOOK_LANGUAGES = ("Français", "Arabe", "Anglais", "Amazigh", "Autre")
BOOK_FORMATS = ("Poche", "Broché", "Relié", "Beau livre", "Autre")


def delivery_price_for(wilaya_code, method):
    """Frais de livraison (DA) ou None si wilaya inconnue / mode indisponible."""
    w = WILAYA_BY_CODE.get(wilaya_code)
    if not w or method not in DELIVERY_METHODS:
        return None
    return w["office_price"] if method == "office" else w["home_price"]


WILAYA_AR = {
    1: "أدرار", 2: "الشلف", 3: "الأغواط", 4: "أم البواقي", 5: "باتنة", 6: "بجاية", 7: "بسكرة", 8: "بشار",
    9: "البليدة", 10: "البويرة", 11: "تمنراست", 12: "تبسة", 13: "تلمسان", 14: "تيارت", 15: "تيزي وزو",
    16: "الجزائر", 17: "الجلفة", 18: "جيجل", 19: "سطيف", 20: "سعيدة", 21: "سكيكدة", 22: "سيدي بلعباس",
    23: "عنابة", 24: "قالمة", 25: "قسنطينة", 26: "المدية", 27: "مستغانم", 28: "المسيلة", 29: "معسكر",
    30: "ورقلة", 31: "وهران", 32: "البيض", 33: "إليزي", 34: "برج بوعريريج", 35: "بومرداس", 36: "الطارف",
    37: "تندوف", 38: "تيسمسيلت", 39: "الوادي", 40: "خنشلة", 41: "سوق أهراس", 42: "تيبازة", 43: "ميلة",
    44: "عين الدفلى", 45: "النعامة", 46: "عين تموشنت", 47: "غرداية", 48: "غليزان", 49: "تيميمون",
    50: "برج باجي مختار", 51: "أولاد جلال", 52: "بني عباس", 53: "عين صالح", 54: "عين قزام",
    55: "تقرت", 56: "جانت", 57: "المغير", 58: "المنيعة",
}
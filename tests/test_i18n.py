"""Tests de l'internationalisation (Flask-Babel) : français (par défaut) et arabe RTL."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pgtest  # définit DATABASE_URL vers la base de test : à garder AVANT « from app import … »
import db
import seed_demo
import tempfile
import security
from app import create_app


class I18nTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pgtest.reset()
        cls.uploads = tempfile.mkdtemp()
        cls.app = create_app({"DATABASE": pgtest.TEST_URL, "TESTING": True, "UPLOAD_FOLDER": cls.uploads})
        seed_demo.OUT_DIR = cls.uploads
        seed_demo.run(cls.app)

    def setUp(self):
        self.client = self.app.test_client()

    def test_french_default(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        html = r.get_data(as_text=True)
        self.assertIn("Catalogue", html)
        self.assertIn('lang="fr"', html)
        self.assertNotIn('dir="rtl"', html)

    def test_arabic_switch(self):
        r_switch = self.client.get("/changer-langue/ar")
        self.assertEqual(r_switch.status_code, 302)
        self.client.set_cookie("lang", "ar")

        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        html = r.get_data(as_text=True)
        self.assertIn('lang="ar"', html)
        self.assertIn('dir="rtl"', html)
        self.assertIn("فهرس", html)
        self.assertIn("من نحن", html)
        self.assertIn("تتبع طلبي", html)
        self.assertIn("سلتي", html)

        r_cat = self.client.get("/catalogue")
        self.assertEqual(r_cat.status_code, 200)
        html_cat = r_cat.get_data(as_text=True)
        self.assertIn("الفلاتر والترتيب", html_cat)
        self.assertIn("بحث", html_cat)

        r_track = self.client.get("/suivi")
        self.assertEqual(r_track.status_code, 200)
        html_track = r_track.get_data(as_text=True)
        self.assertIn("أين طردي؟", html_track)

        r_order = self.client.get("/commande")
        self.assertEqual(r_order.status_code, 200)
        html_order = r_order.get_data(as_text=True)
        self.assertIn("بيانات الاتصال", html_order)
        self.assertIn("تأكيد الطلب", html_order)

        r_login = self.client.get("/connexion")
        self.assertEqual(r_login.status_code, 200)
        html_login = r_login.get_data(as_text=True)
        self.assertIn("تسجيل الدخول", html_login)
        self.assertIn("البريد الإلكتروني", html_login)

    def test_admin_arabic(self):
        with self.app.app_context():
            admin_user = db.query("SELECT * FROM users WHERE is_admin=1", one=True)
            if not admin_user:
                db.execute(
                    "INSERT INTO users(username, email, password_hash, is_admin, must_change_password) VALUES(?,?,?,1,0)",
                    ("Admin", "admin_test@test.dz", security.hash_password("AdminPass123!")),
                )
                admin_user = db.query("SELECT * FROM users WHERE is_admin=1", one=True)
            else:
                db.execute("UPDATE users SET must_change_password=0 WHERE id=?", (admin_user["id"],))
            admin_id = admin_user["id"]

        with self.client.session_transaction() as s:
            s["uid"] = admin_id
            s["lang"] = "ar"

        self.client.set_cookie("lang", "ar")

        r_adm = self.client.get("/admin/", follow_redirects=True)
        self.assertEqual(r_adm.status_code, 200)
        html_adm = r_adm.get_data(as_text=True)
        self.assertIn('lang="ar"', html_adm)
        self.assertIn('dir="rtl"', html_adm)
        self.assertIn("لوحة التحكم", html_adm)
        self.assertIn("الطلبات", html_adm)
        self.assertIn("الكتب", html_adm)
        self.assertIn("الإعدادات", html_adm)

    def test_switch_back_to_french(self):
        self.client.set_cookie("lang", "ar")
        r_switch = self.client.get("/changer-langue/fr")
        self.assertEqual(r_switch.status_code, 302)
        self.client.set_cookie("lang", "fr")

        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        html = r.get_data(as_text=True)
        self.assertIn("Catalogue", html)
        self.assertIn('lang="fr"', html)
        self.assertNotIn('dir="rtl"', html)

    def test_i18n_json_data_payload(self):
        import json
        import re

        # In French
        r_fr = self.client.get("/")
        html_fr = r_fr.get_data(as_text=True)
        self.assertIn('id="i18n-data"', html_fr)
        match_fr = re.search(r'<script id="i18n-data"[^>]*>(.*?)</script>', html_fr)
        self.assertIsNotNone(match_fr)
        data_fr = json.loads(match_fr.group(1))
        self.assertEqual(data_fr["currency"], "DA")
        self.assertEqual(data_fr["add_to_cart"], "Ajouter au panier")

        # In Arabic
        self.client.set_cookie("lang", "ar")
        r_ar = self.client.get("/")
        html_ar = r_ar.get_data(as_text=True)
        self.assertIn('id="i18n-data"', html_ar)
        match_ar = re.search(r'<script id="i18n-data"[^>]*>(.*?)</script>', html_ar)
        self.assertIsNotNone(match_ar)
        data_ar = json.loads(match_ar.group(1))
        self.assertEqual(data_ar["currency"], "دج")
        self.assertEqual(data_ar["add_to_cart"], "أضف إلى السلة")

    def test_about_and_catalog_arabic(self):
        self.client.set_cookie("lang", "ar")
        r_about = self.client.get("/a-propos")
        self.assertEqual(r_about.status_code, 200)
        html_about = r_about.get_data(as_text=True)
        self.assertIn("من نحن", html_about)
        self.assertIn("58 ولاية", html_about)
        self.assertIn("الأسئلة الشائعة", html_about)

        r_cat = self.client.get("/catalogue?q=test")
        self.assertEqual(r_cat.status_code, 200)
        html_cat = r_cat.get_data(as_text=True)
        self.assertIn("الفلاتر والترتيب", html_cat)
        self.assertIn("بحث : test", html_cat)
        self.assertIn("فهرس", html_cat)
        # Vérification des options de tri traduites en arabe
        self.assertIn("الأكثر مبيعاً", html_cat)
        self.assertIn("السعر: من الأقل إلى الأعلى", html_cat)
        self.assertIn("السعر: من الأعلى إلى الأقل", html_cat)
        self.assertIn("العنوان: أ إلى ي", html_cat)
        # Vérification des champs et placeholders de filtres
        self.assertIn("الأدنى", html_cat)
        self.assertIn("السعر الأدنى", html_cat)
        self.assertIn("السعر الأقصى", html_cat)

        # Vérification de la bascule de tri et affichage des livres avec étiquette
        r_pop = self.client.get("/catalogue?badge=new&tri=popular")
        self.assertEqual(r_pop.status_code, 200)
        self.assertIn("badge--bestseller", r_pop.get_data(as_text=True))

        r_new = self.client.get("/catalogue?badge=bestseller&tri=new")
        self.assertEqual(r_new.status_code, 200)
        self.assertIn("badge--new", r_new.get_data(as_text=True))

    def test_admin_subpages_arabic(self):
        with self.app.app_context():
            admin_user = db.query("SELECT * FROM users WHERE is_admin=1", one=True)
            admin_id = admin_user["id"]

        with self.client.session_transaction() as s:
            s["uid"] = admin_id
            s["lang"] = "ar"
        self.client.set_cookie("lang", "ar")

        pages = [
            ("/admin/livres", "الكتب"),
            ("/admin/commandes", "الطلبات"),
            ("/admin/genres", "التصنيفات"),
            ("/admin/clients", "الزبائن"),
            ("/admin/avis", "الآراء"),
            ("/admin/reglages", "الإعدادات"),
            ("/admin/stock", "المخزون"),
        ]
        for path, expected_text in pages:
            res = self.client.get(path)
            self.assertEqual(res.status_code, 200, f"Path {path} failed")
            html = res.get_data(as_text=True)
            self.assertIn(expected_text, html, f"Text {expected_text} not found in {path}")
            self.assertIn('dir="rtl"', html)
            self.assertIn('lang="ar"', html)

    def test_arabic_mobile_menu_and_no_overflow(self):
        self.client.set_cookie("lang", "ar")
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)

        self.assertIn('dir="rtl"', html)
        self.assertIn('lang="ar"', html)
        self.assertIn('id="mobile-sheet"', html)
        self.assertIn('data-menu', html)
        self.assertIn('burger__open', html)
        self.assertIn('burger__close', html)

        with open("static/css/components.css", "r", encoding="utf-8") as f:
            css = f.read()
        self.assertNotIn("left: -9999px", css)
        self.assertIn("clip-path: inset(50%)", css)

        with open("static/css/base.css", "r", encoding="utf-8") as f:
            base_css = f.read()
        self.assertIn("overflow-x: clip", base_css)


if __name__ == "__main__":
    unittest.main()

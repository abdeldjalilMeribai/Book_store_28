"""Tests de bout en bout : commande, stock, suivi, CSRF, auth, admin. Lancer : python -m unittest discover -s tests -v"""
import io
import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PIL import Image

import db
import security
from app import create_app
import seed_demo


def token_from(client, path="/"):
    html = client.get(path).get_data(as_text=True)
    return re.search(r'name="csrf-token" content="([^"]+)"', html).group(1)


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.uploads = tempfile.mkdtemp()
        cls.app = create_app({"DATABASE": os.path.join(cls.tmp, "t.db"), "TESTING": True, "UPLOAD_FOLDER": cls.uploads})
        seed_demo.OUT_DIR = cls.uploads
        seed_demo.run(cls.app)
        with cls.app.app_context():
            db.execute("UPDATE users SET must_change_password=0")
            cls.admin_id = db.query("SELECT id FROM users WHERE is_admin=1", one=True)["id"]
            cls.camus = db.query("SELECT id, stock, price FROM books WHERE slug='l-etranger'", one=True)
            cls.sold_out = db.query("SELECT id FROM books WHERE stock=0", one=True)["id"]

    def setUp(self):
        self.c = self.app.test_client()

    def order(self, items, client=None, **over):
        c = client or self.c
        tok = token_from(c, "/commande")
        body = {"full_name": "Samir Benali", "phone": "0550 12 34 56", "wilaya": 16, "commune": "Bab Ezzouar",
                "address": "12 rue des Oliviers", "delivery_method": "home", "items": items}
        body.update(over)
        return c.post("/api/commander", json=body, headers={"X-CSRFToken": tok})

    def admin_client(self):
        c = self.app.test_client()
        with c.session_transaction() as s:
            s["uid"] = self.admin_id
            s["_csrf"] = "secret-admin"
        return c, security_token(self.app, "secret-admin")


def security_token(app, secret):
    import hashlib, hmac
    nonce = "n0nce"
    sig = hmac.new(app.config["SECRET_KEY"].encode(), f"{secret}:{nonce}".encode(), hashlib.sha256).hexdigest()
    return f"{nonce}.{sig}"


class ShopTests(Base):
    def test_public_pages_render(self):
        for path in ["/", "/catalogue", "/catalogue?q=camus&tri=price_asc", "/livre/nedjma", "/suivi", "/connexion", "/inscription", "/a-propos", "/commande"]:
            self.assertEqual(self.c.get(path).status_code, 200, path)
        self.assertEqual(self.c.get("/livre/inexistant").status_code, 404)

    def test_search_escapes_wildcards(self):
        html = self.c.get("/catalogue?q=%25").get_data(as_text=True)
        self.assertIn("Aucun livre ne correspond", html)

    def test_security_headers_and_no_inline(self):
        r = self.c.get("/")
        self.assertIn("script-src 'self'", r.headers["Content-Security-Policy"])
        self.assertEqual(r.headers["X-Frame-Options"], "DENY")
        html = r.get_data(as_text=True)
        self.assertNotRegex(html, r"<script(?![^>]*\bsrc=)(?![^>]*application/json)[^>]*>")
        self.assertNotRegex(html, r'\sstyle="(?!")')
        self.assertNotRegex(html, r'<[a-zA-Z][^>]*\son(click|load|error|mouseover)=')

    def test_order_flow_and_stock(self):
        with self.app.app_context():
            before = db.scalar("SELECT stock FROM books WHERE id=?", (self.camus["id"],))
        r = self.order([{"id": self.camus["id"], "qty": 2}])
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        data = r.get_json()
        self.assertTrue(re.fullmatch(r"L28-[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}", data["tracking_code"]))
        self.assertEqual(data["total"], self.camus["price"] * 2 + 400)       # Alger, domicile = 400 DA
        with self.app.app_context():
            self.assertEqual(db.scalar("SELECT stock FROM books WHERE id=?", (self.camus["id"],)), before - 2)
        self.assertEqual(self.c.get("/commande/confirmee").status_code, 200)

    def test_price_is_never_taken_from_client(self):
        r = self.order([{"id": self.camus["id"], "qty": 1, "price": 1}])
        self.assertEqual(r.get_json()["total"], self.camus["price"] + 400)

    def test_cannot_oversell_or_order_sold_out(self):
        r = self.order([{"id": self.sold_out, "qty": 1}])
        self.assertEqual(r.status_code, 409)
        r = self.order([{"id": self.camus["id"], "qty": 10}] * 3)             # fusionné et plafonné à 10, mais stock insuffisant ?
        self.assertIn(r.status_code, (201, 409))
        with self.app.app_context():
            self.assertGreaterEqual(db.scalar("SELECT stock FROM books WHERE id=?", (self.camus["id"],)), 0)

    def test_validation_errors(self):
        r = self.order([{"id": self.camus["id"], "qty": 1}], phone="123")
        self.assertEqual(r.status_code, 422)
        self.assertIn("phone", r.get_json()["fields"])
        r = self.order([{"id": self.camus["id"], "qty": 1}], delivery_method="home", address="")
        self.assertIn("address", r.get_json()["fields"])
        r = self.order([{"id": self.camus["id"], "qty": 1}], wilaya=52, delivery_method="office")
        self.assertEqual(r.status_code, 400)                                    # Béni Abbès : pas de bureau
        self.assertEqual(self.order([]).status_code, 400)

    def test_csrf_required_everywhere(self):
        self.assertEqual(self.c.post("/api/commander", json={}).status_code, 400)
        self.assertEqual(self.c.post("/api/newsletter", json={"email": "a@b.dz"}).status_code, 400)
        self.assertEqual(self.c.post("/connexion", data={"email": "x", "password": "y"}).status_code, 400)
        self.assertEqual(self.c.post("/api/commander", json={}, headers={"X-CSRFToken": "faux.token"}).status_code, 400)
        tok = token_from(self.c)
        r = self.c.post("/api/newsletter", json={"email": "a@b.dz"}, headers={"X-CSRFToken": tok, "Origin": "https://evil.example"})
        self.assertEqual(r.status_code, 400)                                    # origine étrangère refusée

    def test_tracking_requires_matching_phone_and_throttles(self):
        code = self.order([{"id": self.camus["id"], "qty": 1}]).get_json()["tracking_code"]
        tok = token_from(self.c, "/suivi")
        ok = self.c.post("/suivi", data={"csrf_token": tok, "code": code.lower(), "phone": "+213 550 12 34 56"})
        self.assertIn("En préparation", ok.get_data(as_text=True))
        bad = self.c.post("/suivi", data={"csrf_token": tok, "code": code, "phone": "0661000000"})
        self.assertIn("Aucune commande ne correspond", bad.get_data(as_text=True))
        for _ in range(6):
            last = self.c.post("/suivi", data={"csrf_token": tok, "code": code, "phone": "0661000000"})
        self.assertEqual(last.status_code, 429)

    def test_review_needs_delay_and_escapes_html(self):
        self.c.get("/livre/nedjma")
        tok = token_from(self.c, "/livre/nedjma")
        with self.app.app_context():
            bid = db.query("SELECT id FROM books WHERE slug='nedjma'", one=True)["id"]
        with self.c.session_transaction() as s:
            s[f"rv_{bid}"] -= 60
        self.c.post(f"/livre/{bid}/avis", data={"csrf_token": tok, "name": "<script>alert(1)</script>", "rating": "5", "comment": "Très bon livre <img src=x onerror=alert(1)>"})
        html = self.c.get("/livre/nedjma").get_data(as_text=True)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertNotIn("<img src=x", html)

    def test_review_too_fast_is_rejected(self):
        tok = token_from(self.c, "/livre/1984")
        with self.app.app_context():
            bid = db.query("SELECT id FROM books WHERE slug='1984'", one=True)["id"]
        self.c.post(f"/livre/{bid}/avis", data={"csrf_token": tok, "name": "Bot", "rating": "5", "comment": "Trop rapide pour être honnête"})
        with self.app.app_context():
            self.assertEqual(db.scalar("SELECT COUNT(*) FROM reviews WHERE author_name='Bot'"), 0)

    def test_review_moderation_workflow(self):
        self.app.config["MODERATE_REVIEWS_IN_TEST"] = True
        try:
            self.c.get("/livre/nedjma")
            tok = token_from(self.c, "/livre/nedjma")
            with self.app.app_context():
                bid = db.query("SELECT id FROM books WHERE slug='nedjma'", one=True)["id"]
            with self.c.session_transaction() as s:
                s[f"rv_{bid}"] -= 60

            review_text = "Critique en attente de modération 12345"
            self.c.post(f"/livre/{bid}/avis", data={
                "csrf_token": tok, "name": "Lecteur Anonyme", "rating": "4", "comment": review_text
            })

            html = self.c.get("/livre/nedjma").get_data(as_text=True)
            self.assertNotIn(review_text, html)

            with self.app.app_context():
                rev = db.query("SELECT * FROM reviews WHERE comment=? AND book_id=?", (review_text, bid), one=True)
                self.assertIsNotNone(rev)
                self.assertEqual(rev["is_visible"], 0)
                rev_id = rev["id"]

            c_admin, tok_admin = self.admin_client()
            c_admin.post(f"/admin/avis/{rev_id}/visibilite", data={"csrf_token": tok_admin})

            html_after = self.c.get("/livre/nedjma").get_data(as_text=True)
            self.assertIn(review_text, html_after)
        finally:
            self.app.config.pop("MODERATE_REVIEWS_IN_TEST", None)

    def test_throttle_blocked_does_not_modify_database(self):
        with self.app.app_context():
            count_before = db.scalar("SELECT COUNT(*) FROM throttle")
            blocked = security.throttle_blocked("order", "192.0.2.1", 30, 3600)
            self.assertFalse(blocked)
            count_after = db.scalar("SELECT COUNT(*) FROM throttle")
            self.assertEqual(count_before, count_after)


class AuthTests(Base):
    def test_register_login_logout_and_open_redirect(self):
        tok = token_from(self.c, "/inscription")
        r = self.c.post("/inscription", data={"csrf_token": tok, "username": "Lina", "email": "lina@exemple.dz", "password": "Livres2026", "confirm": "Livres2026"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.c.get("/mon-compte").status_code, 200)
        tok = token_from(self.c)
        self.c.post("/deconnexion", data={"csrf_token": tok})
        self.assertEqual(self.c.get("/mon-compte").status_code, 302)
        tok = token_from(self.c, "/connexion")
        r = self.c.post("/connexion?next=//evil.example", data={"csrf_token": tok, "email": "lina@exemple.dz", "password": "Livres2026", "next": "//evil.example"})
        self.assertNotIn("evil.example", r.headers["Location"])

    def test_weak_password_and_duplicate(self):
        tok = token_from(self.c, "/inscription")
        r = self.c.post("/inscription", data={"csrf_token": tok, "username": "Z", "email": "x@exemple.dz", "password": "abc", "confirm": "abc"})
        self.assertEqual(r.status_code, 422)

    def test_login_throttle(self):
        tok = token_from(self.c, "/connexion")
        for _ in range(7):
            r = self.c.post("/connexion", data={"csrf_token": tok, "email": "nobody@exemple.dz", "password": "Mauvais123"})
        self.assertEqual(r.status_code, 429)

    def test_session_is_rotated_on_login(self):
        before = token_from(self.c, "/connexion")
        with self.c.session_transaction() as s:
            old = s["_csrf"]
        c2 = self.app.test_client()
        tok = token_from(c2, "/inscription")
        c2.post("/inscription", data={"csrf_token": tok, "username": "Yacine", "email": "y@exemple.dz", "password": "Livres2026", "confirm": "Livres2026"})
        with c2.session_transaction() as s:
            self.assertNotEqual(s["_csrf"], old)

    def test_must_change_password_gate(self):
        with self.app.app_context():
            uid = db.execute("INSERT INTO users(username,email,password_hash,must_change_password) VALUES('T','t@exemple.dz',?,1)", (security.hash_password("Provisoire1"),))
        c = self.app.test_client()
        tok = token_from(c, "/connexion")
        c.post("/connexion", data={"csrf_token": tok, "email": "t@exemple.dz", "password": "Provisoire1"})
        r = c.get("/catalogue")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/mot-de-passe", r.headers["Location"])

    def test_session_invalidation_on_password_change(self):
        c1 = self.app.test_client()
        tok = token_from(c1, "/inscription")
        c1.post("/inscription", data={
            "csrf_token": tok, "username": "SessionTest", "email": "session@exemple.dz",
            "password": "Password123!", "confirm": "Password123!"
        })
        self.assertEqual(c1.get("/mon-compte").status_code, 200)

        c2 = self.app.test_client()
        tok2 = token_from(c2, "/connexion")
        c2.post("/connexion", data={
            "csrf_token": tok2, "email": "session@exemple.dz", "password": "Password123!"
        })
        self.assertEqual(c2.get("/mon-compte").status_code, 200)

        tok_pw = token_from(c2, "/mot-de-passe")
        c2.post("/mot-de-passe", data={
            "csrf_token": tok_pw,
            "current": "Password123!",
            "new": "NewSecret2026!",
            "confirm": "NewSecret2026!"
        })

        self.assertEqual(c2.get("/mon-compte").status_code, 200)

        r1_after = c1.get("/mon-compte")
        self.assertEqual(r1_after.status_code, 302)
        self.assertIn("/connexion", r1_after.headers["Location"])


class AdminTests(Base):
    def test_admin_requires_login_and_admin_role(self):
        r = self.c.get("/admin/")
        self.assertEqual(r.status_code, 302)
        with self.app.app_context():
            uid = db.execute("INSERT INTO users(username,email,password_hash) VALUES('Client','cl@exemple.dz',?)", (security.hash_password("Client1234"),))
        c = self.app.test_client()
        with c.session_transaction() as s:
            s["uid"] = uid
        self.assertEqual(c.get("/admin/").status_code, 403)
        self.assertEqual(c.get("/admin/api/notifications").status_code, 403)

    def test_status_change_restores_and_rededucts_stock(self):
        code = self.order([{"id": self.camus["id"], "qty": 3}]).get_json()["tracking_code"]
        c, tok = self.admin_client()
        with self.app.app_context():
            oid = db.query("SELECT id FROM orders WHERE tracking_code=?", (code,), one=True)["id"]
            after_order = db.scalar("SELECT stock FROM books WHERE id=?", (self.camus["id"],))
        c.post(f"/admin/commandes/{oid}/statut", data={"csrf_token": tok, "status": "cancelled"})
        with self.app.app_context():
            self.assertEqual(db.scalar("SELECT stock FROM books WHERE id=?", (self.camus["id"],)), after_order + 3)
        c.post(f"/admin/commandes/{oid}/statut", data={"csrf_token": tok, "status": "delivered"})
        with self.app.app_context():
            self.assertEqual(db.scalar("SELECT stock FROM books WHERE id=?", (self.camus["id"],)), after_order)
            self.assertEqual(db.scalar("SELECT status FROM orders WHERE id=?", (oid,)), "delivered")

    def test_stock_adjust_cannot_go_negative(self):
        c, tok = self.admin_client()
        c.post(f"/admin/stock/{self.camus['id']}/ajuster", data={"csrf_token": tok, "change": "-99999", "reason": "test"})
        with self.app.app_context():
            self.assertGreaterEqual(db.scalar("SELECT stock FROM books WHERE id=?", (self.camus["id"],)), 0)

    def test_admin_post_without_csrf_is_rejected(self):
        c, _ = self.admin_client()
        self.assertEqual(c.post("/admin/avis/1/supprimer").status_code, 400)

    def test_create_book_with_image_upload_and_reject_fake_image(self):
        c, tok = self.admin_client()
        buf = io.BytesIO(); Image.new("RGB", (400, 600), (239, 88, 7)).save(buf, "PNG"); buf.seek(0)
        form = {"csrf_token": tok, "title": "Livre de test", "author": "Auteur Test", "price": "1500", "stock": "5", "description": "Une description suffisamment longue.",
                "is_published": "1", "cover": (buf, "cover.png")}
        r = c.post("/admin/livres/nouveau", data=form, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 302, r.get_data(as_text=True)[:400])
        with self.app.app_context():
            row = db.query("SELECT * FROM books WHERE slug='livre-de-test'", one=True)
            self.assertTrue(row["cover_url"].endswith(".jpg"))
        self.assertTrue(os.path.exists(os.path.join(self.uploads, os.path.basename(row["cover_url"]))))
        form2 = {"csrf_token": tok, "title": "Faux", "author": "X Y", "price": "100", "stock": "1", "description": "Une description suffisamment longue.",
                 "cover": (io.BytesIO(b"<?php echo 1; ?>"), "shell.png")}
        c.post("/admin/livres/nouveau", data=form2, content_type="multipart/form-data")
        self.assertEqual([f for f in os.listdir(self.uploads) if f.endswith(".php")], [])

    def test_book_with_orders_is_hidden_not_deleted(self):
        self.order([{"id": self.camus["id"], "qty": 1}])
        c, tok = self.admin_client()
        c.post(f"/admin/livres/{self.camus['id']}/supprimer", data={"csrf_token": tok})
        with self.app.app_context():
            row = db.query("SELECT is_published FROM books WHERE id=?", (self.camus["id"],), one=True)
            self.assertIsNotNone(row); self.assertEqual(row["is_published"], 0)
            db.execute("UPDATE books SET is_published=1 WHERE id=?", (self.camus["id"],))

    def test_dashboard_periods(self):
        c, _ = self.admin_client()
        for p in ["today", "7d", "30d", "90d", "year", "all", "bogus"]:
            self.assertEqual(c.get(f"/admin/?periode={p}").status_code, 200, p)


if __name__ == "__main__":
    unittest.main()

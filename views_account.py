"""Comptes : inscription, connexion, déconnexion, mes commandes, changement de mot de passe."""
from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

import db
import security
from security import clean_text, safe_next

bp = Blueprint("account", __name__)


def _default_after_login(user):
    return url_for("admin.dashboard") if user["is_admin"] else url_for("account.profile")


@bp.route("/connexion", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(_default_after_login(g.user))
    nxt = safe_next(request.values.get("next"))
    form = {"email": ""}
    if request.method == "POST":
        email = clean_text(request.form.get("email"), 255).lower()
        password = request.form.get("password", "")
        form["email"] = email
        ip, ident = security.client_ip(), f"mail:{email}"
        if security.throttle_blocked("login", ip, 15, 900) or security.throttle_blocked("login", ident, 6, 900):
            flash("Trop de tentatives. Patientez quelques minutes avant de réessayer.", "error")
            return render_template("login.html", form=form, next=nxt), 429
        user = db.query("SELECT * FROM users WHERE email=? AND is_active=1", (email,), one=True)
        # Même coût de calcul que l'utilisateur existe ou non (pas d'énumération par le temps de réponse).
        stored = user["password_hash"] if user else security.hash_password("x" * 12)
        ok = security.verify_password(stored, password) and user is not None
        if ok:
            security.throttle_clear("login", ident)
            security.login_user(user, remember=bool(request.form.get("remember")))
            return redirect(nxt or _default_after_login(user))
        security.throttle_hit("login", ip)
        security.throttle_hit("login", ident)
        flash("E-mail ou mot de passe incorrect.", "error")
    return render_template("login.html", form=form, next=nxt)


@bp.route("/inscription", methods=["GET", "POST"])
def register():
    if g.user:
        return redirect(url_for("account.profile"))
    form = {"username": "", "email": ""}
    errors = {}
    if request.method == "POST":
        form["username"] = clean_text(request.form.get("username"), 60)
        form["email"] = clean_text(request.form.get("email"), 255).lower()
        password, confirm = request.form.get("password", ""), request.form.get("confirm", "")
        if request.form.get("website"):                       # champ piège pour robots
            return redirect(url_for("shop.home"))
        if security.throttle_blocked("register", security.client_ip(), 5, 3600):
            flash("Trop de créations de compte depuis cette connexion. Réessayez plus tard.", "error")
            return render_template("register.html", form=form, errors=errors), 429
        if len(form["username"]) < 2:
            errors["username"] = "Indiquez votre nom (2 caractères minimum)."
        if not security.valid_email(form["email"]):
            errors["email"] = "Adresse e-mail invalide."
        elif db.query("SELECT 1 FROM users WHERE email=?", (form["email"],), one=True):
            errors["email"] = "Un compte existe déjà avec cet e-mail."
        pw = security.password_errors(password)
        if pw:
            errors["password"] = " ".join(pw)
        elif password != confirm:
            errors["confirm"] = "Les deux mots de passe ne correspondent pas."
        if not errors:
            security.throttle_hit("register", security.client_ip())
            uid = db.execute("INSERT INTO users(username,email,password_hash,session_version) VALUES(?,?,?,1)",
                             (form["username"], form["email"], security.hash_password(password)))
            security.login_user(db.query("SELECT * FROM users WHERE id=?", (uid,), one=True))
            flash("Bienvenue ! Votre compte est créé.", "success")
            return redirect(safe_next(request.args.get("next")) or url_for("account.profile"))
    return render_template("register.html", form=form, errors=errors), (422 if errors else 200)


@bp.post("/deconnexion")
def logout():
    security.logout_user()
    flash("Vous êtes déconnecté.", "info")
    return redirect(url_for("shop.home"))


@bp.route("/mon-compte")
@security.login_required
def profile():
    orders = db.query("SELECT * FROM orders WHERE user_id=? ORDER BY created_at DESC, id DESC", (g.user["id"],))
    return render_template("account.html", orders=orders)


@bp.route("/mot-de-passe", methods=["GET", "POST"])
@security.login_required
def change_password():
    errors = {}
    if request.method == "POST":
        current, new, confirm = (request.form.get(k, "") for k in ("current", "new", "confirm"))
        if security.throttle_blocked("pwchange", str(g.user["id"]), 6, 900):
            flash("Trop d'essais. Patientez quelques minutes.", "error")
            return render_template("change_password.html", errors=errors), 429
        if not security.verify_password(g.user["password_hash"], current):
            security.throttle_hit("pwchange", str(g.user["id"]))
            errors["current"] = "Le mot de passe actuel est incorrect."
        pw = security.password_errors(new)
        if pw:
            errors["new"] = " ".join(pw)
        elif security.verify_password(g.user["password_hash"], new):
            errors["new"] = "Choisissez un mot de passe différent de l'actuel."
        elif new != confirm:
            errors["confirm"] = "Les deux mots de passe ne correspondent pas."
        if not errors:
            new_sv = (g.user["session_version"] if "session_version" in g.user.keys() else 1) + 1
            db.execute("UPDATE users SET password_hash=?, must_change_password=0, session_version=? WHERE id=?",
                       (security.hash_password(new), new_sv, g.user["id"]))
            session["sv"] = new_sv
            security.rotate_csrf()
            flash("Mot de passe mis à jour.", "success")
            return redirect(_default_after_login(g.user))
    return render_template("change_password.html", errors=errors), (422 if errors else 200)

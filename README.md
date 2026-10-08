# 0,00 28 — librairie en ligne (Flask)

Boutique de livres avec **paiement à la livraison**, livraison dans les **58 wilayas**, suivi de commande et panneau d'administration complet. Refonte intégrale du projet vêtements d'origine : nouvelle identité (noir / orange, logo télé), nouveau frontend, backend durci.

## Démarrage rapide

```bash
python -m venv .venv
source .venv/bin/activate          # Windows : .venv\Scripts\activate
pip install -r requirements.txt

flask --app app create-admin       # crée votre compte administrateur (mot de passe fort demandé)
flask --app app seed-demo          # OPTIONNEL : 12 livres de démonstration (prix et stocks fictifs)
python app.py                      # http://127.0.0.1:5000
```

- Administration : `/admin` (connexion via `/connexion`).
- `seed-demo` crée aussi un admin `admin@0028.local` avec un **mot de passe provisoire affiché une seule fois** et à changer à la première connexion. Supprimez ces données avant la mise en ligne.
- Tests : `python -m unittest discover -s tests -v` (23 tests : commande, stock, CSRF, XSS, auth, admin).

## Ce qui a changé par rapport au projet vêtements

| Gardé (adapté) | Supprimé | Ajouté |
|---|---|---|
| Panier et favoris (tiroirs), aperçu rapide, commande à la livraison, tarifs par wilaya (domicile / bureau), suivi par code + téléphone, avis, recherche, stock + historique, seuil d'alerte, prix d'achat / marge, tableau de bord, notifications, upload d'images, comptes, changement de mot de passe | Couleurs, tailles, guide des tailles, genre Homme/Femme, tissu, « essayage à domicile », Cercle Privilège, Web Push inactif, pages mortes | Auteur, éditeur, ISBN, langue, pages, format, année ; étiquettes Nouveauté / Best-seller / promo ; galerie (1ʳᵉ et 4ᵉ de couverture, extraits) ; filtres genre, langue, prix, stock ; tri ; pagination ; modération des avis ; réglages du site ; newsletter |

## Sécurité (corrections par rapport à l'ancien projet)

- Plus de compte admin ni de `SECRET_KEY` écrits dans le code : la clé est lue dans `SECRET_KEY` ou générée dans `instance/`.
- **CSRF** sur toutes les requêtes d'écriture, y compris l'API de commande (jeton lié à la session, contrôle `Origin`).
- **XSS** : échappement Jinja partout, DOM construit sans `innerHTML`, **CSP stricte** (`script-src 'self'`, aucun script ni style inline).
- Prix et stock **toujours relus côté serveur** ; décrémentation atomique du stock (pas de survente) ; quantité plafonnée.
- Limitation des tentatives **persistante** (connexion, suivi, commandes, avis, inscription).
- Images ré-encodées avec Pillow (EXIF et charges cachées supprimés), noms aléatoires.
- Redirections `next` validées, déconnexion en POST, session renouvelée à la connexion, cookies `HttpOnly` + `SameSite=Lax` (+ `Secure` avec `COOKIE_SECURE=1`).

## Personnaliser

- **Tarifs de livraison** : `data_dz.py`.
- **Textes, contacts, bandeau, délais** : Admin → Réglages.
- **Images du site** : `static/img/` (hero, à propos, décors, logo). Les polices sont dans `static/fonts/`.
- **Couleurs et espacements** : `static/css/tokens.css`.

## Mise en ligne

```bash
pip install -r requirements.txt
SECRET_KEY=... COOKIE_SECURE=1 TRUST_PROXY=1 gunicorn app:app --workers 2 --threads 4
```

Servez le site en **HTTPS** (Nginx, Caddy, ou l'hébergeur). Placez `DATABASE_PATH` et `static/uploads/` sur un disque persistant, et sauvegardez la base SQLite régulièrement (`instance/boutique.db`). Voir `.env.example`.

## Structure

```
app.py            application, filtres, erreurs, commandes CLI
config.py         configuration (aucun secret en dur)
db.py             SQLite : schéma, transactions
security.py       CSRF, auth, limitation, CSP, validation
services.py       catalogue, commandes, stock, statistiques
views_shop.py     boutique + API JSON
views_account.py  inscription, connexion, compte, mot de passe
views_admin.py    administration
data_dz.py        wilayas et tarifs
seed_demo.py      livres de démonstration
templates/ static/ tests/
```

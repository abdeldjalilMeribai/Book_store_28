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

## Base de données : PostgreSQL

Le site utilise **PostgreSQL** (plus SQLite).

```bash
# 1. Créer la base (une seule fois) dans psql :
#    CREATE USER livres WITH PASSWORD 'MOT_DE_PASSE';
#    CREATE DATABASE livres OWNER livres;
#    CREATE DATABASE livres_test OWNER livres;   -- pour les tests
# 2. Définir DATABASE_URL (voir .env.example), puis lancer le site : les tables se créent toutes seules.
python migrate_sqlite_to_postgres.py instance/boutique.db "postgresql://livres:MOT_DE_PASSE@localhost:5432/livres"   # reprendre l'ancienne base
```

Tests : `TEST_DATABASE_URL=postgresql://livres:MOT_DE_PASSE@localhost:5432/livres_test python -m unittest discover -s tests -v`
(le nom de la base de test doit finir par `_test` : les tests la vident).

## Mise en ligne

Voir le guide **DEPLOIEMENT** (VPS Contabo, Nginx, HTTPS, sauvegardes). Fichiers prêts à l'emploi dans `deploy/` : `livres.service`, `nginx-livres.conf`, `backup.sh`.

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

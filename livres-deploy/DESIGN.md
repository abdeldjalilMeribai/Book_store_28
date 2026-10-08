# DESIGN — 0,00 28

**Idée** : une librairie qui rend le paiement à la livraison visible. « 0,00 DA à payer maintenant » s'affiche sur un écran de télé rétro, le logo de la marque.

## Matière
- **Encre** `#0a0806` → `#261d17` (fonds, surfaces), lignes `#34281f`.
- **Orange du logo** `#ef5807` (action, accents) ; `#ff7a2b` pour le texte orange sur fond sombre. Texte sur orange : toujours l'encre `#0a0806`.
- **Papier** `#f4ede4` (texte, contours « façon logo »).
- États : ambre (préparation), turquoise (expédiée), vert (livrée), rouge doux (annulée).

## Typographie
- **Bricolage Grotesque** (titres) · **Work Sans** (texte) · **Pixelify Sans** (prix, codes, compteurs : l'écran de la télé).
- Polices sous-titrées en WOFF, servies depuis `static/fonts/` (licences OFL incluses).

## Signature
- `.screen` : contour papier épais, coins arrondis, antennes, deux boutons. Utilisé pour « À payer maintenant », le code de suivi et les erreurs.
- Couvertures en relief (reliure en dégradé, ombre portée), la 4ᵉ de couverture apparaît au survol.
- Bande orange pleine « Vous ne payez qu'en ouvrant le colis ».

## Règles
- Aucun style ni script inline (CSP stricte) ; couleurs et espacements viennent de `tokens.css`.
- Mouvement : transform/opacity uniquement, `prefers-reduced-motion` respecté.
- Mobile d'abord : tiroirs plein écran, barre d'achat fixe sur la fiche livre, filtres repliés.

## Fichiers
`tokens.css` → `base.css` → `components.css` → `pages.css` → `admin.css`.

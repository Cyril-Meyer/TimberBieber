# Analyse du taux de chute par semaine (coloris 215371)

Ce script calcule, pour chaque semaine de commandes, le **taux de chute (TDC)** obtenu en découpant les pièces demandées dans des panneaux bruts avec la bibliothèque [Rectpack](https://github.com/secnot/rectpack). Il produit un tableau récapitulatif et un graphique.

C'est la **référence de base** : un seul algorithme de découpe est utilisé pour toute la semaine, sans optimisation évolutionnaire. Elle sert de point de comparaison pour l'algorithme génétique (dossier `algoGenetique/`).

## Ce que fait le script

1. Lit les articles et les ordres de fabrication (OF).
2. Garde uniquement les articles du coloris `215371`.
3. Regroupe les commandes **par semaine** (du lundi au dimanche) et par article.
4. Arrondit chaque quantité au **multiple supérieur de `QtéParOF`** (1 si la valeur est vide ou nulle). On ne peut pas lancer un demi-OF.
5. Découpe toutes les pièces de la semaine en une fois avec Rectpack.
6. Calcule le TDC, affiche un tableau et trace les graphiques.

## Fichiers d'entrée

À placer dans le dossier d'exécution :

| Fichier | Colonnes utilisées |
|---|---|
| `articles.xlsx` | `Article`, `Coloris`, `X`, `Y`, `QtéParOF` |
| `of.xlsx` | `Article`, `Date cde` (format jour/mois/année), `Qté cdée` |

`X` et `Y` sont les dimensions d'une pièce, dans la même unité que le panneau.

## Installation

```bash
pip install pandas openpyxl numpy matplotlib rectpack
```

## Utilisation

```bash
python analyse_plot.py
```

Pour tester un autre algorithme, modifiez l'argument par défaut de `analyse_semaines`, par exemple :

```python
res = analyse_semaines(algo=maxrects.MaxRectsBaf)
```

## Paramètres

| Paramètre | Valeur | Rôle |
|---|---|---|
| `COLORIS` | `215371` | Coloris étudié (celui qui a le plus fort taux de chute) |
| `PANNEAU` | `(21000, 26550)` | Dimensions du panneau brut (2100 × 2655 mm si l'unité est le dixième de mm) |
| `algo` | `GuillotineBafSas` | Algorithme de placement (Guillotine, MaxRects ou Skyline) |

Réglages Rectpack fixes : mode `Offline` (toutes les pièces connues à l'avance), `bin_algo=BBF` (chaque pièce va dans le panneau où elle s'ajuste le mieux), rotation autorisée, panneaux en nombre illimité. Le tri par défaut de Rectpack s'applique (surface décroissante).

## Fonctions

- **`decoupe(pieces, algo)`** : place les pièces dans les panneaux. Renvoie `(taux de chute, nombre de panneaux)`. Affiche un avertissement si certaines pièces n'ont pas pu être placées.
- **`analyse_semaines(algo)`** : prépare les données et appelle `decoupe` pour chaque semaine. Renvoie un tableau (DataFrame).
- **`tracer(res)`** : trace deux graphiques empilés.

## Sorties

**Tableau** (une ligne par semaine) :

| Colonne | Signification |
|---|---|
| `Semaine` | Numéro de semaine (1, 2, 3, ...) dans l'ordre chronologique |
| `Lundi` | Date du lundi de la semaine |
| `Commandé` | Quantité commandée |
| `Coupé` | Quantité réellement coupée (après arrondi aux multiples de `QtéParOF`) |
| `Panneaux` | Nombre de panneaux utilisés |
| `TDC (%)` | Taux de chute |

Le script affiche aussi le **TDC moyen** sur toutes les semaines.

**Graphique** :
- en haut : la demande par semaine (barres) ;
- en bas : le TDC par semaine (courbe).

## Calcul du taux de chute

```
TDC = 1 - (surface des pièces placées) / (nombre de panneaux × surface d'un panneau)
```

## Limites

- Un seul coloris est traité.
- Le **trait de scie** et la **coupe de propreté** ne sont pas pris en compte (le TDC est donc optimiste).
- Le **sens du fil** est ignoré : la rotation est toujours autorisée.
- Les dernières pièces d'une semaine peuvent ouvrir un panneau presque vide, ce qui fait monter le TDC des petites semaines.
- Les commandes sont regroupées par **date de commande**, sans tenir compte de la date de livraison.
- Les algorithmes MaxRects et Skyline ne garantissent pas des plans réalisables en coupes guillotine. Seul Guillotine donne un plan réalisable à la scie.
- Rectpack est une heuristique : l'optimum n'est pas garanti.

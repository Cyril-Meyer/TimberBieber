# Ordonnancement des OF – réduction du Taux de Chute

École d'automne de l'IA 2026 (Alsace Tech, 26–29 octobre) · Projet Schmidt-Groupe

Outil Python qui génère, **semaine par semaine**, les OF d'une matière : quantité à couper par article, ordre de coupe des panneaux et comparaison avec le taux de chute (TdC) réel de Schmidt. L'objectif est de **réduire le TdC sans rupture au montage**.

Périmètre : matière **215371 CHENE HONEY** (55 articles, environ la moitié des m² coupés en épaisseur 16), pas de temps d'**une semaine**.

**Livrable : un seul fichier Excel, `results/resultats_215371.xlsx`, à 3 feuilles.**

---

## 1. Contenu du dossier

```
IAporject/
├── run.py              ← le seul fichier à lancer
├── requirements.txt
├── README.md
├── ordo_of/            code (ne pas lancer ces fichiers un par un)
│   ├── data.py         lecture des fichiers Excel, demande hebdomadaire
│   ├── nesting.py      imbrication des pièces sur les panneaux, gestion des restes
│   ├── planning.py     quantité à couper par article et par semaine
│   ├── sequencing.py   ordre de coupe, liste des OF, stock tampon
│   ├── comparaison.py  graphiques au format Schmidt « TdC par Coloris »
│   └── main.py         paramètres et écriture du fichier Excel
├── data/               ← y déposer les 3 fichiers Excel de Schmidt (non versionnés)
└── results/            créé à l'exécution
```

## 2. Lancement

1. Installer les bibliothèques (une seule fois) : `pip install -r requirements.txt`
2. Copier les trois fichiers Excel de Schmidt dans `data/`. Ils sont retrouvés par mot-clé : `articles`, `OFs`, `Mouvements`.
3. Lancer `run.py` : F5 dans IDLE, ou `python run.py` depuis le dossier `IAporject`.

Durée : environ 30 secondes (plus une minute la première fois, pour lire le fichier des mouvements).

Erreurs fréquentes :

1. `attempted relative import` : un fichier de `ordo_of/` a été lancé directement ; il faut lancer `run.py`.
2. `FileNotFoundError` : les fichiers Excel ne sont pas dans `data/` (ou indiquer leur dossier dans la variable d'environnement `ORDO_DATA`).

## 3. Paramètres

En haut de `ordo_of/main.py` :

| Paramètre | Valeur | Signification |
|---|---|---|
| `MATIERE` | 215371 | Matière étudiée |
| `SS_WEEKS` | 0.5 | Stock de sécurité au montage (semaines de demande) |
| `SMAX_WEEKS` | 3.0 | Stock maximum au montage (semaines de demande) |
| `LOT_RULE` | `"min"` | OF ≥ QteParOF (`"multiple"` : OF = k × QteParOF) |
| `MAX_DELAI_SEMAINES` | 3 | Délai maximum entre le lancement d'un OF et l'utilisation de ses pièces |
| `RESTES_AGE_MAX` | 4 | Durée de conservation d'un reste avant mise au rebut (semaines) |
| `SEUIL_VOLUME` | 0.5 | Comparaison : semaine écartée si son historique d'OF est sous 50 % du volume médian |

## 4. Méthode

### 4.1 Données utilisées

| Fichier Schmidt | Contenu utilisé | Usage |
|---|---|---|
| Mouvements de stock montage | Consommation + rebut, par semaine (janv.–juil. 2026) | Demande hebdomadaire par article |
| Données articles et matières | Dimensions, sens du fil, QteParOF ; panneau, reste minimum | Géométrie, taille des OF |
| OFs et TdC | OF historiques (avr.–oct. 2026), graphiques de TdC | Situation actuelle, comparaison avec Schmidt |

### 4.2 Quantité à couper chaque semaine (`planning.py`)

On rejoue l'historique semaine par semaine. Ce qui est coupé en semaine t est livré au montage en t+1.

1. **Quantité obligatoire** : demande de la semaine suivante + stock de sécurité − stock restant, arrondie au multiple supérieur de QteParOF.
2. **Imbrication de toute la semaine** en une fois, et non jour par jour ou OF par OF.
3. **Remplissage** (glouton) : les vides des panneaux déjà ouverts reçoivent des pièces nécessaires dans les 3 semaines suivantes, sans ouvrir de panneau ni dépasser le stock maximum.
4. **Restes** : toute zone libre ≥ 800 × 800 mm est stockée et utilisée en priorité les semaines suivantes ; après 4 semaines sans usage, elle est mise au rebut et comptée comme chute.

### 4.3 Ordre de coupe (`sequencing.py`)

1. Les quantités de la semaine sont découpées en OF (≥ QteParOF, le reliquat est ajouté au dernier OF).
2. Règle gloutonne : on coupe d'abord le panneau dont la plus grande part des pièces appartient à des articles déjà commencés, pour compléter les OF au plus tôt.
3. Le stock tampon est simulé pièce par pièce (entrée 2, sortie 3, un OF sort quand il est complet) ; on garde l'ordre (imbrication ou glouton) qui donne le pic le plus bas.

### 4.4 Comparaison avec Schmidt (`comparaison.py`)

1. Les mêmes OF historiques sont imbriqués deux fois : coupés **par jour** (recalcul de la situation actuelle) et **regroupés par semaine**. Les dates de livraison ne changent pas.
2. Seules les semaines présentes sur les graphiques Schmidt sont tracées ; les semaines à historique incomplet (ex. S17, début de l'extraction) ou sans OF (S35–S37) sont retirées.
3. Les valeurs Schmidt sont lues sur leurs graphiques (5 graphiques : toutes matières, 215371, 221612, 220965, 219106).

## 5. Résultat : `results/resultats_215371.xlsx`

| Feuille | Contenu |
|---|---|
| Production par semaine | Quantité à couper par article et par semaine (`2026/Sxx`), QteParOF, total ; en bas : pièces, panneaux, restes réutilisés et TdC de chaque semaine |
| Ordre de coupe | Pour chaque semaine, les panneaux dans l'ordre de coupe : article, n° d'OF (`2026-S03-221737-1`), pièces sur le panneau, cumul de l'OF, « oui » quand l'OF est complet, taille de l'OF, dates de lancement et de livraison |
| Comparaison Schmidt | Les 5 graphiques Schmidt (à gauche) et les nôtres au même format (à droite), puis le tableau des valeurs |

**Synthèse des résultats**

1. Matière 215371, S02–S30 : **TdC de 13,7 %**, 7 048 panneaux, 1 016 OF, aucune rupture, délai OF → livraison de 7 jours, pic du stock tampon de 1 103 pièces (limite 2 553).
2. Le gain vient surtout du **regroupement hebdomadaire** : sur les mêmes OF, 19,1 % coupés par jour contre 14,3 % par semaine. Remplissage et restes n'ajoutent presque rien avec la limite de 3 semaines.
3. Comparaison avec Schmidt (moyenne des semaines retenues) :

| Graphique | Schmidt réel | Notre recalcul, par jour | Regroupé par semaine |
|---|---|---|---|
| 215371 | 20,2 % | 19,3 % | **14,2 %** |
| Toutes matières (épaisseur 16) | 16,1 % | 18,8 % | 15,1 % |
| 221612 | 12,1 % | 12,5 % | 12,2 % |
| 220965 | 14,4 % | 20,2 % | 17,8 % |
| 219106 | 11,2 % | 17,0 % | 15,4 % |

4. Pour 215371, notre recalcul de la situation actuelle (19,3 %) est proche du réel (20,2 %) : l'outil est fiable pour cette matière, et le regroupement hebdomadaire fait gagner environ 6 points.
5. Ordre de grandeur économique : 1 point de TdC en moins représente environ 1 570 m² de panneaux par an pour toutes les matières, soit environ 7 900 € par an à 5 €/m² (prix supposé, à confirmer).

## 6. Limites

1. **La demande future est supposée connue.** L'outil rejoue l'historique : la quantité à couper en semaine t est calculée à partir de la consommation réelle de la semaine t+1, tirée des mouvements de stock. En exploitation, les clients passent commande de façon irrégulière et imprévisible ; l'outil ne prévoit pas ces commandes et ne sait pas réagir à une commande urgente arrivée en cours de semaine. Le « zéro rupture » obtenu ici n'est donc pas garanti en conditions réelles : il faudrait ajouter une prévision de la demande et un stock de sécurité calculé sur l'erreur de prévision.
2. **Imbrication** : l'algorithme est une heuristique de l'équipe, différente de l'optimiseur Schmidt. Sur les petites matières sans fil (220965, 219106), notre recalcul dépasse le réel de 5 à 6 points ; pour elles, seule la comparaison entre nos deux courbes est valable.
3. **Une seule matière planifiée** : les feuilles 1 et 2 ne concernent que 215371 ; le stock tampon est donc compté pour cette matière seule, alors qu'il est partagé.
4. **Algorithmes gloutons** : le remplissage et l'ordre de coupe ne garantissent pas l'optimum ; l'ordre de coupe ne donne pas la position des pièces sur le panneau.
5. **Hypothèses à confirmer avec Schmidt** : QteParOF (minimum ou multiple), capacité de la scie, capacité du stock au montage, unité des 3 192 du stock tampon, durée de conservation des restes, prix du panneau.

"""
Optimisation de découpe par partition évolutionnaire sur toutes les semaines 
avec affichage d'un graphique du Taux de Chute (TDC) par semaine.

- Lit articles.xlsx et of.xlsx
- Prend les articles du matériau COLORIS, regroupés par semaine de commande
- Applique l'algorithme génétique sur CHAQUE semaine
- Affiche un graphique récapitulatif du TDC global par semaine
- Prend en compte le trait de scie (4,4 mm) et la coupe de propreté (21 mm par bord)

Dépendances : pip install pandas openpyxl rectpack tqdm numpy ortools matplotlib
"""
import copy
import math
import random
import time

import matplotlib.patches as patches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rectpack.guillotine as guillotine
import rectpack.maxrects as maxrects
import rectpack.skyline as skyline
from rectpack import SORT_AREA, PackingBin, PackingMode, newPacker
from tqdm import tqdm

try:
    from ortools.sat.python import cp_model
except ImportError:          # ortools absent : CP-SAT est simplement désactivé
    cp_model = None

# ----------------------------------------------------------------------
# Paramètres
# ----------------------------------------------------------------------
COLORIS = 215371

UNITE = 10                       # 1 mm = 10 unités (panneau 2100 x 2655 mm)
TRAIT_SCIE = round(4.4 * UNITE)  # 44 : épaisseur du trait de scie
PROPRETE = round(21 * UNITE)     # 210 : coupe de propreté, par bord

PANNEAU_BRUT = (21000, 26550)
# Panneau utile pour le placement : on retire la coupe de propreté sur les 2 bords,
# et on ajoute un trait de scie (les pièces sont agrandies d'un trait de scie,
# donc la dernière pièce d'une rangée n'a pas de trait après elle)
PANNEAU = (PANNEAU_BRUT[0] - 2 * PROPRETE + TRAIT_SCIE,
           PANNEAU_BRUT[1] - 2 * PROPRETE + TRAIT_SCIE)
SURFACE = PANNEAU_BRUT[0] * PANNEAU_BRUT[1]   # le TdC se calcule sur le panneau brut

FICHIER_ARTICLES = "articles3.xlsx"
FICHIER_OF = "articles.xlsx"

# Familles d'algorithmes que l'évolution a le droit d'utiliser sur un sous-groupe
INCLURE_GUILLOTINE = True   # 18 variantes : plans réalisables à la scie
INCLURE_MAXRECTS = True     # 4 variantes : plans souvent NON réalisables en coupes guillotine
INCLURE_SKYLINE = True      # 6 variantes : idem, et plus lentes

ALGOS = {}
if INCLURE_GUILLOTINE:
    for crit in ["Baf", "Blsf", "Bssf"]:
        for regle in ["Sas", "Las", "Slas", "Llas", "Maxas", "Minas"]:
            nom = f"Guillotine{crit}{regle}"
            ALGOS[nom] = getattr(guillotine, nom)
if INCLURE_MAXRECTS:
    for nom in ["MaxRectsBl", "MaxRectsBssf", "MaxRectsBaf", "MaxRectsBlsf"]:
        ALGOS[nom] = getattr(maxrects, nom)
if INCLURE_SKYLINE:
    for nom in ["SkylineBl", "SkylineBlWm", "SkylineMwf", "SkylineMwfl",
                "SkylineMwfWm", "SkylineMwflWm"]:
        ALGOS[nom] = getattr(skyline, nom)

# CP-SAT (Google OR-Tools) : solveur exact, très lent dès que le groupe grossit.
INCLURE_CPSAT = True
CPSAT_TEMPS_MAX = 80        # secondes maximum par groupe : au-delà, le solveur s'arrête
CPSAT_NB_PIECES_MAX = 40    # au-delà de cette taille de groupe, CP-SAT n'est même pas essayé
CPSAT_BUDGET_TOTAL = 1000    # secondes cumulées sur tout le programme : ensuite CP-SAT est refusé
CPSAT_THREADS = 4

if INCLURE_CPSAT and cp_model is not None:
    ALGOS["CPSAT"] = None   # traité à part dans evaluer_groupe

_cache = {}
_temps_cpsat = 0.0          # temps total déjà consommé par CP-SAT


# ----------------------------------------------------------------------
# 1. Chargement : une liste de pièces (largeur, hauteur) par semaine
# ----------------------------------------------------------------------
def charger_semaines():
    articles = pd.read_excel(FICHIER_ARTICLES)
    articles = articles[articles["Coloris"] == COLORIS]
    of = pd.read_excel(FICHIER_OF)

    # Semaine (lundi) de chaque commande, puis quantité commandée par semaine et par article
    of["Semaine"] = pd.to_datetime(of["Date cde"], dayfirst=True).dt.to_period("W").dt.start_time
    df = of.groupby(["Semaine", "Article"], as_index=False)["Qté cdée"].sum()
    df = df.merge(articles[["Article", "X", "Y", "QtéParOF"]], on="Article")  # garde ce coloris

    # Arrondi au multiple supérieur de QtéParOF (1 si la valeur est vide ou nulle)
    multiple = df["QtéParOF"].fillna(1).clip(lower=1)
    df["Qte"] = (np.ceil(df["Qté cdée"] / multiple) * multiple).astype(int)

    semaines = []
    for _, g in df.groupby("Semaine"):
        g = g.loc[g.index.repeat(g["Qte"])]          # une ligne par pièce à couper
        semaines.append(list(zip(g["X"], g["Y"])))
    return semaines


# ----------------------------------------------------------------------
# 2. Évaluation d'un sous-groupe (mis en cache : seuls les groupes modifiés sont recalculés)
# ----------------------------------------------------------------------
INVALIDE = (float("inf"), 0, 1.0)


def nb_panneaux_heuristique(dims):
    """Nombre de panneaux d'une découpe rapide : sert de borne haute au modèle CP-SAT.
    dims = dimensions RÉELLES des pièces (le trait de scie est ajouté ici)."""
    packer = newPacker(mode=PackingMode.Offline, bin_algo=PackingBin.BBF,
                       pack_algo=guillotine.GuillotineBafSas, sort_algo=SORT_AREA, rotation=True)
    for w, h in dims:
        packer.add_rect(w + TRAIT_SCIE, h + TRAIT_SCIE)
    packer.add_bin(*PANNEAU, count=float("inf"))
    packer.pack()
    return len(packer) if len(packer.rect_list()) == len(dims) else None


def evaluer_cpsat(indices, pieces):
    """Minimise le nombre de panneaux avec CP-SAT, avec limites de taille et de temps.
    Renvoie INVALIDE si le groupe est trop gros, si le budget est épuisé ou si
    aucune solution n'est trouvée dans le temps imparti."""
    global _temps_cpsat
    if len(indices) > CPSAT_NB_PIECES_MAX or _temps_cpsat >= CPSAT_BUDGET_TOTAL:
        return INVALIDE

    debut = time.perf_counter()
    try:
        dims_reel = [(int(pieces[i][0]), int(pieces[i][1])) for i in indices]
        dims = [(w + TRAIT_SCIE, h + TRAIT_SCIE) for w, h in dims_reel]   # pièces agrandies
        nb_max = nb_panneaux_heuristique(dims_reel)
        if nb_max is None:
            return INVALIDE

        W, H = PANNEAU
        model = cp_model.CpModel()
        choix = []                                           # (piece, panneau, présence)
        par_panneau = [([], []) for _ in range(nb_max)]      # intervalles x et y de chaque panneau

        for i, (w, h) in enumerate(dims):
            options = []
            for pw, ph in ([(w, h), (h, w)] if w != h else [(w, h)]):    # avec rotation
                if pw > W or ph > H:
                    continue
                for k in range(nb_max):
                    p = model.NewBoolVar("")
                    x = model.NewIntVar(0, W - pw, "")
                    y = model.NewIntVar(0, H - ph, "")
                    par_panneau[k][0].append(model.NewOptionalFixedSizeIntervalVar(x, pw, p, ""))
                    par_panneau[k][1].append(model.NewOptionalFixedSizeIntervalVar(y, ph, p, ""))
                    options.append(p)
                    choix.append((i, k, p))
            if not options:
                return INVALIDE
            model.AddExactlyOne(options)

        for k in range(nb_max):
            model.AddNoOverlap2D(par_panneau[k][0], par_panneau[k][1])

        utilise = [model.NewBoolVar("") for _ in range(nb_max)]
        for _, k, p in choix:
            model.AddImplication(p, utilise[k])
        for k in range(nb_max - 1):
            model.Add(utilise[k] >= utilise[k + 1])          # casse la symétrie entre panneaux
        # Borne basse : il faut au moins assez de panneaux pour la surface totale des pièces
        surface_pieces = sum(w * h for w, h in dims_reel)
        model.Add(sum(utilise) >= math.ceil(surface_pieces / SURFACE))
        model.Minimize(sum(utilise))

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = CPSAT_TEMPS_MAX    # arrêt si trop long
        solver.parameters.num_workers = CPSAT_THREADS
        statut = solver.Solve(model)
        if statut not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return INVALIDE                                  # rien trouvé dans le temps imparti

        surfaces = [0] * nb_max
        for i, k, p in choix:
            if solver.Value(p):
                surfaces[k] += dims_reel[i][0] * dims_reel[i][1]   # surface réelle
        surfaces = sorted(sf for sf in surfaces if sf > 0)
        return (len(surfaces), sum(surfaces), surfaces[0] / SURFACE)
    finally:
        _temps_cpsat += time.perf_counter() - debut


def evaluer_groupe(indices, nom_algo, pieces):
    cle = (tuple(sorted(indices)), nom_algo)
    if cle in _cache:
        return _cache[cle]

    if nom_algo == "CPSAT":
        _cache[cle] = evaluer_cpsat(indices, pieces)
        return _cache[cle]

    packer = newPacker(mode=PackingMode.Offline, bin_algo=PackingBin.BBF,
                       pack_algo=ALGOS[nom_algo], sort_algo=SORT_AREA, rotation=True)
    for i in indices:
        packer.add_rect(int(pieces[i][0]) + TRAIT_SCIE, int(pieces[i][1]) + TRAIT_SCIE)
    packer.add_bin(*PANNEAU, count=float("inf"))
    packer.pack()

    if len(packer.rect_list()) < len(indices):
        res = (float("inf"), 0, 1.0)                      # pièces non placées : invalide
    else:
        # Surface réelle des pièces (sans le trait de scie ajouté pour le placement)
        surfaces = sorted(sum((r.width - TRAIT_SCIE) * (r.height - TRAIT_SCIE) for r in b)
                          for b in packer)
        res = (len(surfaces), sum(surfaces), surfaces[0] / SURFACE)
    _cache[cle] = res
    return res                                            # (panneaux, surface utilisée, remplissage du moins rempli)


def cout(individu, pieces):
    """Panneaux totaux + (remplissage moyen du dernier panneau de chaque groupe, entre 0 et 1)."""
    res = [evaluer_groupe(g, a, pieces) for g, a in zip(individu["groupes"], individu["algos"])]
    panneaux = sum(r[0] for r in res)
    return panneaux + sum(r[2] for r in res) / len(res)


# ----------------------------------------------------------------------
# 3. Création d'un individu
# ----------------------------------------------------------------------
def individu_aleatoire(n, nb_max_groupes=6):
    k = random.randint(1, nb_max_groupes)
    groupes = [[] for _ in range(k)]
    for i in range(n):
        random.choice(groupes).append(i)
    groupes = [g for g in groupes if g]
    return {"groupes": groupes, "algos": [random.choice(list(ALGOS)) for _ in groupes]}


def individu_un_groupe(n, nom_algo):
    return {"groupes": [list(range(n))], "algos": [nom_algo]}


# ----------------------------------------------------------------------
# 4. Mutations
# ----------------------------------------------------------------------
def deplacer(ind):
    """Change la TAILLE des groupes : déplace quelques pièces vers un autre groupe."""
    if len(ind["groupes"]) < 2:
        return
    src, dst = random.sample(range(len(ind["groupes"])), 2)
    g = ind["groupes"][src]
    k = random.randint(1, max(1, len(g) // 4))
    for i in random.sample(g, min(k, len(g))):
        g.remove(i)
        ind["groupes"][dst].append(i)


def scinder(ind):
    """Change le NOMBRE de groupes : coupe un groupe en deux (nouvel algo tiré au hasard)."""
    candidats = [i for i, g in enumerate(ind["groupes"]) if len(g) >= 2]
    if not candidats:
        return
    g = ind["groupes"][random.choice(candidats)]
    part = random.sample(g, random.randint(1, len(g) - 1))
    for i in part:
        g.remove(i)
    ind["groupes"].append(part)
    ind["algos"].append(random.choice(list(ALGOS)))


def fusionner(ind):
    """Change le NOMBRE de groupes : fusionne deux groupes."""
    if len(ind["groupes"]) < 2:
        return
    a, b = sorted(random.sample(range(len(ind["groupes"])), 2))
    ind["groupes"][a].extend(ind["groupes"][b])
    del ind["groupes"][b], ind["algos"][b]


def changer_algo(ind):
    """Change l'ALGORITHME d'un groupe."""
    k = random.randrange(len(ind["algos"]))
    ind["algos"][k] = random.choice(list(ALGOS))


MUTATIONS = [deplacer, scinder, fusionner, changer_algo]


def muter(individu, max_mutations=3):
    enfant = copy.deepcopy(individu)
    for _ in range(random.randint(1, max_mutations)):
        random.choice(MUTATIONS)(enfant)
    # Supprime les groupes devenus vides
    gardes = [i for i, g in enumerate(enfant["groupes"]) if g]
    enfant["groupes"] = [enfant["groupes"][i] for i in gardes]
    enfant["algos"] = [enfant["algos"][i] for i in gardes]
    return enfant


# ----------------------------------------------------------------------
# 5. Boucle évolutionnaire (tournoi + élitisme, sans croisement), avec barre de progression
# ----------------------------------------------------------------------
def tournoi(population, couts, k=3):
    return population[min(random.sample(range(len(population)), k), key=lambda i: couts[i])]


def evolution(pieces, taille_pop=30, generations=40, elites=2, seed=None):
    if seed is not None:
        random.seed(seed)
    n = len(pieces)

    # Population initiale : tous les "un seul groupe" (références) + des partitions aléatoires
    population = [individu_un_groupe(n, nom) for nom in ALGOS]
    population += [individu_aleatoire(n) for _ in range(max(0, taille_pop - len(population)))]

    historique = []
    barre = tqdm(range(generations), desc="Évolution", unit="gén")
    for _ in barre:
        couts = [cout(ind, pieces) for ind in population]
        classement = sorted(range(len(population)), key=lambda i: couts[i])
        meilleur = population[classement[0]]
        historique.append(couts[classement[0]])
        barre.set_postfix(coût=f"{couts[classement[0]]:.3f}", groupes=len(meilleur["groupes"]))

        nouvelle = [population[i] for i in classement[:elites]]
        while len(nouvelle) < taille_pop:
            nouvelle.append(muter(tournoi(population, couts)))
        population = nouvelle

    couts = [cout(ind, pieces) for ind in population]
    i = min(range(len(population)), key=lambda i: couts[i])
    return population[i], historique


# ----------------------------------------------------------------------
# 6. Résumé de la meilleure partition
# ----------------------------------------------------------------------
def resume(individu, pieces):
    total_panneaux = total_utilise = 0
    for k, (g, a) in enumerate(zip(individu["groupes"], individu["algos"]), start=1):
        nb, utilise, _ = evaluer_groupe(g, a, pieces)
        total_panneaux += nb
        total_utilise += utilise
    tdc = 1 - total_utilise / (total_panneaux * SURFACE)
    print(f"TOTAL : {total_panneaux} panneaux, TDC global {tdc * 100:.1f}%")
    return tdc


# ----------------------------------------------------------------------
# 7. Exécution sur toutes les semaines et tracé du TDC
# ----------------------------------------------------------------------
def main(taille_pop=30, generations=40, seed=1):
    semaines = charger_semaines()
    print(f"Nombre total de semaines à traiter : {len(semaines)}\n")

    noms_semaines = []
    tdc_semaines = []

    for idx, pieces in enumerate(semaines):
        if not pieces:
            continue
        print(f"\n--- Traitement de la Semaine {idx + 1} ({len(pieces)} pièces) ---")
        
        # Lancement de l'algorithme génétique sur la semaine courante
        meilleur, historique = evolution(pieces, taille_pop=taille_pop,
                                         generations=generations, seed=seed)
        
        # Calcul du TDC final de la meilleure partition
        tdc = resume(meilleur, pieces)
        
        noms_semaines.append(f"Sem. {idx + 1}")
        tdc_semaines.append(tdc * 100)  # Stockage en pourcentage

    # Tracé du graphique global du TDC par semaine
    print("\nGénération du graphique d'évolution du TDC par semaine...")
    plt.figure(figsize=(12, 6))
    plt.plot(noms_semaines, tdc_semaines, marker='o', linestyle='-', color='b', linewidth=2, markersize=6)
    plt.title(f"Évolution du Taux de Chute (TDC) par Semaine (Coloris {COLORIS})", fontsize=12, weight='bold')
    plt.xlabel("Semaines", fontsize=10)
    plt.ylabel("TDC Global (%)", fontsize=10)
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
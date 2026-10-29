# Decoupe de panneaux : on cherche la meilleure facon de repartir les pieces
# de chaque semaine en groupes, avec un algo de decoupe different pour chaque groupe.
# Pour chaque semaine on affiche le taux de chute (TDC), puis on trace la courbe.

import math
import random

import matplotlib.pyplot as plt
import pandas as pd
import rectpack.guillotine as guillotine
import rectpack.maxrects as maxrects
import rectpack.skyline as skyline
from rectpack import newPacker, PackingMode, PackingBin, SORT_AREA

COLORIS = 215371
LARGEUR = 21000
HAUTEUR = 26550
SURFACE = LARGEUR * HAUTEUR

TAILLE_POP = 30      # nombre d'individus dans la population
GENERATIONS = 40     # nombre de generations

# tous les algos qu'on peut utiliser
ALGOS = {}
for critere in ["Baf", "Blsf", "Bssf"]:
    for regle in ["Sas", "Las", "Slas", "Llas", "Maxas", "Minas"]:
        nom = "Guillotine" + critere + regle
        ALGOS[nom] = getattr(guillotine, nom)
for nom in ["MaxRectsBl", "MaxRectsBssf", "MaxRectsBaf", "MaxRectsBlsf"]:
    ALGOS[nom] = getattr(maxrects, nom)
for nom in ["SkylineBl", "SkylineBlWm", "SkylineMwf", "SkylineMwfl", "SkylineMwfWm", "SkylineMwflWm"]:
    ALGOS[nom] = getattr(skyline, nom)
NOMS_ALGOS = list(ALGOS.keys())

# pour ne pas refaire le meme calcul plusieurs fois
memoire = {}


def lire_semaines():
    articles = pd.read_excel("articles.xlsx")
    articles = articles[articles["Coloris"] == COLORIS]
    commandes = pd.read_excel("of.xlsx")

    # on regroupe les commandes par semaine et par article
    commandes["Semaine"] = pd.to_datetime(commandes["Date cde"], dayfirst=True).dt.to_period("W")
    tableau = commandes.groupby(["Semaine", "Article"], as_index=False)["Qté cdée"].sum()
    tableau = tableau.merge(articles[["Article", "X", "Y", "QtéParOF"]], on="Article")

    semaines = []
    for semaine, lignes in tableau.groupby("Semaine"):
        pieces = []
        for i, ligne in lignes.iterrows():
            # on coupe un multiple de QtéParOF (au moins 1)
            multiple = ligne["QtéParOF"]
            if pd.isna(multiple) or multiple < 1:
                multiple = 1
            quantite = math.ceil(ligne["Qté cdée"] / multiple) * multiple
            for k in range(int(quantite)):
                pieces.append((int(ligne["X"]), int(ligne["Y"])))
        semaines.append(pieces)
    return semaines


def decouper(indices, nom_algo, pieces):
    # renvoie (nombre de panneaux, surface des pieces, remplissage du panneau le moins rempli)
    cle = (tuple(sorted(indices)), nom_algo)
    if cle in memoire:
        return memoire[cle]

    packer = newPacker(mode=PackingMode.Offline, bin_algo=PackingBin.BBF,
                       pack_algo=ALGOS[nom_algo], sort_algo=SORT_AREA, rotation=True)
    for i in indices:
        packer.add_rect(pieces[i][0], pieces[i][1])
    packer.add_bin(LARGEUR, HAUTEUR, count=float("inf"))
    packer.pack()

    if len(packer.rect_list()) < len(indices):
        resultat = (float("inf"), 0, 1)   # des pieces n'ont pas ete placees
    else:
        surfaces = []
        for panneau in packer:
            surfaces.append(panneau.used_area())
        resultat = (len(surfaces), sum(surfaces), min(surfaces) / SURFACE)

    memoire[cle] = resultat
    return resultat


def cout(individu, pieces):
    # plus le cout est petit, mieux c'est
    nb_panneaux = 0
    somme_remplissage = 0
    for k in range(len(individu["groupes"])):
        nb, surface, remplissage = decouper(individu["groupes"][k], individu["algos"][k], pieces)
        nb_panneaux += nb
        somme_remplissage += remplissage
    return nb_panneaux + somme_remplissage / len(individu["groupes"])


def calculer_tdc(individu, pieces):
    nb_panneaux = 0
    surface_pieces = 0
    for k in range(len(individu["groupes"])):
        nb, surface, remplissage = decouper(individu["groupes"][k], individu["algos"][k], pieces)
        nb_panneaux += nb
        surface_pieces += surface
    tdc = 1 - surface_pieces / (nb_panneaux * SURFACE)
    return tdc, nb_panneaux


# ---------- les individus ----------

def individu_un_groupe(n, nom_algo):
    return {"groupes": [list(range(n))], "algos": [nom_algo]}


def individu_aleatoire(n):
    nb_groupes = random.randint(1, 6)
    groupes = []
    for k in range(nb_groupes):
        groupes.append([])
    for i in range(n):
        random.choice(groupes).append(i)
    algos = []
    for k in range(nb_groupes):
        algos.append(random.choice(NOMS_ALGOS))
    return enlever_groupes_vides({"groupes": groupes, "algos": algos})


def copier(individu):
    groupes = []
    for g in individu["groupes"]:
        groupes.append(list(g))
    return {"groupes": groupes, "algos": list(individu["algos"])}


def enlever_groupes_vides(individu):
    groupes = []
    algos = []
    for k in range(len(individu["groupes"])):
        if len(individu["groupes"][k]) > 0:
            groupes.append(individu["groupes"][k])
            algos.append(individu["algos"][k])
    return {"groupes": groupes, "algos": algos}


# ---------- les mutations ----------

def deplacer(ind):
    # change la taille des groupes : on deplace des pieces d'un groupe a un autre
    if len(ind["groupes"]) < 2:
        return
    source, dest = random.sample(range(len(ind["groupes"])), 2)
    groupe = ind["groupes"][source]
    nb = random.randint(1, max(1, len(groupe) // 4))
    nb = min(nb, len(groupe))
    for i in random.sample(groupe, nb):
        groupe.remove(i)
        ind["groupes"][dest].append(i)


def scinder(ind):
    # change le nombre de groupes : on coupe un groupe en deux
    possibles = []
    for k in range(len(ind["groupes"])):
        if len(ind["groupes"][k]) >= 2:
            possibles.append(k)
    if len(possibles) == 0:
        return
    groupe = ind["groupes"][random.choice(possibles)]
    nb = random.randint(1, len(groupe) - 1)
    nouveau = random.sample(groupe, nb)
    for i in nouveau:
        groupe.remove(i)
    ind["groupes"].append(nouveau)
    ind["algos"].append(random.choice(NOMS_ALGOS))


def fusionner(ind):
    # change le nombre de groupes : on colle deux groupes ensemble
    if len(ind["groupes"]) < 2:
        return
    a, b = random.sample(range(len(ind["groupes"])), 2)
    ind["groupes"][a] = ind["groupes"][a] + ind["groupes"][b]
    ind["groupes"].pop(b)
    ind["algos"].pop(b)


def changer_algo(ind):
    # change l'algo d'un groupe
    k = random.randrange(len(ind["algos"]))
    ind["algos"][k] = random.choice(NOMS_ALGOS)


def muter(individu):
    enfant = copier(individu)
    for fois in range(random.randint(1, 3)):
        mutation = random.choice([deplacer, scinder, fusionner, changer_algo])
        mutation(enfant)
    return enlever_groupes_vides(enfant)


def choisir_parent(population, couts):
    # on tire 3 individus au hasard et on garde le meilleur
    candidats = random.sample(range(len(population)), 3)
    meilleur = candidats[0]
    for c in candidats:
        if couts[c] < couts[meilleur]:
            meilleur = c
    return population[meilleur]


def evolution(pieces):
    random.seed(1)
    n = len(pieces)

    # au depart : un seul groupe avec chaque algo, puis des individus au hasard
    population = []
    for nom in NOMS_ALGOS:
        population.append(individu_un_groupe(n, nom))
    while len(population) < TAILLE_POP:
        population.append(individu_aleatoire(n))

    for gen in range(GENERATIONS):
        couts = []
        for ind in population:
            couts.append(cout(ind, pieces))

        classement = sorted(zip(couts, range(len(population))))
        print("Génération", gen + 1, "/", GENERATIONS, "- meilleur coût :", round(classement[0][0], 3))

        # on garde les 2 meilleurs, le reste vient de mutations
        nouvelle = [population[classement[0][1]], population[classement[1][1]]]
        while len(nouvelle) < TAILLE_POP:
            parent = choisir_parent(population, couts)
            nouvelle.append(muter(parent))
        population = nouvelle

    # le meilleur de la derniere generation
    meilleur = population[0]
    meilleur_cout = cout(meilleur, pieces)
    for ind in population:
        c = cout(ind, pieces)
        if c < meilleur_cout:
            meilleur = ind
            meilleur_cout = c
    return meilleur


def main():
    semaines = lire_semaines()
    print("Nombre de semaines :", len(semaines))

    noms = []
    tdcs = []
    for numero in range(len(semaines)):
        pieces = semaines[numero]
        if len(pieces) == 0:
            continue
        print("\n--- Semaine", numero + 1, ":", len(pieces), "pièces ---")

        memoire.clear()   # les numeros de pieces changent d'une semaine a l'autre
        meilleur = evolution(pieces)
        tdc, nb_panneaux = calculer_tdc(meilleur, pieces)
        print("Résultat :", nb_panneaux, "panneaux, TDC =", round(tdc * 100, 1), "%")

        noms.append("Sem. " + str(numero + 1))
        tdcs.append(tdc * 100)

    print("\nTDC moyen :", round(sum(tdcs) / len(tdcs), 1), "%")

    plt.figure(figsize=(12, 6))
    plt.plot(noms, tdcs, marker="o", color="b")
    plt.title("Taux de chute par semaine (coloris " + str(COLORIS) + ")")
    plt.xlabel("Semaines")
    plt.ylabel("TDC (%)")
    plt.grid(True)
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.show()


main()
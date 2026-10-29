import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rectpack.guillotine as guillotine
import rectpack.maxrects as maxrects
from rectpack import PackingBin, PackingMode, newPacker

COLORIS = 215371
PANNEAU = (21000, 26550)


def decoupe(pieces, algo):
    """Découpe les pièces. Renvoie (taux de chute entre 0 et 1, nombre de panneaux)."""
    packer = newPacker(mode=PackingMode.Offline, bin_algo=PackingBin.BBF,
                       pack_algo=algo, rotation=True)
    for w, h in pieces:
        packer.add_rect(int(w), int(h))
    packer.add_bin(*PANNEAU, count=float("inf"))
    packer.pack()

    if len(packer.rect_list()) < len(pieces):
        print("  Attention : des pièces n'ont pas pu être placées")

    surface_utilisee = sum(b.used_area() for b in packer)
    surface_totale = len(packer) * PANNEAU[0] * PANNEAU[1]
    return 1 - surface_utilisee / surface_totale, len(packer)


def analyse_semaines(algo=guillotine.GuillotineBafSas):
    """Pour chaque semaine : demande, quantité coupée, panneaux utilisés et taux de chute."""
    articles = pd.read_excel("articles.xlsx")
    articles = articles[articles["Coloris"] == COLORIS]
    of = pd.read_excel("of.xlsx")

    # Semaine (lundi) de chaque commande, puis quantité commandée par semaine et par article
    of["Semaine"] = pd.to_datetime(of["Date cde"], dayfirst=True).dt.to_period("W").dt.start_time
    df = of.groupby(["Semaine", "Article"], as_index=False)["Qté cdée"].sum()
    df = df.merge(articles[["Article", "X", "Y", "QtéParOF"]], on="Article")  # garde uniquement ce coloris

    # Arrondi au multiple supérieur de QtéParOF (1 si la valeur est vide ou nulle)
    multiple = df["QtéParOF"].fillna(1).clip(lower=1)
    df["Qte"] = (np.ceil(df["Qté cdée"] / multiple) * multiple).astype(int)

    lignes = []
    for n, (semaine, g) in enumerate(df.groupby("Semaine"), start=1):
        commande = int(g["Qté cdée"].sum())
        g = g.loc[g.index.repeat(g["Qte"])]          # une ligne par pièce à couper
        print(f"Semaine {n} (du {semaine:%d/%m/%Y}) : {commande} commandées, {len(g)} à couper")

        taux, nb_panneaux = decoupe(list(zip(g["X"], g["Y"])), algo)
        lignes.append({
            "Semaine": n,
            "Lundi": f"{semaine:%d/%m/%Y}",
            "Commandé": commande,
            "Coupé": len(g),
            "Panneaux": nb_panneaux,
            "TDC (%)": round(taux * 100, 1),
        })
    return pd.DataFrame(lignes).set_index("Semaine")


def tracer(res):
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 9), sharex=True)

    # Haut : demande par semaine
    barres = ax1.bar(res.index, res["Commandé"], color="#93c5fd")
    ax1.bar_label(barres, fontsize=9)
    ax1.set_ylabel("Quantité commandée")
    ax1.set_title(f"Demande et taux de chute par semaine (coloris {COLORIS})")
    ax1.grid(axis="y", alpha=0.3)

    # Bas : taux de chute par semaine
    ax2.plot(res.index, res["TDC (%)"], marker="o", linewidth=2, color="#2563eb")
    for x, y in zip(res.index, res["TDC (%)"]):
        ax2.annotate(f"{y:.1f}%", (x, y), textcoords="offset points",
                     xytext=(0, 10), ha="center", fontsize=9)
    ax2.set_ylabel("Taux de chute (%)")
    ax2.set_xticks(res.index)
    ax2.set_xticklabels([f"Semaine {n}" for n in res.index], rotation=45)
    ax2.grid(alpha=0.3)

    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    res = analyse_semaines()
    print("\n", res.to_string())
    print(f"\nTaux de chute moyen : {res['TDC (%)'].mean():.1f}%")
    tracer(res)
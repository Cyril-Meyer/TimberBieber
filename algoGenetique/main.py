import pandas as pd
import rectpack.guillotine as guillotine
import rectpack.maxrects as maxrects
from rectpack import PackingBin, PackingMode, newPacker


def decoupe(pieces, algo, largeur_panneau=21000, hauteur_panneau=26550, rotation=True):

    packer = newPacker(
        mode=PackingMode.Offline,
        bin_algo=PackingBin.BBF,
        pack_algo=algo,
        rotation=rotation,
    )

    for w, h in pieces:
        packer.add_rect(int(w), int(h))

    packer.add_bin(largeur_panneau, hauteur_panneau, count=float("inf"))
    packer.pack()

    # Vérifie que toutes les pièces ont été placées
    nb_placees = len(packer.rect_list())
    if nb_placees < len(pieces):
        print(f"Attention : {len(pieces) - nb_placees} pièce(s) non placée(s) "
              f"(trop grandes pour le panneau ?)")

    surface_pieces = sum(b.used_area() for b in packer)
    surface_panneaux = sum(b.width * b.height for b in packer)
    taux_chute = 1 - surface_pieces / surface_panneaux

    print(f"Panneaux utilisés : {len(packer)}")
    return taux_chute

#===================================================
df = pd.read_excel("./articles.xlsx")
df_filtre = df[df["Coloris"].isin([215371])]

df_expanded = df_filtre.loc[
    df_filtre.index.repeat(df_filtre["QtéParSemaine"].astype(int))
]
pieces = list(zip(df_expanded["X"], df_expanded["Y"]))

algos = {
    "Guillotine BSSF-SAS": guillotine.GuillotineBssfSas,
    "Guillotine BAF-SAS": guillotine.GuillotineBafSas,
    "MaxRects BSSF": maxrects.MaxRectsBssf,
    "MaxRects BAF": maxrects.MaxRectsBaf,
}

for nom, algo in algos.items():
    print(nom)
    print(f"Taux de chute : {decoupe(pieces, algo):.1%}\n")
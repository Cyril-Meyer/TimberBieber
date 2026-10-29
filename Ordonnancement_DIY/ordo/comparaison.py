"""
Comparaison avec les graphiques Schmidt « TdC par Coloris » (feuille TdC du fichier
« OFs et TdC »).

Même format que Schmidt : une courbe par matière, étiquettes en %, axe « 2026/Sxx »,
courbe de tendance linéaire en pointillé, et uniquement les semaines affichées par Schmidt.

Notre valeur hebdomadaire = OF historiques de la semaine (date de production) regroupés
et imbriqués ensemble (scénario B0w : mêmes OF, mêmes dates de livraison, donc le délai
commande -> livraison est inchangé et reste <= 3 semaines).
"""
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mt

from .data import load_material, historical_ofs
from .nesting import BestNester, Panel, vieillir_restes

# Valeurs lues sur les graphiques Schmidt (semaine ISO -> TdC en %)
# "global" = « Evolution du Taux de Chute par épaisseur et type d'opti à la PAM3 » (Epaisseur_16)
SCHMIDT = {
    "global": {17: 16.08, 18: 14.02, 19: 17.01, 20: 16.96, 21: 15.98, 22: 14.10, 23: 17.40,
               24: 18.10, 25: 15.99, 26: 17.01, 27: 16.43, 28: 14.57, 29: 17.94, 30: 16.33,
               31: 17.24, 34: 16.53, 35: 15.00, 36: 16.08, 37: 17.25, 38: 14.43, 39: 14.91,
               40: 13.58, 41: 14.61, 42: 19.01},
    215371: {17: 17.13, 18: 17.40, 19: 20.67, 20: 20.47, 21: 20.40, 22: 16.02, 23: 22.15,
             24: 24.27, 25: 20.35, 26: 21.54, 27: 20.20, 28: 18.61, 29: 18.78, 30: 21.19,
             31: 22.72, 35: 18.86, 36: 17.62, 37: 22.38, 38: 21.78, 39: 17.57, 40: 14.86,
             41: 21.55, 42: 23.31},
    221612: {17: 10.36, 18: 14.63, 19: 13.76, 20: 9.68, 21: 16.39, 22: 12.02, 23: 10.33,
             24: 12.40, 25: 10.85, 26: 17.86, 27: 9.85, 28: 10.15, 29: 10.42, 30: 12.35,
             31: 12.07, 35: 14.55, 36: 13.24, 37: 11.35, 38: 12.42, 39: 15.20, 40: 9.67,
             41: 10.95, 42: 20.24},
    220965: {17: 16.92, 18: 10.86, 19: 15.69, 20: 15.94, 21: 11.14, 22: 15.11, 23: 14.99,
             24: 13.99, 25: 15.73, 26: 13.33, 27: 16.28, 28: 12.74, 30: 14.81, 31: 18.29,
             35: 15.26, 36: 16.81, 37: 13.58, 38: 11.11, 39: 13.64, 40: 14.45, 41: 11.60,
             42: 13.42},
    219106: {17: 12.90, 18: 10.16, 19: 10.87, 20: 11.53, 21: 9.17, 22: 11.45, 23: 10.12,
             24: 11.48, 25: 11.26, 26: 12.96, 27: 9.99, 28: 10.98, 29: 19.21, 30: 11.30,
             31: 12.03, 35: 9.80, 36: 18.02, 37: 16.56, 38: 16.07, 39: 10.40, 40: 10.27,
             41: 11.27, 42: 12.89},
}

BLEU = "#4472C4"      # bleu Excel
GRIS = "#A5A5A5"
TEXTE = "#404040"


def weekly_tdc(matiere, restes_age_max=None):
    """TdC par semaine ISO : B0 (OF coupés par jour) et B0w (OF regroupés par semaine)."""
    mat, art = load_material(matiere)
    arts = {}
    P = Panel(L=int(mat.X), W=int(mat.Y),
              reste_min_l=int(mat.ResteMin_X), reste_min_w=int(mat.ResteMin_Y))
    for a, r in art.iterrows():   # articles plus grands que le panneau : ignorés
        try:
            BestNester({a: (r.X, r.Y, r.SensFil)}, P)
            arts[a] = (r.X, r.Y, r.SensFil)
        except ValueError:
            pass
    nester = BestNester(arts, P)
    of = historical_ofs(art)
    of = of[of.Article.isin(arts)]
    of["sem"] = of.DateProd.dt.isocalendar().week.astype(int)
    out = {}
    use = restes_age_max is not None
    stock_w = [] if use else None          # stock de restes, scénario par semaine
    stock_0 = [] if use else None          # stock de restes, scénario par jour
    for s, g in of.groupby("sem"):
        # B0w : toute la semaine en un seul lot
        r = nester.nest(g.groupby("Article")["Qté cdée"].sum().to_dict(), restes=stock_w)
        ca_w = r["consumed_area"]
        if use:
            stock_w, reb = vieillir_restes(r["restes_stock"], restes_age_max)
            ca_w += reb
        # B0 : un lot par jour de production
        pa = ca = 0
        for _, gd in g.groupby("DateProd"):
            rd = nester.nest(gd.groupby("Article")["Qté cdée"].sum().to_dict(), restes=stock_0)
            pa += rd["piece_area"]; ca += rd["consumed_area"]
            if use:
                stock_0 = rd["restes_stock"]
        if use:
            stock_0, reb = vieillir_restes(stock_0, restes_age_max)
            ca += reb
        out[s] = {"B0w": 1 - r["piece_area"] / ca_w, "B0": 1 - pa / ca,
                  "pa": r["piece_area"], "ca_w": ca_w, "ca_0": ca,
                  "pieces": int(g["Qté cdée"].sum())}
    return pd.DataFrame(out).T


def _axes_style(ax, labels, vals_all):
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=10, color=TEXTE)
    lo = min(7, np.floor(np.nanmin(vals_all)) - 1)
    hi = max(27, np.ceil(np.nanmax(vals_all)) + 1)
    ax.set_ylim(lo, hi)
    ax.set_yticks(np.arange(lo, hi + 0.01, 2))
    ax.yaxis.set_major_formatter(mt.FuncFormatter(lambda v, _: f"{v:.2f}%".replace(".", ",")))
    ax.tick_params(axis="y", labelsize=10, colors=TEXTE, length=0)
    ax.tick_params(axis="x", length=0)
    ax.grid(axis="y", color="#D9D9D9", lw=1)
    ax.set_axisbelow(True)
    for s in ["top", "right", "left"]:
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color("#D9D9D9")


def _serie(ax, y, color, name, labels_on=True, lw=3, dy=9):
    x = np.arange(len(y))
    ok = ~np.isnan(y)
    # semaine sans donnée -> la courbe est interrompue (pas de 0)
    ax.plot(x, y, color=color, lw=lw, label=name, solid_joinstyle="round")
    if ok.sum() >= 2:   # courbe de tendance linéaire (comme Excel)
        a, b = np.polyfit(x[ok], y[ok], 1)
        ax.plot(x, a * x + b, ls=(0, (1, 1.5)), color=color, lw=1.6, label=f"Linéaire ({name})")
    if labels_on:
        for xi, yi in zip(x[ok], y[ok]):
            ax.annotate(f"{yi:.2f}%".replace(".", ","), (xi, yi), textcoords="offset points",
                        xytext=(0, dy), ha="center", va="bottom" if dy > 0 else "top", fontsize=9.5, color=TEXTE)


def chart_format_schmidt(matiere, weeks, y, path, titre="TdC par Coloris"):
    """Graphique identique au format Schmidt, une seule série."""
    labels = [f"2026/S{w}" for w in weeks]
    fig, ax = plt.subplots(figsize=(19.5, 6.2))
    _serie(ax, np.array(y, float), BLEU, str(matiere))
    _axes_style(ax, labels, y)
    ax.set_title(titre, fontsize=17, color="#595959", pad=18)
    ax.legend(loc="center left", bbox_to_anchor=(1.0, 0.55), frameon=False, fontsize=12,
              title="Matiere", title_fontsize=11, alignment="left")
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def chart_comparaison(matiere, weeks, y_schmidt, y_nous, path):
    labels = [f"2026/S{w}" for w in weeks]
    fig, ax = plt.subplots(figsize=(19.5, 6.6))
    _serie(ax, np.array(y_schmidt, float), GRIS, "Schmidt (actuel)", labels_on=True, lw=2.5, dy=7)
    _serie(ax, np.array(y_nous, float), BLEU, "OF regroupés par semaine", labels_on=True, dy=-8)
    _axes_style(ax, labels, list(y_schmidt) + list(y_nous))
    ms, mn = np.nanmean(y_schmidt), np.nanmean([v for v in y_nous])
    ax.set_title(f"TdC par Coloris – {matiere} : Schmidt {ms:.1f} %  vs  regroupement hebdo "
                 f"{mn:.1f} % (moyenne des semaines communes)".replace(".", ","),
                 fontsize=15, color="#595959", pad=18)
    ax.legend(loc="center left", bbox_to_anchor=(1.0, 0.55), frameon=False, fontsize=11)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def run(out="results", matieres=(215371,)):
    """
    Par défaut seulement 215371 : pour les matières sans fil (220965, 219106 ...),
    notre imbrication ne fait pas encore pivoter les pièces, elle surestime donc le TdC
    et la comparaison avec Schmidt ne serait pas équitable.
    """
    dossier = os.path.join(out, "comparaison_schmidt")
    os.makedirs(dossier, exist_ok=True)
    tables = {}
    for m in matieres:
        sch = SCHMIDT[m]
        weeks = list(sch)                       # semaines affichées par Schmidt uniquement
        ours = weekly_tdc(m)
        ys = [sch[w] for w in weeks]
        yw = [ours.B0w.get(w, np.nan) * 100 for w in weeks]
        y0 = [ours.B0.get(w, np.nan) * 100 for w in weeks]
        chart_format_schmidt(m, weeks, yw, os.path.join(dossier, f"TdC_par_coloris_{m}_propose.png"))
        common = [i for i, v in enumerate(yw) if not np.isnan(v)]
        chart_comparaison(m, [weeks[i] for i in common], [ys[i] for i in common],
                          [yw[i] for i in common],
                          os.path.join(dossier, f"comparaison_{m}.png"))
        tables[m] = pd.DataFrame({
            "Semaine": [f"2026/S{w}" for w in weeks],
            "TdC Schmidt (%)": ys,
            "TdC OF regroupés par semaine (%)": np.round(yw, 2),
            "TdC OF coupés par jour, recalculé (%)": np.round(y0, 2),
        })
        print(m, "Schmidt", round(np.mean([ys[i] for i in common]), 2),
              "B0 recalc", round(np.nanmean([y0[i] for i in common]), 2),
              "B0w", round(np.nanmean([yw[i] for i in common]), 2),
              "semaines sans données:", [weeks[i] for i, v in enumerate(yw) if np.isnan(v)])
    with pd.ExcelWriter(os.path.join(dossier, "comparaison_TdC_par_coloris.xlsx")) as xw:
        for m, t in tables.items():
            t.to_excel(xw, sheet_name=str(m), index=False)
    return tables


# position du graphique de chaque matière dans la feuille « TdC » du fichier Schmidt
IMAGE_SCHMIDT = {"global": 0, 215371: 1, 221612: 2, 220965: 3, 219106: 4}


def schmidt_image(matiere, path):
    """Extrait le graphique original Schmidt de la matière (feuille TdC) vers `path`."""
    import openpyxl
    from .data import _p, F_OF
    ws = openpyxl.load_workbook(_p(F_OF))["TdC"]
    imgs = sorted(ws._images, key=lambda im: im.anchor._from.row)
    with open(path, "wb") as f:
        f.write(imgs[IMAGE_SCHMIDT[matiere]]._data())
    return path


def weekly_tdc_global(matieres, restes_age_max=None):
    """TdC hebdomadaire toutes matières confondues (pondéré par la surface)."""
    tabs = []
    for m in matieres:
        try:
            tabs.append(weekly_tdc(m, restes_age_max))
        except Exception:      # matière sans OF / sans article
            pass
    t = pd.concat(tabs).groupby(level=0)[["pa", "ca_w", "ca_0", "pieces"]].sum()
    return pd.DataFrame({"B0w": 1 - t.pa / t.ca_w, "B0": 1 - t.pa / t.ca_0,
                         "pieces": t.pieces})


def chart_nous(nom, weeks, y_semaine, y_jour, path, titre):
    """Notre graphique, au format Schmidt (mêmes semaines, étiquettes, tendance linéaire).
    Bleu : OF regroupés par semaine ; gris fin : mêmes OF coupés par jour (notre recalcul)."""
    labels = [f"2026/S{w}" for w in weeks]
    fig, ax = plt.subplots(figsize=(19.5, 6.2))
    yj = np.array(y_jour, float)
    ax.plot(np.arange(len(yj)), yj, color=GRIS, lw=1.6, label="OF coupés par jour (recalcul)")
    _serie(ax, np.array(y_semaine, float), BLEU, "OF regroupés par semaine")
    _axes_style(ax, labels, list(y_semaine) + list(y_jour))
    ax.set_title(titre, fontsize=17, color="#595959", pad=18)
    ax.legend(loc="center left", bbox_to_anchor=(1.0, 0.55), frameon=False, fontsize=11,
              title="Epaisseur_16" if nom == "global" else str(nom), title_fontsize=11,
              alignment="left")
    fig.tight_layout()
    fig.savefig(path, dpi=100)
    plt.close(fig)

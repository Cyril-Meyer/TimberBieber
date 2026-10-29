"""Load and prepare the Schmidt data for one material."""
import glob
import os
import pandas as pd

# default: a "data" folder next to run.py (put the three Excel files there)
DATA_DIR = os.environ.get("ORDO_DATA", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))
F_ART = "1793090026443_Automne_de_lIA_2026_SG_DDM_-_Données_articles_et_matières.xlsx"
F_OF = "1793090026442_Automne_de_lIA_2026_SG_DDM_-_OFs_et_TdC.xlsx"
F_MVT = "1793090026440_Automne_de_lIA_2026_SG_DDM_-_Mouvements_de_stock_montage.xlsx"


def _p(name):
    """Find the Excel file by keyword, so prefixes / renamed files still work."""
    key = {F_ART: "articles", F_OF: "OFs", F_MVT: "Mouvements"}[name]
    found = [f for f in glob.glob(os.path.join(DATA_DIR, "*.xlsx")) if key in os.path.basename(f)]
    if not found:
        raise FileNotFoundError(f"no Excel containing '{key}' in DATA_DIR = {DATA_DIR}")
    return found[0]


def load_material(matiere=215371):
    mat = pd.read_excel(_p(F_ART), "Matière").dropna(subset=["Matiere"])
    mat = mat[mat.Matiere.astype(int) == matiere].iloc[0]
    art = pd.read_excel(_p(F_ART), "Articles")
    art = art[art.Coloris == matiere].copy()
    art["SensFil"] = art.SensFil.fillna("").astype(str).str.strip()
    art["q"] = art["QtéParOF"].round().clip(lower=1).astype(int)  # OF lot size
    art = art.set_index("Article")
    return mat, art


def weekly_demand(art, cache="mouv.pkl"):
    """Weekly consumption (pieces) per article from the assembly stock movements."""
    if os.path.exists(cache):
        mv = pd.read_pickle(cache)
    else:
        mv = pd.read_excel(_p(F_MVT))
        mv.to_pickle(cache)
    mv = mv[mv.Article.isin(art.index)]
    # consumption + scrap both empty the assembly stock
    mv = mv[mv["Catégorie"].isin(["Consommation", "Rebut"])].copy()
    mv["week"] = mv["Date comptable"].dt.to_period("W-SUN").dt.start_time
    d = -mv.pivot_table(index="week", columns="Article", values="Quantité",
                        aggfunc="sum", fill_value=0)
    full = pd.date_range(d.index.min(), d.index.max(), freq="W-MON")
    d = d.reindex(full, fill_value=0).reindex(columns=art.index, fill_value=0)
    return d.clip(lower=0).astype(int)


def historical_ofs(art):
    of = pd.read_excel(_p(F_OF), "OF")
    of = of[of.Article.isin(art.index)].copy()
    of["week"] = of.DateProd.dt.to_period("W-SUN").dt.start_time
    return of

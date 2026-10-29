"""
Intra-week sequencing of panels and buffer (stock tampon) simulation.

Rules from the company sheet:
  - a piece enters the buffer when it is cut (1 time unit per piece)
  - an OF leaves the buffer only when all its pieces are in it
  - exit rate = 3 pieces for every 2 entering  -> 1.5 pieces per time unit
  - capacity 3192, target <= 80 % (2553)

OFs: the weekly quantity of an article is split into OFs of QteParOF pieces
(last OF = remainder). Pieces of an article fill its OFs in order.
"""
import numpy as np
import pandas as pd

CAP = 3192
LIMIT = int(0.8 * CAP)
OUT_RATE = 1.5


def split_ofs(x, q):
    """x: {art: qty}, q: {art: lot} -> list of OF sizes per article"""
    ofs = {}
    for a, n in x.items():
        n = int(n)
        if n <= 0:
            continue
        lot = max(int(q[a]), 1)
        # OF >= QteParOF : le reste est ajouté au dernier OF (ex. 200 avec lot 177 -> 1 OF de 200)
        k = max(n // lot, 1)
        sizes = [lot] * (k - 1) + [n - lot * (k - 1)]
        ofs[a] = sizes
    return ofs


def simulate_buffer(panel_seq, ofs):
    """Return occupancy curve (one point per piece cut) and peak."""
    ofs = {a: list(s) for a, s in ofs.items()}
    filled = {a: 0 for a in ofs}        # pieces cut into the current OF of a
    queue = 0.0                          # pieces of complete OFs waiting to exit
    occ, curve = 0.0, []
    for items in panel_seq:
        for a, n in items.items():
            for _ in range(n):
                occ += 1
                if a in ofs and ofs[a]:
                    filled[a] += 1
                    if filled[a] >= ofs[a][0]:
                        queue += ofs[a].pop(0)
                        filled[a] = 0
                out = min(OUT_RATE, queue)
                queue -= out
                occ -= out
                curve.append(occ)
    # drain at the end of the week
    return np.array(curve), (max(curve) if curve else 0.0)


def sequence_greedy(panels, ofs):
    """
    Order panels so OFs are completed as early as possible:
    next panel = the one whose pieces most belong to articles already started,
    tie-break: fewest pieces of not-yet-started articles.
    """
    remaining = list(range(len(panels)))
    started, seq = set(), []
    # start with the article that has the smallest weekly quantity to clear it fast
    while remaining:
        def score(j):
            it = panels[j]
            tot = sum(it.values())
            inside = sum(n for a, n in it.items() if a in started)
            new = tot - inside
            return (inside / tot if tot else 0, -new)
        j = max(remaining, key=score)
        remaining.remove(j)
        seq.append(panels[j])
        started |= set(panels[j])
    return seq


def week_buffer(panels, x, q, greedy=True):
    ofs = split_ofs(x, q)
    seq = sequence_greedy(panels, ofs) if greedy else panels
    curve, peak = simulate_buffer(seq, ofs)
    return curve, peak, seq


# --------------------------------------------------------------------------
# Ordre de coupe et liste des OF (livrable 3)
# --------------------------------------------------------------------------
def cutting_order(week, panels, x, q, designation, lead_days=7):
    """
    Ordre de coupe d'une semaine.
      week        : lundi de la semaine (Timestamp)
      panels      : liste {article: nb pièces} par panneau (sortie de l'imbrication)
      x           : {article: quantité de la semaine}
      q           : QteParOF par article
    Renvoie (lignes_ordre, lignes_of, pic_stock_tampon)
      lignes_ordre : 1 ligne par (panneau, article) dans l'ordre de coupe
      lignes_of    : 1 ligne par OF (taille, panneau de début / fin, dates)
    """
    ofs = split_ofs(x, q)
    # on garde l'ordre (imbrication ou glouton) qui donne le plus petit pic de stock tampon
    seq_a = panels
    seq_b = sequence_greedy(panels, ofs)
    _, peak_a = simulate_buffer(seq_a, ofs)
    _, peak_b = simulate_buffer(seq_b, ofs)
    seq, peak = (seq_b, peak_b) if peak_b < peak_a else (seq_a, peak_a)

    iso = week.isocalendar()
    tag = f"{iso[0]}-S{iso[1]:02d}"
    # OF identifiers: <année>-S<semaine>-<article>-<n>
    of_list = {a: [{"OF": f"{tag}-{a}-{k + 1}", "Article": a, "Taille OF": s,
                    "coupées": 0, "panneau début": None, "panneau fin": None}
                   for k, s in enumerate(sizes)] for a, sizes in ofs.items()}
    cur = {a: 0 for a in of_list}          # index of the OF being filled
    rows = []
    for n_pan, items in enumerate(seq, start=1):
        for a, n in sorted(items.items()):
            while n > 0 and a in of_list and cur[a] < len(of_list[a]):
                of = of_list[a][cur[a]]
                take = min(n, of["Taille OF"] - of["coupées"])
                if of["panneau début"] is None:
                    of["panneau début"] = n_pan
                of["coupées"] += take
                n -= take
                complete = of["coupées"] >= of["Taille OF"]
                if complete:
                    of["panneau fin"] = n_pan
                rows.append({
                    "Semaine": tag, "N° panneau": n_pan, "Article": a,
                    "Désignation": designation.get(a, ""), "OF": of["OF"],
                    "Pièces sur ce panneau": take,
                    "Cumul OF": f'{of["coupées"]}/{of["Taille OF"]}',
                    "OF complet → sortie": "oui" if complete else "",
                })
                if complete:
                    cur[a] += 1
    lancement = week
    livraison = week + pd.Timedelta(days=lead_days)
    of_rows = []
    for a, lst in of_list.items():
        for of in lst:
            of_rows.append({
                "OF": of["OF"], "Semaine": tag, "Article": a,
                "Désignation": designation.get(a, ""), "Quantité": of["Taille OF"],
                "Date lancement": lancement.strftime("%Y-%m-%d"),
                "Date livraison": livraison.strftime("%Y-%m-%d"),
                "Délai (jours)": lead_days,
                "Panneau début": of["panneau début"], "Panneau fin": of["panneau fin"],
            })
    return rows, of_rows, peak

"""
Guillotine nesting heuristic for one panel material (pattern based).

All dimensions are in 1/10 mm.
  Stage 1: rip cuts across the panel width  -> strips of height h, full usable length
  Stage 2: cross cuts in a strip            -> columns of length l (grain direction)
  Stage 3: cuts in a column                 -> m identical pieces stacked (w + kerf each)

Grain (SensFil): the panel grain runs along its X (length).
  piece grain 'X' -> piece X along panel X
  piece grain 'Y' -> piece rotated, its Y along panel X
  no grain        -> free orientation (narrowest strip chosen)

Algorithm
  1. Strip patterns: for the widest remaining mandatory piece width h, solve a
     bounded knapsack on the strip length (dynamic programming, 1 mm grid):
     items = columns of each article that fits (w <= h), value = piece area.
     Optional pieces may enter with a lower value (they only fill gaps).
     The best pattern is repeated as many times as the stock of pieces allows
     (cutting-stock idea) -> few DP calls.
  2. Strips are packed into panels by First Fit Decreasing on their height.
  3. Leftover height of each panel is filled with strips of optional pieces only,
     so optional pieces never open a new panel.

Waste (TdC) = 1 - piece area / (panels * panel area - reusable offcut of the last panel)
"""
from dataclasses import dataclass
import numpy as np


@dataclass
class Panel:
    L: int = 26550          # length (grain direction)
    W: int = 21000          # width
    trim: int = 210         # cleaning cut per side, kerf included
    kerf: int = 44
    reste_min_l: int = 8000
    reste_min_w: int = 8000

    @property
    def Lu(self):
        return self.L - 2 * self.trim

    @property
    def Wu(self):
        return self.W - 2 * self.trim

    @property
    def area(self):
        return self.L * self.W


def orient(X, Y, sens):
    if sens == "X":
        return [(X, Y)]
    if sens == "Y":
        return [(Y, X)]
    return [(X, Y), (Y, X)]


class Nester:
    GRID = 10  # DP resolution: 10 x 0.1 mm = 1 mm

    def __init__(self, articles, panel=None, opt_weight=0.97):
        """articles: dict art -> (X, Y, SensFil)"""
        self.panel = panel or Panel()
        self.opt_weight = opt_weight
        self.dims, self.area, self.orients = {}, {}, {}
        P = self.panel
        for a, (X, Y, s) in articles.items():
            o = [d for d in orient(int(X), int(Y), s) if d[0] <= P.Lu and d[1] <= P.Wu]
            if not o:
                raise ValueError(f"article {a} does not fit the panel")
            self.dims[a] = min(o, key=lambda d: d[1])   # orientation la plus étroite
            self.orients[a] = o                           # toutes les orientations permises
            self.area[a] = int(X) * int(Y)

    # ------------------------------------------------------------ strip pattern
    def _pattern(self, h, mand, opt):
        """Best set of columns for a strip of height h. Returns {(pool, art): n_pieces}."""
        P, k, g = self.panel, self.panel.kerf, self.GRID
        cap = (P.Lu + k) // g
        items = []  # (weight, value, pool, art, pieces_in_column)
        for pool, wgt in ((mand, 1.0), (opt, self.opt_weight)):
            for a, n in pool.items():
                if n <= 0:
                    continue
                # pièce sans fil : les deux orientations sont proposées au sac à dos
                for l, w in self.orients[a]:
                    if w > h:
                        continue
                    m = (h + k) // (w + k)              # pieces per column
                    full, part = divmod(n, m)
                    wt = -(-(l + k) // g)               # ceil
                    if full:
                        # binary splitting of `full` identical columns
                        c = 1
                        while full > 0:
                            t = min(c, full)
                            items.append((wt * t, wgt * self.area[a] * m * t, pool, a, m * t, w))
                            full -= t
                            c *= 2
                    if part:
                        items.append((wt, wgt * self.area[a] * part, pool, a, part, w))
        if not items:
            return {}, 0
        best = np.zeros(cap + 1)
        take = np.zeros((len(items), cap + 1), dtype=bool)
        for j, (wt, val, *_ ) in enumerate(items):
            if wt > cap:
                continue
            cand = np.full(cap + 1, -1.0)
            cand[wt:] = best[:-wt] + val
            better = cand > best + 1e-9
            take[j] = better
            best = np.where(better, cand, best)
        c = int(np.argmax(best))
        pat, h_used, avail = {}, 0, {}
        for j in range(len(items) - 1, -1, -1):
            if take[j, c]:
                wt, _, pool, a, npc, w = items[j]
                key = (id(pool), a)
                # deux orientations du même article : ne pas dépasser la quantité restante
                avail.setdefault(key, pool[a])
                npc = min(npc, avail[key] - pat.get(key, 0))
                if npc > 0:
                    pat[key] = pat.get(key, 0) + npc
                    h_used = max(h_used, w)
                c -= wt
        return pat, h_used

    def _strips(self, mand, opt, only_opt_h=None):
        """Generate strips; returns list of (h, {art: n}, piece_area)."""
        pools = {id(mand): mand, id(opt): opt}
        out = []
        while True:
            if only_opt_h is None:
                rem = [a for a, n in mand.items() if n > 0]
                if not rem:
                    break
                h = max(self.dims[a][1] for a in rem)
                pat, h_used = self._pattern(h, mand, opt)
                if not any(pid == id(mand) for pid, _ in pat):
                    pat, h_used = self._pattern(h, mand, {})  # guarantee progress
            else:
                return out
            # pieces actually used, and how many times the pattern can repeat
            reps = min(pools[pid][a] // n for (pid, a), n in pat.items())
            reps = max(reps, 1)
            content, parea = {}, 0
            for (pid, a), n in pat.items():
                pools[pid][a] -= n * reps
                content[a] = content.get(a, 0) + n
                parea += n * self.area[a]
            # real strip height = widest piece used
            out.extend([(h_used, content, parea)] * reps)
        return out

    def _fill_height(self, rem_h, opt):
        """One strip of optional pieces fitting in rem_h, or None."""
        cands = [a for a, n in opt.items() if n > 0 and self.dims[a][1] <= rem_h]
        if not cands:
            return None
        best = None
        for h in sorted({self.dims[a][1] for a in cands}, reverse=True)[:4]:
            pat, h_used = self._pattern(h, {}, opt)
            val = sum(n * self.area[a] for (_, a), n in pat.items())
            if pat and (best is None or val / h_used > best[0]):
                best = (val / h_used, h_used, pat)
        if not best:
            return None
        _, h, pat = best
        content, parea = {}, 0
        for (_, a), n in pat.items():
            opt[a] -= n
            content[a] = content.get(a, 0) + n
            parea += n * self.area[a]
        return (h, content, parea)

    # ------------------------------------------------------------------- panels
    def nest(self, mandatory, optional=None):
        P, k = self.panel, self.panel.kerf
        mand = {a: int(n) for a, n in mandatory.items() if n > 0}
        opt = {a: int(n) for a, n in (optional or {}).items() if n > 0}
        opt0 = dict(opt)
        strips = self._strips(mand, opt)
        strips.sort(key=lambda s: -s[0])
        panels = []  # [used_height, [strips]]
        for s in strips:
            for p in panels:
                if p[0] + k + s[0] <= P.Wu:
                    p[0] += k + s[0]
                    p[1].append(s)
                    break
            else:
                panels.append([s[0], [s]])
        for p in panels:
            while True:
                s = self._fill_height(P.Wu - p[0] - k, opt)
                if s is None:
                    break
                p[0] += k + s[0]
                p[1].append(s)

        n_pan = len(panels)
        piece_area = sum(s[2] for p in panels for s in p[1])
        reste = 0
        if panels:
            rem = P.Wu - min(p[0] for p in panels) - k
            if rem >= P.reste_min_w:
                reste = rem * P.Lu
        consumed = n_pan * P.area - reste
        panel_items = []
        for p in panels:
            d = {}
            for s in p[1]:
                for a, n in s[1].items():
                    d[a] = d.get(a, 0) + n
            panel_items.append(d)
        return {
            "n_panels": n_pan,
            "tdc": 1 - piece_area / consumed if consumed else 0.0,
            "piece_area": piece_area,
            "consumed_area": consumed,
            "reste_area": reste,
            "optional_cut": {a: opt0[a] - opt[a] for a in opt0 if opt0[a] > opt[a]},
            "panels": panel_items,
            # hauteur libre en haut de chaque panneau (sur toute la longueur utile)
            "panel_rem": [P.Wu - p[0] - k for p in panels],
        }

    # ----------------------------------------------------------------- restes
    def fill_reste(self, L, W, pool):
        """
        Remplit un reste L x W (L dans le sens du fil, bords déjà propres : pas de
        coupe de propreté) avec les pièces de `pool` (modifié sur place).
        Renvoie (contenu {article: n}, surface pièces, hauteur libre restante).
        """
        N = Nester.__new__(Nester)
        N.panel = Panel(L=int(L), W=int(W), trim=0, kerf=self.panel.kerf,
                        reste_min_l=self.panel.reste_min_l, reste_min_w=self.panel.reste_min_w)
        N.opt_weight, N.area = self.opt_weight, self.area
        N.orients = {a: [d for d in o if d[0] <= L and d[1] <= W]
                     for a, o in self.orients.items()}
        N.orients = {a: o for a, o in N.orients.items() if o}
        N.dims = {a: min(o, key=lambda d: d[1]) for a, o in N.orients.items()}
        sub = {a: n for a, n in pool.items() if a in N.dims and n > 0}
        k, used, content, parea = self.panel.kerf, 0, {}, 0
        while True:
            free = W - used - (k if used else 0)
            st = N._fill_height(free, sub)
            if st is None:
                break
            used += (k if used else 0) + st[0]
            for a, n in st[1].items():
                content[a] = content.get(a, 0) + n
            parea += st[2]
        for a, n in content.items():
            pool[a] -= n
        return content, parea, W - used - (k if used else 0)


class BestNester:
    """
    Tries both first-cut directions and keeps the one with the fewest panels
    (tie -> lower TdC):
      'length': first cuts produce strips along the panel length (grain)
      'width' : first cuts produce strips across the panel (transposed problem)
    Grain constraints are preserved: transposing swaps panel and piece axes together.
    """

    def __init__(self, articles, panel=None, opt_weight=0.97, mode="best"):
        panel = panel or Panel()
        self.panel, self.mode = panel, mode
        self.n_len = Nester(articles, panel, opt_weight)
        pt = Panel(L=panel.W, W=panel.L, trim=panel.trim, kerf=panel.kerf,
                   reste_min_l=panel.reste_min_w, reste_min_w=panel.reste_min_l)
        self.n_wid = Nester.__new__(Nester)
        self.n_wid.panel, self.n_wid.opt_weight = pt, opt_weight
        self.n_wid.dims = {a: (w, l) for a, (l, w) in self.n_len.dims.items()}
        self.n_wid.orients = {a: [(w, l) for l, w in o] for a, o in self.n_len.orients.items()}
        for a, o in self.n_wid.orients.items():   # orientations qui tiennent dans le panneau
            self.n_wid.orients[a] = [d for d in o if d[0] <= pt.Lu and d[1] <= pt.Wu] or o
            self.n_wid.dims[a] = min(self.n_wid.orients[a], key=lambda d: d[1])
        self.n_wid.area = self.n_len.area
        self.area, self.dims = self.n_len.area, self.n_len.dims

    def _qualifie(self, L, W):
        P = self.panel
        return L >= P.reste_min_l and W >= P.reste_min_w

    def nest(self, mandatory, optional=None, restes=None):
        """
        restes = None  : pas de gestion de restes (ancien calcul).
        restes = liste : stock de restes [{"L", "W", "age"}] (L dans le sens du fil).
          1. les pièces obligatoires sont d'abord placées sur les restes du stock
             (les plus grands d'abord) ;
          2. le reste des pièces est imbriqué sur des panneaux neufs ;
          3. toute zone libre >= ResteMin (haut des panneaux, fin des restes utilisés)
             devient un nouveau reste.
          Surface consommée = panneaux neufs + restes utilisés - restes créés.
          Le résultat contient "restes_stock" : le nouveau stock (à vieillir ensuite).
        """
        if restes is None:
            return self._nest_simple(mandatory, optional)
        P, k = self.panel, self.panel.kerf
        mand = {a: int(n) for a, n in mandatory.items() if n > 0}
        used, created, r_panels, pa_r = [], [], [], 0
        for r in sorted(restes, key=lambda r: -r["L"] * r["W"]):
            if not any(n > 0 for n in mand.values()):
                break
            content, pa, free = self.n_len.fill_reste(r["L"], r["W"], mand)
            if pa > 0:
                used.append(r)
                pa_r += pa
                r_panels.append(content)
                if self._qualifie(r["L"], free):
                    created.append({"L": r["L"], "W": free, "age": 0})
        rest = [r for r in restes if not any(r is u for u in used)]
        best = None
        for nest_, frame in ((self.n_len, "length"), (self.n_wid, "width")):
            if self.mode not in ("best", frame):
                continue
            r = nest_.nest(mand, optional)
            new = []
            for free in r["panel_rem"]:
                # restes dans le repère de la matière : L le long du fil (X)
                L, W = (nest_.panel.Lu, free) if frame == "length" else (free, nest_.panel.Lu)
                if self._qualifie(L, W):
                    new.append({"L": L, "W": W, "age": 0})
            cr = created + new
            pa = r["piece_area"] + pa_r
            ca = (r["n_panels"] * P.area + sum(u["L"] * u["W"] for u in used)
                  - sum(c["L"] * c["W"] for c in cr))
            out = dict(r, first_cut=frame, piece_area=pa, consumed_area=ca,
                       tdc=1 - pa / ca if ca > 0 else 0.0,
                       panels=r_panels + r["panels"], restes_stock=rest + cr,
                       n_restes_utilises=len(used),
                       surface_restes_utilises=sum(u["L"] * u["W"] for u in used),
                       surface_restes_crees=sum(c["L"] * c["W"] for c in cr))
            if best is None or (out["tdc"], out["n_panels"]) < (best["tdc"], best["n_panels"]):
                best = out
        return best

    def _nest_simple(self, mandatory, optional=None):
        res = []
        if self.mode in ("best", "length"):
            r = self.n_len.nest(mandatory, optional); r["first_cut"] = "length"; res.append(r)
        if self.mode in ("best", "width"):
            r = self.n_wid.nest(mandatory, optional); r["first_cut"] = "width"; res.append(r)
        # value = useful area per consumed area, counting optional pieces as useful
        return min(res, key=lambda r: (r["tdc"], r["n_panels"]))


def vieillir_restes(stock, age_max):
    """+1 semaine pour chaque reste ; ceux qui dépassent age_max sont mis au rebut.
    Renvoie (nouveau stock, surface mise au rebut)."""
    garde, rebut = [], 0
    for r in stock:
        r = dict(r, age=r["age"] + 1)
        if r["age"] > age_max:
            rebut += r["L"] * r["W"]
        else:
            garde.append(r)
    return garde, rebut

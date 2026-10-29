"""
Weekly lot-sizing / OF generation for one material.

Time step = 1 week, lead time = 1 week:
  S[i,t]  stock at the assembly shop at the START of week t (after receipts)
  d[i,t]  consumption during week t
  x[i,t]  quantity cut during week t, available at the start of week t+1
  S[i,t+1] = S[i,t] - d[i,t] + x[i,t]

Constraints
  (C1) no stock-out:      S[i,t] - d[i,t] >= 0
  (C2) safety stock:      S[i,t+1] >= d[i,t+1] + SS[i]   (cover next week + safety)
  (C3) OF lot:            x[i,t] = q[i] * k[i,t],  k integer   (QteParOF multiples)
  (C4) stock cap:         S[i,t+1] <= Smax[i]
  (C5) saw capacity:      N[t] <= C
  (C6) buffer:            peak occupancy <= 0.8 * 3192  (checked by sequencing.py)
Objective
  min  sum_t N[t]   (+ small costs for #OF and stock)

Two planners are provided:
  - policy_plan : rule "order only what is needed, in multiples of q" (baseline)
  - milp_plan   : MILP (scipy/HiGHS) on the area model
                  sum_i a_i x[i,t] <= eta * A * N[t]
Both are followed by the geometric nester; the optimised variants also fill
the gaps of the opened panels with pieces needed later ("fill").
"""
import numpy as np
import pandas as pd
from scipy.optimize import milp, LinearConstraint, Bounds

from .nesting import vieillir_restes


def params(art, demand, ss_weeks=0.5, smax_weeks=4.0):
    dbar = demand.mean()
    p = pd.DataFrame(index=art.index)
    p["q"] = art.q
    p["a"] = art.X * art.Y
    p["dbar"] = dbar
    p["SS"] = np.ceil(ss_weeks * dbar)
    # stock cap: smax_weeks of demand, but always at least one lot + safety
    p["Smax"] = np.maximum(np.ceil(smax_weeks * dbar), p.q + p.SS + dbar)
    return p


def initial_stock(p, demand):
    return (demand.iloc[0] + p.SS).astype(int)


# --------------------------------------------------------------------------
def simulate(p, demand, nester, mode="policy", plan=None, fill=True, lot_rule="min",
             max_weeks=3, restes_age_max=None, verbose=False):
    """
    Roll week by week.
    mode='policy': mandatory x = smallest multiple of q meeting (C2)
    mode='plan'  : mandatory x given by a precomputed plan (DataFrame week x art)
    fill=True    : add optional pieces into free space, bounded by Smax (C4)
    restes_age_max : None = pas de gestion des restes ; sinon nombre de semaines
                   pendant lesquelles un reste est gardé avant d'être mis au rebut
    max_weeks    : délai max. entre le lancement de l'OF et l'utilisation des pièces.
                   Un OF lancé en semaine t est livré en t+1 (délai 1 sem. <= max_weeks) ;
                   les pièces de remplissage ne couvrent que la demande des semaines
                   t+1 .. t+max_weeks (jamais un besoin plus lointain).
    Returns weekly KPIs and the realised production plan.
    """
    arts = list(p.index)
    S = initial_stock(p, demand).astype(float)
    weeks = demand.index[:-1]  # last week only used as "next week" demand
    rows, prod = [], {}
    stock_r = [] if restes_age_max is not None else None
    for ti, w in enumerate(weeks):
        d_now = demand.loc[w]
        d_next = demand.iloc[ti + 1]
        after = S - d_now                       # stock end of week before receipt
        if (after < -1e-9).any() and verbose:
            print("stock-out", w.date(), list(after[after < 0].index))
        need = (d_next + p.SS - after).clip(lower=0)
        if mode == "policy":
            x = np.ceil(need / p.q) * p.q
        else:
            x = plan.loc[w].reindex(arts).fillna(0)
            x = np.maximum(x, np.ceil(need / p.q) * p.q)  # safety net for (C2)
        mand = {a: int(x[a]) for a in arts if x[a] > 0}
        opt = {}
        if fill:
            # (C5) stock max  et  (C9) horizon de max_weeks semaines
            horizon = demand.iloc[ti + 1: ti + 1 + max_weeks].sum() + p.SS
            cap_i = np.minimum(p.Smax, horizon)
            room = (cap_i - (after + x)).clip(lower=0).astype(int)
            # urgency: articles with the lowest future coverage first
            cover = (after + x) / p.dbar.replace(0, np.nan)
            for a in cover.sort_values().index:
                if room[a] > 0 and p.dbar[a] > 0:
                    opt[a] = int(room[a])
        res = nester.nest(mand, opt, restes=stock_r)
        extra = pd.Series(res["optional_cut"], dtype=float).reindex(arts).fillna(0)
        if fill and extra.sum() > 0:
            # make the filled quantities respect the OF lot rule, then re-nest
            if lot_rule == "multiple":
                extra = np.floor(extra / p.q) * p.q
            else:  # 'min': OF >= q ; extra can join an existing OF of the week
                extra = extra.where((x > 0) | (extra >= p.q), 0)
            x_all = x + extra
            res = nester.nest({a: int(v) for a, v in x_all.items() if v > 0}, restes=stock_r)
        x_tot = x + extra
        rebut = 0
        if stock_r is not None:
            stock_r, rebut = vieillir_restes(res["restes_stock"], restes_age_max)
        S = after + x_tot
        prod[w] = x_tot
        rows.append({
            "week": w, "pieces": int(x_tot.sum()), "pieces_mand": int(x.sum()),
            "pieces_fill": int(extra.sum()), "n_OF": int((x_tot > 0).sum()),
            "panels": res["n_panels"], "tdc": res["tdc"],
            "piece_area": res["piece_area"], "consumed_area": res["consumed_area"] + rebut,
            "restes_utilises": res.get("n_restes_utilises", 0),
            "restes_en_stock": len(stock_r) if stock_r is not None else 0,
            "stock_end": float(S.sum()), "min_stock_after": float(after.min()),
            "_panels": res["panels"], "_x": x_tot,
        })
    kpi = pd.DataFrame(rows).set_index("week")
    return kpi, pd.DataFrame(prod).T


# --------------------------------------------------------------------------
def milp_plan(p, demand, eta=0.83, panel_area=26550 * 21000, cap=None,
              lam_of=0.15, mu_stock=1e-4, time_limit=60):
    """
    Variables per (i,t): k (integer, number of lots), y (binary, OF opened), S (stock)
    Per t: N (integer, panels)
    min sum N + lam_of * sum y + mu_stock * sum S_area
    """
    arts = list(p.index)
    n, T = len(arts), len(demand) - 1
    D = demand[arts].to_numpy(float)  # (T+1, n)
    q = p.q.to_numpy(float)
    a = p.a.to_numpy(float)
    SS = p.SS.to_numpy(float)
    Smax = p.Smax.to_numpy(float)
    S0 = initial_stock(p, demand).to_numpy(float)
    Kmax = np.ceil(Smax / q) + 1

    # index helpers
    nk = n * T
    ik = lambda i, t: i * T + t              # k
    iy = lambda i, t: nk + i * T + t         # y
    iS = lambda i, t: 2 * nk + i * T + t     # S at start of week t+1 (after receipt)
    iN = lambda t: 3 * nk + t
    nv = 3 * nk + T

    c = np.zeros(nv)
    for i in range(n):
        for t in range(T):
            c[iy(i, t)] = lam_of
            c[iS(i, t)] = mu_stock * a[i] / panel_area
    for t in range(T):
        c[iN(t)] = 1.0

    rows, lo, hi = [], [], []

    def add(coefs, l, h):
        r = np.zeros(nv)
        for j, v in coefs:
            r[j] += v
        rows.append(r); lo.append(l); hi.append(h)

    for i in range(n):
        for t in range(T):
            # stock balance: S_t = S_{t-1} - d_t + q k_t   (S_{-1}=S0)
            if t == 0:
                add([(iS(i, t), 1), (ik(i, t), -q[i])], S0[i] - D[0, i], S0[i] - D[0, i])
            else:
                add([(iS(i, t), 1), (iS(i, t - 1), -1), (ik(i, t), -q[i])], -D[t, i], -D[t, i])
            # k <= Kmax * y
            add([(ik(i, t), 1), (iy(i, t), -Kmax[i])], -np.inf, 0)
    # area / panels
    for t in range(T):
        coefs = [(ik(i, t), a[i] * q[i]) for i in range(n)] + [(iN(t), -eta * panel_area)]
        add(coefs, -np.inf, 0)

    lb = np.zeros(nv); ub = np.full(nv, np.inf)
    integ = np.zeros(nv)
    for i in range(n):
        for t in range(T):
            ub[ik(i, t)] = Kmax[i]; integ[ik(i, t)] = 1
            ub[iy(i, t)] = 1; integ[iy(i, t)] = 1
            # (C1)+(C2): S_t - d_{t+1} >= SS  ; (C4) S_t <= Smax
            lb[iS(i, t)] = D[t + 1, i] + SS[i]
            # the window must be at least one lot wide, else multiples of q can't land in it
            ub[iS(i, t)] = max(Smax[i], D[t + 1, i] + SS[i] + q[i])
    for t in range(T):
        integ[iN(t)] = 1
        if cap:
            ub[iN(t)] = cap
    res = milp(c, constraints=LinearConstraint(np.array(rows), lo, hi),
               integrality=integ, bounds=Bounds(lb, ub),
               options={"time_limit": time_limit, "mip_rel_gap": 0.01})
    if res.x is None:
        raise RuntimeError(res.message)
    xk = res.x[:nk].reshape(n, T).round()
    plan = pd.DataFrame((xk * q[:, None]).T, index=demand.index[:-1], columns=arts)
    return plan, res

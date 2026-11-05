"""Calibrate the blessing game: survivors with no gifts vs with free-only redistribution (give spare to whoever is short)."""
import random, itertools, statistics
N = ["Atlas", "Orion", "Vega", "Lyra"]

def sim(start, k, R, seed, policy):
    rb = random.Random(seed * 1000 + 7)
    L = {n: start for n in N}; alive = {n: True for n in N}; nfree = 0
    for t in range(1, R + 1):
        run = [n for n in N if alive[n]]
        if not run: break
        b = rb.choice(run); L[b] += k
        need = R - t + 1
        if policy == "free":
            for g in run:
                sp = L[g] - need
                while sp > 0:
                    short = sorted((n for n in run if n != g and L[n] < need), key=lambda n: need - L[n])
                    if not short: break
                    L[short[0]] += 1; L[g] -= 1; sp -= 1; nfree += 1
        for n in run:
            if L[n] >= 1: L[n] -= 1
            else: alive[n] = False
    return sum(alive.values()), nfree

for start, k, R in itertools.product([1, 2], [2, 3, 4], [4, 5]):
    a = [sim(start, k, R, s, "none")[0] for s in range(400)]
    b = [sim(start, k, R, s, "free") for s in range(400)]
    print(f"start {start} bless {k} R {R}: no gifts {statistics.mean(a):.2f} survive | free redistribution {statistics.mean(x for x, _ in b):.2f} survive, {statistics.mean(y for _, y in b):.1f} free gifts | lives total {4*start + k*R} vs need {4*R}")

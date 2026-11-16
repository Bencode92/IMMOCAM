#!/usr/bin/env python3
"""
Référentiel DVF « hôtels particuliers » par commune (Paris par arrondissement).

- maisons : ventes de maisons >= 200 m² (hors appartements / locaux dans la même vente)
- commerces : ventes d'immeubles ou locaux commerciaux entiers >= 300 m²

Source : geo-dvf (files.data.gouv.fr), 5 dernières années disponibles.
Sortie : data/dvf_ref_hp.json — à relancer une fois par an (ou à chaque nouveau millésime DVF).

Usage : python scripts/build_dvf_ref_hp.py [--depts 75 92 78] [--cache /tmp/dvf]
"""
import argparse, collections, csv, gzip, io, json, statistics as st
from datetime import date
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "dvf_ref_hp.json"
URL = "https://files.data.gouv.fr/geo-dvf/latest/csv/{y}/departements/{d}.csv.gz"
COMMERCE = "Local industriel. commercial ou assimilé"


def rows(year, dept, cache):
    path = Path(cache) / f"{year}_{dept}.csv.gz" if cache else None
    if path and path.exists():
        raw = path.read_bytes()
    else:
        r = requests.get(URL.format(y=year, d=dept), timeout=300)
        if r.status_code != 200:
            return []
        raw = r.content
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
    return csv.DictReader(io.TextIOWrapper(gzip.GzipFile(fileobj=io.BytesIO(raw)), encoding="utf-8"))


def stats(vals):
    if not vals:
        return None
    vals = sorted(vals)
    q = st.quantiles(vals, n=4) if len(vals) > 1 else [vals[0]] * 3
    return {"n": len(vals), "med": round(st.median(vals)), "q1": round(q[0]), "q3": round(q[2])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--depts", nargs="+", default=["75", "92", "78"])
    ap.add_argument("--cache", default=None)
    ap.add_argument("--years", type=int, default=5)
    a = ap.parse_args()
    years = [y for y in range(date.today().year - a.years, date.today().year + 1)]

    muts = collections.defaultdict(list)
    used = []
    for y in years:
        for d in a.depts:
            n = 0
            for r in rows(y, d, a.cache):
                if r["nature_mutation"] == "Vente":
                    muts[r["id_mutation"]].append(r)
                    n += 1
            if n:
                used.append(y)
    maisons, commerces, noms = collections.defaultdict(list), collections.defaultdict(list), {}
    for lines in muts.values():
        try:
            v = float(lines[0]["valeur_fonciere"])
        except ValueError:
            continue
        code = lines[0]["code_commune"]
        noms[code] = lines[0]["nom_commune"]
        types = {x["type_local"] for x in lines if x["type_local"]}
        locs = {(x["type_local"], x["surface_reelle_bati"], x["lot1_numero"]) for x in lines
                if x["type_local"] in ("Maison", "Appartement", COMMERCE)}
        if "Maison" in types and types <= {"Maison", "Dépendance"}:
            s = sum(float(t[1] or 0) for t in locs if t[0] == "Maison")
            if s >= 200 and v > 500_000:
                maisons[code].append(v / s)
        if types and types <= {COMMERCE, "Dépendance"}:
            s = sum(float(t[1] or 0) for t in locs)
            if s >= 300 and v > 1_000_000:
                commerces[code].append(v / s)
    out = {"meta": {"source": "DVF (geo-dvf, data.gouv.fr)", "annees": sorted(set(used)),
                    "genere_le": date.today().isoformat(),
                    "maisons": "maisons >= 200 m², ventes sans appartement ni local",
                    "commerces": "locaux commerciaux / immeubles entiers >= 300 m²"},
           "communes": {}}
    for code in sorted(set(maisons) | set(commerces)):
        out["communes"][code] = {"nom": noms.get(code, ""), "maisons": stats(maisons[code]), "commerces": stats(commerces[code])}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"{len(out['communes'])} communes -> {OUT}")


if __name__ == "__main__":
    main()

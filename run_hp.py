#!/usr/bin/env python3
"""
Flux « Hôtels particuliers » (événementiel / bureaux) — collecte + nouveautés + note.

Usage : python run_hp.py [--sources barnes licitor]
Sortie : data/hp_db.json (une entrée par annonce, first_seen / last_seen / actif)
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from hp.sources import SOURCES  # noqa: E402
from hp.enrich import enrich, load_ref, load_cache, GEOCACHE  # noqa: E402

DB = ROOT / "data" / "hp_db.json"
ZONAGES_URL = "https://opendata.paris.fr/api/explore/v2.1/catalog/datasets/zonagesreglementaires_p/exports/geojson"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", nargs="+", default=list(SOURCES))
    a = ap.parse_args()
    today = date.today().isoformat()
    db = json.loads(DB.read_text()) if DB.exists() else {"meta": {}, "annonces": {}}
    ann = db["annonces"]
    ref, cache = load_ref(), load_cache()
    try:
        zonages = requests.get(ZONAGES_URL, timeout=60).json()
    except (requests.RequestException, ValueError):
        zonages = None

    vus, erreurs = set(), {}
    for name in a.sources:
        try:
            items = SOURCES[name]().collect(known_ids=frozenset(ann))
        except Exception as ex:  # une source en panne ne bloque pas les autres
            erreurs[name] = str(ex)[:200]
            print(f"  {name}: ERREUR {ex}")
            continue
        print(f"  {name}: {len(items)} annonces")
        for x in items:
            vus.add(x["id"])
            old = ann.get(x["id"])
            if old:
                if not x.get("description"):
                    x["description"], x["dpe"] = old.get("description", ""), old.get("dpe", "")
                if old.get("prix") and x.get("prix") and old["prix"] != x["prix"]:
                    x["historique_prix"] = old.get("historique_prix", []) + [{"date": today, "avant": old["prix"]}]
                else:
                    x["historique_prix"] = old.get("historique_prix", [])
                x["first_seen"] = old["first_seen"]
            else:
                x["first_seen"] = today
            x["last_seen"], x["actif"] = today, True
            x["eval"] = enrich(x, ref, cache, zonages)
            ann[x["id"]] = x
    for k, x in ann.items():  # disparues des sources collectées ce jour
        if x["source"] in a.sources and k not in vus and x["source"] not in erreurs:
            x["actif"] = False
    nouveaux = sum(1 for x in ann.values() if x["first_seen"] == today)
    db["meta"] = {"maj": today, "total": len(ann), "actives": sum(1 for x in ann.values() if x.get("actif")),
                  "nouveaux_du_jour": nouveaux, "erreurs": erreurs}
    DB.write_text(json.dumps(db, ensure_ascii=False, indent=1))
    GEOCACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=0))
    print(f"  {len(ann)} annonces, {nouveaux} nouvelles aujourd'hui")


if __name__ == "__main__":
    main()

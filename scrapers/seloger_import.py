"""
Import des données SeLoger Bureaux Commerces depuis le JSON extrait via console.

Usage:
  1. Va sur https://www.seloger-bureaux-commerces.com/achat/bureau/ile-de-france/paris
  2. F12 Console → colle le scraper depuis seloger_intercept.html
  3. Quand "FINI!", tape: copy(JSON.stringify(window._SL))
  4. Colle dans data/seloger_raw.json
  5. python scrapers/seloger_import.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "engine"))

from delta import compute_delta, merge_into_db

RAW_PATH = Path(__file__).parent.parent / "data" / "seloger_raw.json"
DB_PATH = Path(__file__).parent.parent / "data" / "deals_db.json"


def main():
    if not RAW_PATH.exists():
        print(f"Fichier non trouvé: {RAW_PATH}")
        print("Colle le JSON de la console SeLoger dans ce fichier.")
        return

    with open(RAW_PATH) as f:
        deals = json.load(f)

    print(f"SeLoger import: {len(deals)} biens")

    with open(DB_PATH) as f:
        db = json.load(f)

    nouveaux, maj, disparus = compute_delta(deals, db)
    print(f"  Nouveaux: {len(nouveaux)}")
    print(f"  Mis à jour: {len(maj)}")

    merge_into_db(db, nouveaux)

    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

    print(f"  DB: {db['meta']['total_deals']} deals total")
    print(f"  Statuts: {db['meta']['par_statut']}")


if __name__ == "__main__":
    main()

"""
Import des données LoopNet depuis le JSON extrait via console.

Usage:
  1. Colle le JSON dans data/loopnet_raw.json
  2. python scrapers/loopnet_import.py
"""
import json
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent / "engine"))

from delta import compute_delta, merge_into_db
from pathlib import Path

RAW_PATH = Path(__file__).parent.parent / "data" / "loopnet_raw.json"
DB_PATH = Path(__file__).parent.parent / "data" / "deals_db.json"


def main():
    if not RAW_PATH.exists():
        print(f"Fichier non trouvé: {RAW_PATH}")
        print("Colle le JSON de la console LoopNet dans ce fichier.")
        return

    with open(RAW_PATH) as f:
        deals = json.load(f)

    print(f"LoopNet import: {len(deals)} biens")

    # Load DB
    with open(DB_PATH) as f:
        db = json.load(f)

    # Delta
    nouveaux, maj, disparus = compute_delta(deals, db)
    print(f"  Nouveaux: {len(nouveaux)}")
    print(f"  Mis à jour: {len(maj)}")

    # Merge
    merge_into_db(db, nouveaux)

    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

    print(f"  DB: {db['meta']['total_deals']} deals total")
    print(f"  Statuts: {db['meta']['par_statut']}")


if __name__ == "__main__":
    main()

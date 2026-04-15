#!/usr/bin/env python3
"""
Pipeline principal IMMOCAM — scrape + delta + score + export.

Usage:
    python run_scrape.py                     # scrape tous les sites
    python run_scrape.py --sites bureauxlocaux geolocaux
    python run_scrape.py --surface 300 700 --prix 5000000
"""
import json
import sys
import argparse
from pathlib import Path
from datetime import datetime

# Ajouter les dossiers au path
sys.path.insert(0, str(Path(__file__).parent / "scrapers"))
sys.path.insert(0, str(Path(__file__).parent / "engine"))

from bureauxlocaux import BureauxLocauxScraper
from geolocaux import GeolocauxScraper
from investisseur_immo import InvestisseurImmoScraper
from loopnet import LoopNetScraper
from bnppre import BNPPREScraper
from arthurloyd import ArthurLoydScraper
from licitor import LicitorScraper
from espaces_atypiques import EspacesAtypiquesScraper
from delta import compute_delta, merge_into_db, deal_key
from scorer import load_referentiel, find_commune_ref, score_deal, get_segment
from geocoder import geocode_all_deals

DATA_DIR = Path(__file__).parent / "data"
DB_PATH = DATA_DIR / "deals_db.json"
REF_PATH = DATA_DIR / "referentiel_bureaux.json"

SCRAPERS = {
    "bureauxlocaux": BureauxLocauxScraper,
    "geolocaux": GeolocauxScraper,
    "investisseur-immo": InvestisseurImmoScraper,
    "loopnet": LoopNetScraper,
    "bnppre": BNPPREScraper,
    "arthurloyd": ArthurLoydScraper,
    "licitor": LicitorScraper,
    "espaces-atypiques": EspacesAtypiquesScraper,
}


def load_db():
    if DB_PATH.exists():
        with open(DB_PATH) as f:
            return json.load(f)
    return {"meta": {"last_scrape": None, "total_deals": 0, "par_statut": {}}, "deals": {}}


def save_db(db):
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description="IMMOCAM — Scrape + Score pipeline")
    parser.add_argument("--sites", nargs="+", default=list(SCRAPERS.keys()), help="Sites a scraper")
    parser.add_argument("--depts", nargs="+", default=["75", "92"], help="Departements")
    parser.add_argument("--surface", nargs=2, type=int, default=[300, 700], help="Surface min max")
    parser.add_argument("--prix", type=int, default=5000000, help="Prix max")
    parser.add_argument("--dry-run", action="store_true", help="Ne pas sauvegarder en DB")
    args = parser.parse_args()

    filters = {
        "departements": args.depts,
        "surface_min": args.surface[0],
        "surface_max": args.surface[1],
        "prix_max": args.prix,
    }

    print("=" * 60)
    print(f"  IMMOCAM — Scrape Pipeline")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  Sites: {', '.join(args.sites)}")
    print(f"  Filtres: {args.surface[0]}-{args.surface[1]}m², max {args.prix/1e6:.1f}M EUR")
    print(f"  Departements: {', '.join(args.depts)}")
    print("=" * 60)

    # 1) Scrape
    all_scraped = []
    for site_name in args.sites:
        if site_name not in SCRAPERS:
            print(f"\n  Site inconnu: {site_name}")
            continue
        print(f"\n--- {site_name.upper()} ---")
        scraper = SCRAPERS[site_name]()
        try:
            results = scraper.scrape(filters)
            all_scraped.extend(results)
        except Exception as e:
            print(f"  ERREUR: {e}")

    print(f"\n{'=' * 60}")
    print(f"  Total scrape: {len(all_scraped)} biens")

    if not all_scraped:
        print("  Aucun bien trouve. Verifiez les filtres ou la connexion.")
        return

    # 2) Load DB + referentiel
    db = load_db()
    ref = None
    if REF_PATH.exists():
        ref = load_referentiel(REF_PATH)
        print(f"  Referentiel charge: {len(ref.get('referentiel_bureaux_idf', {}).get('communes', []))} communes")
    else:
        print("  Referentiel non trouve — scoring desactive")

    # 3) Delta
    nouveaux, mis_a_jour, disparus = compute_delta(all_scraped, db)
    print(f"\n  Delta:")
    print(f"    Nouveaux:    {len(nouveaux)}")
    print(f"    Mis a jour:  {len(mis_a_jour)}")
    print(f"    Disparus:    {len(disparus)}")

    # 4) Score les nouveaux
    def scorer(deal):
        if not ref:
            return {"score_global": 50, "grade": "?", "alertes": ["Pas de referentiel"]}
        code_insee = deal.get("localisation", {}).get("code_insee", "")
        commune_ref = find_commune_ref(ref, code_insee)
        return score_deal(deal, commune_ref)

    # 5) Merge
    if not args.dry_run:
        merge_into_db(db, nouveaux, scorer_fn=scorer)

        # 6) Geocoder les deals sans GPS
        print(f"\n  Geocodage Nominatim...")
        geocode_all_deals(db)

        save_db(db)
        print(f"\n  DB sauvegardee: {db['meta']['total_deals']} deals")
        print(f"  Statuts: {json.dumps(db['meta']['par_statut'])}")
    else:
        print(f"\n  Dry run — DB non modifiee")

    # 6) Afficher les nouveaux
    if nouveaux:
        print(f"\n{'=' * 60}")
        print(f"  NOUVEAUX DEALS ({len(nouveaux)})")
        print(f"{'=' * 60}")
        for deal in nouveaux[:10]:
            loc = deal.get("localisation", {})
            fin = deal.get("financier", {})
            bien = deal.get("bien", {})
            sc = deal.get("scoring", {})
            print(f"\n  {bien.get('surface_m2', '?')}m2 — {loc.get('commune', '?')}")
            print(f"  Prix: {fin.get('prix_affiche', 0) / 1e6:.2f}M EUR ({fin.get('prix_m2', 0):,.0f} EUR/m2)")
            print(f"  DPE: {bien.get('dpe', '?')} | Score: {sc.get('grade', '?')} ({sc.get('score_global', 0)})")
            if sc.get("alertes"):
                for a in sc["alertes"]:
                    print(f"  ⚠ {a}")
            print(f"  Source: {deal.get('source', '?')}")

    # 7) Afficher les baisses de prix
    if mis_a_jour:
        print(f"\n{'=' * 60}")
        print(f"  BAISSES DE PRIX ({len(mis_a_jour)})")
        print(f"{'=' * 60}")
        for key, changes in mis_a_jour[:10]:
            deal = db["deals"].get(key, {})
            commune = deal.get("localisation", {}).get("commune", "?")
            print(f"  {commune}: {changes['ancien_prix']/1e6:.2f}M -> {changes['nouveau_prix']/1e6:.2f}M ({changes['variation_pct']:+.1f}%)")

    print(f"\n{'=' * 60}")
    print(f"  Pipeline termine. Dashboard: ouvrir dashboard.html")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()

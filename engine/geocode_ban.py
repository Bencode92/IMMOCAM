"""
Géocodage BAN (Base Adresse Nationale, api-adresse.data.gouv.fr).

Beaucoup plus précis que Nominatim pour la France et gratuit/sans limite via
l'endpoint CSV en masse. NON DESTRUCTIF : écrit dans de nouveaux champs
(_ban_lat, _ban_lng, _geo_score, _geo_type, _geo_label) sans toucher aux
coordonnées source existantes.

Précision retournée par la BAN (champ result_type) :
  - housenumber : point au numéro exact      -> vraiment précis
  - street      : milieu de la rue           -> assez précis
  - locality / municipality : centre commune -> approximatif

Usage:
  python engine/geocode_ban.py            # géocode + écrit data/deals_db.json
  python engine/geocode_ban.py --dry-run  # n'écrit rien, affiche juste le bilan
"""
import csv
import io
import json
import re
import sys
from pathlib import Path

import requests

DB_PATH = Path(__file__).parent.parent / "data" / "deals_db.json"
BAN_CSV_URL = "https://api-adresse.data.gouv.fr/search/csv/"

# Seuils pour considérer un point comme "précis"
SCORE_MIN = 0.55


def clean_address(adresse):
    """Nettoie une adresse (retire prix, surfaces, descriptions qui traînent)."""
    if not adresse:
        return ""
    a = re.sub(r"\d[\d\s]*€.*", "", adresse)
    a = re.sub(r"\d+\s*m[²2].*", "", a)
    a = re.sub(r"\s+", " ", a).strip()
    return a


def has_street(adresse):
    """L'adresse contient-elle un numéro + une voie ? (sinon inutile de géocoder fin)"""
    if not adresse:
        return False
    if re.search(
        r"\d+\s*(bis|ter)?\s*(rue|av|avenue|bd|boulevard|impasse|place|quai|"
        r"all[ée]e|cours|chemin|route|passage|faubourg)",
        adresse,
        re.I,
    ):
        return True
    return bool(re.match(r"^\s*\d+\s", adresse))


def geocode_ban_bulk(rows):
    """rows = [{id, adresse, postcode, city}]. Géocode en masse via l'endpoint CSV."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "adresse", "postcode", "city"])
    for r in rows:
        w.writerow([r["id"], r["adresse"], r["postcode"], r["city"]])
    buf.seek(0)

    resp = requests.post(
        BAN_CSV_URL,
        files={"data": ("in.csv", buf.getvalue(), "text/csv")},
        data=[("columns", "adresse"), ("postcode", "postcode")],
        timeout=120,
    )
    resp.raise_for_status()
    out = {}
    reader = csv.DictReader(io.StringIO(resp.text))
    for row in reader:
        out[row["id"]] = row
    return out


def main(dry_run=False):
    db = json.load(open(DB_PATH))
    deals = db.get("deals", {})

    # Construire la liste à géocoder : deals avec une vraie adresse rue
    rows = []
    for key, deal in deals.items():
        loc = deal.get("localisation", {})
        adr = clean_address(loc.get("adresse", "") or "")
        if not has_street(adr):
            continue
        rows.append({
            "id": key,
            "adresse": adr,
            "postcode": (loc.get("code_postal", "") or "")[:5],
            "city": loc.get("commune", "") or "",
        })

    print(f"Deals avec adresse rue à géocoder : {len(rows)} / {len(deals)}")
    if not rows:
        return

    # BAN limite la taille des batchs ; on découpe par 1000
    results = {}
    for i in range(0, len(rows), 1000):
        chunk = rows[i:i + 1000]
        print(f"  Batch {i // 1000 + 1} ({len(chunk)} adresses)...")
        results.update(geocode_ban_bulk(chunk))

    n_house, n_street, n_loc, n_fail = 0, 0, 0, 0
    for key, r in results.items():
        deal = deals[key]
        loc = deal.setdefault("localisation", {})
        lat = r.get("latitude")
        lng = r.get("longitude")
        score = r.get("result_score")
        gtype = r.get("result_type", "") or ""
        try:
            score_f = float(score) if score else 0.0
        except ValueError:
            score_f = 0.0

        if lat and lng and score_f >= SCORE_MIN:
            loc["_ban_lat"] = float(lat)
            loc["_ban_lng"] = float(lng)
            loc["_geo_score"] = round(score_f, 3)
            loc["_geo_type"] = gtype
            loc["_geo_label"] = r.get("result_label", "")
            if gtype == "housenumber":
                n_house += 1
            elif gtype == "street":
                n_street += 1
            else:
                n_loc += 1
        else:
            n_fail += 1

    print(f"\nBilan BAN :")
    print(f"  ✅ housenumber (numéro exact) : {n_house}")
    print(f"  ◐  street (milieu de rue)     : {n_street}")
    print(f"  ○  locality (approx commune)  : {n_loc}")
    print(f"  ✗  échec / score trop bas     : {n_fail}")

    if dry_run:
        print("\n[dry-run] deals_db.json non modifié.")
        return

    json.dump(db, open(DB_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\nÉcrit dans {DB_PATH}")


if __name__ == "__main__":
    main(dry_run="--dry-run" in sys.argv)

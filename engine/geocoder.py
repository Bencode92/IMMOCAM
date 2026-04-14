"""
Geocodage Nominatim (OpenStreetMap) pour les deals sans coordonnees GPS.
Gratuit, 1 requete/seconde max.
"""
import requests
import json
import time
import re
from pathlib import Path

CACHE_PATH = Path(__file__).parent.parent / "data" / "geocode_cache.json"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
HEADERS = {"User-Agent": "IMMOCAM-Pipeline/1.0 (benoit@immocam.local)"}


def load_cache():
    if CACHE_PATH.exists():
        with open(CACHE_PATH) as f:
            return json.load(f)
    return {}


def save_cache(cache):
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def geocode_address(adresse, code_postal, commune):
    """Geocoder une adresse via Nominatim. Retourne (lat, lng) ou (None, None)."""
    # Construire la query
    parts = []
    if adresse:
        # Nettoyer l'adresse (enlever prix, surfaces qui trainent)
        clean = re.sub(r'\d[\d\s]*€.*', '', adresse).strip()
        clean = re.sub(r'\d+\s*m[²2].*', '', clean).strip()
        clean = re.sub(r'\s+', ' ', clean).strip()
        if clean and len(clean) > 3:
            parts.append(clean)
    if code_postal:
        parts.append(code_postal)
    if commune:
        parts.append(commune)

    if not parts:
        return None, None

    query = ", ".join(parts)

    try:
        resp = requests.get(
            NOMINATIM_URL,
            params={"q": query, "format": "json", "limit": 1, "countrycodes": "fr"},
            headers=HEADERS,
            timeout=10,
        )
        if resp.status_code == 200:
            results = resp.json()
            if results:
                lat = float(results[0]["lat"])
                lng = float(results[0]["lon"])
                return lat, lng

        # Fallback: sans adresse, juste commune + CP
        if adresse and (code_postal or commune):
            fallback_parts = []
            if code_postal:
                fallback_parts.append(code_postal)
            if commune:
                fallback_parts.append(commune)
            fallback_query = ", ".join(fallback_parts)
            resp2 = requests.get(
                NOMINATIM_URL,
                params={"q": fallback_query, "format": "json", "limit": 1, "countrycodes": "fr"},
                headers=HEADERS,
                timeout=10,
            )
            if resp2.status_code == 200:
                results2 = resp2.json()
                if results2:
                    return float(results2[0]["lat"]), float(results2[0]["lon"])

    except Exception as e:
        print(f"    Geocode error: {e}")

    return None, None


def geocode_all_deals(db):
    """Geocoder tous les deals sans coordonnees GPS."""
    cache = load_cache()
    geocoded = 0
    skipped = 0
    failed = 0

    deals = db.get("deals", {})
    total = len(deals)

    for key, deal in deals.items():
        loc = deal.get("localisation", {})

        # Deja geocode?
        if loc.get("latitude") and loc.get("longitude"):
            skipped += 1
            continue

        adresse = loc.get("adresse", "") or ""
        cp = loc.get("code_postal", "") or ""
        commune = loc.get("commune", "") or ""

        # Cle de cache
        cache_key = f"{adresse}|{cp}|{commune}".upper().strip()
        if cache_key in cache:
            cached = cache[cache_key]
            if cached:
                loc["latitude"] = cached[0]
                loc["longitude"] = cached[1]
                geocoded += 1
            else:
                failed += 1
            continue

        # Geocoder
        lat, lng = geocode_address(adresse, cp, commune)
        time.sleep(1.1)  # Respecter la limite 1 req/sec

        if lat and lng:
            loc["latitude"] = lat
            loc["longitude"] = lng
            cache[cache_key] = [lat, lng]
            geocoded += 1
        else:
            cache[cache_key] = None
            failed += 1

        # Sauver le cache regulierement
        if (geocoded + failed) % 20 == 0:
            save_cache(cache)

    save_cache(cache)
    print(f"  Geocodage: {geocoded} geocodes, {skipped} deja OK, {failed} echecs")
    return geocoded

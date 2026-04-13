"""Delta entre scrapes — detecte nouveau, mis a jour, disparu."""
import hashlib
import json
from datetime import datetime


def deal_key(deal):
    """Cle unique d'un deal basee sur adresse normalisee + surface approximative."""
    addr = (deal.get("localisation", {}).get("adresse", "") or "").upper().strip()
    commune = (deal.get("localisation", {}).get("commune", "") or "").upper().strip()
    surface = deal.get("bien", {}).get("surface_m2", 0)
    # Arrondir surface a 10m2 pres pour tolerance
    surface_bucket = round(surface / 10) * 10
    raw = f"{addr}|{commune}|{surface_bucket}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def compute_delta(scraped_deals, db):
    """Compare les deals scrapes vs la DB existante.

    Returns:
        nouveaux: list of deals pas encore dans la DB
        mis_a_jour: list of (deal_key, changes) pour deals existants avec prix change
        disparus: list of deal_keys plus dans le scrape
    """
    today = datetime.now().strftime("%Y-%m-%d")
    existing_keys = set(db.get("deals", {}).keys())
    scraped_keys = {}

    nouveaux = []
    mis_a_jour = []

    for deal in scraped_deals:
        key = deal_key(deal)
        scraped_keys[key] = deal

        if key not in existing_keys:
            # Nouveau deal
            deal["_key"] = key
            deal["_first_seen"] = today
            deal["_last_seen"] = today
            deal["_statut"] = "nouveau"
            deal["_prix_historique"] = [{"date": today, "prix": deal.get("financier", {}).get("prix_affiche", 0)}]
            deal["_sources"] = [deal.get("source", "unknown")]
            deal["_notes"] = ""
            nouveaux.append(deal)
        else:
            # Existe deja — check prix change
            existing = db["deals"][key]
            existing["_last_seen"] = today

            # Ajouter source si nouvelle
            source = deal.get("source", "unknown")
            if source not in existing.get("_sources", []):
                existing.setdefault("_sources", []).append(source)

            new_prix = deal.get("financier", {}).get("prix_affiche", 0)
            old_prix = existing.get("financier", {}).get("prix_affiche", 0)

            if new_prix > 0 and old_prix > 0 and abs(new_prix - old_prix) / old_prix > 0.02:
                existing.setdefault("_prix_historique", []).append({"date": today, "prix": new_prix})
                existing["financier"]["prix_affiche"] = new_prix
                existing["financier"]["prix_m2"] = new_prix / max(existing.get("bien", {}).get("surface_m2", 1), 1)
                mis_a_jour.append((key, {"ancien_prix": old_prix, "nouveau_prix": new_prix, "variation_pct": round((new_prix - old_prix) / old_prix * 100, 1)}))

    # Disparus = dans DB (pas poubelle) mais plus dans scrape
    disparus = []
    for key in existing_keys:
        if key not in scraped_keys:
            deal = db["deals"][key]
            if deal.get("_statut") != "poubelle":
                disparus.append(key)

    return nouveaux, mis_a_jour, disparus


def merge_into_db(db, nouveaux, scorer_fn=None):
    """Insere les nouveaux deals dans la DB et les score."""
    for deal in nouveaux:
        key = deal.pop("_key")
        if scorer_fn:
            deal["scoring"] = scorer_fn(deal)
        db["deals"][key] = deal

    # Update meta
    statuts = {}
    for d in db["deals"].values():
        s = d.get("_statut", "nouveau")
        statuts[s] = statuts.get(s, 0) + 1
    db["meta"]["total_deals"] = len(db["deals"])
    db["meta"]["par_statut"] = statuts
    db["meta"]["last_scrape"] = datetime.now().isoformat()

    return db

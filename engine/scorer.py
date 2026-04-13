"""Score un bien contre le referentiel bureaux."""
import json
from pathlib import Path


def load_referentiel(path=None):
    if path is None:
        path = Path(__file__).parent.parent / "data" / "referentiel_bureaux.json"
    with open(path) as f:
        return json.load(f)


def get_segment(surface):
    if surface < 50:
        return "S1_boutique"
    elif surface < 150:
        return "S2_local"
    elif surface < 500:
        return "S3_plateau"
    else:
        return "S4_immeuble"


def find_commune_ref(referentiel, code_insee):
    """Trouve la commune dans le referentiel par code INSEE."""
    communes = referentiel.get("referentiel_bureaux_idf", {}).get("communes", [])
    for c in communes:
        if c.get("code_insee") == code_insee:
            return c
    return None


def score_deal(deal, ref_commune):
    """Score un deal contre sa commune de reference. Retourne un dict scoring."""
    if not ref_commune:
        return {"score_global": 0, "grade": "?", "alertes": ["Commune non trouvee dans le referentiel"]}

    surface = deal.get("bien", {}).get("surface_m2", 0)
    segment = get_segment(surface)
    seg_data = ref_commune.get("prix_vente", {}).get(segment, {})
    loyers = ref_commune.get("loyers", {})

    prix_m2 = deal.get("financier", {}).get("prix_m2", 0)
    loyer_actuel = deal.get("locatif", {}).get("loyer_m2_an", 0)

    scores = {}
    alertes = []

    # 1) Prix vs marche (30%)
    median = seg_data.get("median", 0)
    p25 = seg_data.get("p25", 0)
    p75 = seg_data.get("p75", 0)
    if median > 0 and prix_m2 > 0:
        ecart = (prix_m2 - median) / median * 100
        if prix_m2 <= p25:
            scores["prix"] = 95
        elif prix_m2 <= median:
            scores["prix"] = 70 + 25 * (median - prix_m2) / max(median - p25, 1)
        elif prix_m2 <= p75:
            scores["prix"] = 30 + 40 * (p75 - prix_m2) / max(p75 - median, 1)
        else:
            scores["prix"] = max(0, 30 - (prix_m2 - p75) / p75 * 100)
    else:
        scores["prix"] = 50
        ecart = None

    # 2) Loyer vs potentiel (25%)
    cushman_2de = loyers.get("cushman_2de_main_m2_an", 0)
    if loyer_actuel > 0 and cushman_2de > 0:
        ratio = loyer_actuel / cushman_2de
        if ratio >= 0.8:
            scores["loyer"] = 80
        elif ratio >= 0.5:
            scores["loyer"] = 50 + 30 * (ratio - 0.5) / 0.3
        else:
            scores["loyer"] = 90  # tres sous-loue = potentiel de reversion
            alertes.append(f"Sous-loue a {ratio*100:.0f}% du marche -> potentiel reversion")
    else:
        scores["loyer"] = 50

    # 3) Rendement (20%)
    yield_zone = loyers.get("yield_secondaire_pct", 7)
    yield_actuel = (loyer_actuel / prix_m2 * 100) if prix_m2 > 0 and loyer_actuel > 0 else 0
    if yield_actuel > 0:
        diff = yield_actuel - yield_zone
        scores["rendement"] = min(100, max(0, 50 + diff * 15))
    else:
        scores["rendement"] = 50

    # 4) Risque (15%)
    dpe = deal.get("bien", {}).get("dpe", "")
    scores["risque"] = 70
    if dpe in ("F", "G"):
        scores["risque"] = 20
        alertes.append(f"DPE {dpe} -> travaux lourds obligatoires")
    elif dpe in ("D", "E"):
        scores["risque"] = 50
        alertes.append(f"DPE {dpe} -> travaux a prevoir")
    elif dpe in ("A", "B", "C"):
        scores["risque"] = 90

    vacance = loyers.get("taux_vacance_pct", 0)
    if vacance and vacance > 15:
        scores["risque"] = max(scores["risque"] - 20, 0)
        alertes.append(f"Zone vacance elevee: {vacance}%")

    # 5) Qualite annonce (10%)
    checks = ["adresse", "surface_m2", "dpe", "prix_affiche"]
    present = sum(1 for c in checks if deal.get("bien", {}).get(c) or deal.get("financier", {}).get(c) or deal.get("localisation", {}).get(c))
    scores["qualite"] = min(100, present / len(checks) * 100)

    # Score global
    weights = {"prix": 0.30, "loyer": 0.25, "rendement": 0.20, "risque": 0.15, "qualite": 0.10}
    score_global = sum(scores.get(k, 50) * w for k, w in weights.items())
    score_global = round(score_global)

    if score_global >= 80:
        grade = "A"
    elif score_global >= 60:
        grade = "B"
    elif score_global >= 40:
        grade = "C"
    else:
        grade = "D"

    return {
        "prix_vs_marche_pct": round(ecart, 1) if ecart is not None else None,
        "loyer_vs_cushman_pct": round((loyer_actuel / cushman_2de - 1) * 100, 1) if cushman_2de and loyer_actuel else None,
        "yield_actuel_pct": round(yield_actuel, 2) if yield_actuel else None,
        "scores_detail": scores,
        "score_global": score_global,
        "grade": grade,
        "alertes": alertes,
    }

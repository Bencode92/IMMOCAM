"""
Enrichissement et note « événementiel / bureaux » d'une annonce d'hôtel particulier.

- commune -> code INSEE (Paris par arrondissement, sinon géocodeur IGN avec cache)
- prix au m² comparé au référentiel DVF (grandes maisons et immeubles commerciaux de la commune)
- usage actuel deviné depuis le texte (bureaux / mixte / commercial vs habitation)
- mots-clés utiles (jardin, verrière, sous-sol…) et alertes (hameau, villa privée, copropriété…)
- secteur de compensation renforcée si une adresse précise est connue
"""
import json
import re
import unicodedata
from pathlib import Path

import requests

DATA = Path(__file__).resolve().parent.parent / "data"
GEOCACHE = DATA / "hp_geocache.json"


def norm(s):
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()


ATOUTS = {  # mot-clé (sans accent) -> (libellé, points)
    r"jardin": ("Jardin", 6), r"\bcour\b|cour pavee|cour privee": ("Cour", 5), r"terrasse|rooftop|toit terrasse": ("Terrasse", 3),
    r"verriere|atelier|loft": ("Verrière / atelier", 5), r"hauteur(s)? sous plafond|double hauteur|grands volumes": ("Volumes", 4),
    r"reception|salons? en enfilade|salle de bal|enfilade": ("Réception", 4), r"sous-sol|sous sol|caves?": ("Sous-sol", 3),
    r"porte cochere|acces vehicule|parking|garage|stationnement": ("Accès / parking", 4), r"ascenseur": ("Ascenseur", 2),
    r"independant|entierement independant|immeuble entier": ("Indépendant", 4), r"plusieurs entrees|deux entrees|entree independante": ("Entrées séparées", 3),
}
ALERTES = {
    r"hameau|villa privee|voie privee|impasse privee|allee privee": "Voie privée / hameau : règlement à lire",
    r"copropriete": "Copropriété : activités autorisées ?",
    r"\bappartement|\bduplex\b|\btriplex\b|dernier etage": "Appartement : copropriété, activités autorisées ?",
    r"dpe\W*[fg]\b|\(f\)|\(g\)": "DPE F ou G",
    r"travaux a prevoir|a renover|a restaurer|rehabiliter": "Travaux importants",
    r"monument historique|classe mh|inscrit (a l'inventaire|mh)": "Monument historique",
}
USAGE_PRO = r"commercialite|(a )?usage (de |a usage de )?bureaux?|usage mixte|usage professionnel|usage commercial|local commercial|locaux commerciaux|immeuble de bureaux|siege social|etablissement recevant du public|\berp\b|ambassade|consulat"


PARIS_OUEST = {"75107", "75108", "75115", "75116", "75117"}
BANLIEUE_OUEST = {"92051", "92012", "92044", "92040", "92064", "92073", "92063", "92033", "92076", "92047", "92077",
                  "92072", "92048", "92022", "92062", "92026", "92035", "92009", "92004", "92024", "92050",
                  "78146", "78190", "78650", "78481", "78551", "78358", "78350", "78372", "78092", "78126", "78646", "78158"}


def secteur(insee):
    return "Paris ouest" if insee in PARIS_OUEST else "Neuilly" if insee == "92051" else "Banlieue ouest" if insee in BANLIEUE_OUEST else \
        "Paris (autre)" if insee.startswith("75") else "Hors secteur"


def load_ref():
    p = DATA / "dvf_ref_hp.json"
    return json.loads(p.read_text())["communes"] if p.exists() else {}


def load_cache():
    return json.loads(GEOCACHE.read_text()) if GEOCACHE.exists() else {}


def insee_of(x, cache):
    cp = x.get("code_postal") or ""
    if re.fullmatch(r"750\d\d", cp):
        return "751" + cp[3:]
    nom = (x.get("commune") or "").split(",")[0].strip()
    if not nom:
        return ""
    if nom in cache:
        return cache[nom]
    code = ""
    try:
        r = requests.get("https://data.geopf.fr/geocodage/search", timeout=20,
                         params={"q": nom, "type": "municipality", "limit": 1})
        f = (r.json().get("features") or [None])[0]
        if f and f["properties"].get("score", 0) > 0.6:
            code = f["properties"].get("citycode", "")
    except (requests.RequestException, ValueError):
        pass
    cache[nom] = code
    return code


def in_ring(r, x, y):
    c, j = False, len(r) - 1
    for i in range(len(r)):
        (x1, y1), (x2, y2) = r[i], r[j]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
        j = i
    return c


def scr_at(lon, lat, zonages):
    for f in (zonages or {}).get("features", []):
        if "renforc" not in norm(f["properties"].get("type_reglementation") or f["properties"].get("type")):
            continue
        g = f["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        if any(in_ring(p[0], lon, lat) and not any(in_ring(h, lon, lat) for h in p[1:]) for p in polys):
            return True
    return False


def geocode_adresse(adr, cache):
    key = "adr:" + adr
    if key in cache:
        return cache[key]
    pt = None
    try:
        r = requests.get("https://data.geopf.fr/geocodage/search", timeout=20, params={"q": adr, "limit": 1})
        f = (r.json().get("features") or [None])[0]
        if f and f["properties"].get("score", 0) > 0.7 and f["properties"].get("type") in ("housenumber", "street"):
            pt = f["geometry"]["coordinates"]
    except (requests.RequestException, ValueError):
        pass
    cache[key] = pt
    return pt


def enrich(x, ref, cache, zonages=None):
    texte = norm(" ".join([x.get("titre", ""), x.get("description", ""), " ".join(x.get("extra", {}).get("criteres", []))]))
    e = {"insee": insee_of(x, cache)}
    e["secteur"] = secteur(e["insee"])
    r = ref.get(e["insee"]) or {}
    e["commune_ref"] = r.get("nom", "")
    s, p = x.get("surface") or 0, x.get("prix") or 0
    e["prix_m2"] = round(p / s) if s and p else None
    usage_pro = bool(re.search(USAGE_PRO, texte)) or x["source"] in ("bnppre", "cbre", "jll") or "commerc" in norm(x.get("type"))
    paris = e["insee"].startswith("75")
    e["usage"] = "bureaux / commercial (à vérifier)" if usage_pro else ("habitation : compensation à Paris" if paris else "habitation")
    base = (r.get("commerces") if usage_pro else r.get("maisons")) or r.get("maisons")
    e["dvf_med"] = base["med"] if base else None
    e["dvf_n"] = base["n"] if base else 0
    mise_a_prix = x.get("extra", {}).get("mise_a_prix")  # enchère : prix de départ, pas comparable
    e["ecart_dvf"] = round(e["prix_m2"] / e["dvf_med"] - 1, 3) if e["prix_m2"] and e["dvf_med"] and not mise_a_prix else None
    e["atouts"] = [lib for k, (lib, _) in ATOUTS.items() if re.search(k, texte)]
    e["alertes"] = [lib for k, lib in ALERTES.items() if re.search(k, texte)]
    if x.get("dpe") in ("F", "G") and "DPE F ou G" not in e["alertes"]:
        e["alertes"].append("DPE F ou G")
    e["scr"] = None
    if x.get("adresse"):
        pt = geocode_adresse(f"{x['adresse']} {x.get('code_postal', '')} {x.get('commune', '')}", cache)
        if pt and zonages:
            e["scr"] = scr_at(pt[0], pt[1], zonages)
    # Note sur 100
    sc = 25 if s >= 600 else 18 if s >= 400 else 10 if s >= 300 else 3
    if e["ecart_dvf"] is None:
        sc += 10
    else:
        sc += 25 if e["ecart_dvf"] <= -0.2 else 18 if e["ecart_dvf"] <= 0 else 10 if e["ecart_dvf"] <= 0.2 else 3
    sc += 30 if usage_pro else 0  # critère n°1 : pas de compensation
    sc += min(30, sum(pts for k, (_, pts) in ATOUTS.items() if re.search(k, texte)))
    sc -= 10 * sum(1 for a in e["alertes"] if a.startswith(("Voie", "Copro", "Appart")))
    sc -= 3 * sum(1 for a in e["alertes"] if not a.startswith(("Voie", "Copro", "Appart")))
    e["score"] = max(0, min(100, sc))
    return e

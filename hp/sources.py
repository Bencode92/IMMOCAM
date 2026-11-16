"""
Collecteurs « hôtels particuliers » (événementiel / bureaux).

Chaque collecteur renvoie des annonces au format commun :
  id, source, url, titre, type, commune, code_postal, adresse, surface, prix, description, dpe, extra
Les sites qui bloquent les robots (Belles Demeures, Figaro, CBRE, Leboncoin) passent par les alertes e-mail.
"""
import json
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scrapers"))

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36",
      "Accept-Language": "fr-FR,fr;q=0.9"}


def num(s):
    s = re.sub(r"[^\d,.]", "", s or "").replace(",", ".")
    try:
        return float(s.replace(".", "", s.count(".") - 1)) if s else 0.0
    except ValueError:
        return 0.0


def cp_from_ville(ville):
    m = re.search(r"paris\s*(\d{1,2})", ville or "", re.I)
    return f"750{int(m.group(1)):02d}" if m else ""


BARNES = "https://www.barnes-international.com/fr/vente/france/"


SURFACE_MIN = 500


def dans_perimetre(x):
    """Paris ou Neuilly-sur-Seine, et au moins 500 m² (surface inconnue gardée : à vérifier)."""
    lieu = (x.get("code_postal") or "").startswith("75") or "neuilly" in (x.get("commune") or "").lower()
    return lieu and not (x.get("surface") and x["surface"] < SURFACE_MIN)


class Barnes:
    name = "barnes"
    # Périmètre : Paris intra-muros + Neuilly (filtré ensuite par dans_perimetre)
    LISTES = [BARNES + p + ".html" for p in (
        "paris/hotel-particulier", "paris/maison", "hauts-de-seine/hotel-particulier", "neuilly-sur-seine/maison")]
    SURFACE_MIN = 500

    def collect(self, known_ids=frozenset()):
        out, ids = [], set()
        for url in self.LISTES:
            r = requests.get(url, headers=UA, timeout=40)
            if r.status_code != 200:
                continue
            time.sleep(1.0)
            soup = BeautifulSoup(r.text, "html.parser")
            for art in soup.select("article[id^=property-]"):
                a = art.select_one("a.bc-015-content-link")
                if not a:
                    continue
                ref = art["id"].replace("property-", "")
                titre = a.get("title", "").replace("À vendre ", "")
                ville = (a.select_one("p.mb-2") or a).get_text(" ", strip=True)
                crit = [s.get_text(strip=True) for s in a.select(".bc-015-criteria span")]
                surface = next((num(c) for c in crit if "m²" in c), 0.0)
                prix = num((a.select_one(".bc-015-prix strong") or a).get_text())
                if ref in ids or (surface and surface < self.SURFACE_MIN):
                    continue
                ids.add(ref)
                out.append({"id": f"barnes-{ref}", "source": self.name, "url": a["href"], "titre": titre,
                            "type": "hotel particulier" if "particulier" in titre.lower() else "maison", "commune": ville, "code_postal": cp_from_ville(ville),
                            "adresse": "", "surface": surface, "prix": prix, "description": "", "dpe": "",
                            "extra": {"criteres": crit}})
        out = [x for x in out if dans_perimetre(x)]
        # Fiche détaillée uniquement pour les nouvelles annonces (description, DPE)
        for x in out:
            if x["id"] in known_ids:
                continue
            try:
                h = requests.get(x["url"], headers=UA, timeout=40).text
                for blob in re.findall(r'<script type="application/ld\+json">(.*?)</script>', h, re.S):
                    try:
                        j = json.loads(blob)
                    except ValueError:
                        continue
                    if j.get("@type") == "RealEstateListing":
                        x["titre"] = j.get("name") or x["titre"]
                        x["description"] = (j.get("description") or "")[:4000]
                m = re.search(r"DPE\s*:?\s*[\d.,]*\s*\(?([A-G])\)?", re.sub(r"<[^>]+>", " ", h))
                x["dpe"] = m.group(1) if m else ""
                time.sleep(1.0)
            except requests.RequestException:
                pass
        return out


class LicitorHP:
    """Enchères judiciaires : maisons / propriétés, immeubles, locaux commerciaux (Paris, Neuilly)."""
    name = "licitor"
    PAGES = ["/ventes-aux-encheres-immobilieres/paris-et-ile-de-france/maison-pavillon-propriete.html",
             "/ventes-aux-encheres-immobilieres/paris-et-ile-de-france/immeuble-residentiel.html",
             "/ventes-aux-encheres-immobilieres/paris-et-ile-de-france/local-a-usage-de-commerce.html",
             "/ventes-aux-encheres-immobilieres/paris-et-ile-de-france/autres-biens-immobiliers.html"]

    def collect(self, known_ids=frozenset()):
        from licitor import LicitorScraper
        lic = LicitorScraper()
        out, seen = [], set()
        for path in self.PAGES:
            for page in range(1, 6):
                url = lic.BASE + path + (f"?p={page}" if page > 1 else "")
                r = requests.get(url, headers=lic.HEADERS, timeout=40)
                if r.status_code != 200:
                    break
                items = lic._parse_listing_page(r.text, "75")
                if not items:
                    break
                fresh = 0
                for it in items:
                    parts = [p.strip() for p in it.get("description", "").split("|")]
                    dept = parts[0] if parts and parts[0].isdigit() else it.get("_dept_code")
                    if it["_id"] in seen or dept not in ("75", "92"):
                        continue
                    seen.add(it["_id"])
                    fresh += 1
                    ville = parts[1] if len(parts) > 1 else it.get("ville", "")
                    out.append({"id": f"licitor-{it['_id']}", "source": self.name, "url": it["url"],
                                "titre": f"Enchère – {it.get('_type', '').strip()} {ville}".strip(),
                                "type": "enchere " + it.get("_type", ""), "commune": ville,
                                "code_postal": cp_from_ville(ville),
                                "adresse": "", "surface": it.get("surface", 0), "prix": it.get("prix", 0),
                                "description": it.get("description", ""), "dpe": "",
                                "extra": {"audience": it.get("date_audience", ""), "mise_a_prix": True}})
                if not fresh:
                    break
                time.sleep(1.0)
        return out


SOURCES = {"barnes": Barnes, "licitor": LicitorHP}

"""
Scraper Geolocaux.com — API interne REST.
POST /api/annonces/paginated + /api/annonces/markers
"""
import requests
import json
import time
from base_scraper import BaseScraper


class GeolocauxScraper(BaseScraper):
    name = "geolocaux"
    API = "https://www.geolocaux.com/api/annonces"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Origin": "https://www.geolocaux.com",
        "Referer": "https://www.geolocaux.com/vente/bureau/paris-75/",
    }

    # Codes localisation Geolocaux: D + code dept
    DEPT_CODES = {
        "75": "D75", "92": "D92", "93": "D93", "94": "D94",
        "78": "D78", "91": "D91", "95": "D95", "77": "D77",
    }

    def scrape(self, filters=None):
        filters = filters or {}
        depts = filters.get("departements", ["75", "92"])
        surface_min = filters.get("surface_min", 300)
        surface_max = filters.get("surface_max", 700)
        prix_max = filters.get("prix_max", 5000000)

        all_results = []
        locs = [self.DEPT_CODES[d] for d in depts if d in self.DEPT_CODES]

        print(f"  Geolocaux: API /annonces/paginated (vente bureaux)...")

        page = 1
        total = None

        while True:
            payload = {
                "type": "VEN",         # Vente (pas LOC = location)
                "nature": "BUR",       # Bureaux
                "localisations": locs,
                "tarif_mode": "GLOBAL",
                "lignes": [],
                "lignes_radius": 500,
                "tags": [],
                "activites": [],
                "merge_loccow": True,
                "page": page,
                "limit": 40,
                "sort": "NP",          # Nouveautés en premier
                "viewport": None,
            }

            try:
                resp = requests.post(
                    f"{self.API}/paginated",
                    headers=self.HEADERS,
                    json=payload,
                    timeout=20,
                )

                if resp.status_code != 200:
                    print(f"    Page {page}: HTTP {resp.status_code}")
                    break

                data = resp.json()
                annonces = data.get("annonces", [])
                if total is None:
                    total = data.get("count", 0)
                    print(f"    Total: {total} annonces")

                if not annonces:
                    break

                for a in annonces:
                    surf = a.get("surface", 0) or 0
                    prix_global = a.get("tarif_mensuel_ou_global", 0) or 0

                    if surf < surface_min or surf > surface_max:
                        continue
                    if prix_global > prix_max or prix_global <= 0:
                        continue

                    # Extraire ville/CP du titre ou URL
                    titre = a.get("titre", "")
                    url_path = a.get("url", "")
                    commune = ""
                    cp = ""

                    # L'URL contient souvent la ville: /annonce/bureaux-paris-3-700264.html
                    import re
                    cp_match = re.search(r"-(\d{5})", url_path)
                    if cp_match:
                        cp = cp_match.group(1)

                    deal = self.to_standard({
                        "url": "https://www.geolocaux.com" + url_path if url_path else "",
                        "commune": commune or titre,
                        "code_postal": cp,
                        "departement": cp[:2] if cp else "",
                        "surface": surf,
                        "prix": prix_global,
                        "titre": titre,
                        "description": a.get("accroche", ""),
                        "nb_photos": len(a.get("photos", [])),
                        "agent": a.get("societe", ""),
                    })
                    all_results.append(deal)

                page += 1
                time.sleep(1)

                # Stop apres toutes les pages
                if page * 40 >= (total or 0):
                    break

            except Exception as e:
                print(f"    Page {page}: {e}")
                break

        print(f"  Geolocaux: {len(all_results)} biens (sur {total or '?'} total)")
        self.results = all_results
        return all_results


if __name__ == "__main__":
    s = GeolocauxScraper()
    results = s.scrape({
        "departements": ["75", "92"],
        "surface_min": 300,
        "surface_max": 700,
    })
    print(f"\n{len(results)} biens")
    for r in results[:5]:
        print(f"  {r['bien']['surface_m2']}m2 | {r['financier']['prix_affiche']/1e6:.2f}M | {r['annonce']['titre'][:60]}")

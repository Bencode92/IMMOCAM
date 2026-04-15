"""
Scraper Espaces Atypiques — biens atypiques bureaux/lofts Paris + 92.

Site simple en HTML serveur, pas de protection anti-bot.
Volume faible (~10 biens) mais biens uniques/premium.
"""
import requests
import json
import re
import time
from base_scraper import BaseScraper


class EspacesAtypiquesScraper(BaseScraper):
    name = "espaces-atypiques"
    BASE = "https://www.espaces-atypiques.com"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9",
    }

    # pl=511 (Paris 75), pl=528 (Hauts-de-Seine 92)
    # type=673 (Bureau/local commercial)
    SEARCH_URL = "/ventes/?pl={zones}&type=673&pmin=&pmax={pmax}&smin=&smax=&critere1=&critere2=&s=&order=ddesc&map=&pt=vente"

    ZONE_CODES = {
        "75": "511",
        "92": "528",
    }

    def scrape(self, filters=None):
        filters = filters or {}
        depts = filters.get("departements", ["75", "92"])
        prix_max = filters.get("prix_max", 5000000)

        zones = ",".join(self.ZONE_CODES[d] for d in depts if d in self.ZONE_CODES)
        url = self.BASE + self.SEARCH_URL.format(zones=zones, pmax=prix_max)

        print(f"  EspacesAtypiques: scraping bureaux/locaux 75+92...")

        all_results = []
        page = 1

        while page <= 10:
            page_url = url if page == 1 else url + f"&pg={page}"
            try:
                resp = requests.get(page_url, headers=self.HEADERS, timeout=30)
                if resp.status_code != 200:
                    break

                listings = self._parse_page(resp.text, depts, filters)
                if not listings:
                    break

                all_results.extend(listings)
                print(f"    Page {page}: {len(listings)} biens")

                # Check if there's a next page
                if f"pg={page+1}" not in resp.text and 'class="next"' not in resp.text:
                    break

                page += 1
                time.sleep(1.5)

            except Exception as e:
                print(f"    Erreur page {page}: {e}")
                break

        print(f"  EspacesAtypiques: {len(all_results)} biens au total")
        self.results = all_results
        return all_results

    def _parse_page(self, html, depts, filters):
        results = []
        surface_min = filters.get("surface_min", 0)
        surface_max = filters.get("surface_max", 99999)
        prix_max = filters.get("prix_max", 5000000)

        # Trouver les liens d'annonces (URLs absolues ou relatives)
        listing_urls = re.findall(r'href="((?:https://www\.espaces-atypiques\.com)?/ventes/\d{5}-[^"]+/)"', html)
        # Normaliser en chemins relatifs
        listing_urls = list(set(u.replace("https://www.espaces-atypiques.com", "") for u in listing_urls))

        for path in listing_urls:
            try:
                # Extraire CP et ville depuis l'URL
                url_match = re.match(r'/ventes/(\d{5})-([^/]+)', path)
                if not url_match:
                    continue
                cp = url_match.group(1)
                dept = cp[:2]

                if dept not in depts:
                    continue

                # Fetch la page de détail
                detail_url = self.BASE + path
                resp = requests.get(detail_url, headers=self.HEADERS, timeout=20)
                if resp.status_code != 200:
                    continue

                detail = resp.text

                # Prix
                prix = 0
                prix_match = re.search(r'([\d\s]+)\s*€', detail)
                if prix_match:
                    prix = int(prix_match.group(1).replace(" ", "").replace("\xa0", ""))
                if prix <= 0 or prix > prix_max:
                    continue

                # Surface
                surface = 0
                surf_match = re.search(r'([\d.,]+)\s*m[²2]', detail)
                if surf_match:
                    surface = float(surf_match.group(1).replace(",", "."))

                # Titre
                titre = ""
                title_match = re.search(r'<h1[^>]*>(.*?)</h1>', detail, re.DOTALL)
                if title_match:
                    titre = re.sub(r'<[^>]+>', '', title_match.group(1)).strip()

                # Commune
                commune = ""
                ville_slug = url_match.group(2).split("-")[0]
                commune = ville_slug.replace("-", " ").title()
                if cp.startswith("75"):
                    arr = int(cp[3:])
                    if 1 <= arr <= 20:
                        commune = f"Paris {arr}e"

                deal = self.to_standard({
                    "url": detail_url,
                    "adresse": "",
                    "code_postal": cp,
                    "commune": commune,
                    "departement": dept,
                    "surface": surface,
                    "prix": prix,
                    "titre": titre or f"Bien atypique {int(surface)}m² {commune}",
                    "description": titre,
                })
                results.append(deal)
                time.sleep(1.0)

            except Exception as e:
                print(f"    Detail error: {e}")
                continue

        return results


if __name__ == "__main__":
    scraper = EspacesAtypiquesScraper()
    results = scraper.scrape({
        "departements": ["75", "92"],
        "prix_max": 5000000,
    })
    print(f"\n{len(results)} biens scraped")
    for r in results[:5]:
        loc = r["localisation"]
        fin = r["financier"]
        print(f"  {r['bien']['surface_m2']:.0f}m² — {loc['commune']} — {fin['prix_affiche']/1e6:.2f}M€")
        print(f"    {r['annonce']['titre']}")

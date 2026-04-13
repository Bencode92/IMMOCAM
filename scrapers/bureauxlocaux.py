"""
Scraper BureauxLocaux.com — leader bureaux/commerces France.

Le site embed les données en JSON dans la page. On extrait ce JSON directement.
Nécessite requests + bs4 (pas de headless browser pour l'instant).
Si le site bloque, passer en Playwright.
"""
import requests
import json
import re
import time
from base_scraper import BaseScraper


class BureauxLocauxScraper(BaseScraper):
    name = "bureauxlocaux"
    BASE = "https://www.bureauxlocaux.com"
    SEARCH = "/immobilier-d-entreprise/annonces/{zone}/vente-bureaux"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9",
    }

    # Zones IDF
    ZONES = {
        "75": "paris-75",
        "92": "hauts-de-seine-92",
        "93": "seine-saint-denis-93",
        "94": "val-de-marne-94",
        "78": "yvelines-78",
        "91": "essonne-91",
        "95": "val-d-oise-95",
        "77": "seine-et-marne-77",
    }

    def scrape(self, filters=None):
        """Scrape les annonces bureaux vente IDF."""
        filters = filters or {}
        depts = filters.get("departements", ["75", "92", "93", "94"])
        surface_min = filters.get("surface_min", 300)
        surface_max = filters.get("surface_max", 700)
        prix_max = filters.get("prix_max", 5000000)

        all_results = []

        for dept in depts:
            zone = self.ZONES.get(dept)
            if not zone:
                continue

            print(f"  BureauxLocaux: scraping {zone}...")
            url = self.BASE + self.SEARCH.format(zone=zone)
            params = {
                "surface_min": surface_min,
                "surface_max": surface_max,
                "budget_max": prix_max,
            }

            try:
                resp = requests.get(url, headers=self.HEADERS, params=params, timeout=30)
                if resp.status_code != 200:
                    print(f"    HTTP {resp.status_code}")
                    continue

                # Extraire le JSON embarque dans la page
                listings = self._extract_json(resp.text)
                print(f"    {len(listings)} annonces trouvees")

                for raw in listings:
                    deal = self._parse_listing(raw, dept)
                    if deal:
                        all_results.append(deal)

            except Exception as e:
                print(f"    Erreur: {e}")

            time.sleep(2)  # Rate limiting respectueux

        print(f"  BureauxLocaux: {len(all_results)} biens au total")
        self.results = all_results
        return all_results

    def _extract_json(self, html):
        """Extraire les données JSON des annonces depuis le HTML."""
        listings = []

        # Méthode 1: chercher le JSON dans les scripts
        patterns = [
            r'"items"\s*:\s*(\[.*?\])\s*[,}]',
            r'"results"\s*:\s*\{[^}]*"items"\s*:\s*(\[.*?\])',
            r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});',
            r'window\.__data__\s*=\s*(\{.*?\});',
        ]

        for pattern in patterns:
            match = re.search(pattern, html, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(1))
                    if isinstance(data, list):
                        listings = data
                    elif isinstance(data, dict):
                        # Chercher les items dans la structure
                        for key in ("items", "results", "listings", "annonces"):
                            if key in data:
                                items = data[key]
                                if isinstance(items, dict) and "items" in items:
                                    listings = items["items"]
                                elif isinstance(items, list):
                                    listings = items
                                break
                    if listings:
                        break
                except json.JSONDecodeError:
                    continue

        # Méthode 2: chercher des blocs JSON-LD
        if not listings:
            ld_matches = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
            for ld in ld_matches:
                try:
                    data = json.loads(ld)
                    if isinstance(data, list):
                        listings.extend(data)
                    elif isinstance(data, dict) and data.get("@type") in ("Product", "RealEstateListing", "Offer"):
                        listings.append(data)
                except json.JSONDecodeError:
                    continue

        return listings

    def _parse_listing(self, raw, dept):
        """Convertir un listing brut en format standard."""
        try:
            prix = float(raw.get("sale_price") or raw.get("price") or 0)
            surface = float(raw.get("total_surface") or raw.get("surface") or 0)
            if prix <= 0 or surface <= 0:
                return None

            city = raw.get("city") or raw.get("commune") or ""
            street = raw.get("street") or raw.get("address") or ""
            zipcode = raw.get("zip_code") or raw.get("postal_code") or ""

            # DPE
            dpe = ""
            chars = raw.get("characteristics_json") or raw.get("characteristics") or {}
            if isinstance(chars, str):
                try:
                    chars = json.loads(chars)
                except:
                    chars = {}
            dpe = chars.get("dpe") or chars.get("energy_class") or ""

            # Services
            services = raw.get("services_json") or raw.get("services") or {}
            if isinstance(services, str):
                try:
                    services = json.loads(services)
                except:
                    services = {}

            url = raw.get("url") or ""
            if url and not url.startswith("http"):
                url = self.BASE + url

            return self.to_standard({
                "url": url,
                "adresse": street,
                "code_postal": zipcode,
                "commune": city,
                "departement": dept,
                "surface": surface,
                "prix": prix,
                "dpe": dpe.upper() if dpe else "",
                "titre": raw.get("label") or raw.get("title") or f"Bureaux {surface}m² — {city}",
                "description": raw.get("description") or "",
                "nb_photos": len(raw.get("images", {}).get("normal", [])) if isinstance(raw.get("images"), dict) else 0,
                "parking": services.get("parking") or services.get("nb_parking") or 0,
                "ascenseur": services.get("lift") or services.get("ascenseur"),
                "clim": services.get("air_conditioning") or services.get("climatisation"),
                "annee": chars.get("construction_year") or chars.get("annee_construction"),
            })
        except Exception as e:
            print(f"    Parse error: {e}")
            return None


if __name__ == "__main__":
    scraper = BureauxLocauxScraper()
    results = scraper.scrape({
        "departements": ["75", "92"],
        "surface_min": 300,
        "surface_max": 700,
        "prix_max": 5000000,
    })
    print(f"\n{len(results)} biens scraped")
    for r in results[:3]:
        print(json.dumps(r, indent=2, ensure_ascii=False)[:500])

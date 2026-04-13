"""
Scraper Geolocaux.com — plateforme avec API interne JSON.

Le site utilise une API REST interne qu'on peut appeler directement.
"""
import requests
import json
import time
from base_scraper import BaseScraper


class GeolocauxScraper(BaseScraper):
    name = "geolocaux"
    # L'API interne est souvent sur un sous-domaine ou path /api/
    API_BASE = "https://www.geolocaux.com"
    SEARCH_URL = "/api/search"  # A ajuster apres inspection DevTools
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36",
        "Accept": "application/json",
        "Accept-Language": "fr-FR,fr;q=0.9",
        "Referer": "https://www.geolocaux.com/vente/bureau/paris-75/",
    }

    def scrape(self, filters=None):
        """Scrape via API interne Geolocaux."""
        filters = filters or {}
        surface_min = filters.get("surface_min", 300)
        surface_max = filters.get("surface_max", 700)
        prix_max = filters.get("prix_max", 5000000)

        # Essayer plusieurs endpoints possibles
        endpoints = [
            "/api/v1/listings",
            "/api/search",
            "/api/annonces",
            "/search.json",
        ]

        all_results = []
        params = {
            "type": "bureau",
            "transaction": "vente",
            "region": "ile-de-france",
            "surface_min": surface_min,
            "surface_max": surface_max,
            "prix_max": prix_max,
            "limit": 100,
            "offset": 0,
        }

        print(f"  Geolocaux: recherche bureaux IDF {surface_min}-{surface_max}m²...")

        # Methode 1: API JSON directe
        for endpoint in endpoints:
            try:
                url = self.API_BASE + endpoint
                resp = requests.get(url, headers=self.HEADERS, params=params, timeout=15)
                if resp.status_code == 200:
                    data = resp.json()
                    listings = data if isinstance(data, list) else data.get("results", data.get("listings", data.get("items", [])))
                    if listings:
                        print(f"    API {endpoint}: {len(listings)} annonces")
                        for raw in listings:
                            deal = self._parse(raw)
                            if deal:
                                all_results.append(deal)
                        break
            except Exception as e:
                continue

        # Methode 2: scraping HTML si API echoue
        if not all_results:
            print("    API non trouvee, fallback HTML...")
            all_results = self._scrape_html(filters)

        print(f"  Geolocaux: {len(all_results)} biens")
        self.results = all_results
        return all_results

    def _scrape_html(self, filters):
        """Fallback: scraper les pages HTML."""
        results = []
        zones = [
            "paris-75", "hauts-de-seine-92", "seine-saint-denis-93", "val-de-marne-94",
        ]

        for zone in zones:
            url = f"{self.API_BASE}/vente/bureau/{zone}/"
            try:
                resp = requests.get(url, headers={
                    "User-Agent": self.HEADERS["User-Agent"],
                    "Accept": "text/html",
                }, timeout=30)

                if resp.status_code != 200:
                    continue

                # Chercher du JSON embarque
                import re
                json_matches = re.findall(r'(?:window\.__data__|window\.__INITIAL_STATE__|var\s+listings\s*=)\s*(\{.*?\});', resp.text, re.DOTALL)
                for match in json_matches:
                    try:
                        data = json.loads(match)
                        items = data.get("listings", data.get("items", data.get("results", [])))
                        if isinstance(items, list):
                            for raw in items:
                                deal = self._parse(raw)
                                if deal:
                                    results.append(deal)
                    except:
                        continue

            except Exception as e:
                print(f"    {zone}: {e}")
            time.sleep(2)

        return results

    def _parse(self, raw):
        """Parser un listing Geolocaux en format standard."""
        try:
            prix = float(raw.get("price") or raw.get("prix") or raw.get("sale_price") or 0)
            surface = float(raw.get("surface") or raw.get("area") or raw.get("total_surface") or 0)
            if prix <= 0 or surface <= 0:
                return None

            return self.to_standard({
                "url": raw.get("url") or raw.get("link") or "",
                "adresse": raw.get("address") or raw.get("adresse") or "",
                "code_postal": raw.get("zip_code") or raw.get("postal_code") or raw.get("cp") or "",
                "commune": raw.get("city") or raw.get("ville") or raw.get("commune") or "",
                "departement": str(raw.get("department") or raw.get("departement") or ""),
                "surface": surface,
                "prix": prix,
                "dpe": (raw.get("dpe") or raw.get("energy_class") or "").upper(),
                "titre": raw.get("title") or raw.get("titre") or "",
                "description": raw.get("description") or "",
                "nb_photos": raw.get("nb_photos") or raw.get("photos_count") or 0,
                "parking": raw.get("parking") or 0,
            })
        except:
            return None


if __name__ == "__main__":
    scraper = GeolocauxScraper()
    results = scraper.scrape({"surface_min": 300, "surface_max": 700})
    print(f"\n{len(results)} biens")

"""
Scraper Geolocaux.com — nécessite Playwright (headless browser).
Le site rend tout en JS côté client.
"""
import json
import re
import time
from base_scraper import BaseScraper


class GeolocauxScraper(BaseScraper):
    name = "geolocaux"
    BASE = "https://www.geolocaux.com"

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
        filters = filters or {}
        depts = filters.get("departements", ["75", "92", "93", "94"])
        surface_min = filters.get("surface_min", 300)
        surface_max = filters.get("surface_max", 700)
        prix_max = filters.get("prix_max", 5000000)

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            print("  Geolocaux: playwright non installe (pip install playwright && playwright install chromium)")
            return []

        all_results = []

        print(f"  Geolocaux: lancement headless browser...")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            )

            for dept in depts:
                zone = self.ZONES.get(dept)
                if not zone:
                    continue

                url = f"{self.BASE}/vente/bureau/{zone}/"
                print(f"  Geolocaux: {zone}...")

                try:
                    page.goto(url, timeout=30000, wait_until="networkidle")
                    time.sleep(2)

                    # Attendre le contenu
                    page.wait_for_selector("[class*='annonce'], [class*='listing'], [class*='card'], article", timeout=10000)

                    # Intercepter les requetes API XHR
                    content = page.content()

                    # Chercher les annonces dans le DOM rendu
                    listings = page.evaluate("""() => {
                        const results = [];
                        // Adapter les selecteurs au DOM réel de Geolocaux
                        const cards = document.querySelectorAll('[class*="annonce"], [class*="listing"], [class*="property"], article, .card');
                        cards.forEach(card => {
                            const text = card.innerText || '';
                            const link = card.querySelector('a[href]');
                            const priceMatch = text.match(/([\d\s]+)\s*€/);
                            const surfMatch = text.match(/(\d+)\s*m[²2]/);
                            if (priceMatch && surfMatch) {
                                results.push({
                                    url: link ? link.href : '',
                                    text: text.substring(0, 500),
                                    price: priceMatch[1].replace(/\s/g, ''),
                                    surface: surfMatch[1],
                                });
                            }
                        });
                        return results;
                    }""")

                    # Si pas de cards, chercher dans le JSON embarqué
                    if not listings:
                        json_data = page.evaluate("""() => {
                            // Chercher des stores/state globaux
                            const keys = ['__NUXT__', '__NEXT_DATA__', '__data__', '__INITIAL_STATE__'];
                            for (const k of keys) {
                                if (window[k]) return JSON.stringify(window[k]);
                            }
                            return null;
                        }""")
                        if json_data:
                            try:
                                data = json.loads(json_data)
                                print(f"    State JS trouvé: {list(data.keys())[:5] if isinstance(data, dict) else type(data)}")
                            except:
                                pass

                    print(f"    {len(listings)} annonces trouvées")

                    for raw in listings:
                        try:
                            prix = int(raw.get("price", 0))
                            surface = int(raw.get("surface", 0))
                            if surface < surface_min or surface > surface_max:
                                continue
                            if prix > prix_max or prix < 10000:
                                continue

                            # Extraire ville du texte
                            ville = ""
                            cp = ""
                            cp_match = re.search(r"(\d{5})", raw.get("text", ""))
                            if cp_match:
                                cp = cp_match.group(1)

                            deal = self.to_standard({
                                "url": raw.get("url", ""),
                                "commune": ville,
                                "code_postal": cp,
                                "departement": dept,
                                "surface": surface,
                                "prix": prix,
                                "titre": f"Bureaux {surface}m²",
                                "description": raw.get("text", "")[:300],
                            })
                            all_results.append(deal)
                        except:
                            continue

                except Exception as e:
                    print(f"    Erreur {zone}: {e}")

                time.sleep(2)

            browser.close()

        print(f"  Geolocaux: {len(all_results)} biens")
        self.results = all_results
        return all_results


if __name__ == "__main__":
    s = GeolocauxScraper()
    results = s.scrape({"departements": ["75", "92"], "surface_min": 300, "surface_max": 700})
    print(f"\n{len(results)} biens")

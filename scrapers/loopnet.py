"""
Scraper LoopNet.fr — nécessite Playwright (Cloudflare protection).
"""
import json
import re
import time
from base_scraper import BaseScraper


class LoopNetScraper(BaseScraper):
    name = "loopnet"
    BASE = "https://www.loopnet.fr"

    def scrape(self, filters=None):
        filters = filters or {}
        surface_min = filters.get("surface_min", 300)
        surface_max = filters.get("surface_max", 700)
        prix_max = filters.get("prix_max", 5000000)

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            print("  LoopNet: playwright non installé")
            return []

        all_results = []
        print(f"  LoopNet: lancement headless browser...")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
            )
            page = ctx.new_page()

            # Intercepter les réponses API
            api_data = []
            def handle_response(response):
                if "/api/" in response.url or "search" in response.url.lower():
                    try:
                        if "json" in response.headers.get("content-type", ""):
                            data = response.json()
                            api_data.append(data)
                    except:
                        pass
            page.on("response", handle_response)

            url = f"{self.BASE}/recherche/bureaux/paris---france/a-vendre/"
            print(f"  LoopNet: chargement {url}...")

            try:
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                time.sleep(5)  # Attendre le JS

                # Essayer de passer le Cloudflare challenge
                page.wait_for_load_state("networkidle", timeout=15000)
                time.sleep(3)

                content = page.content()
                print(f"    Page chargée: {len(content)} chars")

                # Chercher les placards/listings dans le DOM
                listings = page.evaluate("""() => {
                    const results = [];
                    const cards = document.querySelectorAll('.placard-content, .search-card, [class*="listing"], article');
                    cards.forEach(card => {
                        const text = card.innerText || '';
                        const link = card.querySelector('a[href]');
                        const priceMatch = text.match(/([\d\s.,]+)\s*€/);
                        const surfMatch = text.match(/(\d+)\s*m[²2]/);
                        const addrEl = card.querySelector('[class*="address"], [class*="location"]');
                        if (priceMatch || surfMatch) {
                            results.push({
                                url: link ? link.href : '',
                                text: text.substring(0, 500),
                                price: priceMatch ? priceMatch[1].replace(/[\s.]/g, '').replace(',', '.') : '',
                                surface: surfMatch ? surfMatch[1] : '',
                                address: addrEl ? addrEl.innerText.trim() : '',
                            });
                        }
                    });
                    return results;
                }""")

                print(f"    DOM cards: {len(listings)}")

                # Parser les API interceptées
                if api_data:
                    print(f"    API interceptées: {len(api_data)}")

                for raw in listings:
                    try:
                        prix = float(raw.get("price", 0) or 0)
                        surface = float(raw.get("surface", 0) or 0)
                        if surface < surface_min or surface > surface_max:
                            continue
                        if prix > prix_max or prix < 10000:
                            continue

                        # Extraire ville/CP du texte
                        addr = raw.get("address", "")
                        cp_match = re.search(r"(\d{5})", raw.get("text", ""))
                        cp = cp_match.group(1) if cp_match else ""

                        deal = self.to_standard({
                            "url": raw.get("url", ""),
                            "adresse": addr,
                            "code_postal": cp,
                            "departement": cp[:2] if cp else "75",
                            "commune": addr or "Paris",
                            "surface": surface,
                            "prix": prix,
                            "titre": f"Bureaux {int(surface)}m²",
                            "description": raw.get("text", "")[:300],
                        })
                        all_results.append(deal)
                    except:
                        continue

            except Exception as e:
                print(f"    Erreur: {e}")

            browser.close()

        print(f"  LoopNet: {len(all_results)} biens")
        self.results = all_results
        return all_results


if __name__ == "__main__":
    s = LoopNetScraper()
    results = s.scrape({"surface_min": 300, "surface_max": 700})
    print(f"\n{len(results)} biens")

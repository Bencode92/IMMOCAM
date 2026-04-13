"""
Scraper LoopNet.fr — Cloudflare + pageguid.
Nécessite Playwright pour passer Cloudflare, puis API /services/search.
"""
import json
import re
import time
from bs4 import BeautifulSoup
from base_scraper import BaseScraper


class LoopNetScraper(BaseScraper):
    name = "loopnet"
    BASE = "https://www.loopnet.fr"
    SEARCH_API = "/services/search"

    def scrape(self, filters=None):
        filters = filters or {}
        surface_min = filters.get("surface_min", 300)
        surface_max = filters.get("surface_max", 700)
        prix_max = filters.get("prix_max", 5000000)

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            print("  LoopNet: playwright requis (pip install playwright && playwright install chromium)")
            return []

        all_results = []
        print("  LoopNet: lancement Playwright (Cloudflare bypass)...")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
                locale="fr-FR",
            )
            page = ctx.new_page()

            # 1) Charger la page pour passer Cloudflare et obtenir pageguid
            print("    Chargement page vente bureaux Paris...")
            try:
                page.goto(f"{self.BASE}/recherche/bureaux/paris---france/a-vendre/", timeout=30000)
                page.wait_for_load_state("networkidle", timeout=20000)
                time.sleep(3)
            except:
                print("    Timeout page initiale, tentative continue...")

            content = page.content()
            print(f"    Page: {len(content)} chars")

            # 2) Extraire pageguid
            guid_match = re.search(r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}', content)
            pageguid = guid_match.group(0) if guid_match else None
            print(f"    pageguid: {pageguid or 'non trouvé'}")

            # 3) Si pas de GUID, parser directement le HTML déjà chargé
            if not pageguid:
                print("    Fallback: parsing HTML direct...")
                all_results = self._parse_html(content, surface_min, surface_max, prix_max)
            else:
                # 4) Appeler l'API via le navigateur (cookies Cloudflare inclus)
                print("    Appel API /services/search via navigateur...")
                for pg in range(1, 30):
                    try:
                        api_result = page.evaluate(f"""async () => {{
                            const resp = await fetch('{self.BASE}{self.SEARCH_API}', {{
                                method: 'POST',
                                headers: {{'Content-Type': 'application/json'}},
                                body: JSON.stringify({{
                                    pageguid: '{pageguid}',
                                    pageNumber: {pg},
                                    criteria: {{
                                        PropertyTypes: 536870920,
                                        Country: 'FR',
                                        State: 'PAR',
                                        GeographyFilters: [{{
                                            GeographyId: 393,
                                            GeographyType: 1,
                                            Display: 'Paris',
                                        }}],
                                    }}
                                }})
                            }});
                            return await resp.text();
                        }}""")

                        data = json.loads(api_result)
                        html = data.get("SearchPlacards", {}).get("Html", "")
                        if not html:
                            break

                        results = self._parse_html(html, surface_min, surface_max, prix_max)
                        if not results and pg > 1:
                            break
                        all_results.extend(results)
                        print(f"    Page {pg}: {len(results)} biens")

                        time.sleep(1.5)
                    except Exception as e:
                        print(f"    Page {pg}: {e}")
                        break

            browser.close()

        print(f"  LoopNet: {len(all_results)} biens")
        self.results = all_results
        return all_results

    def _parse_html(self, html, surf_min, surf_max, prix_max):
        """Parser les cards HTML LoopNet."""
        results = []
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select("article")

        for card in cards:
            text = card.get_text(separator=" | ", strip=True)
            if not text:
                continue

            link = card.select_one("a[href*='/annonce/']")
            url = link["href"] if link else ""
            if url and not url.startswith("http"):
                url = self.BASE + url

            # Surface
            surf_m = re.search(r"(\d[\d\s]*)\s*m[²2]", text)
            if not surf_m:
                continue
            surface = int(re.sub(r"\s", "", surf_m.group(1)))
            if surface < surf_min or surface > surf_max:
                continue

            # Prix (vente = montant global, pas €/m²/an)
            prix = 0
            prix_matches = re.findall(r"([\d\s.,]+)\s*€", text)
            for pm in prix_matches:
                val = float(re.sub(r"[\s.]", "", pm).replace(",", "."))
                if val > 10000:  # Ignorer les loyers
                    prix = max(prix, val)
            if prix <= 0 or prix > prix_max:
                continue

            # Adresse
            addr = ""
            cp = ""
            addr_match = re.search(r"(\d+[^|]*?\d{5}\s+\w+)", text)
            if addr_match:
                addr = addr_match.group(1).strip()
            cp_match = re.search(r"(\d{5})", text)
            if cp_match:
                cp = cp_match.group(1)

            deal = self.to_standard({
                "url": url,
                "adresse": addr,
                "code_postal": cp,
                "departement": cp[:2] if cp else "75",
                "commune": "Paris",
                "surface": surface,
                "prix": prix,
                "titre": f"Bureaux {surface}m²",
                "description": text[:300],
            })
            results.append(deal)

        return results


if __name__ == "__main__":
    s = LoopNetScraper()
    results = s.scrape({"surface_min": 300, "surface_max": 700})
    print(f"\n{len(results)} biens")

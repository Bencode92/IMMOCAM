"""
Scraper Investisseur-Immo.fr — spécialiste IDR et bureaux pleine propriété IDF.
Site plus simple, HTML classique, moins de protection anti-bot.
"""
import requests
from bs4 import BeautifulSoup
import json
import time
import re
from base_scraper import BaseScraper


class InvestisseurImmoScraper(BaseScraper):
    name = "investisseur-immo"
    BASE = "https://www.investisseur-immo.fr"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml",
    }

    def scrape(self, filters=None):
        """Scrape les biens bureaux en vente."""
        filters = filters or {}
        surface_min = filters.get("surface_min", 300)
        surface_max = filters.get("surface_max", 700)
        prix_max = filters.get("prix_max", 5000000)

        all_results = []
        page = 1
        max_pages = 10

        print(f"  InvestisseurImmo: recherche bureaux {surface_min}-{surface_max}m²...")

        while page <= max_pages:
            try:
                url = f"{self.BASE}/annonces/bureaux/vente/ile-de-france"
                params = {"page": page}
                resp = requests.get(url, headers=self.HEADERS, params=params, timeout=20)

                if resp.status_code != 200:
                    break

                soup = BeautifulSoup(resp.text, "html.parser")

                # Chercher les cartes d'annonces
                cards = soup.select(".annonce-card, .listing-item, .property-card, article.annonce, .bien-item")
                if not cards:
                    # Essayer des selecteurs plus generiques
                    cards = soup.select("[data-listing], [data-annonce], .card")

                if not cards:
                    break

                count_before = len(all_results)
                for card in cards:
                    deal = self._parse_card(card, surface_min, surface_max, prix_max)
                    if deal:
                        all_results.append(deal)

                # Si aucun nouveau resultat, on a fini
                if len(all_results) == count_before:
                    break

                page += 1
                time.sleep(2)

            except Exception as e:
                print(f"    Page {page}: {e}")
                break

        print(f"  InvestisseurImmo: {len(all_results)} biens")
        self.results = all_results
        return all_results

    def _parse_card(self, card, surf_min, surf_max, prix_max):
        """Parser une carte HTML d'annonce."""
        try:
            text = card.get_text(separator=" ", strip=True)

            # Extraire le prix
            prix_match = re.search(r'(\d[\d\s,.]+)\s*(?:€|EUR)', text)
            if not prix_match:
                return None
            prix = float(prix_match.group(1).replace(" ", "").replace(",", "."))
            if prix < 100000:  # Probablement un loyer, pas un prix
                return None
            if prix > prix_max:
                return None

            # Extraire la surface
            surf_match = re.search(r'(\d[\d\s,.]+)\s*m[²2]', text)
            if not surf_match:
                return None
            surface = float(surf_match.group(1).replace(" ", "").replace(",", "."))
            if surface < surf_min or surface > surf_max:
                return None

            # Extraire l'adresse/ville
            ville = ""
            addr_el = card.select_one(".ville, .city, .location, .adresse, h3, h4")
            if addr_el:
                ville = addr_el.get_text(strip=True)

            # URL
            link = card.select_one("a[href]")
            url = ""
            if link:
                href = link.get("href", "")
                url = href if href.startswith("http") else self.BASE + href

            # Titre
            title_el = card.select_one("h2, h3, .titre, .title")
            titre = title_el.get_text(strip=True) if title_el else f"Bureaux {surface}m²"

            # DPE
            dpe = ""
            dpe_match = re.search(r'DPE\s*[:=]?\s*([A-G])', text, re.IGNORECASE)
            if dpe_match:
                dpe = dpe_match.group(1).upper()

            # Rendement
            rdt_match = re.search(r'(\d[,.]?\d*)\s*%', text)
            rendement = float(rdt_match.group(1).replace(",", ".")) if rdt_match else 0

            return self.to_standard({
                "url": url,
                "commune": ville,
                "surface": surface,
                "prix": prix,
                "dpe": dpe,
                "titre": titre,
                "description": text[:300],
            })

        except Exception:
            return None


if __name__ == "__main__":
    scraper = InvestisseurImmoScraper()
    results = scraper.scrape({"surface_min": 300, "surface_max": 700})
    print(f"\n{len(results)} biens")

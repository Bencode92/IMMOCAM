"""
Scraper Licitor.com — enchères judiciaires immobilières.

Scrape les ventes aux enchères bureaux + locaux commerciaux
pour Paris (75) et Hauts-de-Seine (92).
HTML classique, pas de Cloudflare, pas de captcha.
"""
import requests
import re
import time
from bs4 import BeautifulSoup
from base_scraper import BaseScraper


class LicitorScraper(BaseScraper):
    name = "licitor"
    BASE = "https://www.licitor.com"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9",
    }

    # Pages à scraper — bureaux + locaux commerciaux (bureaux souvent classés là)
    TARGETS = {
        "75": [
            "/ventes-aux-encheres-immobilieres/paris-et-ile-de-france/bureaux.html",
            "/ventes-aux-encheres-immobilieres/paris-et-ile-de-france/local-a-usage-de-commerce.html",
            "/ventes-aux-encheres-immobilieres/paris-ouest.html",
            "/ventes-aux-encheres-immobilieres/paris-nord.html",
            "/ventes-aux-encheres-immobilieres/paris-est.html",
            "/ventes-aux-encheres-immobilieres/paris-sud.html",
        ],
        "92": [
            "/ventes-aux-encheres-immobilieres/hauts-de-seine/bureaux.html",
            "/ventes-aux-encheres-immobilieres/hauts-de-seine/local-a-usage-de-commerce.html",
            "/ventes-aux-encheres-immobilieres/hauts-de-seine.html",
        ],
    }

    def scrape(self, filters=None):
        filters = filters or {}
        depts = filters.get("departements", ["75", "92"])
        surface_min = filters.get("surface_min", 100)  # Plus bas pour enchères
        surface_max = filters.get("surface_max", 2000)  # Plus large
        prix_max = filters.get("prix_max", 5000000)

        all_results = []
        seen_ids = set()

        for dept in depts:
            targets = self.TARGETS.get(dept, [])
            if not targets:
                continue

            print(f"  Licitor: scraping dept {dept}...")

            for target_path in targets:
                page = 1
                while page <= 10:
                    url = f"{self.BASE}{target_path}"
                    if page > 1:
                        url += f"?p={page}"

                    try:
                        resp = requests.get(url, headers=self.HEADERS, timeout=30)
                        if resp.status_code != 200:
                            break

                        listings = self._parse_listing_page(resp.text, dept)
                        if not listings:
                            break

                        new_count = 0
                        for listing in listings:
                            lid = listing.get("_id", "")
                            if lid in seen_ids:
                                continue
                            seen_ids.add(lid)

                            # Filtrer par type — garder bureaux, locaux commerciaux, locaux pro
                            ltype = listing.get("_type", "").lower()
                            if not any(t in ltype for t in ["bureau", "commercial", "professionnel", "local", "immeuble"]):
                                continue

                            # Filtrer département
                            if listing.get("_dept_code", "") not in ["75", "92"]:
                                continue

                            deal = self._to_deal(listing, dept, surface_min, surface_max, prix_max)
                            if deal:
                                all_results.append(deal)
                                new_count += 1

                        if new_count == 0 and page > 1:
                            break

                        page += 1
                        time.sleep(1.0)

                    except Exception as e:
                        print(f"    Erreur page {page}: {e}")
                        break

            count_dept = sum(1 for r in all_results if r.get("localisation", {}).get("departement") == dept)
            print(f"    {dept}: {count_dept} enchères")

        print(f"  Licitor: {len(all_results)} enchères au total")
        self.results = all_results
        return all_results

    def _parse_listing_page(self, html, default_dept):
        """Extraire les annonces d'une page listing."""
        soup = BeautifulSoup(html, "html.parser")
        listings = []

        # Chercher tous les liens d'annonces
        links = soup.find_all("a", href=re.compile(r"/annonce/.*\.html"))

        for link in links:
            href = link.get("href", "")
            text = link.get_text(" | ", strip=True)
            if not text or len(text) < 20:
                continue

            # ID depuis l'URL
            id_match = re.search(r'/(\d+)\.html', href)
            lid = id_match.group(1) if id_match else ""

            # Département depuis le texte (ex: "75 Paris 10ème" ou "92 Courbevoie")
            dept_match = re.search(r'\b(75|92|93|94)\b', text)
            dept_code = dept_match.group(1) if dept_match else default_dept

            # Type depuis l'URL
            type_match = re.search(r'vente-aux-encheres/([\w-]+)/', href)
            ltype = type_match.group(1).replace("-", " ") if type_match else ""

            # Surface
            surf_match = re.search(r'([\d\s.,]+)\s*m[²2]', text)
            surface = 0
            if surf_match:
                try:
                    surface = float(surf_match.group(1).replace(" ", "").replace(",", "."))
                except ValueError:
                    pass

            # Mise à prix
            prix_match = re.search(r'(?:mise\s*[àa]\s*prix|prix)\s*[:\s]*([\d\s.,]+)\s*(?:€|EUR)', text, re.IGNORECASE)
            if not prix_match:
                prix_match = re.search(r'([\d\s.,]+)\s*(?:€|EUR)', text)
            prix = 0
            if prix_match:
                try:
                    prix = float(prix_match.group(1).replace(" ", "").replace(".", "").replace(",", "."))
                except ValueError:
                    pass

            # Ville
            ville = ""
            ville_match = re.search(r'(?:75|92)\s+([\w\s-]+?)(?:\s*\||\s*$|\s*\d)', text)
            if ville_match:
                ville = ville_match.group(1).strip()

            # Date audience
            date = ""
            date_match = re.search(r'(\d{1,2}\s+\w+\s+\d{4}|\w+\s+\d{1,2}\s+\w+)', text)
            if date_match:
                date = date_match.group(1)

            listings.append({
                "_id": lid,
                "_type": ltype,
                "_dept_code": dept_code,
                "url": self.BASE + href if href.startswith("/") else href,
                "surface": surface,
                "prix": prix,
                "ville": ville,
                "date_audience": date,
                "description": text[:300],
            })

        return listings

    def _to_deal(self, listing, dept, surf_min, surf_max, prix_max):
        """Convertir un listing en deal standard."""
        surface = listing.get("surface", 0)
        prix = listing.get("prix", 0)

        # Pas de filtre surface strict — enchères ont souvent des surfaces atypiques
        # Mais exclure les trop petits
        if surface > 0 and surface < 50:
            return None
        if prix > 0 and prix > prix_max:
            return None

        ville = listing.get("ville", "")
        dept_code = listing.get("_dept_code", dept)

        # CP depuis la ville si Paris
        cp = ""
        arr_match = re.search(r'(\d+)[eè]me', ville, re.IGNORECASE)
        if arr_match:
            cp = f"75{int(arr_match.group(1)):03d}"
            ville = f"Paris {arr_match.group(1)}e"
        elif "paris" in ville.lower():
            cp = "75000"
        elif dept_code == "92":
            cp = "92000"

        return self.to_standard({
            "url": listing.get("url", ""),
            "adresse": "",
            "code_postal": cp,
            "commune": ville,
            "departement": dept_code,
            "surface": surface,
            "prix": prix,
            "titre": f"Enchère — {listing.get('_type', 'Bureau').title()} {int(surface)}m² {ville}".strip(),
            "description": f"Mise à prix: {int(prix):,}€. {listing.get('date_audience', '')}. {listing.get('description', '')}"[:300],
        })


if __name__ == "__main__":
    scraper = LicitorScraper()
    results = scraper.scrape({
        "departements": ["75", "92"],
        "surface_min": 100,
        "surface_max": 2000,
        "prix_max": 5000000,
    })
    print(f"\n{len(results)} enchères scraped")
    for r in results[:10]:
        loc = r["localisation"]
        fin = r["financier"]
        bien = r["bien"]
        print(f"  {bien['surface_m2']:.0f}m² — {loc['commune']} — Mise à prix: {fin['prix_affiche']/1e3:.0f}K€")
        print(f"    {r['annonce']['titre']}")

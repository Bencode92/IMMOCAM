"""
Scraper Investisseur-Immo.fr — HTML classique, div.vignette-offre.
"""
import requests
from bs4 import BeautifulSoup
import re
import time
from base_scraper import BaseScraper


class InvestisseurImmoScraper(BaseScraper):
    name = "investisseur-immo"
    BASE = "https://www.investisseur-immo.fr"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    }

    def scrape(self, filters=None):
        filters = filters or {}
        surface_min = filters.get("surface_min", 300)
        surface_max = filters.get("surface_max", 700)
        prix_max = filters.get("prix_max", 5000000)

        all_results = []
        page = 1

        print(f"  InvestisseurImmo: recherche bureaux {surface_min}-{surface_max}m²...")

        while page <= 5:
            url = f"{self.BASE}/annonces" + (f"?page={page}" if page > 1 else "")
            try:
                r = requests.get(url, headers=self.HEADERS, timeout=20)
                if r.status_code != 200:
                    break

                soup = BeautifulSoup(r.text, "html.parser")
                vignettes = soup.select(".vignette-offre")
                if not vignettes:
                    break

                found = 0
                for v in vignettes:
                    td = v.find("div")
                    if not td or "vendre" not in td.get_text().lower():
                        continue

                    link = v.select_one('a[href*="/Annonce"]')
                    deal_url = self.BASE + link["href"] if link else ""

                    resume = v.select_one(".resume-offre")
                    if not resume:
                        continue

                    text = resume.get_text(separator=" ", strip=True).replace("\xa0", " ").replace("\u202f", " ")

                    h2 = resume.select_one("h2")
                    type_b = h2.get_text(strip=True) if h2 else ""
                    h3 = resume.select_one("h3")
                    ville = h3.get_text(strip=True) if h3 else ""

                    # Surface
                    nums = re.findall(r"(\d[\d\s]*)\s*m[²2]", text)
                    surface = int(re.sub(r"\s", "", nums[0])) if nums else 0

                    # Prix (le plus grand nombre avant €)
                    pnums = re.findall(r"(\d[\d\s]*)\s*€", text)
                    prix = 0
                    for p in pnums:
                        val = int(re.sub(r"\s", "", p))
                        if val > prix:
                            prix = val

                    # Code postal
                    cpm = re.search(r"(\d{5})", text)
                    cp = cpm.group(1) if cpm else ""
                    dept = cp[:2] if cp else ""

                    if not ("bureau" in type_b.lower()):
                        continue
                    if surface < surface_min or surface > surface_max:
                        continue
                    if prix > prix_max:
                        continue

                    deal = self.to_standard({
                        "url": deal_url,
                        "commune": ville,
                        "code_postal": cp,
                        "departement": dept,
                        "surface": surface,
                        "prix": prix,
                        "titre": f"{type_b} {surface}m² — {ville}",
                    })
                    all_results.append(deal)
                    found += 1

                if found == 0:
                    break
                page += 1
                time.sleep(2)

            except Exception as e:
                print(f"    Page {page}: {e}")
                break

        print(f"  InvestisseurImmo: {len(all_results)} biens")
        self.results = all_results
        return all_results


if __name__ == "__main__":
    s = InvestisseurImmoScraper()
    results = s.scrape({"surface_min": 300, "surface_max": 700})
    for r in results:
        print(f"  {r['bien']['surface_m2']}m² {r['localisation']['commune']} | {r['financier']['prix_affiche']/1e6:.2f}M€")

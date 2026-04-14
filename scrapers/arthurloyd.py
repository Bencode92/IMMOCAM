"""
Scraper Arthur Loyd (arthur-loyd.com) — 1er reseau immobilier entreprise France.

Strategie: scraper par departement + sous-pages ville/arrondissement
pour contourner le "load more" AJAX (max ~20 items par page).
Puis fetch des pages detail pour le JSON-LD (prix exact).
Pas de Cloudflare, pas de captcha.
"""
import requests
import json
import re
import time
from base_scraper import BaseScraper


class ArthurLoydScraper(BaseScraper):
    name = "arthurloyd"
    BASE = "https://www.arthur-loyd.com"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9",
    }

    DEPT_SLUGS = {
        "75": "paris",
        "92": "hauts-de-seine",
        "93": "seine-saint-denis-93",
        "94": "val-de-marne",
        "78": "yvelines",
        "91": "essonne",
        "95": "val-d-oise",
        "77": "seine-et-marne",
    }

    # Paris arrondissements pour depasser la limite de ~20 items
    PARIS_ARRS = [
        "paris-1-75001", "paris-2-75002", "paris-3-75003", "paris-4-75004",
        "paris-5-75005", "paris-6-75006", "paris-7-75007", "paris-8-75008",
        "paris-9-75009", "paris-10-75010", "paris-11-75011", "paris-12-75012",
        "paris-13-75013", "paris-14-75014", "paris-15-75015", "paris-16-75016",
        "paris-17-75017", "paris-18-75018", "paris-19-75019", "paris-20-75020",
    ]

    def scrape(self, filters=None):
        filters = filters or {}
        depts = filters.get("departements", ["75", "92", "93", "94"])
        surface_min = filters.get("surface_min", 300)
        surface_max = filters.get("surface_max", 700)
        prix_max = filters.get("prix_max", 5000000)

        all_results = []
        seen_refs = set()

        for dept in depts:
            slug = self.DEPT_SLUGS.get(dept)
            if not slug:
                continue

            if dept == "75":
                # Paris: scraper par arrondissement
                print(f"  ArthurLoyd: scraping Paris (par arrondissement)...")
                for arr in self.PARIS_ARRS:
                    url = f"{self.BASE}/bureau-vente/ile-de-france/paris/{arr}"
                    self._scrape_listing_page(url, dept, surface_min, surface_max, prix_max, all_results, seen_refs)
                    time.sleep(1.0)
            else:
                print(f"  ArthurLoyd: scraping {slug}...")
                # D'abord la page departement
                url = f"{self.BASE}/bureau-vente/ile-de-france/{slug}"
                # Trouver les sous-pages villes
                city_urls = self._find_city_urls(url, slug)
                if city_urls:
                    for city_url in city_urls:
                        self._scrape_listing_page(city_url, dept, surface_min, surface_max, prix_max, all_results, seen_refs)
                        time.sleep(1.0)
                else:
                    self._scrape_listing_page(url, dept, surface_min, surface_max, prix_max, all_results, seen_refs)
                    time.sleep(1.0)

            count_dept = sum(1 for r in all_results if r.get("localisation", {}).get("departement") == dept)
            print(f"    {dept}: {count_dept} biens")

        print(f"  ArthurLoyd: {len(all_results)} biens au total")
        self.results = all_results
        return all_results

    def _find_city_urls(self, dept_url, dept_slug):
        """Trouver les URLs de villes depuis la page departement."""
        try:
            resp = requests.get(dept_url, headers=self.HEADERS, timeout=30)
            if resp.status_code != 200:
                return []
            # Chercher les liens vers les villes
            pattern = rf'/bureau-vente/ile-de-france/{re.escape(dept_slug)}/[\w-]+'
            urls = list(set(re.findall(pattern, resp.text)))
            return [self.BASE + u for u in urls[:50]]
        except:
            return []

    def _scrape_listing_page(self, url, dept, surf_min, surf_max, prix_max, results, seen_refs):
        """Scraper une page listing (departement, ville ou arrondissement)."""
        try:
            resp = requests.get(url, headers=self.HEADERS, timeout=30)
            if resp.status_code != 200:
                return

            # Extraire les liens d'annonces
            listing_urls = re.findall(r'href="(/bureau-vente/ile-de-france/[^"]+ref-[\w-]+)"', resp.text)
            listing_urls = list(set(listing_urls))

            for listing_path in listing_urls:
                # Extraire la reference
                ref_match = re.search(r'ref-([\w-]+)', listing_path)
                ref = ref_match.group(1) if ref_match else ""
                if not ref or ref in seen_refs:
                    continue
                seen_refs.add(ref)

                # Fetch la page detail pour le JSON-LD
                deal = self._fetch_detail(listing_path, dept, surf_min, surf_max, prix_max, ref)
                if deal:
                    results.append(deal)
                time.sleep(0.8)

        except Exception as e:
            print(f"    Erreur listing: {e}")

    def _fetch_detail(self, path, dept, surf_min, surf_max, prix_max, ref):
        """Fetch une page detail et extraire les donnees."""
        try:
            url = self.BASE + path
            resp = requests.get(url, headers=self.HEADERS, timeout=30)
            if resp.status_code != 200:
                return None

            html = resp.text

            # 1) JSON-LD pour le prix
            prix = 0
            jsonld_blocks = re.findall(
                r'<script\s+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
                html, re.DOTALL
            )
            for block in jsonld_blocks:
                try:
                    data = json.loads(block)
                    if isinstance(data, dict) and data.get("@type") == "Product":
                        offers = data.get("offers", {})
                        low = offers.get("lowPrice", 0)
                        high = offers.get("highPrice", 0)
                        prix = float(high or low or 0)
                except:
                    continue

            # 2) Surface depuis le texte
            surface = 0
            # Pattern "Entre X m² et Y m²" ou "X m²"
            range_match = re.search(r'Entre\s+([\d\s]+)\s*m.*?et\s+([\d\s]+)\s*m', html, re.IGNORECASE)
            if range_match:
                s1 = float(range_match.group(1).replace(" ", "").replace("\xa0", ""))
                s2 = float(range_match.group(2).replace(" ", "").replace("\xa0", ""))
                surface = s2  # Prendre la surface max
            if surface == 0:
                # Chercher tous les "X m²" et prendre le plus grand raisonnable
                all_surfs = re.findall(r'([\d\s\xa0]+)\s*m[²2\xb2]', html)
                for s in all_surfs:
                    cleaned = s.replace(" ", "").replace("\xa0", "").strip()
                    if not cleaned:
                        continue
                    try:
                        val = float(cleaned)
                    except ValueError:
                        continue
                    if 50 < val < 50000 and val > surface:
                        surface = val

            # 3) Adresse + CP + ville
            adresse = ""
            cp = ""
            commune = ""
            # Chercher le pattern "rue/avenue..., 75018 Paris"
            addr_match = re.search(r'(\d+[^<]{3,60}?)\s*,?\s*(\d{5})\s+([A-Za-zÀ-ÿ\s-]+)', html)
            if addr_match:
                adresse = addr_match.group(1).strip()
                cp = addr_match.group(2)
                commune = addr_match.group(3).strip()
            else:
                # Fallback: CP depuis le texte
                cp_match = re.search(r'(\d{5})', html)
                if cp_match:
                    cp = cp_match.group(1)
                # Commune depuis l'URL
                url_match = re.search(r'/bureau-vente/ile-de-france/[\w-]+/([\w-]+)/', path)
                if url_match:
                    commune = url_match.group(1).replace("-", " ").title()

            # Paris arrondissement
            if cp and cp.startswith("75") and len(cp) == 5:
                arr = int(cp[3:])
                if 1 <= arr <= 20:
                    commune = f"Paris {arr}e"

            # 4) Titre
            titre = ""
            title_match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL)
            if title_match:
                titre = re.sub(r'<[^>]+>', '', title_match.group(1)).strip()

            # Filtres — garder si au moins surface OU prix est renseigne
            if surface > 0 and (surface < surf_min or surface > surf_max):
                return None
            if prix > 0 and prix > prix_max:
                return None
            if prix <= 0 and surface <= 0:
                return None
            # Recalculer prix_m2 seulement si les deux sont renseignes
            if surface > 0 and prix > 0:
                pass  # to_standard le calcule
            elif surface <= 0:
                surface = 0  # Sera affiche comme "? m²"

            return self.to_standard({
                "url": self.BASE + path,
                "adresse": adresse,
                "code_postal": cp,
                "commune": commune,
                "departement": dept,
                "surface": surface,
                "prix": prix,
                "titre": titre or f"Bureaux {int(surface)}m² {commune}",
                "description": f"Réf. {ref}",
            })

        except Exception as e:
            print(f"    Detail error: {e}")
            return None


if __name__ == "__main__":
    scraper = ArthurLoydScraper()
    results = scraper.scrape({
        "departements": ["75", "92"],
        "surface_min": 300,
        "surface_max": 700,
        "prix_max": 5000000,
    })
    print(f"\n{len(results)} biens scraped")
    for r in results[:5]:
        loc = r["localisation"]
        fin = r["financier"]
        print(f"  {r['bien']['surface_m2']:.0f}m² — {loc['commune']} {loc['code_postal']} — {fin['prix_affiche']/1e6:.2f}M€ ({fin['prix_m2']:.0f}€/m²)")

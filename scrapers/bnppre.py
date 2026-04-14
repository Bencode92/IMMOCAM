"""
Scraper BNP Paribas Real Estate (bnppre.fr).

Le site embed des JSON-LD (schema.org) dans chaque page listing.
Pas de Cloudflare, pas de captcha — requests simple suffit.
On scrape par département + arrondissement Paris pour contourner la limite de 40 items/page.
"""
import requests
import json
import re
import time
from base_scraper import BaseScraper


class BNPPREScraper(BaseScraper):
    name = "bnppre"
    BASE = "https://www.bnppre.fr"
    SEARCH = "/a-vendre/bureau/{zone}/"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9",
    }

    # Zones IDF — départements
    ZONES = {
        "92": "hauts-de-seine-92",
        "93": "seine-saint-denis-93",
        "94": "val-de-marne-94",
        "78": "yvelines-78",
        "91": "essonne-91",
        "95": "val-d-oise-95",
        "77": "seine-et-marne-77",
    }

    # Paris par arrondissement pour dépasser la limite de 40 items/page
    PARIS_ARRONDISSEMENTS = {
        "75001": "paris-75/paris-1-75001",
        "75002": "paris-75/paris-2-75002",
        "75003": "paris-75/paris-3-75003",
        "75004": "paris-75/paris-4-75004",
        "75005": "paris-75/paris-5-75005",
        "75006": "paris-75/paris-6-75006",
        "75007": "paris-75/paris-7-75007",
        "75008": "paris-75/paris-8-75008",
        "75009": "paris-75/paris-9-75009",
        "75010": "paris-75/paris-10-75010",
        "75011": "paris-75/paris-11-75011",
        "75012": "paris-75/paris-12-75012",
        "75013": "paris-75/paris-13-75013",
        "75014": "paris-75/paris-14-75014",
        "75015": "paris-75/paris-15-75015",
        "75016": "paris-75/paris-16-75016",
        "75017": "paris-75/paris-17-75017",
        "75018": "paris-75/paris-18-75018",
        "75019": "paris-75/paris-19-75019",
        "75020": "paris-75/paris-20-75020",
    }

    def scrape(self, filters=None):
        """Scrape les annonces bureaux vente IDF."""
        filters = filters or {}
        depts = filters.get("departements", ["75", "92"])
        surface_min = filters.get("surface_min", 300)
        surface_max = filters.get("surface_max", 700)
        prix_max = filters.get("prix_max", 5000000)

        all_results = []
        seen_refs = set()

        for dept in depts:
            if dept == "75":
                # Paris: scraper par arrondissement
                zones = list(self.PARIS_ARRONDISSEMENTS.items())
                label = "Paris (par arrondissement)"
            else:
                zone = self.ZONES.get(dept)
                if not zone:
                    continue
                zones = [(dept, zone)]
                label = zone

            print(f"  BNPPRE: scraping {label}...")

            for zone_key, zone_path in zones:
                url = self.BASE + self.SEARCH.format(zone=zone_path)
                params = {}
                if surface_min:
                    params["surface_min"] = surface_min
                if surface_max:
                    params["surface_max"] = surface_max

                try:
                    resp = requests.get(url, headers=self.HEADERS, params=params, timeout=30)
                    if resp.status_code != 200:
                        continue

                    offers = self._extract_jsonld_offers(resp.text)
                    for offer in offers:
                        deal = self._parse_offer(offer, dept, surface_min, surface_max, prix_max)
                        if deal and deal.get("_ref") not in seen_refs:
                            seen_refs.add(deal.pop("_ref"))
                            all_results.append(deal)

                    time.sleep(1.0)

                except Exception as e:
                    print(f"    Erreur {zone_key}: {e}")

            count_dept = sum(1 for r in all_results if r.get("localisation", {}).get("departement") == dept)
            print(f"    {dept}: {count_dept} biens")

        print(f"  BNPPRE: {len(all_results)} biens au total")
        self.results = all_results
        return all_results

    def _extract_jsonld_offers(self, html):
        """Extraire les offres depuis les blocs JSON-LD."""
        offers = []
        # Trouver tous les blocs JSON-LD
        blocks = re.findall(
            r'<script\s+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            html, re.DOTALL
        )

        for block in blocks:
            try:
                data = json.loads(block)
            except json.JSONDecodeError:
                continue

            # Chercher les offres dans différentes structures possibles
            if isinstance(data, list):
                for item in data:
                    offers.extend(self._find_offers(item))
            else:
                offers.extend(self._find_offers(data))

        return offers

    def _find_offers(self, data):
        """Trouver les offres dans un objet JSON-LD."""
        offers = []
        if not isinstance(data, dict):
            return offers

        # Offre directe
        if data.get("@type") == "Offer" and data.get("url"):
            offers.append(data)

        # AggregateOffer avec sous-offres
        agg = data.get("offers")
        if isinstance(agg, dict):
            sub = agg.get("offers", [])
            if isinstance(sub, list):
                for o in sub:
                    if isinstance(o, dict) and o.get("url"):
                        offers.append(o)

        # ItemList
        items = data.get("itemListElement", [])
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    inner = item.get("item", item)
                    if isinstance(inner, dict) and inner.get("url"):
                        offers.append(inner)

        return offers

    def _parse_offer(self, offer, dept, surf_min, surf_max, prix_max):
        """Convertir une offre JSON-LD en format standard."""
        try:
            url = offer.get("url", "")
            name = offer.get("name", "")
            price = offer.get("price")
            sku = offer.get("sku", "")

            # Prix
            if price is None or price == 0:
                return None
            prix = float(price)
            if prix <= 0 or prix > prix_max:
                return None

            # Extraire référence depuis URL ou SKU
            ref = sku
            if not ref:
                ref_match = re.search(r'(OVBUR\d+)', url)
                ref = ref_match.group(1) if ref_match else ""
            if not ref:
                return None

            # Extraire surface depuis le name: "Vente bureau Paris 308.84m² 75018 Paris"
            surface = 0
            surf_match = re.search(r'([\d\s.,]+)\s*m[²2]', name)
            if surf_match:
                surface = float(surf_match.group(1).replace(",", ".").replace(" ", ""))
            # Fallback: depuis URL "vente-bureau-308-m2"
            if surface == 0:
                url_surf = re.search(r'vente-bureau-(\d+)-m2', url)
                if url_surf:
                    surface = float(url_surf.group(1))

            if surface < surf_min or surface > surf_max:
                return None

            # Code postal depuis name ou URL
            cp = ""
            cp_match = re.search(r'(\d{5})', name)
            if cp_match:
                cp = cp_match.group(1)
            if not cp:
                cp_match = re.search(r'/(\d{5})/', url)
                if cp_match:
                    cp = cp_match.group(1)

            # Commune depuis URL: ".../pantin-93500/..." ou name
            commune = ""
            commune_match = re.search(r'/([a-z][\w-]+)-\d{5}/', url)
            if commune_match:
                commune = commune_match.group(1).replace("-", " ").title()
            # Paris arrondissement
            if cp and cp.startswith("75"):
                arr = int(cp[3:]) if len(cp) == 5 else 0
                if arr > 0:
                    commune = f"Paris {arr}e"

            # Divisible?
            divisible = "divisible" in url and "non-divisible" not in url

            # URL complète
            if url and not url.startswith("http"):
                url = self.BASE + url

            deal = self.to_standard({
                "url": url,
                "adresse": "",
                "code_postal": cp,
                "commune": commune,
                "departement": dept,
                "surface": surface,
                "prix": prix,
                "titre": name,
                "description": f"Réf. {ref}" + (" — Divisible" if divisible else ""),
            })
            deal["_ref"] = ref
            return deal

        except Exception as e:
            print(f"    Parse error: {e}")
            return None


if __name__ == "__main__":
    scraper = BNPPREScraper()
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

"""Base scraper — classe abstraite pour tous les scrapers."""
from abc import ABC, abstractmethod
from datetime import datetime


class BaseScraper(ABC):
    """Chaque scraper herite de cette classe et implemente scrape()."""

    name = "base"

    def __init__(self, config=None):
        self.config = config or {}
        self.results = []

    @abstractmethod
    def scrape(self, filters=None):
        """Scrape le site et retourne une liste de deals au format standard.

        filters: dict avec surface_min, surface_max, prix_min, prix_max, departements, etc.
        """
        pass

    def to_standard(self, raw):
        """Convertit un resultat brut en format standard deal."""
        return {
            "source": self.name,
            "url": raw.get("url", ""),
            "date_scrape": datetime.now().strftime("%Y-%m-%d"),
            "localisation": {
                "adresse": raw.get("adresse", ""),
                "code_postal": raw.get("code_postal", ""),
                "commune": raw.get("commune", ""),
                "departement": raw.get("departement", ""),
                "code_insee": raw.get("code_insee", ""),
                "latitude": raw.get("lat"),
                "longitude": raw.get("lng"),
            },
            "bien": {
                "type": raw.get("type", "bureaux"),
                "surface_m2": raw.get("surface", 0),
                "dpe": raw.get("dpe", ""),
                "ges": raw.get("ges", ""),
                "annee_construction": raw.get("annee"),
                "etat": raw.get("etat", ""),
                "parking": raw.get("parking", 0),
                "ascenseur": raw.get("ascenseur"),
                "climatisation": raw.get("clim"),
            },
            "financier": {
                "prix_affiche": raw.get("prix", 0),
                "prix_m2": raw.get("prix", 0) / max(raw.get("surface", 1), 1),
                "honoraires_pct": raw.get("honoraires_pct"),
                "taxe_fonciere_an": raw.get("taxe_fonciere"),
                "charges_copro_an": raw.get("charges"),
            },
            "locatif": {
                "occupation": raw.get("occupation", ""),
                "loyer_actuel_an": raw.get("loyer_an", 0),
                "loyer_m2_an": raw.get("loyer_an", 0) / max(raw.get("surface", 1), 1) if raw.get("loyer_an") else 0,
            },
            "annonce": {
                "titre": raw.get("titre", ""),
                "description": raw.get("description", ""),
                "photos": raw.get("nb_photos", 0),
                "date_publication": raw.get("date_pub", ""),
                "agent": raw.get("agent", ""),
            },
        }


class ManualImporter(BaseScraper):
    """Import manuel depuis CSV/JSON pour biens off-market ou broker."""

    name = "manual"

    def scrape(self, filters=None):
        """Pas de scraping — les donnees sont passees en config."""
        return self.config.get("deals", [])

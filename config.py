"""Configuration globale IMMOCAM."""
from pathlib import Path

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"

# GitHub
GITHUB_REPO = "Bencode92/IMMOCAM"
DVFMAJ_REPO = "Bencode92/DVFMAJ"
REFERENTIEL_URL = f"https://raw.githubusercontent.com/{DVFMAJ_REPO}/main/output/referentiel_bureaux.json"

# Scoring weights
SCORING = {
    "prix_vs_marche": 0.30,
    "loyer_vs_potentiel": 0.25,
    "rendement": 0.20,
    "risque": 0.15,
    "qualite_annonce": 0.10,
}

# DPE decote travaux estimee (EUR/m2)
DPE_TRAVAUX = {"A": 0, "B": 0, "C": 50, "D": 150, "E": 300, "F": 500, "G": 700}

# Statuts deals
STATUTS = ["nouveau", "a_verifier", "a_contacter", "simulation", "poubelle"]

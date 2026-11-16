"""
Agences de prestige lisibles sans navigateur (repérage du 16/11/2026) : Sotheby's (France, Paris Ouest,
Propriétés Parisiennes), Daniel Féau, Kretz, Junot, Coldwell Banker, Vaneau, Engel & Völkers.
Toutes renvoient le format commun de hp/sources.py ; le tri Paris / Neuilly ≥ 500 m² est fait par dans_perimetre.
"""
import json
import re
import time

import requests
from bs4 import BeautifulSoup

from hp.sources import UA, num, cp_from_ville, dans_perimetre


def txt(el, sel):
    x = el.select_one(sel)
    return x.get_text(" ", strip=True) if x else ""


def norm_cp(cp):
    return "75016" if cp == "75116" else cp


def lieu(cp):
    if cp.startswith("75"):
        return f"Paris {int(cp[3:])}e"
    return "Neuilly-sur-Seine" if cp == "92200" else ""


def annonce(source, rid, url, titre, cp, surface, prix, commune="", extra=None):
    cp, titre = norm_cp(cp), " ".join((titre or "").split())
    return {"id": f"{source}-{rid}", "source": source, "url": url, "titre": titre,
            "type": "hotel particulier" if "particulier" in titre.lower() else "maison",
            "commune": commune or lieu(cp), "code_postal": cp if cp.startswith("75") else "", "adresse": "",
            "surface": surface, "prix": prix, "description": "", "dpe": "", "extra": extra or {}}


def decrire(out, known_ids, session=None):
    """Description (meta / og:description) des seules nouvelles annonces du périmètre."""
    get = (session or requests).get
    for x in out:
        if x["id"] in known_ids:
            continue
        try:
            h = get(x["url"], headers=UA, timeout=40).text
            m = re.search(r'<meta[^>]+(?:property="og:description"|name="description")[^>]+content="([^"]*)"', h)
            x["description"] = BeautifulSoup(m.group(1), "html.parser").get_text()[:4000] if m else ""
            time.sleep(1.0)
        except requests.RequestException:
            pass
    return out


class Sothebys:
    name = "sothebys"
    BASE = "https://www.sothebysrealty-france.com"

    def collect(self, known_ids=frozenset()):
        out, ids = [], set()
        for p in range(1, 15):
            body = "ajax=true&no_redirect=true&nbbypage=100&surface=500" + (f"&p={p}" if p > 1 else "")
            r = requests.post(self.BASE + "/fr/vente-proprietes-de-luxe/?ajax=true", data=body, timeout=60,
                              headers={**UA, "Content-Type": "application/x-www-form-urlencoded"})
            s = BeautifulSoup(r.text, "html.parser")
            for c in s.select("div.annonce"):
                a = c.select_one("a[href]")
                m = re.search(r"ref-([a-z0-9]+-\d+)/.*-(\d{5})/?$", a["href"]) if a else None
                if not m or m.group(1) in ids:
                    continue
                ids.add(m.group(1))
                url = a["href"] if a["href"].startswith("http") else self.BASE + a["href"]
                out.append(annonce(self.name, m.group(1), url, f"{txt(c, '.type')} – {txt(c, '.city')}", m.group(2),
                                   num(txt(c, ".surface .chiffre")), num(txt(c, ".price"))))
            meta = s.select_one("meta#jsDataAjaxAnnonces")
            if not meta or p >= int(meta.get("data-page-count") or 1):
                break
            time.sleep(1.0)
        return decrire([x for x in out if dans_perimetre(x)], known_ids)


class Feau:
    name = "feau"
    BASE = "https://danielfeau.com"
    LISTES = ["/fr/listing/france/vente/maisons/paris", "/fr/listing/france/vente/maisons/neuilly",
              "/fr/acheter/proprietes-exceptionnelles"]

    def collect(self, known_ids=frozenset()):
        out, ids = [], set()
        for path in self.LISTES:
            for p in range(1, 10):
                r = requests.get(self.BASE + path + (f"?page={p}" if p > 1 else ""), headers=UA, timeout=40)
                lis = BeautifulSoup(r.text, "html.parser").select("ul.listing li.property[data-loaded]")
                fresh = 0
                for li in lis:
                    pid = li.get("data-property-id")
                    if not pid or pid in ids:
                        continue
                    ids.add(pid)
                    fresh += 1
                    t = txt(li, "h2 > div")
                    ms, cp = re.search(r"([\d.,]+)\s*m²", t), re.search(r"\((\d{5})\)", t)
                    out.append(annonce(self.name, pid, f"{self.BASE}/fr/annonce-immobiliere/{pid}", t.split(", ref")[0],
                                       cp.group(1) if cp else "", num(ms.group(1)) if ms else 0.0, num(txt(li, "span.price"))))
                if not fresh:
                    break
                time.sleep(1.0)
        return decrire([x for x in out if dans_perimetre(x)], known_ids)


class Kretz:
    name = "kretz"
    URL = "https://kretzrealestate.com/page-data/fr/acheter/page-data.json"

    def collect(self, known_ids=frozenset()):
        nodes = requests.get(self.URL, headers=UA, timeout=90).json()["result"]["data"]["allProperty"]["nodes"]
        out = []
        for n in nodes:
            cp, ref = str(n.get("codePostal") or ""), n.get("reference") or ""
            if not ref or n.get("isOffmarket"):
                continue
            prix = 0.0 if n.get("prixConfidentiel") else num(str(n.get("prixAffichageFai") or ""))
            slug = (n.get("propertyTypeSlug") or "house").lower()
            x = annonce(self.name, ref, f"https://kretzrealestate.com/fr/annonce/{ref.lower()}/{slug}/",
                        n.get("titreFr") or f"{n.get('propertyType', '')} {n.get('ville', '')}", cp,
                        num(str(n.get("surfaceHabitable") or "")), prix,
                        commune=lieu(norm_cp(cp)) or n.get("ville", ""))
            out.append(x)
        return decrire([x for x in out if dans_perimetre(x)], known_ids)


class Junot:
    name = "junot"
    BASE = "https://www.junot.fr"
    LIEUX = [121, 103, 32, 102, 105, 33, 28, 106, 31, 114, 107, 193, 101, 112, 108, 29, 34, 25, 111, 109, 104]

    def collect(self, known_ids=frozenset()):
        out, ids, total = [], set(), None
        for p in range(1, 15):
            params = [("types[]", 5)] + [("lieux[]", v) for v in self.LIEUX] + [("tri", "prix-decroissant"), ("page", p)]
            s = BeautifulSoup(requests.get(self.BASE + "/fr/biens-immobiliers/acheter/", params=params, headers=UA,
                                           timeout=40).text, "html.parser")
            if total is None:
                sec = s.select_one("section[data-product-count]")
                total = int(sec["data-product-count"]) if sec else 0
            for c in s.select(".product-card"):
                a = c.select_one("a.product-card-link[href]")
                if not a or len(ids) >= total:
                    continue
                m = re.search(r"/biens/(\d+)", a["href"])
                if not m or m.group(1) in ids:
                    continue
                ids.add(m.group(1))
                loc = txt(c, ".product-card-title")
                cp = cp_from_ville(loc) or ("92200" if "neuilly" in loc.lower() else "")
                out.append(annonce(self.name, m.group(1), self.BASE + a["href"] if a["href"].startswith("/") else a["href"],
                                   f"{txt(c, '.product-card-type')} – {loc}", cp,
                                   num(txt(c, ".product-card-feature-area-liveable")), num(txt(c, ".product-card-price"))))
            if len(ids) >= total:
                break
            time.sleep(1.0)
        return decrire([x for x in out if dans_perimetre(x)], known_ids)


class Coldwell:
    name = "coldwell"
    BASE = "https://www.coldwellbanker.fr"

    def collect(self, known_ids=frozenset()):
        out, ids = [], set()
        for p in range(1, 20):
            s = BeautifulSoup(requests.get(f"{self.BASE}/vente-immobilier?by_min_area=500&page={p}", headers=UA,
                                           timeout=40).text, "html.parser")
            fresh = 0
            for c in s.select("article[id^=accommodation_]"):
                rid, a = c["id"].split("_")[-1], c.select_one('a[href^="/vente-immobilier/"]')
                if rid in ids or not a:
                    continue
                ids.add(rid)
                fresh += 1
                m = re.search(r"-(\d{5})/", a["href"])
                tr = [t.get_text(" ", strip=True) for t in c.select("p.truncate")]
                out.append(annonce(self.name, rid, self.BASE + a["href"], txt(c, "h3"), m.group(1) if m else "",
                                   num(re.sub(r"m².*", "", tr[1])) if len(tr) > 1 else 0.0,
                                   num(txt(c, 'p[class*="text-[20px]"]'))))
            if not fresh:
                break
            time.sleep(1.0)
        return decrire([x for x in out if dans_perimetre(x)], known_ids)


class Vaneau:
    name = "vaneau"
    URL = "https://www.vaneau.fr/fr/vaneau-search/search"

    def collect(self, known_ids=frozenset()):
        out, off = [], 0
        while True:
            d = requests.get(self.URL, params={"field_ad_type[eq]": "buying", "offset": off, "limit": 100, "mode": "list"},
                             headers=UA, timeout=60).json()
            cards = BeautifulSoup(d.get("html", ""), "html.parser").select("div.property__search-item")
            for c in cards:
                nom = txt(c, ".property-name")
                cp = cp_from_ville(nom) or ("92200" if "neuilly" in nom.lower() else "")
                url = c.get("data-url", "")
                out.append(annonce(self.name, c.get("data-node-id"), url if url.startswith("http") else "https://www.vaneau.fr" + url,
                                   nom, cp, num(re.sub(r"m².*", "", txt(c, ".property-surface"))), num(txt(c, ".property-price"))))
            off += 100
            if not cards or off >= int(d.get("total") or 0):
                break
            time.sleep(1.0)
        return decrire([x for x in out if dans_perimetre(x)], known_ids)


class EngelVoelkers:
    """Pages thématiques (35 annonces max par page côté serveur) : on prend des pages étroites."""
    name = "engel-voelkers"
    BASE = "https://www.engelvoelkers.com"
    PAGES = ["/fr/fr/propriete/res/vendre/maison/ile-de-france/paris/16e-arrondissement",
             "/fr/fr/propriete/res/vendre/maison/ile-de-france/neuilly-sur-seine",
             "/fr/fr/propriete/res/vendre/maison/ile-de-france/paris",
             "/fr/fr/propriete/res/vendre/immobilier/luxe/ile-de-france/paris"]

    def collect(self, known_ids=frozenset()):
        out, ids = [], set()
        for path in self.PAGES:
            h = requests.get(self.BASE + path, headers=UA, timeout=40).text
            m = re.search(r'<script id="__NEXT_DATA__" type="application/json"[^>]*>(.*?)</script>', h, re.S)
            if not m:
                continue
            qs = json.loads(m.group(1))["props"]["pageProps"].get("dehydratedState", {}).get("queries", [])
            for q in qs:
                if q.get("queryKey", [None])[0] != "listings":
                    continue
                for it in (q["state"].get("data") or {}).get("listings", []):
                    L = it.get("listing")
                    if not L or L["id"] in ids:
                        continue
                    ids.add(L["id"])
                    loc = " ".join(c["text"] for c in L.get("addressComponents", [])
                                   if c.get("placeType") in ("locality", "sublocality_level_1"))
                    cp = cp_from_ville(loc) or ("92200" if "neuilly" in loc.lower() else "")
                    if not cp and re.search(r"\bparis\b", loc, re.I):
                        cp = cp_from_ville(L.get("profile", {}).get("title", ""))
                    a = L.get("area") or {}
                    surf = (a.get("livingSurface") or {}).get("min") or (a.get("totalSurface") or {}).get("min") or 0
                    prix = 0 if L.get("hasPriceOnRequest") else ((L.get("price") or {}).get("salesPrice") or {}).get("min") or 0
                    out.append(annonce(self.name, L.get("displayId") or L["id"], f"{self.BASE}/fr/fr/exposes/{L['id']}",
                                       (L.get("profile") or {}).get("title", ""), cp, float(surf), float(prix),
                                       commune=loc))
            time.sleep(1.0)
        return decrire([x for x in out if dans_perimetre(x)], known_ids)


AGENCES = {"sothebys": Sothebys, "feau": Feau, "kretz": Kretz, "junot": Junot,
           "coldwell": Coldwell, "vaneau": Vaneau, "engel-voelkers": EngelVoelkers}

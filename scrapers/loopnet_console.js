/**
 * LOOPNET CONSOLE SCRAPER
 *
 * 1. Ouvre https://www.loopnet.fr/recherche/bureaux/paris---france/a-vendre/
 * 2. F12 → Console
 * 3. Colle ce script → Entrée
 * 4. Attends que ça finisse → copie le JSON
 * 5. Colle dans IMMOCAM/data/loopnet_raw.json
 */

(async () => {
  const SURFACE_MIN = 300;
  const SURFACE_MAX = 700;
  const PRIX_MAX = 5000000;
  const MAX_PAGES = 30;

  console.log("🏢 LoopNet Scraper — démarrage...");

  // Trouver le pageguid dans la page
  let pageguid = null;
  const scripts = document.querySelectorAll("script");
  for (const s of scripts) {
    const match = s.textContent.match(/pageguid['"]\s*:\s*['"]([a-f0-9-]{36})/i);
    if (match) { pageguid = match[1]; break; }
  }
  // Fallback: chercher dans le DOM
  if (!pageguid) {
    const allText = document.documentElement.innerHTML;
    const m = allText.match(/[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}/);
    if (m) pageguid = m[0];
  }

  if (!pageguid) {
    console.error("❌ pageguid non trouvé. Es-tu sur une page de recherche LoopNet ?");
    return;
  }
  console.log("✅ pageguid:", pageguid);

  const allDeals = [];
  let totalIds = 0;

  for (let pg = 1; pg <= MAX_PAGES; pg++) {
    try {
      const resp = await fetch("/services/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          pageguid,
          pageNumber: pg,
          criteria: {
            PropertyTypes: 536870920, // ForSale + Office
            Country: "FR",
            State: "PAR",
            GeographyFilters: [{
              GeographyId: 393,
              GeographyType: 1,
              Display: "Paris",
            }],
          }
        })
      });

      if (!resp.ok) {
        console.warn(`Page ${pg}: HTTP ${resp.status}`);
        break;
      }

      const data = await resp.json();
      const html = data.SearchPlacards?.Html || "";
      if (!html) break;

      if (pg === 1) {
        totalIds = (data.AllListingIds || []).length;
        console.log(`📊 Total annonces: ${totalIds}`);
      }

      // Parser le HTML
      const parser = new DOMParser();
      const doc = parser.parseFromString(html, "text/html");
      const cards = doc.querySelectorAll("article");

      let pageCount = 0;
      for (const card of cards) {
        const text = card.innerText || "";
        const link = card.querySelector("a[href*='/annonce/']");
        const url = link ? link.href : "";

        // Surface
        const surfMatch = text.match(/(\d[\d\s]*)\s*m[²2]/);
        if (!surfMatch) continue;
        const surface = parseInt(surfMatch[1].replace(/\s/g, ""));

        // Prix (montant global, pas loyer)
        let prix = 0;
        const prixMatches = text.matchAll(/([\d\s.,]+)\s*€/g);
        for (const pm of prixMatches) {
          const val = parseFloat(pm[1].replace(/[\s.]/g, "").replace(",", "."));
          if (val > 10000) prix = Math.max(prix, val);
        }

        // Adresse
        const cpMatch = text.match(/(\d{5})/);
        const cp = cpMatch ? cpMatch[1] : "";

        // Filtres
        if (surface < SURFACE_MIN || surface > SURFACE_MAX) continue;
        if (prix <= 0 || prix > PRIX_MAX) continue;

        allDeals.push({
          source: "loopnet",
          url: url.startsWith("http") ? url : "https://www.loopnet.fr" + url,
          date_scrape: new Date().toISOString().split("T")[0],
          localisation: {
            adresse: text.split("|")[0]?.trim() || "",
            code_postal: cp,
            commune: "Paris",
            departement: cp.substring(0, 2) || "75",
          },
          bien: {
            type: "bureaux",
            surface_m2: surface,
          },
          financier: {
            prix_affiche: prix,
            prix_m2: Math.round(prix / surface),
          },
          annonce: {
            titre: `Bureaux ${surface}m²`,
            description: text.substring(0, 300),
          },
        });
        pageCount++;
      }

      console.log(`  Page ${pg}: ${cards.length} cards, ${pageCount} matchent`);
      if (cards.length === 0) break;

      await new Promise(r => setTimeout(r, 1500));
    } catch (e) {
      console.error(`Page ${pg}:`, e);
      break;
    }
  }

  console.log(`\n✅ ${allDeals.length} biens extraits sur ${totalIds} total`);
  console.log("📋 Copie le JSON ci-dessous :");

  // Stocker dans window pour récup facile
  window.__LOOPNET_DATA = allDeals;

  // Copier dans le presse-papier
  const jsonStr = JSON.stringify(allDeals, null, 2);
  try {
    await navigator.clipboard.writeText(jsonStr);
    console.log("✅ JSON copié dans le presse-papier !");
  } catch {
    console.log("⚠️ Copie auto échouée. Tape: copy(JSON.stringify(window.__LOOPNET_DATA))");
  }

  // Afficher un résumé
  console.table(allDeals.map(d => ({
    surface: d.bien.surface_m2 + "m²",
    prix: (d.financier.prix_affiche / 1e6).toFixed(2) + "M€",
    "€/m²": d.financier.prix_m2,
    cp: d.localisation.code_postal,
    url: d.url.substring(0, 60),
  })));
})();

(function(){
  var all  = JSON.parse(sessionStorage.getItem("_SL")||"[]");
  var seen = JSON.parse(sessionStorage.getItem("_SL_seen")||"{}");

  // --- 1. Récupère le tableau d'annonces, peu importe le format ---
  function findClassifieds(){
    // a) Ancien format Pages Router
    var nd = document.getElementById("__NEXT_DATA__");
    if(nd){
      try{
        var sr = JSON.parse(nd.textContent).props.pageProps.searchResponse;
        if(sr && sr.classifieds) return {list:sr.classifieds, pg:sr.pagination||{}, via:"__NEXT_DATA__"};
      }catch(e){}
    }
    // b) Nouveau format App Router : stream RSC dans window.__next_f
    var blob = "";
    if(window.__next_f) window.__next_f.forEach(function(c){ if(c && typeof c[1]==="string") blob += c[1]; });
    if(!blob) [].forEach.call(document.scripts, function(s){ blob += s.textContent; });

    // brace-matching pour extraire le tableau qui suit une clé "classifieds"
    function extractArrayAfter(key){
      var k = blob.indexOf('"'+key+'"');
      while(k !== -1){
        var i = blob.indexOf("[", k);
        if(i !== -1){
          var depth=0, inStr=false, esc=false;
          for(var j=i;j<blob.length;j++){
            var ch=blob[j];
            if(inStr){ if(esc)esc=false; else if(ch==="\\")esc=true; else if(ch==='"')inStr=false; continue; }
            if(ch==='"'){inStr=true;continue;}
            if(ch==="["||ch==="{")depth++;
            else if(ch==="]"||ch==="}"){ depth--; if(depth===0){
              try{ var arr=JSON.parse(blob.slice(i,j+1)); if(arr.length) return arr; }catch(e){}
              break;
            }}
          }
        }
        k = blob.indexOf('"'+key+'"', k+1);
      }
      return null;
    }
    var list = extractArrayAfter("classifieds") || extractArrayAfter("listings") || extractArrayAfter("results");
    if(list) return {list:list, pg:{}, via:"__next_f (RSC)"};
    return null;
  }

  var found = findClassifieds();
  if(!found){ console.log("❌ Annonces introuvables — tape: copy([].map.call(document.scripts,s=>s.textContent.slice(0,200)).join('\\n')) et envoie-moi"); return; }

  // --- 2. Mapping défensif (les clés peuvent avoir bougé) ---
  function g(o, path, def){ try{ return path.split(".").reduce(function(a,k){return a[k];}, o); }catch(e){ return def; } }
  var n=0;
  found.list.forEach(function(c){
    var id = ""+(c.idAnnonce||c.id||c.listingId||g(c,"localisation.adresse","")+g(c,"space",""));
    if(seen[id]) return; seen[id]=1;

    var prix = g(c,"price.buy.price.value", 0) || c.price || c.prix || 0;
    var pm2  = Math.round(g(c,"price.buy.priceBySquareMeter.value", 0) || 0);
    var surf = c.space || c.surface || c.surfaceTotale || 0;
    var lo   = c.localisation || c.location || {};
    var cp   = lo.codePostal || lo.zipCode || "";
    var geo  = lo.geoLocation || lo.geo || {};
    var url  = c.detailUrl || c.url || "";
    if(url && url.indexOf("http")<0) url = "https://www.seloger-bureaux-commerces.com"+url;

    n++;
    all.push({
      source:"seloger-bc", url:url, date_scrape:new Date().toISOString().split("T")[0],
      localisation:{ adresse:lo.adresse||lo.address||"", code_postal:cp, commune:lo.nomVille||lo.city||"",
        departement:lo.codeDepartement||cp.substring(0,2)||"", latitude:geo.latitude||null, longitude:geo.longitude||null },
      bien:{ type:"bureaux", surface_m2:surf },
      financier:{ prix_affiche:prix, prix_m2:pm2 || Math.round(prix/Math.max(surf,1)) },
      annonce:{ titre:(c.cardTitle||"Bureau")+" "+surf+"m2 "+(lo.nomVille||lo.city||""),
        description:(c.cardDescription||c.description||"").substring(0,300) }
    });
  });

  sessionStorage.setItem("_SL", JSON.stringify(all));
  sessionStorage.setItem("_SL_seen", JSON.stringify(seen));
  console.log("✅ via "+found.via+" | +"+n+" | Total: "+all.length);
  if(n>0 && all.length===n) console.log("🔎 Structure 1er bien (vérifie le mapping):", JSON.stringify(found.list[0]).substring(0,600));
  console.log("→ Page suivante puis re-exécute. Fini? copy(sessionStorage.getItem(\"_SL\"))");
})();

// JLL scraper — methode 1: __NEXT_DATA__ (donnees deja dans la page)
var d=[];
try{
  var nd=JSON.parse(document.getElementById("__NEXT_DATA__").textContent);
  // Explorer la structure pour trouver les proprietes
  console.log("NEXT_DATA keys:", Object.keys(nd));
  console.log("props keys:", nd.props?Object.keys(nd.props):"none");
  var pp=nd.props&&nd.props.pageProps?nd.props.pageProps:{};
  console.log("pageProps keys:", Object.keys(pp));
  // Chercher les items dans differents chemins possibles
  var items=pp.properties||pp.items||pp.listings||pp.searchResults||(pp.data&&pp.data.properties&&pp.data.properties.items)||[];
  if(pp.dehydratedState){
    console.log("dehydratedState found, checking queries...");
    var queries=pp.dehydratedState.queries||[];
    queries.forEach(function(q,i){
      console.log("Query "+i+":", q.queryKey, q.state&&q.state.data?Object.keys(q.state.data):"no data");
      var qd=q.state&&q.state.data?q.state.data:{};
      if(qd.properties&&qd.properties.items){items=qd.properties.items;console.log("FOUND "+items.length+" items in query "+i)}
    });
  }
  if(!items.length){
    // Dump complet pour debug
    console.log("pageProps dump:", JSON.stringify(pp).substring(0,2000));
  }
  console.log("Items trouves: "+items.length);
  items.forEach(function(it){
    var surf=0;
    if(it.surfaceAreas&&it.surfaceAreas.length>0){var sa=it.surfaceAreas[0].value;surf=sa?(sa.max||sa.min||0):0}
    if(!surf&&it.surfaceArea)surf=it.surfaceArea.max||it.surfaceArea.min||it.surfaceArea||0;
    var prix=0;
    if(it.salePrice&&it.salePrice.amount)prix=it.salePrice.amount;
    // Si prix est par m2, multiplier
    if(prix>0&&prix<50000&&surf>0)prix=prix*surf;
    var cp=it.postcode||"";
    var dept=cp.substring(0,2)||"75";
    d.push({source:"jll",url:"https://immobilier.jll.fr"+(it.pageUrl||""),date_scrape:new Date().toISOString().split("T")[0],localisation:{adresse:it.address||"",code_postal:cp,commune:it.city||"",departement:dept,latitude:it.latitude||null,longitude:it.longitude||null},bien:{type:"bureaux",surface_m2:surf},financier:{prix_affiche:prix,prix_m2:surf>0?Math.round(prix/surf):0},annonce:{titre:it.title||"",description:""}});
  });
}catch(e){console.log("Erreur NEXT_DATA:",e)}

// Si pas de resultats via NEXT_DATA, essayer le fetch GraphQL avec les bons headers
if(d.length===0){
  console.log("Tentative GraphQL...");
  // Recuperer les cookies/headers de la page
  var csrfMeta=document.querySelector("meta[name='csrf-token']");
  var csrf=csrfMeta?csrfMeta.content:"";
  (async function(){
    // D'abord, intercepter la vraie query en regardant le network
    // Tester plusieurs formats de query
    var queries=[
      {operationName:"SearchResults",variables:{market:"FR",language:"fr",propertyTypes:["office"],tenureTypes:["sale"],regions:["Ile-de-France"],take:"50",skip:0}},
      {operationName:"SearchResults",variables:{market:"FR",language:"fr",propertyTypes:["office"],tenureTypes:["sale"],regions:["Ile-de-France"],take:50,skip:0}},
    ];
    // Ajouter la query GraphQL
    var gql="query SearchResults($market:String!,$language:String!,$propertyTypes:[String!],$tenureTypes:[String!],$regions:[String!],$take:IntString,$skip:Int){properties(market:$market,language:$language,propertyTypes:$propertyTypes,tenureTypes:$tenureTypes,regions:$regions,take:$take,skip:$skip){count items{id title address city postcode region latitude longitude salePrice{amount currency unit}surfaceAreas{value{min max}unit}pageUrl}}}";
    for(var q of queries){
      q.query=gql;
      try{
        var resp=await fetch("/api/graphql",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(q)});
        console.log("Status:",resp.status);
        var txt=await resp.text();
        console.log("Response (500 chars):",txt.substring(0,500));
        if(resp.ok){
          var data=JSON.parse(txt);
          if(data.data&&data.data.properties){
            console.log("GraphQL OK! "+data.data.properties.count+" total, "+data.data.properties.items.length+" items");
            break;
          }
        }
      }catch(e){console.log("GraphQL error:",e)}
    }
  })();
}else{
  console.log("FINI! "+d.length+" biens via NEXT_DATA");
  console.table(d.slice(0,15).map(function(x){return{surf:x.bien.surface_m2+"m2",prix:x.financier.prix_affiche>1e6?(x.financier.prix_affiche/1e6).toFixed(2)+"M":x.financier.prix_affiche,pm2:x.financier.prix_m2,cp:x.localisation.code_postal,ville:x.localisation.commune}}));
  window._JLL=d;
  console.log("Tape: copy(JSON.stringify(window._JLL))");
}

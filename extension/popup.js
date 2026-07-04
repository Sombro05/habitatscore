document.getElementById("btn").addEventListener("click", () => {
  const status = document.getElementById("status");
  const dataDiv = document.getElementById("data");

  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    const tab = tabs[0];

    const sitesImmo = ["leboncoin.fr", "seloger.com", "pap.fr", "logic-immo.com",
                       "bienici.com", "orpi.com", "century21.fr", "laforet.com"];
    const estSiteImmo = sitesImmo.some(s => tab.url.includes(s));
    if (!estSiteImmo) {
      status.className = "err";
      status.style.display = "block";
      status.innerText = "⚠️ Ouvrez une annonce immobilière.";
      return;
    }

    chrome.tabs.sendMessage(tab.id, { action: "extraire" }, (data) => {
      if (!data) {
        status.className = "err";
        status.style.display = "block";
        status.innerText = "❌ Impossible de lire la page. Rechargez-la.";
        return;
      }

      // Afficher les données extraites
      status.className = "ok";
      status.style.display = "block";
      status.innerText = "✅ Données extraites !";

      dataDiv.innerHTML = `
        <b>Ville :</b> ${data.ville || "—"}<br>
        <b>Code postal :</b> ${data.code_postal || "—"}<br>
        <b>Prix :</b> ${data.prix ? data.prix.toLocaleString() + " €" : "—"}<br>
        <b>Surface :</b> ${data.surface ? data.surface + " m²" : "—"}<br>
        <b>Type :</b> ${data.type_bien || "—"}<br>
        <b>DPE :</b> ${data.dpe || "—"}
      `;

      // Construire l'URL ImmoScore avec les paramètres
      // Nettoyer la ville : garder uniquement le nom avant le code postal
      const villeClean = (data.ville || "").split(/\s+\d{5}/)[0].trim();

      const params = new URLSearchParams({
        ville:       villeClean,
        code_postal: data.code_postal || "",
        prix:        data.prix || "",
        surface:     data.surface || "",
        type_bien:   data.type_bien || "Appartement",
        dpe:         data.dpe || "",
      });

      // Ouvrir ImmoScore avec les données pré-remplies
      const immoscoreUrl = `http://localhost:8501/?${params.toString()}`;
      chrome.tabs.create({ url: immoscoreUrl });
    });
  });
});
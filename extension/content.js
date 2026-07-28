const API_URL = "https://immoscore-api-pppe.onrender.com";

async function scorerAnnonce(ville, surface, prix, typeBien, dpe) {
  try {
    const params = new URLSearchParams({
      ville, surface, prix, type_bien: typeBien, 
      dpe: dpe || "E"  // E par défaut si non renseigné
    });
    const res = await fetch(`${API_URL}/score?${params}`);
    if (!res.ok) return null;
    return await res.json();
  } catch (e) { return null; }
}

function couleurScore(score) {
  if (score >= 65) return "#27AE60";
  if (score >= 40) return "#E67E22";
  return "#E74C3C";
}

// Sélecteurs par site
const SELECTEURS = {
  "leboncoin.fr":   '[data-qa-id="aditem_container"], [class*="styles_adCard"]',
  "seloger.com": '[id^="classified-card-"]',
  "pap.fr":         '[class*="property-card"], [class*="listing-item"]',
  "logic-immo.com": '[class*="annonce"], [class*="property-card"]',
  "bienici.com":    '[class*="realEstateCard"], [class*="announcement"]',
  "orpi.com":       '[class*="property-card"], [class*="annonce"]',
  "century21.fr":   '[class*="property-card"], [class*="bien"]',
  "laforet.com":    '[class*="property-card"], [class*="bien"]',
};

function getSiteName() {
  const host = window.location.hostname;
  for (const site of Object.keys(SELECTEURS)) {
    if (host.includes(site)) return site;
  }
  return null;
}

function extraireCartes() {
  const site = getSiteName();
  if (!site) return [];

  const sel = SELECTEURS[site];
  const toutes = [...document.querySelectorAll(sel)];

  return toutes.filter(carte => {
    const parent = carte.parentElement?.closest(sel);
    return parent === null;
  });
}

function extraireInfoCarte(carte) {
  const texte = carte.innerText || "";

  // Prix
  const prixMatch = texte.match(/(\d[\d\s]*)\s*€/);
  const prix = prixMatch ? parseInt(prixMatch[1].replace(/\s/g, "")) : null;

  // Surface
  const surfMatch = texte.match(/(\d+)\s*m²/i);
  const surface = surfMatch ? parseInt(surfMatch[1]) : null;

  // Ville
  const lignes = texte.split("\n").map(l => l.trim()).filter(Boolean);
  let ville = null;
  for (const l of lignes) {
    if (/\b\d{5}\b/.test(l) && l.length < 80 && !l.includes("{") && !l.includes(".")) {
      if (l.includes(",") && l.includes("(")) {
        ville = l.split(",").pop().replace(/\(?\d{5}\)?/g, "").trim();
      } else if (l.includes("(") && l.includes(")")) {
        ville = l.replace(/\(?\d{5}\)?/g, "").replace(/[,()]/g, "").trim();
      } else {
        const match = l.match(/^(.*?)\s+\d{5}/);
        ville = match?.[1]?.trim() || null;
      }
      if (ville) break;
    }
  }

  // Type de bien
  const texteLower = texte.toLowerCase();
  const typeBien = (texteLower.includes("maison") || texteLower.includes("villa"))
    ? "Maison" : "Appartement";

  // DPE
  const dpeImg = carte.querySelector('img[alt*="nergie"]');
  let dpe = null;
  if (dpeImg) {
    const dpeMatch = dpeImg.alt.match(/[A-G]/);
    if (dpeMatch) dpe = dpeMatch[0];
  }

  return { prix, surface, ville, typeBien, dpe };
}

function ajouterBadge(carte, data) {
  carte.querySelectorAll(".habitatscore-badge").forEach(b => b.remove());

  const badge = document.createElement("div");
  badge.className = "habitatscore-badge";
  badge.style.cssText = `
    position: absolute; top: 8px; right: 8px;
    background: ${couleurScore(data.score)};
    color: white; border-radius: 6px; padding: 4px 8px;
    font-size: 12px; font-weight: 600; z-index: 999;
    display: flex; flex-direction: column; align-items: center;
    line-height: 1.4; box-shadow: 0 2px 6px rgba(0,0,0,0.3);
    cursor: default; min-width: 80px; text-align: center;
  `;

  const ecartTexte = data.ecart !== null
    ? `${data.ecart > 0 ? "+" : ""}${data.ecart.toFixed(1)}% vs marché` : "";

  badge.innerHTML = `
    <span style="font-size:14px;font-weight:700">${data.score}/100</span>
    <span style="font-size:10px;opacity:0.9">${ecartTexte}</span>
  `;

  const style = window.getComputedStyle(carte);
  if (style.position === "static") carte.style.position = "relative";
  carte.appendChild(badge);
}

function creerBarreFiltrage() {
  if (document.getElementById("habitatscore-barre")) return;
  
  // Afficher uniquement sur les pages de recherche immobilière Leboncoin
  const url = window.location.href;
  const estListeImmo = (
    (url.includes("leboncoin.fr/recherche") && url.includes("category=9")) ||
    (url.includes("seloger.com") && !url.includes("/annonce/"))
  );
  if (!estListeImmo) return;

  const barre = document.createElement("div");
  barre.id = "habitatscore-barre";
  barre.style.cssText = `
    position: fixed; top: 60px; right: 16px; z-index: 99999;
    background: white; border: 1px solid #ddd; border-radius: 10px;
    padding: 10px 14px; box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    font-family: sans-serif; font-size: 13px; width: 220px;
    cursor: grab; user-select: none;
  `;

  barre.innerHTML = `
    <div style="display:flex;align-items:center;margin-bottom:8px;cursor:grab">
      <span style="font-weight:600">🏠 HabitatScore</span>
    </div>
    <label style="font-size:12px;color:#444">Score minimum : <b id="habitatscore-valeur">0</b>/100</label>
    <input type="range" id="habitatscore-slider" min="0" max="100" value="0"
      style="width:100%;margin:6px 0;accent-color:#27AE60;cursor:pointer">
    <button id="habitatscore-reset" style="
      width:100%;padding:5px;border:1px solid #ddd;border-radius:6px;
      background:white;cursor:pointer;font-size:12px;margin-top:4px">
      Tout afficher
    </button>
  `;

  document.body.appendChild(barre);

  const slider = document.getElementById("habitatscore-slider");
  const valeur = document.getElementById("habitatscore-valeur");

  slider.addEventListener("input", () => {
    valeur.innerText = slider.value;
    appliquerFiltre(parseInt(slider.value));
  });

  document.getElementById("habitatscore-reset").addEventListener("click", () => {
    slider.value = 0;
    valeur.innerText = "0";
    appliquerFiltre(0);
  });

  // Drag & drop
  let isDragging = false, startX, startY, startLeft, startTop;
  barre.addEventListener("mousedown", (e) => {
    if (e.target === slider || e.target.id === "habitatscore-reset") return;
    isDragging = true;
    startX = e.clientX; startY = e.clientY;
    const rect = barre.getBoundingClientRect();
    startLeft = rect.left; startTop = rect.top;
    barre.style.cursor = "grabbing";
    barre.style.right = "auto";
    barre.style.left = startLeft + "px";
    barre.style.top = startTop + "px";
  });
  document.addEventListener("mousemove", (e) => {
    if (!isDragging) return;
    barre.style.left = (startLeft + e.clientX - startX) + "px";
    barre.style.top = (startTop + e.clientY - startY) + "px";
  });
  document.addEventListener("mouseup", () => {
    isDragging = false;
    barre.style.cursor = "grab";
  });
}

function appliquerFiltre(scoreMin) {
  observer.disconnect();
  const cartes = extraireCartes();

  cartes.forEach(carte => {
    const badge = carte.querySelector(".habitatscore-badge");
    if (!badge) { carte.style.display = ""; return; }

    const scoreText = badge.querySelector("span")?.innerText || "0";
    const score = parseInt(scoreText.replace("/100", "")) || 0;
    const parent = carte.closest("li, article") || carte;

    if (score >= scoreMin) {
      parent.style.display = ""; carte.style.display = "";
    } else {
      parent.style.display = "none";
    }
  });

  observer.observe(document.body, { childList: true, subtree: true });
}

async function analyserToutesLesCartes() {
  const cartes = extraireCartes();
  if (cartes.length === 0) return;

  // N'afficher la barre que si on a des annonces
  creerBarreFiltrage();

  for (const carte of cartes) {
    if (carte.querySelector(".habitatscore-badge")) continue;
    const info = extraireInfoCarte(carte);
    if (!info.prix || !info.surface || !info.ville) continue;

    const badgeLoad = document.createElement("div");
    badgeLoad.className = "habitatscore-badge";
    badgeLoad.style.cssText = `
      position: absolute; top: 8px; right: 8px;
      background: #95a5a6; color: white;
      border-radius: 6px; padding: 4px 8px;
      font-size: 11px; font-weight: 600;
      z-index: 999; box-shadow: 0 2px 6px rgba(0,0,0,0.3);
    `;
    badgeLoad.innerText = "...";
    const style = window.getComputedStyle(carte);
    if (style.position === "static") carte.style.position = "relative";
    carte.appendChild(badgeLoad);

    const result = await scorerAnnonce(info.ville, info.surface, info.prix, info.typeBien, info.dpe);
    badgeLoad.remove();
    if (result && !result.erreur) ajouterBadge(carte, result);
  }

  const slider = document.getElementById("habitatscore-slider");
  if (slider && parseInt(slider.value) > 0) {
    appliquerFiltre(parseInt(slider.value));
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", analyserToutesLesCartes);
} else {
  analyserToutesLesCartes();
}

let debounceTimer = null;
const observer = new MutationObserver(() => {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(() => {
    const sel = getSiteName() ? SELECTEURS[getSiteName()] : null;
    if (!sel) return;
    const sansBadge = [...document.querySelectorAll(sel)]
      .filter(c => !c.querySelector(".habitatscore-badge"));
    if (sansBadge.length > 0) analyserToutesLesCartes();
  }, 1000);
});
observer.observe(document.body, { childList: true, subtree: true });

// ── EXTRACTION PAGE ANNONCE ─────────────────────────────────────────────
function extraireAnnonce() {
  const data = {};
  const allText = document.body.innerText;
  const host = window.location.hostname;

  // ── PRIX ────────────────────────────────────
  if (host.includes("seloger.com")) {
    // SeLoger affiche "189 900 €" dans le texte
    const prixMatch = allText.match(/^([\d\s]+)\s*€/m);
    if (prixMatch) data.prix = parseInt(prixMatch[1].replace(/\s/g, ""));
  } else {
    const prixEl = document.querySelector('[data-qa-id="adview_price"]') ||
                   document.querySelector('[class*="price"]');
    if (prixEl) {
      data.prix = parseInt(prixEl.innerText.replace(/[^\d]/g, "")) || null;
    }
  }

  // ── SURFACE ─────────────────────────────────
  const surfaceDetailMatch = allText.match(/Surface\s+habitable\s*:?\s*([\d,.]+)\s*m²/i) ||
                             allText.match(/(\d+)\s*m²/i);
  if (surfaceDetailMatch) {
    data.surface = Math.round(parseFloat(surfaceDetailMatch[1].replace(",", ".")));
  }

  // ── VILLE + CODE POSTAL ─────────────────────
  if (host.includes("seloger.com")) {
    // SeLoger : "L'île-Saint Maurille, Les Ponts-de-Cé (49130)"
    const villeMatch = allText.match(/([^,\n]+),\s*[^\n(]+\((\d{5})\)/);
    if (villeMatch) {
      data.code_postal = villeMatch[2];
      // Prendre la ville principale (avant la virgule)
      data.ville = villeMatch[0].replace(/\(?\d{5}\)?/g, "").replace(/,.*$/, "").trim();
    } else {
      // Fallback : chercher code postal
      const cpMatch = allText.match(/\((\d{5})\)/);
      if (cpMatch) {
        data.code_postal = cpMatch[1];
        const lignes = allText.split("\n");
        for (const l of lignes) {
          if (l.includes(cpMatch[1])) {
            data.ville = l.replace(/\(?\d{5}\)?/g, "").replace(/[,()]/g, "").trim();
            break;
          }
        }
      }
    }
  } else {
    const locEl = document.querySelector('[data-qa-id="adview_location_informations"]') ||
                  document.querySelector('[class*="location"]');
    if (locEl) {
      const locText = locEl.innerText;
      const cpMatch = locText.match(/(\d{5})/);
      if (cpMatch) data.code_postal = cpMatch[1];
      data.ville = locText.replace(/\d{5}/, "").replace(/[,]/g, "").trim();
    }
  }

  // ── TYPE DE BIEN ────────────────────────────
  const titreEl = document.querySelector('h1') ||
                  document.querySelector('[data-qa-id="adview_title"]');
  if (titreEl) {
    const titre = titreEl.innerText.toLowerCase();
    data.type_bien = (titre.includes("maison") || titre.includes("villa"))
      ? "Maison" : "Appartement";
  }

  // ── DPE ─────────────────────────────────────
  if (host.includes("seloger.com")) {
    // SeLoger affiche le DPE avec une lettre dans un badge coloré
    const dpeEl = document.querySelector('[class*="dpe"], [class*="energy"], [aria-label*="DPE"]');
    if (dpeEl) {
      const dpeMatch = dpeEl.innerText.match(/^[A-G]$/);
      if (dpeMatch) data.dpe = dpeMatch[0];
    }
    // Fallback texte
    if (!data.dpe) {
      const dpeMatch = allText.match(/Consommation\s+énergie\s*[:\s]*([A-G])/i) ||
                       allText.match(/classe\s+([A-G])\s/i);
      if (dpeMatch) data.dpe = dpeMatch[1].toUpperCase();
    }
  } else {
    // DPE depuis la fiche annonce (élément actif = plus grand)
  const dpeEl = document.querySelector('[title="Classe énergie"] .h-sz-24') ||
                document.querySelector('[title="Classe énergie"] .h-sz-32');
  if (dpeEl && /^[A-G]$/.test(dpeEl.innerText.trim())) {
    data.dpe = dpeEl.innerText.trim();
  }
  }

  return data;
}

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "extraire") sendResponse(extraireAnnonce());
});

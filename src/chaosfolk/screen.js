// Read the screen for Chaosfolk. The engine evaluates this function in the page.
// Quatre modes :
//   voir      l'écran en texte pour un humain : une ligne par élément utile, avec sa référence [rN]
//   decrire   la cible d'un geste (rôle, nom, rang, hors de l'écran...), pour la retrouver au rejeu
//   chercher  les éléments visibles qui portent un libellé donné (geste écrit avec un libellé)
//   focus     l'élément qui a le focus clavier, en une ligne courte (key --times N)
(opts) => {
  // En lecture (voir, chercher), les noms sont ceux qu'un humain voit : sans le texte masqué
  // pour les lecteurs d'écran. Pour decrire, on garde le nom accessible complet, que le rejeu
  // retrouve avec get_by_role.
  const lecture = opts.mode !== 'decrire';

  // État propre au document. Un nouveau document repart de la mémoire transmise par le moteur :
  // un élément de même rôle, même nom et même rang garde sa référence, et une référence
  // n'est jamais redonnée à un autre élément.
  const etat = window.__horde || (window.__horde = {n: 0, cles: new Map(Object.entries(opts.cles || {}))});
  etat.n = Math.max(etat.n, opts.debut || 0);
  const vues = {};          // clés des éléments référencés pendant cette lecture
  const rangs = new Map();  // rang de chaque couple rôle et nom dans cette lecture

  const ROLES_FR = {button: 'bouton', link: 'lien', textbox: 'champ', searchbox: 'recherche',
    combobox: 'liste', checkbox: 'case', radio: 'choix', switch: 'interrupteur', tab: 'onglet',
    menuitem: 'menu', menuitemcheckbox: 'menu', menuitemradio: 'menu', option: 'option',
    slider: 'curseur', spinbutton: 'nombre', treeitem: 'element', clickable: 'zone cliquable'};
  const ROLE_SEL = {
    button: 'button,[role="button"],input[type="button"],input[type="submit"],input[type="reset"],summary',
    link: 'a[href],[role="link"]',
    textbox: 'input,textarea,[role="textbox"],[contenteditable="true"]',
    combobox: 'select,input,[role="combobox"]',
    checkbox: 'input[type="checkbox"],[role="checkbox"]',
    radio: 'input[type="radio"],[role="radio"]',
  };
  const SEL_INTER = 'a[href],button,input,select,textarea,summary,[role],[contenteditable="true"]';
  const SEL_ALERTE = '[data-sonner-toast],[role="alert"],[role="status"],.mantine-Notification-root';
  const CHAMPS = ['INPUT', 'SELECT', 'TEXTAREA'];

  // ---- outils ----
  const abrege = (s, max) => {
    s = (s || '').replace(/\s+/g, ' ').trim();
    return s.length > max ? s.slice(0, max - 3) + '...' : s;
  };
  const visibleSelonCss = (el) => !el.checkVisibility || el.checkVisibility({opacityProperty: true, visibilityProperty: true});
  const estVisible = (el) => {
    if (!(el instanceof Element) || !visibleSelonCss(el)) return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 1 && rect.height > 1;
  };
  // texte réservé aux lecteurs d'écran (VisuallyHidden, sr-only) : présent mais invisible
  const estMasque = (el) => {
    const style = getComputedStyle(el);
    if (style.position !== 'absolute' && style.position !== 'fixed') return false;
    return style.clip === 'rect(0px, 0px, 0px, 0px)' || style.clipPath === 'inset(50%)' ||
      (el.offsetWidth <= 1 && el.offsetHeight <= 1);
  };
  const texte = (el) => {
    let t = el.innerText || el.textContent || '';
    if (!lecture || !el.getElementsByTagName) return t;
    const descendants = el.getElementsByTagName('*');
    if (descendants.length > 40) return t;
    for (const x of descendants) {
      const cache = x.innerText;
      if (cache && estMasque(x)) t = t.replace(cache, ' ');
    }
    return t;
  };
  const texteDesIds = (ids) => ids.split(/\s+/)
    .map(id => { const x = document.getElementById(id); return x ? x.innerText : ''; }).join(' ').trim();

  const roleDe = (el) => {
    const explicite = el.getAttribute('role');
    if (explicite) return explicite.split(' ')[0];
    const tag = el.tagName;
    if (tag === 'A' && el.hasAttribute('href')) return 'link';
    if (tag === 'BUTTON' || tag === 'SUMMARY') return 'button';
    if (tag === 'SELECT') return 'combobox';
    if (tag === 'TEXTAREA') return 'textbox';
    if (tag === 'INPUT') {
      const type = (el.type || 'text').toLowerCase();
      if (['button', 'submit', 'reset', 'image', 'file'].includes(type)) return 'button';
      if (type === 'hidden') return null;
      if (type === 'checkbox') return 'checkbox';
      if (type === 'radio') return 'radio';
      if (type === 'range') return 'slider';
      if (type === 'number') return 'spinbutton';
      if (type === 'search') return 'searchbox';
      if (el.getAttribute('aria-haspopup') === 'listbox') return 'combobox';
      return 'textbox';
    }
    if (el.isContentEditable && el.getAttribute('contenteditable') !== null) return 'textbox';
    if (/^H[1-6]$/.test(tag)) return 'heading';
    return null;
  };
  // élément sans rôle qui se clique (curseur main), le plus haut de sa lignée
  const estCliquable = (el) => {
    if (['HTML', 'BODY', 'INPUT', 'SELECT', 'TEXTAREA', 'BUTTON', 'OPTION'].includes(el.tagName)) return false;
    let curseur;
    try { curseur = getComputedStyle(el).cursor; } catch (e) { return false; }
    if (curseur !== 'pointer') return false;
    const parent = el.parentElement;
    return !(parent && getComputedStyle(parent).cursor === 'pointer');
  };
  const nomDe = (el) => {
    const aria = el.getAttribute('aria-label');
    if (aria && aria.trim()) return aria.trim();
    const parIds = el.getAttribute('aria-labelledby');
    if (parIds) { const n = texteDesIds(parIds); if (n) return n; }
    const champ = CHAMPS.includes(el.tagName);
    if (champ) {
      if (el.id) {
        const etiquette = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
        if (etiquette && etiquette.innerText.trim()) return texte(etiquette).trim();
      }
      const englobante = el.closest('label');
      if (englobante && englobante !== el) { const t = texte(englobante).trim(); if (t) return t; }
      return (el.getAttribute('placeholder') || el.getAttribute('title') || el.getAttribute('name') || '').trim();
    }
    const t = texte(el).replace(/\s+/g, ' ').trim();
    if (t) return t;
    const image = el.querySelector && el.querySelector('img[alt]');
    if (image && image.alt.trim()) return image.alt.trim();
    const titre = el.getAttribute('title');
    if (titre) return titre.trim();
    const titreSvg = el.querySelector && el.querySelector('svg title');
    if (titreSvg) return titreSvg.textContent.trim();
    const icone = el.querySelector && el.querySelector('svg[class*="lucide-"]');
    if (icone) {
      const noms = (icone.getAttribute('class') || '').match(/lucide-([a-z0-9-]+)/g);
      if (noms) return 'icone ' + noms[noms.length - 1].replace('lucide-', '');
    }
    return '';
  };
  const valeurDe = (el) => {
    if (el.tagName === 'SELECT') return el.selectedOptions[0] ? el.selectedOptions[0].text : '';
    if (CHAMPS.includes(el.tagName) && !['checkbox', 'radio', 'button', 'submit', 'reset', 'file', 'image'].includes(el.type)) {
      if (el.type === 'password') return el.value ? '********' : '';
      return el.value;
    }
    if (el.isContentEditable && el.getAttribute('contenteditable') !== null) return el.innerText;
    return null;
  };

  // focus clavier et entrée en surbrillance (menu ou liste parcourus aux flèches)
  const actif = document.activeElement;
  const avecFocus = actif && actif !== document.body && actif !== document.documentElement ? actif : null;
  const idSurligne = avecFocus && avecFocus.getAttribute('aria-activedescendant');
  const surligne = idSurligne ? document.getElementById(idSurligne) : null;
  let focusAffiche = false;
  const enSurbrillance = (el) => el === surligne || el.hasAttribute('data-hovered') ||
    el.hasAttribute('data-highlighted') || el.hasAttribute('data-combobox-selected');

  // états entre parenthèses ; focus et surbrillance toujours en dernier (le moteur les repère)
  const etatsDe = (el, role, enCellule) => {
    const etats = [];
    if (el.disabled || el.getAttribute('aria-disabled') === 'true' || el.hasAttribute('data-disabled')) etats.push('désactivé');
    if (['checkbox', 'radio', 'switch', 'menuitemcheckbox', 'menuitemradio'].includes(role)) {
      const coche = (typeof el.checked === 'boolean') ? el.checked : el.getAttribute('aria-checked') === 'true';
      etats.push(coche ? 'coché' : 'non coché');
    }
    const courant = el.getAttribute('aria-current');
    if (el.getAttribute('aria-selected') === 'true' || (courant && courant !== 'false') ||
        el.getAttribute('aria-pressed') === 'true' || el.hasAttribute('data-active')) etats.push('actif');
    if (el.getAttribute('aria-expanded') === 'true') etats.push('ouvert');
    if (el.required || el.getAttribute('aria-required') === 'true') etats.push('obligatoire');
    if (el.getAttribute('aria-invalid') === 'true') {
      const decrit = el.getAttribute('aria-describedby');
      const message = decrit ? texteDesIds(decrit) : '';
      etats.push(message ? 'en erreur : "' + abrege(message, 60) + '"' : 'en erreur');
    }
    if (el.readOnly && role === 'textbox') etats.push('lecture seule');
    // dans une cellule de tableau, le focus est donné par la ligne finale (une ligne de tableau est longue)
    if (el === avecFocus && !enCellule) { etats.push('focus'); focusAffiche = true; }
    else if (enSurbrillance(el)) etats.push('en surbrillance');
    return etats;
  };

  // référence [rN] : `cle` (rôle et nom) permet de redonner la même référence à un élément recréé
  const refDe = (el, cle) => {
    let ref = el.getAttribute('data-horde-ref');
    if (cle !== undefined) {
      const rang = (rangs.get(cle) || 0) + 1;
      rangs.set(cle, rang);
      const cleRang = cle + '|' + rang;
      if (!ref) {
        const ancienne = etat.cles.get(cleRang);
        if (ancienne && !document.querySelector('[data-horde-ref="' + ancienne + '"]')) ref = ancienne;
      }
      if (!ref) ref = 'r' + (++etat.n);
      etat.cles.set(cleRang, ref);
      vues[cleRang] = ref;
    } else if (!ref) {
      ref = 'r' + (++etat.n);
    }
    el.setAttribute('data-horde-ref', ref);
    return ref;
  };

  // une ligne pour un élément interactif. Dans une cellule de tableau : pas le mot "bouton",
  // et `retirer` (le libellé de la ligne ou de la colonne) est ôté du nom
  const ligneInter = (el, role, options = {}) => {
    const nomComplet = nomDe(el);
    let nom = nomComplet;
    const retirer = options.retirer;
    if (retirer && nom !== retirer && nom.includes(retirer)) {
      const reste = nom.replace(retirer, ' ').replace(/\s+/g, ' ').trim();
      if (reste) nom = reste;
    }
    const ref = refDe(el, role + '|' + abrege(nomComplet, 80));
    if (options.entete && /^Filtrer par /i.test(nomComplet)) return '[' + ref + '] filtre';
    const mot = options.enCellule && role === 'button' ? '' : (ROLES_FR[role] || role);
    let s = '[' + ref + ']' + (mot ? ' ' + mot : '');
    const nomCourt = abrege(nom, options.maxNom || 80);
    if (nomCourt) s += ' "' + nomCourt + '"';
    else if (['button', 'link', 'clickable'].includes(role)) s += ' sans nom';
    const valeur = valeurDe(el);
    if (valeur !== null) {
      s += valeur ? ' = "' + abrege(valeur, 60) + '"' : ' (vide)';
      const indice = el.getAttribute('placeholder');
      if (!valeur && indice && abrege(indice, 80) !== nomCourt) s += ' indice "' + abrege(indice, 40) + '"';
    }
    const etats = etatsDe(el, role, options.enCellule);
    if (etats.length) s += ' (' + etats.join(', ') + ')';
    return s;
  };

  const cheminCss = (el) => {
    const parties = [];
    let e = el;
    while (e && e.nodeType === 1 && parties.length < 12) {
      if (e === document.body) { parties.unshift('body'); break; }
      if (e.id && !/[:]|mantine|radix|headless|^r\d|^_r_|\d{4,}/i.test(e.id)) { parties.unshift('#' + CSS.escape(e.id)); break; }
      let partie = e.tagName.toLowerCase();
      if (partie === 'svg' || e.namespaceURI !== 'http://www.w3.org/1999/xhtml') { e = e.parentElement; continue; }
      const parent = e.parentElement;
      if (parent) {
        const memes = Array.from(parent.children).filter(c => c.tagName === e.tagName);
        if (memes.length > 1) partie += ':nth-of-type(' + (memes.indexOf(e) + 1) + ')';
      }
      parties.unshift(partie);
      e = parent;
    }
    return parties.join(' > ');
  };

  // hors de l'écran et impossible à faire venir en faisant défiler : tiroir fermé (translateX(-100%)),
  // panneau fixe poussé hors de la fenêtre. Un élément dans une zone qui défile n'est pas hors de l'écran.
  const horsEcran = (el) => {
    const r = el.getBoundingClientRect();
    if (r.width <= 1 || r.height <= 1) return false;
    const dedans = r.right > 0 && r.bottom > 0 && r.left < window.innerWidth && r.top < window.innerHeight;
    if (dedans) return false;
    let fixe = false;
    for (let e = el; e && e !== document.documentElement; e = e.parentElement) {
      let style;
      try { style = getComputedStyle(e); } catch (x) { return false; }
      if (style.position === 'fixed') { fixe = true; break; }
      if (e !== el && /(auto|scroll|overlay)/.test(style.overflowX + ' ' + style.overflowY) &&
          (e.scrollWidth > e.clientWidth + 1 || e.scrollHeight > e.clientHeight + 1)) return false;
    }
    // un élément fixe ne bouge pas quand on fait défiler : hors de la fenêtre, il y reste
    if (fixe) return true;
    const x = r.left + window.scrollX, y = r.top + window.scrollY;
    const doc = document.documentElement;
    return x + r.width <= 0 || y + r.height <= 0 ||
      x >= Math.max(doc.scrollWidth, document.body ? document.body.scrollWidth : 0);
  };

  // ---- focus : l'élément qui a le focus clavier, sans toucher à la mémoire des références ----
  if (opts.mode === 'focus') {
    const actifEl = document.activeElement;
    if (!actifEl || actifEl === document.body || actifEl === document.documentElement) return {ligne: '', n: etat.n};
    let role = roleDe(actifEl);
    if (!(role && ROLES_FR[role]) && estCliquable(actifEl)) role = 'clickable';
    const nom = abrege(nomDe(actifEl), 60);
    const ref = refDe(actifEl);
    return {ligne: '[' + ref + '] ' + ((role && ROLES_FR[role]) || actifEl.tagName.toLowerCase()) + (nom ? ' "' + nom + '"' : ''),
      n: etat.n};
  }

  // ---- decrire : la cible d'un geste, pour le rejeu ----
  if (opts.mode === 'decrire') {
    const el = document.querySelector('[data-horde-ref="' + opts.ref + '"]');
    if (!el) return null;
    let role = roleDe(el);
    if (!role && estCliquable(el)) role = 'clickable';
    const nom = nomDe(el);
    let index = 0, nb = null;
    if (role && role !== 'clickable' && nom) {
      const selecteur = ROLE_SEL[role] || ('[role="' + role + '"]');
      const memes = Array.from(document.querySelectorAll(selecteur))
        .filter(x => roleDe(x) === role && nomDe(x) === nom && estVisible(x));
      index = Math.max(0, memes.indexOf(el));
      nb = memes.length;
    }
    return {role: role, nom: abrege(nom, 120), tag: el.tagName.toLowerCase(),
      ...((el.type === 'password' || /\b(?:current-password|new-password|one-time-code)\b/i.test(el.getAttribute('autocomplete') || '')) ? {sensitive: true} : {}),
      testid: el.getAttribute('data-testid') || el.getAttribute('data-test') || null,
      placeholder: el.getAttribute('placeholder'), texte: abrege(el.innerText || '', 120),
      css: cheminCss(el), index: index, nb: nb, ref: el.getAttribute('data-horde-ref'), hors_ecran: horsEcran(el)};
  }

  // ---- chercher : un libellé à la place d'une référence ----
  if (opts.mode === 'chercher') {
    const norme = (s) => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
    let libelle = (opts.libelle || '').trim().replace(/^\[|\]$/g, '');
    const avecRole = libelle.match(/^(?:bouton|lien|champ|liste|case|choix|menu|onglet|option|zone cliquable)\s+"(.*)"$/i);
    if (avecRole) libelle = avecRole[1];
    libelle = norme(libelle.replace(/^"|"$/g, ''));
    const exacts = [], proches = [];
    for (const el of new Set(document.querySelectorAll(SEL_INTER + ',[data-horde-ref]'))) {
      if (!estVisible(el)) continue;
      let role = roleDe(el);
      if (!(role && ROLES_FR[role])) {
        if (!el.hasAttribute('data-horde-ref') && !estCliquable(el)) continue;
        role = 'clickable';
      }
      const nom = norme(nomDe(el));
      if (!nom || !libelle) continue;
      if (nom === libelle) exacts.push([el, role]);
      else if (nom.includes(libelle) && proches.length < 6) proches.push([el, role]);
    }
    const presenter = ([el, role]) => ({ref: refDe(el), ligne: ROLES_FR[role] + ' "' + abrege(nomDe(el), 60) + '"'});
    return {exacts: exacts.slice(0, 8).map(presenter), proches: proches.map(presenter), n: etat.n};
  }

  // ---- voir : l'écran en texte ----
  const MAX = opts.max || 170;
  const sortie = [];
  let restant = 0;
  const hauteur = window.innerHeight;
  let pliMarque = false;
  const pousser = (ligne, el) => {
    if (sortie.length >= MAX) { restant++; return; }
    if (el && !pliMarque) {
      const rect = el.getBoundingClientRect();
      if (rect.top > hauteur) { sortie.push('--- plus bas, il faut faire défiler ---'); pliMarque = true; }
    }
    if (sortie[sortie.length - 1] !== ligne) sortie.push(ligne);
  };
  const texteDirect = (el) => {
    let t = '';
    for (const c of el.childNodes) if (c.nodeType === 3) t += c.textContent;
    return t.replace(/\s+/g, ' ').trim();
  };
  const estAlerte = (el) => el.matches(SEL_ALERTE);
  const roleAffiche = (el) => { const role = roleDe(el); return role && ROLES_FR[role] ? role : null; };

  const tableau = (table) => {
    const lignes = Array.from(table.querySelectorAll('tr')).filter(estVisible);
    if (!lignes.length) return;
    const tete = lignes[0].querySelector('th') && !lignes[0].querySelector('td') ? lignes.shift() : null;
    const cellules = (tr, max, libelleLigne, entete) => Array.from(tr.children).map(cellule => {
      const brut = texte(cellule).replace(/\s+/g, ' ').trim();
      const court = abrege(brut, max);
      const interactifs = Array.from(cellule.querySelectorAll(SEL_INTER + ',a'))
        .filter(x => estVisible(x) && (roleAffiche(x) || estCliquable(x)));
      if (!interactifs.length) return court;
      let avecTexte = !!court;
      const refs = interactifs.map(x => {
        if (brut && nomDe(x).startsWith(brut)) avecTexte = false;
        return ligneInter(x, roleAffiche(x) || 'clickable', {maxNom: 40, enCellule: true, retirer: libelleLigne, entete: entete});
      }).join(' ');
      return (avecTexte ? court + ' ' : '') + refs;
    });
    pousser('tableau (' + lignes.length + ' lignes)', table);
    if (tete) pousser('en-têtes : | ' + cellules(tete, 30, null, true).join(' | ') + ' |', tete);
    const limite = opts.complet ? 60 : 8;
    lignes.slice(0, limite).forEach(tr => {
      const premiere = tr.children.length > 1 ? texte(tr.children[0]).replace(/\s+/g, ' ').trim() : '';
      let ligne = '| ' + cellules(tr, 40, premiere).join(' | ') + ' |';
      if (estCliquable(tr) || tr.getAttribute('role') === 'button') {
        ligne = '[' + refDe(tr, 'ligne|' + abrege(texte(tr), 80)) + '] ligne cliquable ' + ligne;
      }
      pousser(ligne, tr);
    });
    if (lignes.length > limite) pousser('... ' + (lignes.length - limite) + ' autres lignes', null);
  };

  const dejaLus = new Set();  // menus flottants déjà donnés en tête : on ne les relit pas dans la page
  const parcourir = (el, seulementInteractifs) => {
    if (!(el instanceof Element) || dejaLus.has(el)) return;
    let affichage = '';
    try { affichage = getComputedStyle(el).display; } catch (e) {}
    if (!visibleSelonCss(el)) return;
    // un conteneur sans taille (portail de menu, pile de notifications) peut porter des enfants
    // visibles : on descend toujours, on n'affiche que ce qui a une taille
    const rect = el.getBoundingClientRect();
    if (affichage !== 'contents' && !(rect.width > 1 && rect.height > 1)) {
      for (const c of el.children) parcourir(c, seulementInteractifs);
      return;
    }
    if (['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE'].includes(el.tagName)) return;
    if (el.tagName === 'IFRAME') { pousser('[cadre intégré : contenu non lisible]', el); return; }
    const role = roleDe(el);
    if (role === 'heading' && !seulementInteractifs) {
      const niveau = parseInt(el.getAttribute('aria-level') || (el.tagName[1] || '3'), 10);
      const titre = abrege(texte(el), 100);
      if (titre) pousser('#'.repeat(Math.min(niveau, 4)) + ' ' + titre, el);
      return;
    }
    if (role && ROLES_FR[role]) { pousser(ligneInter(el, role), el); return; }
    if (!role && estCliquable(el)) {
      pousser(ligneInter(el, 'clickable'), el);
      for (const c of el.children) parcourir(c, true);
      return;
    }
    if (seulementInteractifs) { for (const c of el.children) parcourir(c, true); return; }
    if (estAlerte(el)) {
      const message = abrege(texte(el), 160);
      if (message) pousser('>> message : "' + message + '"', el);
      for (const c of el.querySelectorAll(SEL_INTER)) {
        const roleEnfant = roleAffiche(c);
        if (roleEnfant && estVisible(c)) pousser(ligneInter(c, roleEnfant), c);
      }
      return;
    }
    if (el.tagName === 'TABLE') { tableau(el); return; }
    if (el.tagName === 'IMG') {
      const alt = (el.getAttribute('alt') || '').trim();
      if (alt) pousser('[image "' + abrege(alt, 60) + '"]', el);
      return;
    }
    if (el.tagName === 'LABEL' && (el.htmlFor || el.querySelector('input,select,textarea'))) {
      for (const c of el.children) parcourir(c, true);
      return;
    }
    const direct = texteDirect(el);
    if (direct.length > 1 && !el.querySelector(SEL_INTER)) { pousser(abrege(texte(el), 160), el); return; }
    if (direct.length > 1) pousser(abrege(direct, 160), el);
    if (el.shadowRoot) for (const c of el.shadowRoot.children) parcourir(c, false);
    for (const c of el.children) parcourir(c, false);
  };

  const dialogues = Array.from(document.querySelectorAll('[role="dialog"],[role="alertdialog"],dialog[open]')).filter(estVisible);
  const notifications = Array.from(document.querySelectorAll(SEL_ALERTE)).filter(estVisible);
  if (dialogues.length) {
    const flottants = Array.from(document.querySelectorAll('[role="listbox"],[role="menu"]'))
      .filter(x => estVisible(x) && !dialogues.some(d => d.contains(x)));
    for (const d of dialogues) {
      const titre = abrege(nomDe(d) || (d.querySelector('h1,h2,h3,[class*="title"]') || {}).innerText || '', 80);
      pousser('=== fenêtre' + (titre ? ' "' + titre + '"' : '') + ' ===', null);
      for (const c of d.children) parcourir(c, false);
      pousser('=== fin de la fenêtre (le reste de la page est derrière) ===', null);
    }
    for (const f of flottants) for (const c of f.children) parcourir(c, false);
    for (const n of notifications) if (!dialogues.some(d => d.contains(n))) parcourir(n, false);
  } else {
    // un menu ou une liste qui vient de s'ouvrir est ce que l'humain regarde : lu d'abord, sans être noyé
    // en bas d'une longue page (portail à la fin du body). Une liste posée dans la page n'est pas flottante.
    const SEL_FLOTTANT = '[role="menu"],[role="listbox"],[data-radix-popper-content-wrapper],[class*="mantine-"][class*="-dropdown"]';
    const flotte = (el) => {
      if (el.matches('[data-radix-popper-content-wrapper],[class*="mantine-"][class*="-dropdown"]')) return true;
      let e = el;
      for (let i = 0; e && e !== document.body && i < 5; i++, e = e.parentElement) {
        const position = getComputedStyle(e).position;
        // une barre latérale fixe prend toute la hauteur ; un menu déroulant, non
        if (position === 'absolute' || position === 'fixed') return e.getBoundingClientRect().height < window.innerHeight * 0.9;
      }
      return false;
    };
    const menus = Array.from(document.querySelectorAll(SEL_FLOTTANT)).filter(x => estVisible(x) && flotte(x));
    const racines = menus.filter(x => !menus.some(y => y !== x && y.contains(x)));
    for (const menu of racines) {
      pousser('=== menu ouvert ===', null);
      for (const c of menu.children) parcourir(c, false);
      pousser('=== fin du menu ===', null);
      dejaLus.add(menu);
    }
    parcourir(document.body, false);
  }
  if (!sortie.length) sortie.push("(page blanche : rien ne s'affiche)");
  // la lecture suit l'ordre de la page, pas la fenêtre : faire défiler ne montre pas les éléments en trop
  if (restant) sortie.push('... (' + restant + ' éléments de plus' + (opts.complet ? ', non lus)' : ', utiliser "look --full")'));
  // le focus clavier sur un élément que l'écran ne montre pas : une ligne pour que Tab se voie
  if (avecFocus && !focusAffiche && estVisible(avecFocus)) {
    const role = roleDe(avecFocus);
    const nom = abrege(nomDe(avecFocus), 60);
    const ref = avecFocus.getAttribute('data-horde-ref');
    sortie.push('(focus clavier sur : ' + (ref ? '[' + ref + '] ' : '') +
      ((role && ROLES_FR[role]) || avecFocus.tagName.toLowerCase()) + (nom ? ' "' + nom + '"' : '') + ')');
  }
  return {lignes: sortie, titre: document.title, url: location.href, n: etat.n, cles: vues};
}

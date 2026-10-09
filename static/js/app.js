/* 0,00 28 — interface commune : panier, favoris, tiroirs, aperçu rapide, newsletter.
   Aucun innerHTML : tout le DOM est construit avec textContent / setAttribute (anti-XSS). */
(() => {
  'use strict';
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const NS = 'http://www.w3.org/2000/svg';
  const MAX_QTY = 10;
  const csrf = () => ($('meta[name="csrf-token"]') || {}).content || '';

  let I18N = {};
  try {
    const dataNode = document.getElementById('i18n-data');
    if (dataNode && dataNode.textContent) I18N = JSON.parse(dataNode.textContent);
  } catch {}
  const t = (k, fb = '') => I18N[k] != null ? I18N[k] : fb;
  const isRtl = document.documentElement.dir === 'rtl';
  const fmt = (n) => {
    const num = new Intl.NumberFormat('fr-FR').format(Number(n) || 0).replace(/[\u202f\u00a0]/g, '\u00a0');
    const curr = t('currency', 'DA');
    return isRtl ? `${num} ${curr}` : `${num}\u00a0${curr}`;
  };

  // ───── Stockage tolérant aux erreurs (navigation privée, quota) ─────
  const store = {
    get(key) { try { const v = JSON.parse(localStorage.getItem(key) || '[]'); return Array.isArray(v) ? v : []; } catch { return []; } },
    set(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* ignoré */ } },
  };
  const KEYS = { cart: 'z28.cart', wish: 'z28.wish' };

  // ───── Construction DOM sûre ─────
  const safePath = (p, prefix) => (typeof p === 'string' && p.startsWith(prefix) && !p.startsWith('//') ? p : '');
  function el(tag, attrs = {}, ...kids) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v === false || v == null) continue;
      if (k === 'class') node.className = v;
      else if (k === 'text') node.textContent = v;
      else if (k.startsWith('on')) node.addEventListener(k.slice(2), v);
      else node.setAttribute(k, v === true ? '' : String(v));
    }
    for (const kid of kids.flat()) if (kid != null && kid !== false) node.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
    return node;
  }
  function icon(name, cls = '') {
    const svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('class', 'icon ' + cls); svg.setAttribute('aria-hidden', 'true');
    const use = document.createElementNS(NS, 'use'); use.setAttribute('href', '#i-' + name);
    svg.append(use); return svg;
  }

  // ───── Notifications ─────
  function toast(message, kind = 'ok') {
    const zone = $('[data-toasts]'); if (!zone) return;
    const t = el('div', { class: 'toast' + (kind === 'error' ? ' toast--error' : ''), role: 'status' }, icon(kind === 'error' ? 'alert' : 'check'), message);
    zone.append(t); setTimeout(() => t.remove(), 3600);
  }

  async function api(url, body) {
    const res = await fetch(url, {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf(), Accept: 'application/json' },
      body: JSON.stringify(body || {}),
    });
    let data = {}; try { data = await res.json(); } catch { /* corps vide */ }
    return { ok: res.ok, status: res.status, data };
  }

  // ───── Panier ─────
  const getCart = () => store.get(KEYS.cart);
  const saveCart = (items) => { store.set(KEYS.cart, items); renderAll(); };
  const getWish = () => store.get(KEYS.wish);
  const saveWish = (items) => { store.set(KEYS.wish, items); renderAll(); };
  const itemFrom = (node) => {
    const d = node.dataset;
    return { id: Number(d.id), slug: d.slug || '', title: d.title || '', author: d.author || '', price: Number(d.price) || 0, cover: d.cover || '', stock: Number(d.stock) || 0 };
  };

  function addToCart(item, qty = 1, { open = true } = {}) {
    if (item.stock <= 0) { toast(t('sold_out', 'Ce livre est épuisé.'), 'error'); return false; }
    const cart = getCart(); const line = cart.find((l) => l.id === item.id);
    const wanted = (line ? line.qty : 0) + qty; const cap = Math.min(item.stock, MAX_QTY);
    if (line) { line.qty = Math.min(wanted, cap); Object.assign(line, item, { qty: line.qty }); } else cart.push({ ...item, qty: Math.min(qty, cap) });
    saveCart(cart);
    if (wanted > cap) toast(t('qty_limited', 'Quantité limitée à {n} pour ce livre.').replace('{n}', cap), 'error'); else toast(t('added_cart', 'Ajouté au panier'));
    if (open) openDrawer('cart');
    return true;
  }
  function setQty(id, qty) {
    const cart = getCart(); const line = cart.find((l) => l.id === id); if (!line) return;
    line.qty = Math.max(1, Math.min(qty, line.stock || MAX_QTY, MAX_QTY)); saveCart(cart);
  }
  const removeFromCart = (id) => saveCart(getCart().filter((l) => l.id !== id));
  const clearCart = () => saveCart([]);
  const subtotal = () => getCart().reduce((s, l) => s + l.price * l.qty, 0);

  function coverImg(item, w = 64) {
    const src = safePath(item.cover, '/static/');
    return src ? el('img', { src, alt: '', width: w, height: Math.round(w * 1.5), loading: 'lazy' }) : el('span', { class: 'book__ph' }, '');
  }
  const bookHref = (slug) => '/livre/' + encodeURIComponent(slug);

  function cartLine(l) {
    const maxed = l.qty >= Math.min(l.stock || MAX_QTY, MAX_QTY);
    return el('div', { class: 'line' },
      coverImg(l),
      el('div', {},
        el('h3', {}, el('a', { href: bookHref(l.slug) }, l.title)),
        el('p', { class: 'line__author' }, l.author),
        el('div', {},
          el('div', { class: 'qty', role: 'group', 'aria-label': t('qty_of', 'Quantité de {title}').replace('{title}', l.title) },
            el('button', { type: 'button', 'aria-label': t('decrease', 'Diminuer'), disabled: l.qty <= 1, onclick: () => setQty(l.id, l.qty - 1) }, icon('minus')),
            el('output', {}, String(l.qty)),
            el('button', { type: 'button', 'aria-label': t('increase', 'Augmenter'), disabled: maxed, onclick: () => setQty(l.id, l.qty + 1) }, icon('plus'))),
          el('button', { type: 'button', class: 'link-remove', onclick: () => removeFromCart(l.id) }, t('remove', 'Retirer'))),
        l.stock > 0 && l.stock <= 3 ? el('p', { class: 'line__warn' }, t('more_than_stock', 'Plus que {n} en stock').replace('{n}', l.stock)) : null,
        l.stock <= 0 ? el('p', { class: 'line__warn' }, t('line_soldout_cart', 'Épuisé : retirez ce livre pour commander')) : null),
      el('div', { class: 'line__price nums' }, fmt(l.price * l.qty)));
  }

  function emptyState(iconName, title, text, href, label) {
    return el('div', { class: 'empty' }, icon(iconName), el('h3', {}, title), el('p', {}, text), el('a', { class: 'btn', href }, label));
  }

  function renderCart() {
    const body = $('[data-cart-body]'); if (!body) return;
    const cart = getCart(); body.replaceChildren();
    const foot = $('[data-cart-foot]');
    if (!cart.length) {
      body.append(emptyState('bag', t('cart_empty', 'Votre panier est vide'), t('cart_empty_hint', 'Ajoutez un livre : vous ne payez rien avant la livraison.'), '/catalogue', t('browse_catalog', 'Parcourir le catalogue')));
      if (foot) foot.hidden = true; return;
    }
    cart.forEach((l) => body.append(cartLine(l)));
    if (foot) { foot.hidden = false; $('[data-cart-subtotal]', foot).textContent = fmt(subtotal()); }
  }

  function renderWish() {
    const body = $('[data-wish-body]'); if (!body) return;
    const wish = getWish(); body.replaceChildren();
    if (!wish.length) { body.append(emptyState('heart', t('wish_empty', 'Aucun favori'), t('wish_empty_hint', 'Touchez le cœur d\'un livre pour le retrouver ici.'), '/catalogue', t('browse_catalog', 'Parcourir le catalogue'))); return; }
    wish.forEach((w) => body.append(el('div', { class: 'line' },
      coverImg(w),
      el('div', {}, el('h3', {}, el('a', { href: bookHref(w.slug) }, w.title)), el('p', { class: 'line__author' }, w.author),
        el('div', {}, el('button', { type: 'button', class: 'btn btn--sm', disabled: w.stock <= 0, onclick: () => addToCart(w) }, w.stock <= 0 ? t('sold_out_short', 'Épuisé') : t('add_to_cart', 'Ajouter au panier')),
          el('button', { type: 'button', class: 'link-remove', onclick: () => toggleWish(w) }, t('remove', 'Retirer')))),
      el('div', { class: 'line__price nums' }, fmt(w.price)))));
  }

  function renderCounts() {
    const c = getCart().reduce((s, l) => s + l.qty, 0); const w = getWish().length;
    $$('[data-cart-count]').forEach((n) => { n.textContent = String(c); n.dataset.zero = c === 0 ? 'true' : 'false'; });
    $$('[data-wish-count]').forEach((n) => { n.textContent = String(w); n.dataset.zero = w === 0 ? 'true' : 'false'; });
  }
  function renderHearts() {
    const ids = new Set(getWish().map((w) => w.id));
    $$('[data-wish]').forEach((btn) => { const host = btn.closest('[data-book]'); if (host) btn.setAttribute('aria-pressed', ids.has(Number(host.dataset.id)) ? 'true' : 'false'); });
  }
  function renderAll() { renderCounts(); renderCart(); renderWish(); renderHearts(); document.dispatchEvent(new CustomEvent('z28:cart')); }

  function toggleWish(item) {
    const wish = getWish(); const i = wish.findIndex((w) => w.id === item.id);
    if (i >= 0) { wish.splice(i, 1); toast(t('removed_wish', 'Retiré des favoris')); } else { wish.push(item); toast(t('added_wish', 'Ajouté aux favoris')); }
    saveWish(wish);
  }

  // Re-synchronise prix et stock avec le serveur (le serveur recalcule de toute façon à la commande).
  let verified = false;
  async function verifyCart(force = false) {
    if (verified && !force) return; const cart = getCart(); if (!cart.length) return; verified = true;
    try {
      const { ok, data } = await api('/api/panier/verifier', { items: cart.map((l) => ({ id: l.id, qty: l.qty })) });
      if (!ok || !data.books) return;
      const fresh = new Map(data.books.map((b) => [b.id, b])); let changed = false;
      const next = cart.filter((l) => { if (!fresh.has(l.id)) { changed = true; return false; } return true; }).map((l) => {
        const b = fresh.get(l.id);
        if (b.price !== l.price || b.stock !== l.stock) changed = true;
        return { ...l, title: b.title, author: b.author, price: b.price, stock: b.stock, cover: b.cover, slug: b.slug, qty: Math.max(1, Math.min(l.qty, b.stock || 1, MAX_QTY)) };
      });
      if (changed) { saveCart(next); toast(t('cart_updated', 'Votre panier a été mis à jour (prix ou stock).')); }
    } catch { /* hors-ligne : on garde le panier tel quel */ }
  }

  // ───── Tiroirs ─────
  let lastFocus = null;
  function openDrawer(name) {
    $('#mobile-sheet')?.classList.remove('is-open'); $('[data-menu]')?.setAttribute('aria-expanded', 'false');
    const drawer = $(`[data-drawer="${name}"]`); if (!drawer) return;
    lastFocus = document.activeElement; $$('.drawer.is-open').forEach(closeDrawer);
    drawer.classList.add('is-open'); drawer.setAttribute('aria-hidden', 'false'); $('[data-scrim]').classList.add('is-open'); document.body.classList.add('no-scroll');
    setTimeout(() => (drawer.querySelector('[data-close]') || drawer).focus(), 60);
    if (name === 'cart') verifyCart();
  }
  function closeDrawer(drawer) {
    drawer = drawer || $('.drawer.is-open'); if (!drawer) return;
    drawer.classList.remove('is-open'); drawer.setAttribute('aria-hidden', 'true');
    if (!$('.drawer.is-open')) { $('[data-scrim]').classList.remove('is-open'); document.body.classList.remove('no-scroll'); }
    if (lastFocus && document.contains(lastFocus)) lastFocus.focus();
  }
  function trapFocus(e) {
    const open = $('.drawer.is-open'); if (!open || e.key !== 'Tab') return;
    const f = $$('a[href], button:not([disabled]), input, select, textarea, [tabindex]:not([tabindex="-1"])', open).filter((n) => !n.closest('[hidden]'));
    if (!f.length) return; const first = f[0], last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); } else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  }

  // ───── Aperçu rapide ─────
  async function quickView(id) {
    const dlg = $('#quick-view'); if (!dlg || !dlg.showModal) { location.href = '/catalogue'; return; }
    try {
      const res = await fetch('/api/livre/' + encodeURIComponent(id), { credentials: 'same-origin', headers: { Accept: 'application/json' } });
      const { book } = await res.json(); if (!res.ok || !book) throw new Error('indisponible');
      const item = { id: book.id, slug: book.slug, title: book.title, author: book.author, price: book.price, cover: book.cover, stock: book.stock };
      const src = safePath(book.cover, '/static/');
      dlg.replaceChildren(el('div', { class: 'quick' },
        el('button', { type: 'button', class: 'icon-btn quick__close', 'aria-label': t('close', 'Fermer'), onclick: () => dlg.close() }, icon('close')),
        src ? el('img', { src, alt: t('cover_of', 'Couverture de {title}').replace('{title}', book.title), width: 240, height: 360 }) : el('span'),
        el('div', {},
          el('h2', {}, book.title), el('p', { class: 'muted' }, [book.author, book.category].filter(Boolean).join(' · ')),
          el('p', { class: 'price price--big' }, fmt(book.price)),
          el('p', {}, book.excerpt + (book.excerpt.length >= 320 ? '…' : '')),
          el('div', { class: 'done__actions' },
            el('button', { type: 'button', class: 'btn', disabled: book.stock <= 0, onclick: () => { if (addToCart(item)) dlg.close(); } }, book.stock <= 0 ? t('sold_out_short', 'Épuisé') : t('add_to_cart', 'Ajouter au panier')),
            el('a', { class: 'btn btn--ghost', href: bookHref(book.slug) }, t('view_detail', 'Voir la fiche'))))));
      dlg.showModal();
    } catch { toast(t('preview_unavailable', 'Aperçu indisponible pour le moment.'), 'error'); }
  }

  // ───── Délégation d'événements ─────
  document.addEventListener('click', (e) => {
    const tEl = e.target instanceof Element ? e.target : null; if (!tEl) return;
    const open = tEl.closest('[data-open]'); if (open) { e.preventDefault(); openDrawer(open.dataset.open); return; }
    if (tEl.closest('[data-close]') || tEl.matches('[data-scrim]')) { closeDrawer(); return; }
    const add = tEl.closest('[data-add]'); if (add) {
      const host = add.closest('[data-book]'); if (!host) return;
      const qtyOut = $('[data-qty-out]', host); addToCart(itemFrom(host), qtyOut ? Number(qtyOut.textContent) || 1 : 1); return;
    }
    const wish = tEl.closest('[data-wish]'); if (wish) { e.preventDefault(); const host = wish.closest('[data-book]'); if (host) toggleWish(itemFrom(host)); return; }
    const quick = tEl.closest('[data-quick]'); if (quick) { e.preventDefault(); quickView(quick.dataset.quick); return; }
    const copy = tEl.closest('[data-copy]'); if (copy) { navigator.clipboard?.writeText(copy.dataset.copy).then(() => toast(t('copied', 'Code copié')), () => toast(t('copy_failed', 'Copie impossible'), 'error')); return; }
    const menu = tEl.closest('[data-menu]'); if (menu) {
      const sheet = $('#mobile-sheet');
      if (sheet) {
        const isOpen = sheet.classList.toggle('is-open');
        menu.setAttribute('aria-expanded', String(isOpen));
        menu.setAttribute('aria-label', isOpen ? t('close', 'Fermer') : t('open_menu', 'Ouvrir le menu'));
        document.body.classList.toggle('no-scroll', isOpen);
      }
      return;
    }
    if (tEl.closest('#mobile-sheet a')) {
      const sheet = $('#mobile-sheet');
      if (sheet && sheet.classList.contains('is-open')) {
        sheet.classList.remove('is-open');
        const menuBtn = $('[data-menu]');
        if (menuBtn) {
          menuBtn.setAttribute('aria-expanded', 'false');
          menuBtn.setAttribute('aria-label', t('open_menu', 'Ouvrir le menu'));
        }
        document.body.classList.remove('no-scroll');
      }
    }
    const dlg = $('#quick-view'); if (dlg && tEl === dlg) dlg.close();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      closeDrawer();
      const sheet = $('#mobile-sheet');
      if (sheet && sheet.classList.contains('is-open')) {
        sheet.classList.remove('is-open');
        const menuBtn = $('[data-menu]');
        if (menuBtn) {
          menuBtn.setAttribute('aria-expanded', 'false');
          menuBtn.setAttribute('aria-label', t('open_menu', 'Ouvrir le menu'));
        }
        document.body.classList.remove('no-scroll');
      }
    }
    trapFocus(e);
  });
  document.addEventListener('change', (e) => { const trg = e.target; if (trg instanceof Element && trg.matches('[data-autosubmit]')) { const f = trg.closest('form'); if (f) f.requestSubmit(); } });
  window.addEventListener('storage', (e) => { if (Object.values(KEYS).includes(e.key)) renderAll(); });

  // Filtres : repliés sur mobile, ouverts sur ordinateur
  const panel = $('[data-filters-panel]');
  if (panel) { const mq = matchMedia('(max-width: 960px)'); const sync = () => { panel.open = !mq.matches; }; sync(); mq.addEventListener('change', sync); }

  // Newsletter
  $$('[data-newsletter]').forEach((form) => form.addEventListener('submit', async (e) => {
    e.preventDefault(); const msg = $('[data-news-msg]'); const fd = new FormData(form);
    const { data } = await api('/api/newsletter', { email: fd.get('email'), website: fd.get('website') });
    msg.textContent = data.success ? data.message || t('thanks', 'Merci !') : data.error || t('generic_error', 'Une erreur est survenue.'); if (data.success) form.reset();
  }));

  window.Z28 = { $, $$, el, icon, fmt, api, toast, csrf, getCart, saveCart, clearCart, addToCart, setQty, removeFromCart, subtotal, verifyCart, itemFrom, MAX_QTY, t, I18N, isRtl };
  renderAll();
})();

/* Notifications : un clic (ou Entrée / Espace / Échap quand elle a le focus) la ferme.
   Valable pour tout ce qui porte la classe .toast ou .flash, même créé plus tard par un autre script. */
(() => {
  'use strict';
  const SEL = '.toast, .flash';
  const HINT = document.documentElement.lang === 'ar' ? 'انقر للإغلاق' : 'Cliquer pour fermer';

  function arm(el) {                                   // rend une notification cliquable et accessible au clavier
    if (el.dataset.dismissArmed || el.hasAttribute('data-keep')) return;
    el.dataset.dismissArmed = '1';
    if (!el.hasAttribute('tabindex')) el.tabIndex = 0;
    el.title = HINT;
  }

  function close(el) {
    if (el.dataset.closing) return;
    el.dataset.closing = '1';
    el.classList.add('is-leaving');                    // petite animation de sortie (CSS)
    setTimeout(() => {
      const box = el.parentElement;
      if (el.hasAttribute('data-form-alert')) {        // bandeau d'erreur du formulaire : réutilisé par checkout.js, on le masque seulement
        el.hidden = true; el.classList.remove('is-leaving'); delete el.dataset.closing;
      } else {
        el.remove();
        if (box && box.classList.contains('flashes') && !box.children.length) box.remove();   // plus de trou vide
      }
    }, 220);
  }

  document.addEventListener('click', (e) => {
    const target = e.target instanceof Element ? e.target : null;
    if (!target) return;
    const news = target.closest('[data-news-msg]');    // message de la newsletter (pied de page)
    if (news && news.textContent) { news.textContent = ''; return; }
    const el = target.closest(SEL);
    if (el && !el.hasAttribute('data-keep') && !target.closest('a, button')) close(el);
  });

  document.addEventListener('keydown', (e) => {
    const el = e.target instanceof Element ? e.target.closest(SEL) : null;
    if (el && !el.hasAttribute('data-keep') && ['Enter', ' ', 'Escape'].includes(e.key)) { e.preventDefault(); close(el); }
  });

  document.querySelectorAll(SEL).forEach(arm);
  new MutationObserver((records) => records.forEach((r) => r.addedNodes.forEach((n) => {
    if (n.nodeType !== 1) return;
    if (n.matches(SEL)) arm(n);
    n.querySelectorAll(SEL).forEach(arm);
  }))).observe(document.body, { childList: true, subtree: true });
})();
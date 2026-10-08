/* Fiche livre : galerie, onglets, quantité, « commander maintenant ». */
(() => {
  'use strict';
  const { $, $$, addToCart, itemFrom, toast } = window.Z28;
  const host = $('.pdp'); if (!host) return;

  // Galerie
  const stage = $('[data-stage]');
  $$('[data-thumb]').forEach((btn) => btn.addEventListener('click', () => {
    if (!stage) return;
    const url = btn.dataset.thumb; if (!url.startsWith('/static/')) return;
    stage.classList.add('is-swapping');
    setTimeout(() => { stage.src = url; stage.alt = btn.dataset.caption || ''; stage.classList.remove('is-swapping'); }, 160);
    $$('[data-thumb]').forEach((b) => b.setAttribute('aria-current', b === btn ? 'true' : 'false'));
  }));

  // Quantité
  const out = $('[data-qty-out]', host); const minus = $('[data-qty-minus]', host); const plus = $('[data-qty-plus]', host);
  const stock = Number(host.dataset.stock) || 0; const cap = Math.min(stock, window.Z28.MAX_QTY);
  const setQ = (n) => { n = Math.max(1, Math.min(n, cap || 1)); out.textContent = String(n); minus.disabled = n <= 1; plus.disabled = n >= cap; };
  if (out) { minus.addEventListener('click', () => setQ(Number(out.textContent) - 1)); plus.addEventListener('click', () => setQ(Number(out.textContent) + 1)); }

  // Commander maintenant
  const buy = $('[data-buy]', host);
  const t = window.Z28.t || ((k, fb) => fb);
  if (buy) buy.addEventListener('click', () => { if (addToCart(itemFrom(host), Number(out.textContent) || 1, { open: false })) location.href = '/commande'; else toast(t('sold_out', 'Ce livre est épuisé.'), 'error'); });

  // Onglets (clavier compris)
  const tabs = $$('[role="tab"]'); const panels = tabs.map((t) => $('#' + t.getAttribute('aria-controls')));
  function select(i, focus) {
    tabs.forEach((t, k) => { t.setAttribute('aria-selected', String(k === i)); t.tabIndex = k === i ? 0 : -1; panels[k].hidden = k !== i; });
    if (focus) tabs[i].focus();
  }
  tabs.forEach((t, i) => {
    t.addEventListener('click', () => select(i));
    t.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowRight') { e.preventDefault(); select((i + 1) % tabs.length, true); }
      if (e.key === 'ArrowLeft') { e.preventDefault(); select((i - 1 + tabs.length) % tabs.length, true); }
    });
  });
  const reviewsIdx = tabs.findIndex((t) => t.id === 'tab-avis');
  const openReviews = () => { select(reviewsIdx); $('#tab-avis').scrollIntoView({ behavior: 'smooth', block: 'start' }); };
  $$('[data-tab-link="avis"]').forEach((a) => a.addEventListener('click', (e) => { e.preventDefault(); openReviews(); }));
  if (location.hash === '#avis') openReviews();
})();

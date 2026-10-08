/* Page commande : récapitulatif, frais par wilaya, validation, envoi. Le serveur recalcule tout. */
(() => {
  'use strict';
  const Z = window.Z28; const { $, $$, el, icon, fmt, t } = Z;
  const root = $('[data-checkout]'); if (!root) return;
  const form = $('[data-checkout-form]', root); const summary = $('[data-checkout-summary]', root); const empty = $('[data-checkout-empty]', root);
  const wilaya = $('#c-wilaya'); const alertBox = $('[data-form-alert]', root); const submit = $('[data-submit]', root);
  const addrField = $('[data-address-field]', root); const address = $('#c-address');
  const method = () => (form.querySelector('input[name="delivery_method"]:checked') || {}).value || 'home';

  function shipPrice() {
    const opt = wilaya.selectedOptions[0]; if (!opt || !opt.value) return null;
    const raw = opt.dataset[method()]; return raw === '' || raw == null ? null : Number(raw);
  }

  function renderPrices() {
    const opt = wilaya.selectedOptions[0]; const has = opt && opt.value;
    $('[data-price-home]').textContent = has ? fmt(opt.dataset.home) : '—';
    const office = has && opt.dataset.office !== '' ? fmt(opt.dataset.office) : has ? t('unavailable', 'Indisponible') : '—';
    $('[data-price-office]').textContent = office;
    const officeInput = form.querySelector('input[value="office"]'); officeInput.disabled = Boolean(has && opt.dataset.office === '');
    if (officeInput.disabled && officeInput.checked) form.querySelector('input[value="home"]').checked = true;
    addrField.hidden = method() !== 'home'; address.required = method() === 'home';
  }

  function renderSummary() {
    const cart = Z.getCart(); const ok = cart.length > 0;
    empty.hidden = ok; form.hidden = !ok; summary.hidden = !ok; if (!ok) return;
    const box = $('[data-checkout-lines]', summary); box.replaceChildren();
    cart.forEach((l) => box.append(el('div', { class: 'line' },
      l.cover && l.cover.startsWith('/static/') ? el('img', { src: l.cover, alt: '', width: 48, height: 72 }) : el('span'),
      el('div', {}, el('h3', {}, l.title), el('p', { class: 'line__author' }, `${l.qty} × ${fmt(l.price)}`),
        l.stock <= 0 ? el('p', { class: 'line__warn' }, t('line_soldout_checkout', 'Épuisé : retirez-le du panier')) : null),
      el('div', { class: 'line__price nums' }, fmt(l.price * l.qty)))));
    const books = Z.subtotal(); const ship = shipPrice();
    $('[data-sum-books]').textContent = fmt(books);
    $('[data-sum-ship]').textContent = ship == null ? t('choose_wilaya', 'Choisissez une wilaya') : fmt(ship);
    $('[data-sum-total]').textContent = ship == null ? '—' : fmt(books + ship);
    const blocked = cart.some((l) => l.stock <= 0); submit.disabled = blocked;
    $('[data-stock-note]').textContent = blocked ? t('stock_blocked', 'Un livre de votre panier est épuisé : retirez-le pour continuer.') : '';
  }

  function showErrors(fields) {
    $$('[data-err]', form).forEach((p) => { p.hidden = true; p.textContent = ''; });
    $$('[aria-invalid]', form).forEach((i) => i.removeAttribute('aria-invalid'));
    Object.entries(fields || {}).forEach(([name, msg]) => {
      const p = $(`[data-err="${name}"]`, form); if (p) { p.textContent = msg; p.hidden = false; }
      const input = form.elements[name]; const first = input && (input.length ? input[0] : input); if (first && first.setAttribute) first.setAttribute('aria-invalid', 'true');
    });
    const firstBad = $('[aria-invalid="true"]', form); if (firstBad) firstBad.focus();
  }
  function showAlert(msg) { const s = $('span', alertBox); s.textContent = msg; alertBox.hidden = !msg; if (msg) alertBox.scrollIntoView({ behavior: 'smooth', block: 'center' }); }

  function clientCheck(data) {
    const f = {};
    if (data.full_name.trim().length < 3) f.full_name = t('name_required', 'Indiquez votre nom complet.');
    if (!/^0[567]\d{8}$/.test(data.phone.replace(/[\s.\-]/g, '').replace(/^(\+213|00213)/, '0'))) f.phone = t('phone_invalid', 'Numéro invalide : 10 chiffres commençant par 05, 06 ou 07.');
    if (!data.wilaya) f.wilaya = t('wilaya_required', 'Choisissez votre wilaya.');
    if (data.commune.trim().length < 2) f.commune = t('commune_required', 'Indiquez votre commune.');
    if (data.delivery_method === 'home' && data.address.trim().length < 6) f.address = t('address_required', 'Indiquez votre adresse pour la livraison à domicile.');
    return f;
  }

  form.addEventListener('submit', async (e) => {
    e.preventDefault(); showAlert(''); showErrors({});
    const fd = new FormData(form);
    const data = { full_name: fd.get('full_name') || '', phone: fd.get('phone') || '', wilaya: fd.get('wilaya') || '', commune: fd.get('commune') || '',
      address: fd.get('address') || '', delivery_method: method(), website: fd.get('website') || '', items: Z.getCart().map((l) => ({ id: l.id, qty: l.qty })) };
    const local = clientCheck(data); if (Object.keys(local).length) { showErrors(local); return; }
    submit.disabled = true; const label = submit.textContent; submit.textContent = t('sending', 'Envoi en cours…');
    try {
      const { ok, data: res } = await Z.api('/api/commander', data);
      if (ok && res.success) { Z.clearCart(); location.href = res.redirect || '/commande/confirmee'; return; }
      if (res.fields) showErrors(res.fields); showAlert(res.error || t('order_failed', 'La commande n\'a pas pu être enregistrée.'));
      if (res.error && /stock|épuis|vendu|disponible|exemplaire/i.test(res.error)) Z.verifyCart(true);
    } catch { showAlert(t('network', 'Connexion impossible. Vérifiez votre réseau puis réessayez.')); }
    submit.disabled = false; submit.textContent = label;
  });

  // Efface l'erreur d'un champ dès que la personne le corrige
  form.addEventListener('input', (e) => {
    const t = e.target; if (!(t instanceof Element) || !t.name) return;
    const p = $(`[data-err="${t.name}"]`, form); if (p) { p.hidden = true; p.textContent = ''; }
    t.removeAttribute('aria-invalid');
  });
  form.addEventListener('change', (e) => {
    const t = e.target; if (!(t instanceof Element) || !t.name) return;
    const p = $(`[data-err="${t.name}"]`, form); if (p) { p.hidden = true; p.textContent = ''; }
    t.removeAttribute('aria-invalid');
  });

  [wilaya, ...$$('input[name="delivery_method"]', form)].forEach((n) => n.addEventListener('change', () => { renderPrices(); renderSummary(); }));
  document.addEventListener('z28:cart', renderSummary);
  renderPrices(); renderSummary(); Z.verifyCart(true).then(renderSummary);
})();

/* Administration : menu mobile, confirmations, notifications de commande, aperçu d'image. */
(() => {
  'use strict';
  const $ = (s, r = document) => r.querySelector(s); const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const csrf = () => ($('meta[name="csrf-token"]') || {}).content || '';

  const burger = $('[data-adm-menu]'); const side = $('#adm-side');
  if (burger && side) {
    burger.addEventListener('click', () => { const o = side.classList.toggle('is-open'); burger.setAttribute('aria-expanded', String(o)); });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') { side.classList.remove('is-open'); burger.setAttribute('aria-expanded', 'false'); } });
  }
  // Volet « œil » (téléphone) : le détail d'une carte monte du bas, empilé à la verticale.
  const sheet = $('#sheet');
  if (sheet && typeof sheet.showModal === 'function') {
    const panel = $('[data-sheet-panel]', sheet);
    const calm = window.matchMedia('(prefers-reduced-motion: reduce)');
    let drag = null;
    const reset = () => { sheet.classList.remove('is-closing', 'is-dragging', 'is-settling'); sheet.style.transform = ''; };
    const open = (card) => {
      const tpl = $('template[data-sheet]', card); if (!tpl) return;
      panel.replaceChildren(tpl.content.cloneNode(true)); reset(); sheet.showModal();
    };
    const close = () => {
      if (!sheet.open || sheet.classList.contains('is-closing')) return;
      if (calm.matches) { sheet.close(); return; }
      let done = false; const end = () => { if (!done) { done = true; sheet.close(); } };
      sheet.classList.add('is-closing'); sheet.addEventListener('animationend', end, { once: true }); setTimeout(end, 400);
    };
    sheet.addEventListener('close', () => { panel.replaceChildren(); reset(); });
    document.addEventListener('click', (e) => {
      const eye = e.target.closest('[data-sheet-open]');
      if (eye) { open(eye.closest('.rcard')); return; }
      if (e.target.closest('[data-sheet-close]') || e.target === sheet) close();
      const step = e.target.closest('[data-step]');
      if (step) {
        const input = $('input[name="change"]', step.closest('form')); const v = parseInt(input.value, 10) || 0;
        input.value = String(v + Number(step.dataset.step)); input.dispatchEvent(new Event('input', { bubbles: true }));
      }
      const fill = e.target.closest('[data-fill]');
      if (fill) { const input = $('input[name="reason"]', fill.closest('form')); input.value = fill.dataset.fill; input.focus(); }
    });
    // Aperçu du stock après ajustement
    sheet.addEventListener('input', (e) => {
      if (!e.target.matches('input[name="change"]')) return;
      const box = $('[data-preview-box]', sheet); if (!box) return;
      const cur = Number(e.target.dataset.current); const raw = parseInt(e.target.value, 10);
      box.hidden = Number.isNaN(raw); if (Number.isNaN(raw)) return;
      const next = cur + raw; $('[data-preview-val]', box).textContent = String(next); box.classList.toggle('is-bad', next < 0);
    });
    // Glisser vers le bas pour fermer
    sheet.addEventListener('pointerdown', (e) => { if (e.target.closest('[data-sheet-grab]') && !e.target.closest('button')) drag = { y: e.clientY, dy: 0, on: false, id: e.pointerId }; });
    sheet.addEventListener('pointermove', (e) => {
      if (!drag) return; drag.dy = Math.max(0, e.clientY - drag.y);
      if (!drag.on && drag.dy > 6) { drag.on = true; sheet.setPointerCapture(drag.id); sheet.classList.add('is-dragging'); }
      if (drag.on) sheet.style.transform = `translateY(${drag.dy}px)`;
    });
    const release = () => {
      if (!drag) return; const d = drag; drag = null; if (!d.on) return;
      sheet.classList.remove('is-dragging'); sheet.classList.add('is-settling');
      if (d.dy > 100) { sheet.style.transform = 'translateY(100%)'; setTimeout(() => sheet.close(), 240); } else sheet.style.transform = '';
    };
    sheet.addEventListener('pointerup', release); sheet.addEventListener('pointercancel', release);
  }
  const focused = $('.rcard.is-focus'); if (focused) focused.scrollIntoView({ block: 'center' });
  // Confirmations : formulaires (data-confirm) et boutons (data-confirm-btn)
  document.addEventListener('submit', (e) => {
    const f = e.target; const sub = e.submitter;
    const msg = (sub && sub.dataset.confirmBtn) || (f instanceof Element && f.dataset.confirm);
    if (msg && !window.confirm(msg)) e.preventDefault();
  });

  // Aperçu de la couverture avant envoi
  $$('[data-preview]').forEach((input) => input.addEventListener('change', () => {
    const file = input.files && input.files[0]; if (!file || !file.type.startsWith('image/')) return;
    let img = input.parentElement.querySelector('.cover-prev');
    if (!img) {
      img = document.createElement('img'); img.className = 'cover-prev'; img.width = 90; img.height = 135;
      img.alt = document.documentElement.lang === 'ar' ? 'معاينة الغلاف' : 'Aperçu de la couverture';
      input.parentElement.insertBefore(img, input);
    }
    img.src = URL.createObjectURL(file);
  }));

  // Notifications de nouvelles commandes (toutes les 30 s)
  const counters = $$('[data-notif-count]');
  async function poll() {
    try {
      const res = await fetch('/admin/api/notifications', { credentials: 'same-origin', headers: { Accept: 'application/json' } });
      if (!res.ok) return; const data = await res.json();
      counters.forEach((c) => { c.textContent = String(data.count); c.dataset.zero = data.count === 0 ? 'true' : 'false'; });
      const prev = Number(sessionStorage.getItem('z28.notif') || 0);
      if (data.count > prev && prev !== -1 && data.orders.length) {
        const zone = $('[data-toasts]'); const t = document.createElement('div'); t.className = 'toast'; t.setAttribute('role', 'status');
        const prefix = document.documentElement.lang === 'ar' ? 'طلب جديد : ' : 'Nouvelle commande : ';
        t.textContent = `${prefix}${data.orders[0].full_name}`; zone.append(t); setTimeout(() => t.remove(), 5000);
      }
      sessionStorage.setItem('z28.notif', String(data.count));
    } catch { /* réseau indisponible : on réessaie au prochain cycle */ }
  }
  poll(); setInterval(poll, 30000);
  const link = $('[data-notif-link]');
  if (link) link.addEventListener('click', () => {
    fetch('/admin/api/notifications/lu', { method: 'POST', credentials: 'same-origin', headers: { 'X-CSRFToken': csrf(), 'Content-Type': 'application/json' }, body: '{}', keepalive: true });
  });
})();

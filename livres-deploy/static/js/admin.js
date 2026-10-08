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

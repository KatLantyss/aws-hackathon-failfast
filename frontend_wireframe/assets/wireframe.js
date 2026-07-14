// ============================================================
// Wireframe interaction script — just enough behavior to make
// the wireframe navigable/clickable for internal review.
// No real app logic. No network calls.
// ============================================================

document.addEventListener('DOMContentLoaded', () => {
  // Mobile nav toggle
  const mobileToggle = document.querySelector('[data-mobile-toggle]');
  const mobileNav = document.querySelector('[data-mobile-nav]');
  if (mobileToggle && mobileNav) {
    mobileToggle.addEventListener('click', () => {
      const open = mobileNav.getAttribute('data-open') === 'true';
      mobileNav.setAttribute('data-open', String(!open));
    });
  }

  // Tabs (used on vessel detail page)
  document.querySelectorAll('[data-tabs]').forEach((tabGroup) => {
    const buttons = tabGroup.querySelectorAll('[data-tab-target]');
    buttons.forEach((btn) => {
      btn.addEventListener('click', () => {
        const target = btn.getAttribute('data-tab-target');
        buttons.forEach((b) => b.setAttribute('data-active', String(b === btn)));
        document.querySelectorAll('[data-tab-panel]').forEach((panel) => {
          panel.setAttribute('data-active', String(panel.getAttribute('data-tab-panel') === target));
        });
      });
    });
  });

  // Accordion (inspections page)
  document.querySelectorAll('[data-accordion-item]').forEach((item) => {
    const head = item.querySelector('[data-accordion-head]');
    if (!head) return;
    head.addEventListener('click', () => {
      const open = item.getAttribute('data-open') === 'true';
      item.setAttribute('data-open', String(!open));
    });
  });

  // Generic button-group toggle (e.g. sort/filter chips) — purely visual
  document.querySelectorAll('[data-btn-group]').forEach((group) => {
    const buttons = group.querySelectorAll('.wf-btn');
    buttons.forEach((btn) => {
      btn.addEventListener('click', () => {
        buttons.forEach((b) => b.classList.remove('active'));
        btn.classList.add('active');
      });
    });
  });

  // Voice overlay open/close
  document.querySelectorAll('[data-open-voice]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const overlay = document.querySelector('[data-voice-overlay]');
      if (overlay) overlay.setAttribute('data-open', 'true');
    });
  });
  document.querySelectorAll('[data-close-voice]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const overlay = document.querySelector('[data-voice-overlay]');
      if (overlay) overlay.setAttribute('data-open', 'false');
    });
  });

  // Table row expand (vessel list fathometer row, noon report anomaly note etc.)
  document.querySelectorAll('[data-expand-row]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const targetId = btn.getAttribute('data-expand-row');
      const row = document.getElementById(targetId);
      if (!row) return;
      const isHidden = row.style.display === 'none' || !row.style.display;
      row.style.display = isHidden ? 'table-row' : 'none';
      btn.textContent = isHidden ? '▾' : '▸';
    });
  });
});

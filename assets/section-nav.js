(() => {
  'use strict';
  const root = document.documentElement;
  const header = document.querySelector('.site-header');
  const nav = document.querySelector('[data-section-nav]');
  const localNav = document.querySelector('[data-local-section-nav]');
  const measure = () => {
    root.style.setProperty('--site-header-height', `${header?.getBoundingClientRect().height || 0}px`);
    root.style.setProperty('--section-nav-height', `${nav?.getBoundingClientRect().height || localNav?.getBoundingClientRect().height || 0}px`);
    root.classList.add('section-nav-ready');
  };
  measure();
  if ('ResizeObserver' in window) {
    const observer = new ResizeObserver(measure);
    // Sticky offsets include padding and borders, not just the content box.
    [header, nav, localNav].filter(Boolean).forEach(node => observer.observe(node, { box: 'border-box' }));
  }
  window.addEventListener('resize', measure);
  document.fonts?.ready.then(measure);

  if (!nav) return;
  const links = [...nav.querySelectorAll('[data-section-item]')];
  const budgetPage = location.pathname.split('/').pop() === 'national-budget.html';
  if (budgetPage) {
    nav.addEventListener('click', event => {
      const link = event.target.closest('a[data-section-item]');
      if (!link || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const target = new URL(link.href);
      if (target.origin !== location.origin || target.pathname !== location.pathname) return;
      event.preventDefault();
      // Same-module views retain query filters and the already validated snapshot.
      location.hash = target.hash || '#projects';
    });
  }
  const updateCurrent = () => {
    if (!budgetPage) return;
    const item = location.hash === '#offices' ? 'offices'
      : location.hash === '#about-data' ? 'about' : 'projects';
    links.forEach(link => {
      if (link.dataset.sectionItem === item) link.setAttribute('aria-current', 'location');
      else link.removeAttribute('aria-current');
    });
    const selected = links.find(link => link.dataset.sectionItem === item);
    if (selected) {
      const strip = nav.querySelector('.section-nav-links');
      const bounds = selected.getBoundingClientRect();
      const viewport = strip.getBoundingClientRect();
      if (bounds.left < viewport.left || bounds.right > viewport.right) {
        strip.scrollLeft += bounds.left - viewport.left;
      }
    }
  };
  updateCurrent();
  window.addEventListener('hashchange', updateCurrent);
  window.addEventListener('popstate', updateCurrent);
})();

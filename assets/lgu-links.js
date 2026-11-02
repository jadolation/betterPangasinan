// Old province-wide bookmarks lead residents back to their unified local profile.
(() => {
  'use strict';
  const sections = { 'finances.html': ['finances', 'finances'], 'projects.html': ['projects', 'projects'], 'services.html': ['government', 'services'], 'legislation.html': ['sources', 'source references'], 'procurement.html': ['projects', 'project records'] };
  const current = sections[location.pathname.split('/').pop()];
  const id = new URLSearchParams(location.search).get('lgu');
  if (!current || !id) return;
  fetch('data/public.json').then(response => { if (!response.ok) throw new Error('Unavailable'); return response.json(); }).then(data => {
    const mode = document.querySelector('meta[name="data-mode"]')?.content;
    const lgu = (data.lgus || []).find(row => row.id === id && (mode === 'test' || (row.is_mock === false && (mode === 'preview' || row.publication_status === 'approved'))));
    if (!lgu) return;
    const box = document.createElement('aside'); box.className = 'lgu-profile-shortcut wrap'; box.id = 'lgu-profile-shortcut';
    const link = document.createElement('a'); link.href = `lgu.html?id=${encodeURIComponent(lgu.id)}#${current[0]}`; link.textContent = `View ${lgu.name}'s ${current[1]} in its LGU profile`;
    box.append(link); const main = document.querySelector('main'); main.insertBefore(box, main.children[1] || null);
  }).catch(() => {});
})();

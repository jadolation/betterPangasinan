/* Dedicated source-preserving reference explorer. No generic record publication rules. */
(() => {
  'use strict';
  document.querySelectorAll('[data-reference]').forEach((root, rootIndex) => {
  const results = root.querySelector('[data-results]');
  const status = root.querySelector('[data-status]');
  const form = root.querySelector('form');
  const node = (tag, text, parent) => {
    const el = document.createElement(tag);
    if (text !== undefined) el.textContent = text;
    if (parent) parent.append(el);
    return el;
  };
  const link = (url, label, parent) => {
    if (!/^https:\/\//.test(url)) return;
    const a = node('a', label, parent); a.href = url;
  };
  const showValue = value => value === null ? 'Not established by source' : typeof value === 'object' ? JSON.stringify(value) : String(value);
  const contactLinks = (raw, parent) => {
    node('span', raw, parent);
    // Match only complete source-listed domestic numbers; never supply a prefix.
    const numbers = raw.match(/(?<!\d)(?:\(075\)|075)[ -]*\d{3}[ -]*\d{4}(?!\d)|(?<!\d)09\d{2}[ -]*\d{3}[ -]*\d{4}(?!\d)/g) || [];
    [...new Set(numbers.map(number => number.replace(/\D/g, '')))].forEach(number => {
      parent.append(document.createTextNode(' '));
      const a = node('a', `Call ${number}`, parent); a.href = `tel:${number}`;
    });
  };
  const sourceDetails = (row, parent) => {
    const details = node('details', undefined, parent);
    details.className = 'pr-details';
    node('summary', 'Source, dates and original record', details);
    node('p', `Source collected: ${row.collected_at || row.collected_date || 'Unknown'}. Source as-of date: ${row.as_of_date || 'Not established by source'}.`, details);
    if (row.notes) node('p', row.notes, details);
    node('pre', JSON.stringify(row, null, 2), details);
  };
  const evidenceLink = (row, parent) => link(row.source_url || row.url || '', 'Original source', parent);
  fetch(new URL('data/provincial-reference.json', document.baseURI))
    .then(response => { if (!response.ok) throw new Error('Unavailable'); return response.json(); })
    .then(data => {
      if (!Array.isArray(data.statistics) || !Array.isArray(data.official_pages)) throw new Error('Invalid bundle');
      const mode = root.dataset.reference;
      const page = id => data.official_pages.find(p => p.id === id);
      const sections = [];
      const lguCollection = 'LGU population comparisons (2024)';
      if (mode === 'statistics') {
        sections.push(['Statistics', data.statistics]);
        sections.push([lguCollection, data.lgu_registry_2024]);
        const trend = data.statistics.filter(r => r.indicator === 'Total population' && ['2010','2015','2020','2024'].includes(r.reference_period)).sort((a,b) => a.reference_period.localeCompare(b.reference_period));
        const region = root.querySelector('[data-trend]');
        node('h2', 'Provincial population census trend', region);
        node('p', 'Province-wide context, not an individual LGU trend. PSA research observations, persons. Collection: 2026-10-31; this is not a 2026 population estimate.', region);
        const table = node('table', undefined, region);
        node('caption', 'Population trend: accessible chart data', table);
        const head = node('tr', undefined, node('thead', undefined, table));
        ['Census year','Population (persons)','Relative scale'].forEach(t => { const th = node('th',t,head); th.scope='col'; });
        const body = node('tbody',undefined,table);
        trend.forEach(r => { const tr=node('tr',undefined,body); node('td',r.reference_period,tr); node('td',Number(r.value).toLocaleString('en-US'),tr); const bar=node('meter',undefined,node('td',undefined,tr)); bar.min=0; bar.max=3500000; bar.value=r.value; bar.setAttribute('aria-label',`${r.reference_period}: ${r.value} persons`); });
        link(trend[0]?.source_url || '', 'Population source', region);
      } else if (mode === 'hospitals') {
        sections.push(['Hospital heads: Directory-listed',data.hospital_directory_observations]);
        sections.push(['Hospital public contacts', (page('directory')?.rows || []).filter(r => /hospital/i.test(r[0])).map((r,i)=>({id:`contact-${i}`,institution:r[0],public_contact:r[1],source_url:page('directory').source_url,collected_at:page('directory').collected_at,as_of_date:null}))]);
        sections.push(['Emergency services', (page('disaster-services')?.text || []).map((text,i)=>({id:`service-${i}`,text,source_url:page('disaster-services').source_url,collected_at:page('disaster-services').collected_at,as_of_date:null}))]);
        if (page('disaster-services')?.text.some(t => t.includes('24/7 Emergency 911 Hotline'))) {
          const p=node('p','Official DRRMO page lists a 24/7 emergency hotline: ',root.querySelector('[data-emergency]'));
          const a=node('a','Call 911',p); a.href='tel:911';
          link(page('disaster-services').source_url,' Source',p);
        }
      } else if (mode === 'history') {
        ['history','about'].forEach(id => {
          const p=page(id);
          if(!p) return;
          const excerpts=p.text.filter(t=>t.length>100 && (id==='about' || /Fast-forward to 1580|Long before the arrival|In September 1902|Governor Daniel Maramba|From January 9-13, 1945/.test(t)));
          sections.push([id === 'history' ? 'Official history: selected milestones' : 'Culture and provincial context',excerpts.map((text,i)=>({id:`${id}-${i}`,text,source_url:p.source_url,collected_at:p.collected_at}))]);
          if(id==='history' && p.links.includes('https://seepangasinan.com/')) link('https://seepangasinan.com/','Tourism site linked by the official province website',root.querySelector('[data-tourism]'));
        });
      } else if (['budgets','legislation','projects'].includes(mode)) {
        const dedicated = {
          budgets: ['Budget observations','budget_observations'],
          legislation: ['Legislation discovery index','legislation_index'],
          projects: ['Planning project leads, not awards','project_leads']
        };
        const [title,key] = dedicated[mode];
        sections.push([title,data[key]]);
      } else {
        const p=page('directory');
        sections.push(['Directory-listed offices', (p?.rows || []).filter(r=>r.length===3 && r[0]!=='Name').map((r,i)=>({id:`office-${i}`,name_and_office:r[0],public_contact:r[1],email_as_displayed:r[2],source_url:p.source_url,collected_at:p.collected_at,as_of_date:null,notes:'Functions, location and term dates not established in this listing.'}))]);
        [['Budget observations','budget_observations'],['Legislation discovery index','legislation_index'],['Planning project leads, not awards','project_leads'],['Source inventory','sources'],['Collection gaps','collection_gaps'],['2024 LGU registry','lgu_registry_2024']].forEach(([title,key])=>sections.push([title,data[key]]));
      }
      const select = form.elements.collection;
      sections.forEach(([title])=>{ const o=node('option',title,select); o.value=title; });
      const collectionLabel = select.closest('label');
      if (sections.length === 1 && collectionLabel) collectionLabel.hidden = true;
      const budgetFilters = sections.some(([title]) => title === 'Budget observations') ? node('div', undefined, form) : null;
      if (budgetFilters) {
        budgetFilters.className = 'pr-budget-filters';
        [['year', 'Budget year', [...new Set(data.budget_observations.map(r => String(r.year)))].sort()], ['type', 'Budget type', [...new Set(data.budget_observations.map(r => r.budget_type))].sort()]].forEach(([name, title, values]) => {
          const wrapper = node('div', undefined, budgetFilters); wrapper.className = 'pr-budget-filter';
          const label = node('label', title, wrapper);
          const field = node('select', undefined, wrapper); field.name = name;
          field.id = `pr-budget-${rootIndex}-${name}`; label.htmlFor = field.id;
          const all = node('option', `All ${name === 'year' ? 'years' : 'types'}`, field); all.value = '';
          values.forEach(value => { const option = node('option', value, field); option.value = value; });
          field.addEventListener('change', () => { currentPage = 1; render(); });
        });
      }
      const aliases = {budgets:'Budget observations', legislation:'Legislation discovery index', projects:'Planning project leads, not awards', sources:'Source inventory', gaps:'Collection gaps', offices:'Directory-listed offices'};
      let currentPage = 1;
      let selectedLGU = '';
      const pagination = node('nav',undefined,root);
      pagination.className='pr-pagination';
      pagination.setAttribute('aria-label','Reference result pages');
      const readURL = () => {
        const params = new URLSearchParams(location.search);
        form.elements.q.value=params.get('q') || '';
        selectedLGU=mode==='statistics' ? params.get('lgu') || '' : '';
        const value=params.get('collection') || (selectedLGU ? lguCollection : '') || aliases[location.hash.slice(1)] || '';
        select.value=sections.some(([title])=>title===value) ? value : aliases[value] || '';
        if (budgetFilters) ['year','type'].forEach(key => { form.elements[key].value = params.get(key) || ''; });
        currentPage=Math.max(1,Number.parseInt(params.get('page'),10) || 1);
      };
      const writeURL = () => {
        const url=new URL(location.href);
        [['q',form.elements.q.value.trim()],['collection',select.value],['page',currentPage>1 ? String(currentPage) : '']].forEach(([key,value])=>{ if(value) url.searchParams.set(key,value); else url.searchParams.delete(key); });
        if (budgetFilters) ['year','type'].forEach(key => { const value = form.elements[key].value; if (value) url.searchParams.set(key, value); else url.searchParams.delete(key); });
        // A collection fragment is a one-time deep-link; filters own subsequent state.
        if(aliases[url.hash.slice(1)]) url.hash='';
        history.replaceState(null,'',url);
      };
      const render = (syncURL=true) => {
        results.replaceChildren();
        pagination.replaceChildren();
        const query=form.elements.q.value.toLowerCase().trim();
        if (budgetFilters) budgetFilters.hidden = Boolean(select.value && select.value !== 'Budget observations');
        const matches=sections.flatMap(([title,rows])=>select.value && select.value!==title ? [] : rows.filter(r=>(!selectedLGU || (title===lguCollection && `lgu-${r.psgc_10}`===selectedLGU)) && (!budgetFilters || budgetFilters.hidden || (!form.elements.year.value && !form.elements.type.value) || (title === 'Budget observations' && (!form.elements.year.value || String(r.year) === form.elements.year.value) && (!form.elements.type.value || r.budget_type === form.elements.type.value))) && JSON.stringify(r).toLowerCase().includes(query)).map(row=>({title,row})));
        if(mode==='statistics') {
          const region=root.querySelector('[data-trend]');
          region.hidden=Boolean(selectedLGU);
          const scope=root.querySelector('[data-lgu-scope]');
          scope.replaceChildren();
          if(selectedLGU) {
            const selected=data.lgu_registry_2024.find(r=>`lgu-${r.psgc_10}`===selectedLGU);
            node('p',selected ? `${selected.name}: one 2024 population observation, not an LGU time series. Provincial trend hidden for this LGU view.` : 'No registry LGU matches this identifier. No population or trend is inferred.',scope);
            if (selected) {
              const profile = node('a', `Open ${selected.name}'s local statistics and profile`, scope);
              profile.className = 'btn pr-profile-link';
              profile.href = `lgu.html?id=${encodeURIComponent(selectedLGU)}#statistics`;
            }
            const a=node('a','View all LGUs and provincial context',scope);
            const url=new URL(location.href); ['lgu','page','q','collection'].forEach(key=>url.searchParams.delete(key)); a.href=url.href;
          }
        }
        const count=matches.length;
        const totalPages=Math.max(1,Math.ceil(count/25));
        currentPage=Math.min(currentPage,totalPages);
        const start=(currentPage-1)*25;
        let section, lastTitle, comparisonBody, budgetBody;
        matches.slice(start,start+25).forEach(({title,row})=>{
            if(title!==lastTitle) {
              section=node('section',undefined,results); node('h2',title,section); lastTitle=title;
              section.className = 'pr-collection';
              if (title === 'Budget observations') {
                const wrap = node('div', undefined, section); wrap.className = 'pr-table-scroll'; wrap.tabIndex = 0; wrap.setAttribute('role', 'region'); wrap.setAttribute('aria-label', 'Budget evidence table');
                const table = node('table', undefined, wrap);
                node('caption', 'Budget evidence: amounts are not actual spending', table);
                const head = node('tr', undefined, node('thead', undefined, table));
                ['Government / year', 'Source budget type', 'Amount (PHP)', 'Qualification / evidence'].forEach(text => { node('th', text, head).scope = 'col'; });
                budgetBody = node('tbody', undefined, table);
              }
              if(title===lguCollection) {
                const total=data.lgu_registry_2024.reduce((sum,r)=>sum+r.population_2024,0);
                node('p',`${data.lgu_registry_2024.length} LGUs in the full registry; population total ${total.toLocaleString('en-US')} persons. Census reference dates and source-snapshot notes are retained below; collection is not the census date.`,section);
                const table=node('table',undefined,section);
                table.style.tableLayout='fixed';
                table.style.overflowWrap='anywhere';
                node('caption','2024 LGU population comparison: accessible chart data',table);
                const head=node('tr',undefined,node('thead',undefined,table));
                ['LGU / PSGC','Population (persons)','Relative scale','Source and dates'].forEach(text=>{const th=node('th',text,head); th.scope='col';});
                comparisonBody=node('tbody',undefined,table);
              }
            }
            if(title===lguCollection) {
              const tr=node('tr',undefined,comparisonBody);
              node('th',`${row.name} / ${row.psgc_10}`,tr).scope='row';
              node('td',row.population_2024.toLocaleString('en-US'),tr);
              const meter=node('meter',undefined,node('td',undefined,tr));
              meter.min=0; meter.max=Math.max(...data.lgu_registry_2024.map(r=>r.population_2024)); meter.value=row.population_2024;
              meter.setAttribute('aria-label',`${row.name}: ${row.population_2024} persons, 2024`);
              const source=node('td',undefined,tr);
              node('p',`Census reference: ${row.population_reference_date || 'Unknown'}. Source collected: ${row.collected_date || 'Unknown'}.`,source);
              link(row.source_url,'PSA source',source);
               const details = node('details', undefined, source); node('summary', 'Census and source notes', details); node('p',row.psgc_snapshot_note,details);
               return;
             }
             if (title === 'Budget observations') {
               const tr = node('tr', undefined, budgetBody); tr.className = 'pr-record pr-budget-row';
               const name = node('th', row.lgu, tr); name.scope = 'row'; node('small', String(row.year), name);
               node('td', row.budget_type, tr);
               node('td', row.amount_php === null ? 'Unknown' : Number(row.amount_php).toLocaleString('en-PH', { maximumFractionDigits: 2 }), tr).className = 'pr-number';
               const evidence = node('td', undefined, tr);
               if (row.provincial_review_disposition) node('strong', row.provincial_review_disposition, evidence);
               if (row.notes) node('p', row.notes, evidence);
               evidenceLink(row, evidence); sourceDetails(row, evidence);
               return;
             }
             const article=node('article',undefined,section); article.className='pr-record';
             if (row.indicator) {
               article.classList.add('pr-statistic');
               node('h3', row.indicator, article);
               const value = node('p', undefined, article); value.className = 'pr-stat-value';
               node('strong', typeof row.value === 'number' ? row.value.toLocaleString('en-US') : showValue(row.value), value);
               node('span', row.unit, value);
               node('p', `${row.reference_period} / ${row.geography}`, article).className = 'pr-period';
             } else if (row.institution) {
               node('h3', row.institution, article);
               node('p', 'Directory-listed; currentness not established', article).className = 'pr-label';
               if (row.chief_listed) node('p', `Directory-listed head: ${row.chief_listed}`, article);
               if (row.public_contact) contactLinks(row.public_contact, node('p', undefined, article));
             } else if (row.name_and_office) {
               const split = row.name_and_office.match(/^(.*?)\s+(Provincial Governor|Provincial Administrator|Chief Administrative Officer|Provincial Legal Officer)(.*)$/);
               node('h3', split ? split[2] : row.name_and_office, article);
               if (split) node('p', split[1], article);
               node('p', 'Directory-listed; current term unknown', article).className = 'pr-label';
               contactLinks(row.public_contact, node('p', undefined, article));
               node('p', `Email as displayed: ${row.email_as_displayed}`, article);
             } else if (row.text) {
               node('p', row.text, article).className = 'pr-excerpt';
             } else {
               node('h3', row.title || row.name || row.indicator || row.source_id || row.id || row.category, article);
               const description = row.summary || row.description || row.gap || row.notes;
               if (description) node('p', showValue(description), article);
             }
             evidenceLink(row, article);
             sourceDetails(row, article);
        });
        status.textContent=`${count} source-backed observations match. Showing ${count ? start+1 : 0}-${Math.min(start+25,count)}. Original source and period notes retained.`;
        if(!count) node('p','No observations match these filters.',results);
        if(totalPages>1) {
          const previous=node('button','Previous',pagination); previous.type='button'; previous.className='btn btn-outline'; previous.disabled=currentPage===1;
          node('span',`Page ${currentPage} of ${totalPages}`,pagination);
          const next=node('button','Next',pagination); next.type='button'; next.className='btn btn-outline'; next.disabled=currentPage===totalPages;
          previous.addEventListener('click',()=>{currentPage--;render();});
          next.addEventListener('click',()=>{currentPage++;render();});
        }
        if(syncURL) writeURL();
      };
      const filter = () => {currentPage=1;render();};
      form.addEventListener('submit',event=>{event.preventDefault();filter();});
      form.elements.q.addEventListener('input',filter);
      select.addEventListener('change',filter);
      form.addEventListener('reset',()=>setTimeout(filter,0));
      window.addEventListener('popstate',()=>{readURL();render(false);});
      window.addEventListener('hashchange',()=>{readURL();render(false);});
      readURL();
      render(false);
    }).catch(() => { status.textContent='Reference data could not be loaded. No missing values or current officeholders are inferred. Use the linked original sources or retry later.'; });
  });
})();

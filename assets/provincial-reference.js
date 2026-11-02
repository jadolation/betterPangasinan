/* Dedicated source-preserving reference explorer. No generic record publication rules. */
(() => {
  'use strict';
  document.querySelectorAll('[data-reference]').forEach(root => {
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
  const label = key => key.replaceAll('_', ' ');
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
        currentPage=Math.max(1,Number.parseInt(params.get('page'),10) || 1);
      };
      const writeURL = () => {
        const url=new URL(location.href);
        [['q',form.elements.q.value.trim()],['collection',select.value],['page',currentPage>1 ? String(currentPage) : '']].forEach(([key,value])=>{ if(value) url.searchParams.set(key,value); else url.searchParams.delete(key); });
        // A collection fragment is a one-time deep-link; filters own subsequent state.
        if(aliases[url.hash.slice(1)]) url.hash='';
        history.replaceState(null,'',url);
      };
      const render = (syncURL=true) => {
        results.replaceChildren();
        pagination.replaceChildren();
        const query=form.elements.q.value.toLowerCase().trim();
        const matches=sections.flatMap(([title,rows])=>select.value && select.value!==title ? [] : rows.filter(r=>(!selectedLGU || (title===lguCollection && `lgu-${r.psgc_10}`===selectedLGU)) && JSON.stringify(r).toLowerCase().includes(query)).map(row=>({title,row})));
        if(mode==='statistics') {
          const region=root.querySelector('[data-trend]');
          region.hidden=Boolean(selectedLGU);
          const scope=root.querySelector('[data-lgu-scope]');
          scope.replaceChildren();
          if(selectedLGU) {
            const selected=data.lgu_registry_2024.find(r=>`lgu-${r.psgc_10}`===selectedLGU);
            node('p',selected ? `${selected.name}: one 2024 population observation, not an LGU time series. Provincial trend hidden for this LGU view.` : 'No registry LGU matches this identifier. No population or trend is inferred.',scope);
            const a=node('a','View all LGUs and provincial context',scope);
            const url=new URL(location.href); ['lgu','page','q','collection'].forEach(key=>url.searchParams.delete(key)); a.href=url.href;
          }
        }
        const count=matches.length;
        const totalPages=Math.max(1,Math.ceil(count/25));
        currentPage=Math.min(currentPage,totalPages);
        const start=(currentPage-1)*25;
        let section, lastTitle, comparisonBody;
        matches.slice(start,start+25).forEach(({title,row})=>{
            if(title!==lastTitle) {
              section=node('section',undefined,results); node('h2',title,section); lastTitle=title;
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
              node('p',row.psgc_snapshot_note,source);
              return;
            }
            const article=node('article',undefined,section); article.className='pr-record';
            node('h3',row.indicator || row.institution || row.name_and_office || row.title || row.category || row.id || row.source_id,article);
            const dl=node('dl',undefined,article);
            Object.entries(row).forEach(([key,value])=>{
              if(key==='id') return;
              node('dt',key==='chief_listed'?'Directory-listed head':label(key),dl);
              const dd=node('dd',undefined,dl);
              if((key==='source_url'||key==='url') && typeof value==='string') link(value,value,dd);
              else if(key==='public_contact' && typeof value==='string') contactLinks(value,dd);
              else dd.textContent=showValue(value);
            });
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

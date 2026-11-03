// Presentation only. Validation, filtering, calculations and CSV stay in the entry point.
(() => {
  'use strict';
  const scopeLabels = { geographic: 'Reviewed geographic match', office: 'Office-associated', shared: 'Shared allocation', uncertain: 'Location not yet verified' };
  const groupLabels = { house_only: 'House bill only', nep_only: 'NEP only', unchanged: 'Unchanged', increased: 'Increased', decreased: 'Decreased', scope_review: 'Other or uncertain' };
  const programLabels = { dpwh: 'DPWH infrastructure', fmr: 'Farm-to-market roads', hfep: 'Health facilities', nia: 'Irrigation' };
  const human = value => ({ reviewed_with_warnings: 'Published with source warnings', pending: 'Location not yet verified', pending_geographic_review: 'Location not yet verified', unverified: 'Location not yet verified', reviewed: 'Reviewed', dpwh: 'DPWH infrastructure', fmr: 'Farm-to-market roads', hfep: 'Health facilities', nia: 'Irrigation' })[value] || (typeof value === 'string' ? value.replace(/_/g, ' ') : 'Not supplied');
  const comparisonLabel = value => value.split(' / ').map(part => groupLabels[part] || human(part)).join(' / ');

  window.BudgetViews = function (context) {
    const { element, money, amount, office, versions, comparable, comparison, link, sourceLinks } = context;
    let locationIndex = null;
    try { locationIndex = JSON.parse(document.getElementById('nb-location-index')?.textContent || 'null'); } catch { /* No stale map claims without a valid build index. */ }
    function locationInfo(row) {
      const info = locationIndex?.snapshot_id === row.snapshot_id && Object.hasOwn(locationIndex.projects || {}, row.id) ? locationIndex.projects[row.id] : null;
      return info?.record_sha256 === row.record_sha256 ? info : null;
    }
    function locationAction(row) {
      const info = locationInfo(row);
      if (!info) return element('small', 'Map availability not checked');
      if (!info.has_coordinates) return element('small', 'Location unavailable');
      const anchor = element('a', info.status === 'suspicious' ? 'View suspicious location on map' : 'View on map', 'nb-map-link');
      anchor.href = `map.html?project=${encodeURIComponent(row.id)}`;
      return anchor;
    }
    function list(pairs) {
      const dl = element('dl', undefined, 'nb-definition-list');
      for (const [label, value] of pairs) dl.append(element('dt', label), element('dd', value));
      return dl;
    }
    function section(title) {
      const node = element('section', undefined, 'nb-detail-section');
      node.append(element('h3', title));
      return node;
    }
    function projectRow(row, openDetails) {
      const tr = element('tr');
      tr.setAttribute('role', 'row');
      tr.dataset.recordId = row.id;
      const [nep, house] = versions(row);
      const cell = (label, className) => {
        const td = element('td', undefined, className);
        td.setAttribute('role', 'cell');
        const mobileLabel = element('span', label, 'nb-mobile-label');
        mobileLabel.setAttribute('aria-hidden', 'true');
        td.append(mobileLabel);
        tr.append(td);
        return td;
      };
      const title = cell('Project', 'nb-project-cell');
      const button = element('button', undefined, 'nb-project-button');
      button.type = 'button';
      button.setAttribute('aria-label', `View details: ${row.title}`);
      button.setAttribute('aria-haspopup', 'dialog');
      button.append(element('span', row.title, 'nb-record-name'), element('span', 'View details', 'nb-detail-hint'));
      button.addEventListener('click', () => openDetails(row, button));
      title.append(button, element('span', scopeLabels[row.scope], 'nb-scope-label'));
      title.append(locationAction(row));
      const agency = cell('Office / Program');
      agency.append(element('span', office(row) || 'Office not supplied'), element('small', programLabels[row.dataset] || row.dataset));
      const status = cell('Comparison');
      status.append(element('span', groupLabels[row.upstream.bridge_group] || 'Other or uncertain', 'nb-comparison-label'));
      if (row.upstream.held) status.append(element('small', 'Held pairing'));
      if (row.source_review_status !== 'reviewed' || (row.upstream.flags || []).length) status.append(element('small', 'Source warning', 'nb-inline-warning'));
      cell('NEP', 'nb-number').append(element('span', money(nep)));
      const houseCell = cell('House', 'nb-number');
      houseCell.append(element('span', money(house)), element('small', row.house_stage === 'hgab3' ? '3rd reading' : '2nd reading'));
      cell('Change', 'nb-number').append(element('span', comparable(row) && nep !== null && house !== null ? money(row.upstream.delta_php) : 'Not comparable'));
      return tr;
    }
    function evidence(row, manifest) {
      const content = document.createDocumentFragment();
      const heading = element('h2', row.title);
      heading.id = 'nb-dialog-heading';
      content.append(heading, element('p', `${programLabels[row.dataset] || row.dataset} / ${row.house_stage === 'hgab3' ? 'House third reading' : 'House second reading'}`, 'nb-caption'));
      const overview = section('Overview');
      overview.append(list([
        ['Program', row.upstream.program || programLabels[row.dataset]], ['Office', office(row) || 'Not supplied'],
        ['Comparison', comparisonLabel(comparison(row))], ['Scope', scopeLabels[row.scope]],
      ]));
      content.append(overview);
      const financial = section('Financial comparison');
      const [nep, house] = versions(row);
      financial.append(list([['NEP proposal', money(nep)], [`House proposal (${row.house_stage === 'hgab3' ? 'third reading' : 'second reading'})`, money(house)], ['Source-supplied change', money(row.upstream.delta_php)]]));
      financial.append(element('p', comparable(row) && nep !== null && house !== null
        ? 'Both amounts are known and this pairing is eligible for comparable-row totals. Publication does not independently verify its source evidence.'
        : 'Excluded from comparable-row change totals. One version is unknown, the pairing is held, or the source compares different scopes.', 'nb-caption'));
      const labels = row.detail_evidence?.[0]?.envelope?.data?.labels;
      if (typeof labels?.status?.help === 'string') financial.append(element('p', labels.status.help));
      content.append(financial);
      const location = section('Location and attribution');
      location.append(list([
        ['LGU associations', row.lgu_associations.map(lgu => `${lgu.name} (${lgu.psgc})`).join('; ') || 'No reviewed LGU match'],
        ['Geographic review', human(row.geographic_review_status)], ['Source review', human(row.source_review_status)],
      ]));
      if (row.geographic_review_status !== 'reviewed') location.append(element('p', 'No verified location is established by this record. Search matches may refer to places outside Pangasinan.', 'nb-warning'));
      if (row.scope === 'shared') location.append(element('p', 'Shared umbrella allocation: no Pangasinan share is inferred.', 'nb-warning'));
      if (row.scope === 'office') location.append(element('p', 'An office association does not prove location in any city, municipality or legislative district.', 'nb-warning'));
      content.append(location);
      const mapAction = element('p'); mapAction.append(locationAction(row)); content.append(mapAction);
      const sources = section('Source evidence');
      sources.append(element('p', `${human(row.source_review_status)}. Publication approval does not clear upstream evidence flags.`, 'nb-warning'));
      if ((row.upstream.flags || []).includes('nep_evidence_review')) sources.append(element('p', 'NEP evidence needs review: the source has flagged the proposal-side evidence for checking. The displayed comparison is not independently verified.', 'nb-warning'));
      for (const version of ['nep', row.house_stage]) {
        const p = element('p');
        const anchor = link(row.upstream.pdf_url?.[version], version === 'nep' ? 'Original NEP PDF' : `Original House PDF (${version === 'hgab3' ? 'third reading' : 'second reading'})`);
        if (anchor) p.append(anchor);
        else p.textContent = `${version === 'nep' ? 'NEP' : 'House'} PDF: no valid HTTPS source link supplied.`;
        p.append(element('small', `Document: ${row.upstream[`${version}_doc`] || 'Not supplied'} / Page: ${row.upstream[`${version}_page`] ?? 'Not supplied'}`));
        sources.append(p);
      }
      sources.append(list([['Original identifier', row.upstream_id], ['Snapshot', manifest.snapshot_id], ['Source flags', (row.upstream.flags || []).map(human).join('; ') || 'None supplied']]));
      content.append(sources);
      const advanced = element('details', undefined, 'nb-disclosure');
      advanced.append(element('summary', 'Advanced technical metadata'));
      advanced.append(element('p', `Record ${row.id}; SHA-256 ${row.record_sha256}`, 'tp-mono'));
      advanced.append(element('p', 'Original upstream fields, inclusion reasons, source review metadata and additional detail evidence are retained below.'));
      // Large original records are formatted only when a researcher opens the disclosure.
      advanced.addEventListener('toggle', () => {
        if (advanced.open && !advanced.querySelector('pre')) {
          sourceLinks(row.upstream, advanced);
          advanced.append(element('pre', JSON.stringify(row, null, 2), 'tp-mono'));
        }
      });
      content.append(advanced);
      return content;
    }
    function officeCard(item, rows, matchesScope) {
      const card = element('article', undefined, 'card nb-office-card');
      const raw = item.upstream || {};
      const fy = raw.fy2027 || {};
      card.append(element('span', `Attribution tier ${item.tier}`, 'nb-scope-label'), element('h3', item.matched_label));
      const districtLabels = item.district_ids.map(id => /^leg:pangasinan:\d+(st|nd|rd|th)$/.test(id) ? `Pangasinan ${id.split(':').pop()} district` : id);
      card.append(element('p', `Serving districts: ${districtLabels.join('; ')}. Office totals are not split between districts.`));
      card.append(element('p', `Co-served district context: ${(raw.co_served_districts || []).map(district => district.label || district.id).join('; ') || 'None listed'}.`, 'nb-caption'));
      const whole = (raw.years || []).find(year => year.fy === 2027 && year.stage === 'nep' && year.matched_label === item.matched_label);
      card.append(list([
        ['Whole-office NEP (context only)', money(amount(whole?.php))],
        ['FY2027 named-project NEP', money(amount(fy.nep_php))],
        ['House third reading', money(amount(fy.hgab3_php))],
      ]));
      card.append(element('p', 'Whole-office and named-project scopes differ. Versions are compared, never added.', 'nb-warning'));
      const related = rows.filter(row => matchesScope(row, 'office') && office(row) === item.matched_label).length;
      const anchor = element('a', `Browse ${related} published office-associated records`, 'nb-office-projects');
      anchor.href = `national-budget.html?scope=office&office=${encodeURIComponent(item.matched_label)}#projects`;
      card.append(anchor);
      if (typeof raw.tier_text === 'string') card.append(element('p', raw.tier_text, 'nb-caption'));
      const details = element('details', undefined, 'nb-disclosure');
      details.append(element('summary', 'Original office comparison metadata'), element('pre', JSON.stringify(raw, null, 2), 'tp-mono'));
      sourceLinks(raw, details);
      card.append(details);
      return card;
    }
    return { projectRow, evidence, officeCard, scopeLabels, groupLabels, programLabels, human, comparisonLabel };
  };
})();

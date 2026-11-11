/* BNN Asia Intelligence – interactive views. Vanilla JS, no dependencies (~12 KB). */
(function () {
  'use strict';
  var CFG = window.BNN_INTEL || { endpoint: '/wp-json/bnn-intel/v1/data', countryBase: '/country-intelligence/' };
  var cache = {};

  function api(path, params) {
    var q = new URLSearchParams(Object.assign({ path: path }, params || {}));
    var url = CFG.endpoint + (CFG.endpoint.indexOf('?') > -1 ? '&' : '?') + q.toString();
    if (!cache[url]) {
      cache[url] = fetch(url, { headers: { Accept: 'application/json' } }).then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      });
    }
    return cache[url];
  }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function el(html) { var d = document.createElement('div'); d.innerHTML = html.trim(); return d.firstChild; }
  function fmt(v, d) { return v == null ? '–' : Number(v).toLocaleString(undefined, { maximumFractionDigits: d == null ? 2 : d }); }
  function date(s) { return s ? new Date(s).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' }) : ''; }
  function countryUrl(slug) { return CFG.countryBase + slug + '/'; }
  function badge(conf) { return '<span class="bnn-i-badge bnn-i-c-' + esc(conf) + '">' + esc(conf) + ' confidence</span>'; }
  function change(n) {
    if (n == null) return '<span class="bnn-i-chg">–</span>';
    if (n > 0) return '<span class="bnn-i-chg up" title="Up ' + n + '">▲ ' + n + '</span>';
    if (n < 0) return '<span class="bnn-i-chg down" title="Down ' + (-n) + '">▼ ' + (-n) + '</span>';
    return '<span class="bnn-i-chg">＝</span>';
  }
  function bar(v) { var w = Math.max(0, Math.min(100, v || 0)); return '<span class="bnn-i-bar"><i style="width:' + w + '%"></i></span>'; }
  function fail(root, msg) { root.innerHTML = '<div class="bnn-i-empty">' + esc(msg || 'Data is temporarily unavailable. Please try again shortly.') + '</div>'; }
  function freshness(ts) {
    if (!ts) return '';
    var days = Math.round((Date.now() - new Date(ts)) / 864e5);
    var cls = days <= 7 ? 'fresh' : days <= 45 ? 'aging' : 'stale';
    return '<span class="bnn-i-fresh ' + cls + '" title="Last data update">● Updated ' + esc(date(ts)) + '</span>';
  }

  /* ---------- Ranking table ---------- */
  function ranking(root) {
    var params = root.dataset.category ? { category: root.dataset.category } : {};
    api('ranking/', params).then(function (d) {
      if (!d.results || !d.results.length) return fail(root, d.message || 'The ' + (d.period || '') + ' ranking has not been published yet. Rankings are released only after data verification.');
      var rows = d.results, regions = {};
      rows.forEach(function (r) { regions[r.country.region] = 1; });
      var m = d.snapshot.methodology;
      root.innerHTML =
        '<div class="bnn-i-head"><div><span class="bnn-i-eyebrow">' + esc(d.label) + '</span>' +
        '<p class="bnn-i-meta">Period ' + esc(d.period) + ' · Methodology v' + esc(m.version) + ' (' + esc(m.mode) + ' weighting) · Published ' + esc(date(d.snapshot.published_at)) + '</p></div>' +
        '<div class="bnn-i-tools"><input type="search" placeholder="Search country…" aria-label="Search country">' +
        '<select aria-label="Region"><option value="">All regions</option>' + Object.keys(regions).sort().map(function (r) { return '<option>' + esc(r) + '</option>'; }).join('') + '</select></div></div>' +
        '<div class="bnn-i-scroll"><table class="bnn-i-table"><thead><tr>' +
        '<th data-k="rank">Rank</th><th data-k="name">Country</th><th data-k="score">Score</th><th data-k="chg">Change</th><th data-k="cov">Data coverage</th><th>Confidence</th></tr></thead><tbody></tbody></table></div>' +
        '<p class="bnn-i-note">' + esc(m.limitations || '') + ' Countries without enough verified data are shown as “Not Ranked – Insufficient Data”; missing data is never counted as zero.</p>';
      var tbody = root.querySelector('tbody'), q = root.querySelector('input'), sel = root.querySelector('select');
      var sortKey = 'rank', dir = 1;
      function key(r) {
        return { rank: r.rank || 1e9, name: r.country.name, score: -(r.score == null ? -1 : r.score), chg: -(r.position_change || 0), cov: -r.coverage }[sortKey];
      }
      function draw() {
        var t = q.value.toLowerCase(), reg = sel.value;
        var list = rows.filter(function (r) { return (!t || r.country.name.toLowerCase().indexOf(t) > -1) && (!reg || r.country.region === reg); })
          .sort(function (a, b) { var x = key(a), y = key(b); return (x > y ? 1 : x < y ? -1 : 0) * dir; });
        tbody.innerHTML = list.map(function (r) {
          return '<tr class="' + (r.is_ranked ? '' : 'is-unranked') + '"><td class="bnn-i-rank">' + (r.is_ranked ? r.rank : '–') + '</td>' +
            '<td><a href="' + countryUrl(r.country.slug) + '"><span class="bnn-i-flag">' + esc(r.country.flag_emoji) + '</span>' + esc(r.country.name) + '</a><small>' + esc(r.country.region) + '</small></td>' +
            '<td>' + (r.is_ranked ? '<strong>' + fmt(r.score, 1) + '</strong>' + bar(r.score) : '<em class="bnn-i-muted">' + esc(r.status_label) + '</em>') + '</td>' +
            '<td>' + (r.is_ranked ? change(r.position_change) : '') + '</td><td>' + fmt(r.coverage * 100, 0) + '%</td><td>' + (r.is_ranked ? badge(r.confidence) : '') + '</td></tr>';
        }).join('') || '<tr><td colspan="6" class="bnn-i-muted">No matching countries.</td></tr>';
      }
      root.querySelectorAll('th[data-k]').forEach(function (th) {
        th.tabIndex = 0;
        th.addEventListener('click', function () { if (sortKey === th.dataset.k) dir = -dir; else { sortKey = th.dataset.k; dir = 1; } draw(); });
      });
      q.addEventListener('input', draw); sel.addEventListener('change', draw); draw();
    }).catch(function () { fail(root); });
  }

  /* ---------- Official (source) rankings ---------- */
  function official(root) {
    api('official-rankings/', { indicator: root.dataset.indicator || 'wgi_cc' }).then(function (d) {
      if (!d.results.length) return fail(root, 'No published data for this index yet.');
      var src = d.results[0];
      root.innerHTML = '<div class="bnn-i-head"><div><span class="bnn-i-eyebrow">' + esc(src.source) + ' · ' + esc(d.edition) + '</span>' +
        '<p class="bnn-i-meta">' + esc(d.note) + '</p></div></div>' +
        '<div class="bnn-i-scroll"><table class="bnn-i-table"><thead><tr><th>Asia position<br><small>(BNN calculation)</small></th><th>Country</th><th>Value</th><th>Official global rank</th><th>Source</th></tr></thead><tbody>' +
        d.results.map(function (r) {
          return '<tr><td class="bnn-i-rank">' + r.bnn_asia_position + '</td><td><a href="' + countryUrl(r.country.slug) + '">' + esc(r.country.flag_emoji) + ' ' + esc(r.country.name) + '</a></td>' +
            '<td>' + fmt(r.value) + '</td><td>' + (r.official_global_rank ? r.official_global_rank + ' / ' + r.official_global_of : '–') + '</td>' +
            '<td><a href="' + esc(r.source_url) + '" target="_blank" rel="noopener">' + esc(r.source) + '</a></td></tr>';
        }).join('') + '</tbody></table></div>';
    }).catch(function () { fail(root); });
  }

  /* ---------- Country directory with tile map ---------- */
  function countries(root) {
    api('countries/').then(function (list) {
      var regions = {};
      list.forEach(function (c) { (regions[c.region] = regions[c.region] || []).push(c); });
      root.innerHTML = '<div class="bnn-i-tools wide"><input type="search" placeholder="Find a country…" aria-label="Find a country">' +
        '<div class="bnn-i-chips"><button class="on" data-r="">All</button>' + Object.keys(regions).sort().map(function (r) { return '<button data-r="' + esc(r) + '">' + esc(r) + '</button>'; }).join('') + '</div></div>' +
        '<div class="bnn-i-grid"></div>';
      var grid = root.querySelector('.bnn-i-grid'), q = root.querySelector('input'), reg = '';
      function draw() {
        var t = q.value.toLowerCase();
        grid.innerHTML = list.filter(function (c) { return (!reg || c.region === reg) && (!t || c.name.toLowerCase().indexOf(t) > -1); })
          .map(function (c) {
            return '<a class="bnn-i-tile" href="' + countryUrl(c.slug) + '"><span class="bnn-i-flag big">' + esc(c.flag_emoji) + '</span><strong>' + esc(c.name) + '</strong><small>' + esc(c.region) + '</small></a>';
          }).join('');
      }
      root.querySelectorAll('.bnn-i-chips button').forEach(function (b) {
        b.addEventListener('click', function () { root.querySelectorAll('.bnn-i-chips button').forEach(function (x) { x.classList.remove('on'); }); b.classList.add('on'); reg = b.dataset.r; draw(); });
      });
      q.addEventListener('input', draw); draw();
    }).catch(function () { fail(root); });
  }

  /* ---------- Country profile ---------- */
  function svgBars(items) {
    // horizontal 0–100 bars for normalised category scores
    var h = items.length * 34 + 10;
    return '<svg class="bnn-i-svg" viewBox="0 0 520 ' + h + '" role="img" aria-label="Category scores">' + items.map(function (it, i) {
      var y = i * 34 + 6, w = it.score == null ? 0 : it.score * 3.2;
      return '<text x="0" y="' + (y + 15) + '">' + esc(it.label) + '</text><rect x="190" y="' + y + '" width="320" height="20" rx="4" class="bg"/>' +
        (it.score == null ? '<text x="196" y="' + (y + 15) + '" class="na">Insufficient data</text>' :
          '<rect x="190" y="' + y + '" width="' + w + '" height="20" rx="4" class="fg"/><text x="' + (196 + Math.max(w, 20)) + '" y="' + (y + 15) + '" class="val">' + fmt(it.score, 1) + '</text>');
    }).join('') + '</svg>';
  }
  function country(root) {
    var slug = root.dataset.slug;
    if (!slug) return fail(root, 'No country selected.');
    api('countries/' + slug + '/profile/').then(function (d) {
      var c = d.country, overall = (d.scores || []).filter(function (s) { return !s.category; })[0];
      var byCat = {};
      d.observations.forEach(function (o) { (byCat[o.category] = byCat[o.category] || []).push(o); });
      var catScores = {};
      (d.scores || []).forEach(function (s) { if (s.category) catScores[s.category] = s; });
      var tabs = d.categories.map(function (cat, i) {
        return '<button role="tab" aria-selected="' + (i === 0) + '" data-t="' + esc(cat.slug) + '">' + esc(cat.name) + '</button>';
      }).join('');
      var panels = d.categories.map(function (cat, i) {
        var obs = byCat[cat.slug] || [];
        var current = obs.filter(function (o) { return !o.is_historical; }), hist = obs.filter(function (o) { return o.is_historical; });
        var cs = catScores[cat.slug];
        function row(o) {
          return '<tr><td>' + esc(o.indicator_name) + '</td><td><strong>' + fmt(o.value) + '</strong> ' + esc(o.unit) + '</td><td>' + esc(o.reference_label) +
            (o.data_status !== 'final' ? ' <span class="bnn-i-badge bnn-i-c-low">' + esc(o.data_status) + '</span>' : '') + '</td>' +
            '<td>' + (o.published_rank ? o.published_rank + ' / ' + o.published_rank_of : '–') + '</td>' +
            '<td><a href="' + esc(o.source_url) + '" target="_blank" rel="noopener">' + esc(o.source) + '</a></td></tr>';
        }
        return '<section role="tabpanel" data-p="' + esc(cat.slug) + '"' + (i ? ' hidden' : '') + '>' +
          '<p class="bnn-i-meta">' + esc(cat.description) + '</p>' +
          (cs ? '<p class="bnn-i-catscore">' + (cs.is_ranked ? 'Category score <strong>' + fmt(cs.score, 1) + '</strong> · Asia rank ' + cs.rank : esc(cs.status_label)) + '</p>' : '') +
          (current.length ? '<div class="bnn-i-scroll"><table class="bnn-i-table compact"><thead><tr><th>Indicator</th><th>Value</th><th>Reference</th><th>Global rank</th><th>Source</th></tr></thead><tbody>' + current.map(row).join('') + '</tbody></table></div>'
            : '<div class="bnn-i-empty">No verified data for this category in the current reporting period.</div>') +
          (hist.length ? '<details class="bnn-i-hist"><summary>Historical reference (' + hist.length + ') – not used in ' + esc(d.period.name) + ' scores</summary><table class="bnn-i-table compact"><tbody>' + hist.map(row).join('') + '</tbody></table></details>' : '') +
          '</section>';
      }).join('');
      var inc = d.recent_incidents || [];
      root.innerHTML =
        '<header class="bnn-i-hero"><div><span class="bnn-i-eyebrow">' + esc(c.region) + ' · Country intelligence ' + esc(d.period.name) + '</span>' +
        '<h1><span class="bnn-i-flag big">' + esc(c.flag_emoji) + '</span> ' + esc(c.name) + '</h1>' +
        '<p class="bnn-i-meta">Capital: ' + esc(c.capital) + ' · ' + freshness(d.last_updated) + '</p></div>' +
        '<div class="bnn-i-kpi">' + (overall && overall.is_ranked ?
          '<span>BNN Asia Index</span><b>' + fmt(overall.score, 1) + '</b><em>Rank ' + overall.rank + ' ' + change(overall.position_change) + '</em>' + badge(overall.confidence) :
          '<span>BNN Asia Index</span><b class="na">Not ranked</b><em>' + esc(overall ? overall.status_label : 'Ranking not yet published') + '</em>') + '</div></header>' +
        (Object.keys(catScores).length ? '<div class="bnn-i-card">' + svgBars(d.categories.filter(function (x) { return catScores[x.slug]; }).map(function (x) { return { label: x.name, score: catScores[x.slug].score }; })) + '</div>' : '') +
        '<div class="bnn-i-tabs" role="tablist">' + tabs + '</div><div class="bnn-i-panels">' + panels + '</div>' +
        '<h2 class="bnn-i-h2">Verified incidents ' + esc(d.period.name) + '</h2>' +
        (Object.keys(d.incident_counts).length ? '<div class="bnn-i-counts">' + Object.keys(d.incident_counts).map(function (k) { return '<div><b>' + d.incident_counts[k] + '</b><span>' + esc(k) + '</span></div>'; }).join('') + '</div>' : '') +
        (inc.length ? '<ul class="bnn-i-inc">' + inc.map(function (i) {
          return '<li><time>' + esc(date(i.event_date)) + '</time><strong>' + esc(i.type) + '</strong> ' + esc(i.title) +
            '<div class="bnn-i-src">' + i.sources.map(function (s) { return '<a href="' + esc(s.url) + '" target="_blank" rel="noopener">' + esc(s.organisation) + '</a>'; }).join(' · ') + '</div></li>';
        }).join('') + '</ul>' : '<div class="bnn-i-empty">No published, verified incidents for this period yet.</div>') +
        (d.reports.length ? '<h2 class="bnn-i-h2">Reports</h2><ul class="bnn-i-reports">' + d.reports.map(function (r) { return '<li><a href="' + esc(r.pdf_url) + '" target="_blank" rel="noopener">⬇ ' + esc(r.title) + ' (PDF)</a></li>'; }).join('') + '</ul>' : '') +
        '<p class="bnn-i-note">All figures link to their original source. BNN Asia scores are BNN Asia’s own calculation; official ranks belong to the publishing organisations.</p>';
      root.querySelectorAll('[role=tab]').forEach(function (b) {
        b.addEventListener('click', function () {
          root.querySelectorAll('[role=tab]').forEach(function (x) { x.setAttribute('aria-selected', x === b); });
          root.querySelectorAll('[role=tabpanel]').forEach(function (p) { p.hidden = p.dataset.p !== b.dataset.t; });
        });
      });
    }).catch(function () { fail(root, 'Country data is temporarily unavailable.'); });
  }

  /* ---------- Category page: indicator × country heat table ---------- */
  function category(root) {
    var slug = root.dataset.slug;
    Promise.all([api('config/'), api('indicators/')]).then(function (r) {
      var cat = r[0].categories.filter(function (c) { return c.slug === slug; })[0];
      if (!cat) return fail(root, 'This category is not currently published.');
      var inds = r[1].filter(function (i) { return i.category === slug; });
      root.innerHTML = '<div class="bnn-i-head"><div><span class="bnn-i-eyebrow">' + esc(cat.name) + '</span><p class="bnn-i-meta">' + esc(cat.description) + '</p></div>' +
        '<div class="bnn-i-tools"><select aria-label="Indicator">' + inds.map(function (i) { return '<option value="' + esc(i.code) + '">' + esc(i.name) + '</option>'; }).join('') + '</select></div></div><div class="bnn-i-out"></div>';
      var sel = root.querySelector('select'), out = root.querySelector('.bnn-i-out');
      function draw() {
        out.innerHTML = '<div class="bnn-i-skeleton"></div>';
        var o = document.createElement('div'); o.className = 'bnn-intel'; o.dataset.indicator = sel.value;
        out.innerHTML = ''; out.appendChild(o); official(o);
      }
      sel.addEventListener('change', draw); if (inds.length) draw(); else fail(out, 'No indicators published yet.');
    }).catch(function () { fail(root); });
  }

  /* ---------- Comparison ---------- */
  function compare(root) {
    Promise.all([api('countries/'), api('indicators/')]).then(function (r) {
      var cs = r[0], inds = r[1].filter(function (i) { return i.used_in_scoring; });
      var pre = (root.dataset.countries || 'bangladesh,india,pakistan').split(',');
      var chosenSet = pre.slice(0, 6);
      root.innerHTML = '<div class="bnn-i-tools wide"><input type="search" placeholder="Filter countries…" aria-label="Filter countries">' +
        '<div class="bnn-i-chips" role="group" aria-label="Countries to compare (up to 6)">' + cs.map(function (c) {
          return '<button type="button" data-s="' + esc(c.slug) + '" aria-pressed="' + (chosenSet.indexOf(c.slug) > -1) + '"' + (chosenSet.indexOf(c.slug) > -1 ? ' class="on"' : '') + '>' + esc(c.flag_emoji) + ' ' + esc(c.name) + '</button>'; }).join('') +
        '</div><small class="bnn-i-muted">Select up to 6 countries.</small></div><div class="bnn-i-out"></div>';
      var out = root.querySelector('.bnn-i-out'), filt = root.querySelector('input');
      filt.addEventListener('input', function () { var t = filt.value.toLowerCase(); root.querySelectorAll('.bnn-i-chips button').forEach(function (b) { b.hidden = t && b.textContent.toLowerCase().indexOf(t) < 0 && !b.classList.contains('on'); }); });
      root.querySelectorAll('.bnn-i-chips button').forEach(function (b) {
        b.addEventListener('click', function () {
          var i = chosenSet.indexOf(b.dataset.s);
          if (i > -1) chosenSet.splice(i, 1); else if (chosenSet.length < 6) chosenSet.push(b.dataset.s); else return;
          b.classList.toggle('on', chosenSet.indexOf(b.dataset.s) > -1); b.setAttribute('aria-pressed', chosenSet.indexOf(b.dataset.s) > -1); draw();
        });
      });
      function draw() {
        var chosen = chosenSet.slice();
        if (!chosen.length) { out.innerHTML = ''; return; }
        api('compare/', { countries: chosen.join(',') }).then(function (d) {
          var names = {}; cs.forEach(function (c) { names[c.slug] = c.flag_emoji + ' ' + c.name; });
          out.innerHTML = '<div class="bnn-i-scroll"><table class="bnn-i-table"><thead><tr><th>Indicator</th>' + chosen.map(function (s) { return '<th>' + esc(names[s]) + '</th>'; }).join('') + '</tr></thead><tbody>' +
            inds.filter(function (i) { return d.indicators[i.code]; }).map(function (i) {
              var vals = d.indicators[i.code].values, nums = chosen.map(function (s) { return vals[s] ? vals[s].value : null; }).filter(function (v) { return v != null; });
              var best = i.direction === 'lower_better' ? Math.min.apply(null, nums) : Math.max.apply(null, nums);
              return '<tr><td>' + esc(i.name) + ' <small>' + esc(i.unit) + '</small></td>' + chosen.map(function (s) {
                var v = vals[s];
                return '<td' + (v && v.value === best && nums.length > 1 ? ' class="best"' : '') + '>' + (v ? '<a href="' + esc(v.source_url) + '" target="_blank" rel="noopener" title="' + esc(v.ref) + '">' + fmt(v.value) + '</a>' : '<span class="bnn-i-muted">no data</span>') + '</td>';
              }).join('') + '</tr>';
            }).join('') + '</tbody></table></div><p class="bnn-i-note">Highlighted = best among selected countries. “no data” means no verified figure – it is not zero.</p>';
        }).catch(function () { fail(out); });
      }
      draw();
    }).catch(function () { fail(root); });
  }

  /* ---------- Incidents list ---------- */
  function incidents(root) {
    var p = { limit: root.dataset.limit || 20 };
    if (root.dataset.country) p.country__slug = root.dataset.country;
    api('incidents/', p).then(function (d) {
      var list = d.results || [];
      if (!list.length) return fail(root, 'No published, verified incidents yet.');
      root.innerHTML = '<ul class="bnn-i-inc">' + list.map(function (i) {
        return '<li><time>' + esc(date(i.event_date)) + '</time><strong>' + esc(i.type) + '</strong> <a href="' + countryUrl(i.country) + '">' + esc(i.title) + '</a>' +
          (i.victims_reported_min != null ? '<span class="bnn-i-muted"> · reported ' + (i.victims_reported_min === i.victims_reported_max ? i.victims_reported_min : i.victims_reported_min + '–' + i.victims_reported_max) + '</span>' : '') +
          '<div class="bnn-i-src">' + i.sources.map(function (s) { return '<a href="' + esc(s.url) + '" target="_blank" rel="noopener">' + esc(s.organisation) + '</a>'; }).join(' · ') + '</div></li>';
      }).join('') + '</ul>';
    }).catch(function () { fail(root); });
  }

  var VIEWS = { ranking: ranking, official: official, countries: countries, country: country, category: category, compare: compare, incidents: incidents };
  function boot() {
    document.querySelectorAll('.bnn-intel[data-bnn]').forEach(function (root) {
      var fn = VIEWS[root.dataset.bnn];
      if (fn && !root.dataset.ready) { root.dataset.ready = 1; fn(root); }
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();

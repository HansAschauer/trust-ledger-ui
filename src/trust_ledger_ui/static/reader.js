/* The read-only page for referees and readers (SPEC.md section 16): one paper's ledger, from the JSON block that
 * `ledger-ui --export` writes into the page. No network, no state beyond the address (#claim=..., #hyp=...). */
function readerApp() {
  const ORDER = { ok: 0, stale: 1, none: 2 };
  const VERDICT = { consistent: 'ok', partial: 'stale', check: 'stale', mismatch: 'none', unclear: 'stale' };
  return {
    d: null, error: '', view: 'claims', filter: 'all', search: '', sortKey: 'name', sortDir: 1,
    current: '', detail: null, rendered: null, renderIssues: [], currentHyp: '', hypDetail: null, hypRendered: null, diffView: null,

    init() {
      try { this.d = JSON.parse(document.getElementById('ledger-data').textContent); }
      catch (e) { this.error = 'The data block of this page cannot be read: ' + e.message; return; }
      if (!this.d) { this.error = 'This is the page template. Run `ledger-ui --export DIR` to write a page with a ledger in it.'; return; }
      for (const c of this.d.status.claims) c.attention = !c.attestations.length ? 'none' : c.attestations.some(a => a.current) ? 'ok' : 'stale';
      window.addEventListener('hashchange', () => this.route());
      this.route();
    },
    route() {
      const h = new URLSearchParams(location.hash.slice(1));
      if (h.get('claim') && this.d.claims[h.get('claim')]) { this.view = 'claims'; this.show(h.get('claim')); }
      else if (h.get('hyp') && this.d.hypotheses[h.get('hyp')]) { this.view = 'hyps'; this.showHyp(h.get('hyp')); }
      else if (h.get('view')) this.view = h.get('view');
    },
    go(kind, name) { location.hash = kind + '=' + encodeURIComponent(name); },

    // ---- header
    get title() { return this.d ? (this.d.title || this.d.paper) : ''; },
    get counts() {
      const cl = this.d ? this.d.status.claims : [];
      const n = (f) => cl.filter(f).length;
      const hs = this.d ? this.d.status.hypotheses : [];
      return { claims: cl.length, ok: n(c => c.attention === 'ok'), stale: n(c => c.attention === 'stale'), none: n(c => c.attention === 'none'),
               hyps: hs.length, known: hs.filter(h => h.known_theorem).length };
    },
    get rootMismatch() { return this.d && this.d.printed_root && this.d.printed_root !== this.d.status.root; },
    get dirty() { return this.d && this.d.git && this.d.git.dirty_count > 0; },
    get repoUrl() { return this.d && this.d.repo && /^https:\/\//.test(this.d.repo) ? this.d.repo : ''; },
    evidenceName(id) { const e = this.d ? this.d.vocabulary.evidence.find(x => x.id === id) : null; return e ? e.name : id; },

    // ---- the list
    verdictOf(c) { return c.assessment ? c.assessment.verdict : ''; },
    get rows() {
      if (!this.d) return [];
      const s = this.search.trim().toLowerCase();
      const r = this.d.status.claims.filter(c => {
        if (['ok', 'stale', 'none'].includes(this.filter) && c.attention !== this.filter) return false;
        if (this.filter === 'toolnotok' && !Object.values(c.tools).some(t => t.status !== 'ok' && t.status !== 'none')) return false;
        if (this.filter === 'notool' && Object.values(c.tools).some(t => t.status !== 'none')) return false;
        if (this.filter === 'assessnot' && !(c.assessment && c.assessment.verdict !== 'consistent')) return false;
        if (this.filter === 'hyp' && !c.hypotheses.length) return false;
        return !s || c.name.toLowerCase().includes(s) || c.labels.some(l => l.toLowerCase().includes(s));
      });
      const k = this.sortKey, dir = this.sortDir;
      const key = (c) => k === 'attention' ? ORDER[c.attention] : k === 'label' ? (c.labels[0] || '~') : k === 'verdict' ? this.verdictOf(c) : c[k];
      r.sort((a, b) => { const x = key(a), y = key(b); return (x < y ? -1 : x > y ? 1 : a.name < b.name ? -1 : 1) * dir; });
      return r;
    },
    sortBy(k) { if (this.sortKey === k) this.sortDir = -this.sortDir; else { this.sortKey = k; this.sortDir = 1; } },
    attLabel(c) {
      if (!c.attestations.length) return 'not attested';
      const cur = c.attestations.filter(a => a.current);
      const a = cur.length ? cur[0] : c.attestations[0];
      return a.level + (a.current ? '' : ' · stale') + (c.attestations.length > 1 ? ' +' + (c.attestations.length - 1) : '');
    },
    toolText(c, t) {
      const x = c.tools[t]; if (!x || x.status === 'none') return '';
      const k = x.known_theorems && x.known_theorems[1] ? ' (' + x.known_theorems[0] + '/' + x.known_theorems[1] + ' known)' : '';
      return x.word + k;
    },
    toolClass(c, t) {
      const s = c.tools[t] && c.tools[t].status;
      return s === 'failed' || s === 'missing' ? 'bad' : s === 'open' || s === 'conditional' ? 'warn' : '';
    },
    verdictClass(v) { return VERDICT[v] || 'stale'; },

    // ---- one claim
    record(name, kind, a) {          // the written record behind a row of status: reason, checklist, signature state
      const recs = this.d.attestations.filter(r => r[kind] === name && r.person === a.person && r.level === a.level && r.date === a.date);
      return recs.length ? recs[recs.length - 1] : null;
    },
    sigText(s) {
      return { signed: 'signature valid (checked by ledger.py when this page was generated)', unsigned: 'not signed',
               unchecked: 'signed; not checked when this page was generated', invalid: 'signature INVALID', 'unknown-key': 'signed with an unregistered key',
               revoked: 'signed with a revoked key' }[s] || s;
    },
    show(name) {
      const d = this.d.claims[name];
      if (!d) return;
      this.current = name; this.detail = null; this.diffView = null;
      const issues = [];
      const run = (src) => { const r = texlite.toHtml(src, { katex, macros: this.d.macros }); issues.push(...r.failures); return r; };
      this.rendered = { statement: run(d.statement), reading: d.reading ? run(d.reading) : null,
                        assessment: d.assessment && d.assessment.notes ? run(d.assessment.notes) : null };
      this.renderIssues = issues;
      this.detail = d;
      const df = this.d.diffs['claim:' + name];
      if (df) this.diffView = this.buildDiff(df);
      this.$nextTick(() => { const el = document.querySelector('#detail-claim'); if (el && window.innerWidth <= 900) el.scrollIntoView(); });
    },
    get detailAttention() {
      if (!this.detail) return 'none';
      const a = this.detail.attestations;
      return !a.length ? 'none' : a.some(x => x.current) ? 'ok' : 'stale';
    },
    get detailAttentionText() { return { none: 'not attested', stale: 'attestation stale', ok: 'attested' }[this.detailAttention]; },
    hypsOf(c) { return (c.hypotheses || []).map(h => typeof h === 'string' ? h : h.name); },

    buildDiff(d) {
      const base = { available: d.available, current: !!d.current, att: d.attestation || null, reason: d.reason || '', git: d.git || null,
                     unverified: d.unverified || null };
      if (!d.available || d.current) return base;
      return Object.assign(base, {
        textChanged: d.text.changed, textHtml: tldiff.toHtml(tldiff.diff(d.text.old, d.text.new)),
        uses: d.uses.map(u => ({ name: u.name, change: u.change,
          html: u.old_text !== u.new_text ? tldiff.toHtml(tldiff.diff(u.old_text || '', u.new_text || '')) : '' })),
        nodes: d.nodes.map(n => ({ id: n.id, kind: n.kind, change: n.change, same: n.content_same, fields: tldiff.fields(n.old || {}, n.new || {}) })),
      });
    },

    // ---- hypotheses
    hypRow(name) { return this.d.status.hypotheses.find(h => h.name === name) || null; },
    hypStatus(h) {
      const cur = h.attestations.filter(x => x.current);
      if (cur.length) return cur[0].level === 'green' ? 'known theorem' : cur[0].level;
      return h.attestations.length ? 'stale' : 'not attested';
    },
    hypClass(h) { const s = this.hypStatus(h); return s === 'known theorem' ? 'ok' : s === 'not attested' ? 'none' : 'stale'; },
    showHyp(name) {
      const d = this.d.hypotheses[name];
      if (!d) return;
      this.currentHyp = name; this.diffView = null;
      this.hypRendered = texlite.toHtml(d.statement, { katex, macros: this.d.macros });
      this.hypDetail = d;
      const df = this.d.diffs['hypothesis:' + name];
      if (df) this.diffView = this.buildDiff(df);
    },
    get claimChecklist() { return this.d ? Object.entries(this.d.vocabulary.checklist).filter(([, v]) => v.applies !== 'hypothesis') : []; },
    get lockCounts() {
      if (!this.d || !this.d.lock) return { nodes: 0, kinds: [] };
      const k = {};
      for (const n of Object.values(this.d.lock.nodes)) k[n.kind] = (k[n.kind] || 0) + 1;
      return { nodes: Object.keys(this.d.lock.nodes).length, kinds: Object.entries(k).sort((a, b) => b[1] - a[1]) };
    },
  };
}

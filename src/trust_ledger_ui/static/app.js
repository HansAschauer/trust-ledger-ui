/* The page: one Alpine component. All state lives on the server (the ledger's own files); this only displays it. */
function ledgerApp() {
  const ORDER = { none: 0, stale: 1, ok: 2 };
  return {
    token: '', overview: { papers: [], project: '', person: '', key: '' }, scope: '', data: null,
    loading: false, error: '', changed: false,
    filter: 'attention', search: '', sortKey: 'attention', sortDir: 1,
    current: '', detail: null, rendered: { statement: { html: '' }, reading: null }, renderIssues: [],
    macroCache: {}, auditRows: null, auditScope: null, auditLoading: false, auditMsg: '', recovering: false, recoverMsg: '', diffView: null, view: 'claims', currentHyp: '', hypDetail: null, hypRendered: null, selected: [], jobs: [], jobsOpen: false, jobLog: { id: null, lines: [], next: 0 }, packView: null,

    async init() {
      const h = location.hash.slice(1);
      if (h) { sessionStorage.setItem('tlui-token', h); history.replaceState(null, '', location.pathname + location.search); }
      this.token = sessionStorage.getItem('tlui-token') || '';
      if (!this.token) { this.error = 'No access token: open the URL that ledger-ui printed (it ends in #token).'; return; }
      await this.refreshOverview();
      const qs = new URLSearchParams(location.search);
      this.scope = qs.has('paper') ? qs.get('paper') : localStorage.getItem('tlui-scope');
      if (this.scope === null || (this.scope !== '' && !this.overview.papers.some(p => p.name === this.scope)))
        this.scope = this.overview.papers.length ? this.overview.papers[0].name : '';
      this.pollOverview();
      setInterval(() => this.pollState(), 5000);
      document.addEventListener('keydown', (e) => this.onKey(e));
      this.refreshJobs();
      await this.loadScope();
      if (qs.get('claim')) this.open(qs.get('claim'));
    },

    async api(path, method, body) {
      const headers = { Authorization: 'Bearer ' + this.token };
      if (body !== undefined) headers['Content-Type'] = 'application/json';
      const r = await fetch(path, { method: method || 'GET', headers, body: body === undefined ? undefined : JSON.stringify(body) });
      let out = null;
      try { out = await r.json(); } catch (e) { /* not JSON */ }
      if (!r.ok) throw new Error((out && out.error) || (r.status + ' ' + r.statusText));
      return out;
    },
    q(extra) { return '?paper=' + encodeURIComponent(this.scope) + (extra || ''); },

    async refreshOverview() {
      try { this.overview = await this.api('/api/papers'); } catch (e) { this.error = e.message; }
    },
    pollOverview() {                       // the server loads all papers in the background; show their counts when ready
      if (!this.overview.papers.some(p => p.state === 'loading')) return;
      setTimeout(async () => { await this.refreshOverview(); this.pollOverview(); }, 1500);
    },
    async pollState() {
      if (!this.data || this.loading) return;
      try { this.changed = (await this.api('/api/state' + this.q())).changed; } catch (e) { /* server gone: ignore */ }
    },

    async selectScope() {
      localStorage.setItem('tlui-scope', this.scope); this.auditRows = null;
      this.current = ''; this.detail = null; this.currentHyp = ''; this.hypDetail = null; this.selected = []; this.link();
      await this.loadScope();
    },
    async loadScope() {
      this.loading = true; this.error = ''; this.changed = false;
      try { this.data = await this.api('/api/claims' + this.q()); }
      catch (e) { this.error = e.message; this.data = null; }
      this.loading = false;
      this.refreshOverview();
    },
    async reload() {
      this.auditRows = null;
      this.loading = true;
      try { await this.api('/api/reload' + this.q(), 'POST'); } catch (e) { /* GET below reports */ }
      this.macroCache = {};
      await this.loadScope();
      if (this.current) this.open(this.current);
    },

    // ---- the list
    get rows() {
      if (!this.data) return [];
      const s = this.search.trim().toLowerCase();
      let r = this.data.claims.filter(c => {
        if (this.filter === 'attention' && c.attention === 'ok') return false;
        if (this.filter === 'none' && c.attention !== 'none') return false;
        if (this.filter === 'stale' && c.attention !== 'stale') return false;
        if (this.filter === 'current' && c.attention !== 'ok') return false;
        if (this.filter === 'assessold' && !(c.assessment && c.assessment.state !== 'current')) return false;
        if (this.filter === 'toolnotok' && !Object.values(c.tools).some(t => t.status !== 'ok' && t.status !== 'none')) return false;
        return !s || c.name.toLowerCase().includes(s) || c.labels.some(l => l.toLowerCase().includes(s));
      });
      const k = this.sortKey, d = this.sortDir;
      r.sort((a, b) => {
        const x = k === 'attention' ? ORDER[a.attention] : a[k], y = k === 'attention' ? ORDER[b.attention] : b[k];
        return (x < y ? -1 : x > y ? 1 : a.name < b.name ? -1 : 1) * d;
      });
      return r;
    },
    sortBy(k) { if (this.sortKey === k) this.sortDir = -this.sortDir; else { this.sortKey = k; this.sortDir = 1; } },
    attLabel(c) {                                      // a current attestation is the one that counts; else the first stale one
      if (!c.attestations.length) return 'none';
      const cur = c.attestations.filter(a => a.current);
      const a = cur.length ? cur[0] : c.attestations[0];
      return a.level + (a.current ? '' : ' · STALE') + (c.attestations.length > 1 ? ' +' + (c.attestations.length - 1) : '');
    },
    toolText(c, t) {
      const x = c.tools[t]; if (!x) return '';
      const k = x.known_theorems && x.known_theorems[0] ? ' (' + x.known_theorems[0] + '/' + x.known_theorems[1] + ' known)' : '';
      return x.word + k;
    },
    toolClass(c, t) {
      const s = c.tools[t] && c.tools[t].status;
      return s === 'failed' || s === 'missing' ? 'bad' : s === 'open' || s === 'conditional' ? 'warn' : '';
    },

    // ---- the detail
    get detailAttention() {
      if (!this.detail) return 'none';
      const a = this.detail.attestations;
      return !a.length ? 'none' : a.some(x => x.current) ? 'ok' : 'stale';
    },
    get detailAttentionText() { return { none: 'no attestation', stale: 'stale', ok: 'current' }[this.detailAttention]; },

    async macrosFor(paper) {
      const key = paper || '';
      if (!this.macroCache[key]) this.macroCache[key] = await this.api('/api/macros?paper=' + encodeURIComponent(key));
      return this.macroCache[key];
    },
    link() {                               // keep the selection in the address, so that a reload returns to it
      const qs = new URLSearchParams({ paper: this.scope });
      if (this.current) qs.set('claim', this.current);
      history.replaceState(null, '', '?' + qs);
    },
    async open(name) {
      this.current = name; this.detail = null; this.renderIssues = []; this.diffView = null; this.link();
      try {
        const d = await this.api('/api/claims/' + encodeURIComponent(name) + this.q());
        const macros = await this.macrosFor(d.paper || this.scope);
        const issues = [];
        const run = (src) => {
          const r = texlite.toHtml(src, { katex, macros });
          issues.push(...r.failures);
          return r;
        };
        this.rendered = { statement: run(d.statement), reading: d.reading ? run(d.reading) : null,
                          assessment: d.assessment && d.assessment.notes ? run(d.assessment.notes) : null };
        this.renderIssues = issues;
        this.detail = d;
        this.loadDiff('claim', name, d.attestations);
        if (d.assessment && d.assessment.state === 'unbound') this.loadAudit();
        if (window.innerWidth <= 900) document.querySelector('#detail-claim').scrollIntoView();
      } catch (e) { this.error = e.message; }
    },

    // ---- selection (for a batch)
    toggleSel(name) {
      const i = this.selected.indexOf(name);
      if (i >= 0) this.selected.splice(i, 1); else this.selected.push(name);
    },
    get allShownSelected() { return this.rows.length > 0 && this.rows.every(c => this.selected.includes(c.name)); },
    toggleShown(on) {
      const shown = this.rows.map(c => c.name);
      this.selected = on ? [...new Set([...this.selected, ...shown])] : this.selected.filter(n => !shown.includes(n));
    },
    selectBy(how) {
      if (!this.data || !how) return;
      const pick = (f) => this.data.claims.filter(f).map(c => c.name);
      if (how === 'clear') this.selected = [];
      else if (how === 'shown') this.selected = this.rows.map(c => c.name);
      else if (how === 'stale') this.selected = pick(c => c.attention === 'stale');
      else if (how === 'none') this.selected = pick(c => c.attention === 'none');
      else if (how === 'unseen') this.selected = this.rows.filter(c => !this.isSeen(c.name)).map(c => c.name);
    },
    get selectedSeen() { this.seenTick; return this.selected.filter(n => this.isSeen(n)).length; },
    get unseenSelected() { this.seenTick; return this.selected.filter(n => !this.isSeen(n)); },
    nextUnseen() {                                    // the next selected, unseen claim after the current one (in list order)
      const order = this.rows.map(c => c.name).filter(n => this.unseenSelected.includes(n));
      if (!order.length) return;
      const i = order.indexOf(this.current);
      this.open(order[(i + 1) % order.length]);
    },
    moveCurrent(d) {
      if (this.view === 'hyps') {
        const hs = this.data ? this.data.hypotheses.map(x => x.name) : [];
        if (hs.length) { const i = hs.indexOf(this.currentHyp); this.openHyp(hs[Math.min(hs.length - 1, Math.max(0, i < 0 ? 0 : i + d))]); }
        return;
      }
      const names = this.rows.map(c => c.name);
      if (!names.length) return;
      const i = names.indexOf(this.current);
      this.open(names[Math.min(names.length - 1, Math.max(0, i < 0 ? 0 : i + d))]);
    },

    // ---- "seen": the person read this claim in its current state (explicit; kept in this browser, not in the ledger)
    boundOf(name, kind) {
      if (!this.data) return '';
      const x = (kind === 'hypothesis' ? this.data.hypotheses : this.data.claims).find(c => c.name === name);
      return x ? x.bound : '';
    },
    seenKey(name, kind) { return 'tlui-seen:' + (this.overview.project || '') + ':' + (kind === 'hypothesis' ? 'hyp:' : '') + name; },
    isSeen(name, kind) { const b = this.boundOf(name, kind); return !!b && localStorage.getItem(this.seenKey(name, kind)) === b; },
    toggleSeen(name, kind) {
      const k = this.seenKey(name, kind), b = this.boundOf(name, kind);
      if (this.isSeen(name, kind)) localStorage.removeItem(k); else localStorage.setItem(k, b);
      this.seenTick++;                                           // re-evaluate isSeen() in the page
    },
    seenTick: 0,
    seen(name, kind) { this.seenTick; return this.isSeen(name, kind); },
    onKey(e) {
      if (e.target.closest('input, textarea, select') || e.ctrlKey || e.metaKey || e.altKey || this.dlg.open) return;
      const hyp = this.view === 'hyps';
      if (e.key === 'v' && (hyp ? this.currentHyp : this.current)) this.toggleSeen(hyp ? this.currentHyp : this.current, hyp ? 'hypothesis' : 'claim');
      else if (e.key === 'a' && hyp && this.currentHyp) this.openAttest([this.currentHyp], 'hypothesis');
      else if (e.key === 'a' && this.current) this.openAttest(this.selected.length ? this.selected : [this.current]);
      else if (e.key === 'x' && !hyp && this.current) this.toggleSel(this.current);
      else if (e.key === 'j') this.moveCurrent(1);
      else if (e.key === 'k') this.moveCurrent(-1);
      else if (e.key === 't') this.view = hyp ? 'claims' : 'hyps';
    },

    // ---- attesting (SPEC.md section 6)
    dlg: { open: false, kind: 'claim', state: 'edit', targets: [], level: 'yellow', reason: '', checklist: [], key: '', ack: false,
           preview: null, job: null, error: '', opts: null, undone: '' },
    async openAttest(targets, kind) {
      Object.assign(this.dlg, { open: true, kind: kind || 'claim', state: 'edit', targets: targets.slice(), checklist: [], preview: null, job: null,
                                error: '', ack: false, undone: '' });
      try {
        this.dlg.opts = await this.api('/api/attest/options' + this.q());
        if (!this.dlg.key || !this.dlg.opts.keys.some(k => k.id === this.dlg.key)) this.dlg.key = this.dlg.opts.default_key;
        if (!this.dlg.opts.levels.includes(this.dlg.level)) this.dlg.level = this.dlg.opts.levels[0];
      } catch (e) { this.dlg.error = e.message; }
    },
    closeAttest() {
      const done = this.dlg.state === 'done' || this.dlg.state === 'failed';
      this.dlg.open = false;
      if (done) this.afterAttest();
    },
    async afterAttest() {
      const done = new Set(((this.dlg.job && this.dlg.job.results) || []).filter(r => r.status === 'attested').map(r => r.target));
      if (this.dlg.kind === 'claim') this.selected = this.selected.filter(n => !done.has(n));
      await this.loadScope();
      this.selected = this.selected.filter(n => this.data && this.data.claims.some(c => c.name === n));
      if (this.current) this.open(this.current);
      if (this.currentHyp) this.openHyp(this.currentHyp);
    },
    edited() { if (this.dlg.state === 'review') { this.dlg.state = 'edit'; this.dlg.preview = null; this.dlg.ack = false; } },
    toggleChecklist(id) {
      const i = this.dlg.checklist.indexOf(id);
      if (i >= 0) this.dlg.checklist.splice(i, 1); else this.dlg.checklist.push(id);
      this.edited();
    },
    useReason(r) { if (r) { this.dlg.reason = r; this.edited(); } },
    get claimChecklist() {                              // the checklist items that apply to what is being attested
      const c = this.dlg.opts ? this.dlg.opts.checklist : {};
      return Object.entries(c).filter(([, v]) => v.applies === this.dlg.kind || v.applies === 'both');
    },
    get unseen() { this.seenTick; return this.dlg.targets.filter(t => !this.isSeen(t, this.dlg.kind)); },
    get keyInfo() { return this.dlg.opts ? this.dlg.opts.keys.find(k => k.id === this.dlg.key) : null; },
    async reviewAttest() {
      this.dlg.error = '';
      try {
        this.dlg.preview = await this.api('/api/attest/preview', 'POST', {
          paper: this.scope, kind: this.dlg.kind, targets: this.dlg.targets, level: this.dlg.level, reason: this.dlg.reason,
          checklist: this.dlg.checklist, key: this.dlg.key });
        this.dlg.state = 'review'; this.dlg.ack = false;
      } catch (e) { this.dlg.error = e.message; }
    },
    get canSign() {
      const p = this.dlg.preview;
      return this.dlg.state === 'review' && p && p.signatures > 0 && p.key_in_agent && (!this.unseen.length || this.dlg.ack);
    },
    async signAttest() {
      this.dlg.error = '';
      try {
        const r = await this.api('/api/attest', 'POST', { preview: this.dlg.preview.id });
        this.dlg.state = 'running';
        this.dlg.job = { id: r.job, state: 'running', results: this.dlg.preview.items.map(i => ({ target: i.target, status: 'pending', message: '' })) };
        this.pollJob();
      } catch (e) { this.dlg.error = e.message; }
    },
    async pollJob() {
      try {
        this.dlg.job = await this.api('/api/attest/jobs/' + this.dlg.job.id);
        if (this.dlg.job.state === 'running') return setTimeout(() => this.pollJob(), 400);
        this.dlg.state = this.dlg.job.state === 'done' ? 'done' : 'failed';
      } catch (e) { this.dlg.error = e.message; this.dlg.state = 'failed'; }
    },
    async undoLast() {
      try {
        const r = await this.api('/api/attest/undo', 'POST', {});
        this.dlg.undone = 'Removed the attestation(s) of: ' + r.removed.join(', ');
      } catch (e) { this.dlg.error = e.message; }
    },
    // ---- background jobs and review packs (SPEC.md sections 7 and 8)
    // ---- unbound assessments: what changed since they were written, from git (once per scope, a few seconds)
    get auditRow() {
      return this.auditRows && this.detail ? this.auditRows.find(r => r.claim === this.detail.name) || null : null;
    },
    async loadAudit() {
      if (this.auditScope === this.scope && this.auditRows) return;
      this.auditLoading = true; this.auditMsg = '';
      try {
        const r = await this.api('/api/assessments/audit' + this.q());
        this.auditRows = r.rows.filter(x => x.claim); this.auditScope = this.scope;
        if (r.rows.some(x => x.state === 'no git')) this.auditMsg = 'No git history to compare with.';
      } catch (e) { this.auditMsg = 'The comparison with git failed: ' + e.message; }
      this.auditLoading = false;
    },

    // ---- what changed since the attestation (SPEC.md section 5.3)
    async loadDiff(kind, name, atts) {
      if (!atts.some(x => !x.current)) return;               // nothing stale: nothing to explain
      try {
        const d = await this.api('/api/' + (kind === 'claim' ? 'claims' : 'hypotheses') + '/' + encodeURIComponent(name) + '/diff' + this.q());
        const still = kind === 'claim' ? this.current === name : this.currentHyp === name;
        if (still) this.diffView = this.buildDiff(d);
      } catch (e) { /* the diff is an aid; the page works without it */ }
    },
    buildDiff(d) {
      const base = { available: d.available, current: !!d.current, att: d.attestation || null, reason: d.reason || '',
                     git: d.git || null, unverified: d.unverified || null };
      if (!d.available || d.current) return base;
      return Object.assign(base, {
        textChanged: d.text.changed, textHtml: tldiff.toHtml(tldiff.diff(d.text.old, d.text.new)),
        uses: d.uses.map(u => ({ name: u.name, change: u.change,
          html: u.old_text !== u.new_text ? tldiff.toHtml(tldiff.diff(u.old_text || '', u.new_text || '')) : '' })),
        nodes: d.nodes.map(n => ({ id: n.id, kind: n.kind, change: n.change, same: n.content_same,
          fields: tldiff.fields(n.old || {}, n.new || {}) })),
      });
    },
    async recoverFromGit(partial) {
      this.recovering = true; this.recoverMsg = ''; this.error = '';
      try {
        const r = await this.api('/api/snapshots' + this.q(), 'POST', { from_git: true, partial });
        const n = (s) => r.results.filter(x => x.status === s).length;
        this.recoverMsg = n('recovered') + ' rebuilt exactly, ' + n('partial') + ' as text only, ' +
          (n('partial kept') ? n('partial kept') + ' kept as text only from before, ' : '') + n('not found') + ' not recoverable.';
        await this.loadScope();
        if (this.current) this.open(this.current);
        if (this.currentHyp) this.openHyp(this.currentHyp);
      } catch (e) { this.error = e.message; }
      this.recovering = false;
    },
    async recordSnapshots() {
      try {
        const r = await this.api('/api/snapshots' + this.q(), 'POST', {});
        this.error = '';
        await this.loadScope();
        this.$nextTick(() => { if (!r.recorded.length) this.error = 'No snapshot had to be recorded.'; });
      } catch (e) { this.error = e.message; }
    },

    // ---- hypotheses (SPEC.md section 5.4)
    hypStatus(h) {
      const cur = h.attestations.filter(x => x.current);
      if (cur.length) return cur[0].level === 'green' ? 'known theorem' : cur[0].level;
      return h.attestations.length ? 'stale' : 'not attested';
    },
    hypClass(h) { const s = this.hypStatus(h); return s === 'known theorem' ? 'ok' : s === 'stale' ? 'stale' : s === 'not attested' ? 'none' : 'stale'; },
    async openHyp(name) {
      this.currentHyp = name; this.hypDetail = null; this.diffView = null;
      try {
        const d = await this.api('/api/hypotheses/' + encodeURIComponent(name) + this.q());
        const macros = await this.macrosFor(d.paper || this.scope);
        const r = texlite.toHtml(d.statement, { katex, macros });
        this.hypRendered = r;
        this.hypDetail = d;
        this.loadDiff('hypothesis', name, d.attestations);
        if (window.innerWidth <= 900) document.querySelector('#detail-hyp').scrollIntoView();
      } catch (e) { this.error = e.message; }
    },
    gotoClaim(name) { this.view = 'claims'; this.open(name); },

    // ---- background jobs and review packs (SPEC.md sections 7 and 8)
    get scopeInfo() { return this.overview.papers.find(p => p.name === this.scope) || null; },
    async openEdition(kind) {
      const p = this.scopeInfo;
      try {
        const r = await fetch('/api/editions/' + encodeURIComponent(p.name) + '/' + kind + '.pdf', { headers: { Authorization: 'Bearer ' + this.token } });
        if (!r.ok) throw new Error('the ' + kind + ' PDF is not available (' + r.status + ')');
        this.closePack();
        this.packView = { id: null, job: null, heading: kind === 'paper' ? 'Paper' : kind[0].toUpperCase() + kind.slice(1) + ' edition',
                          label: p.title || p.name, url: URL.createObjectURL(await r.blob()) };
        this.$nextTick(() => document.querySelector('section.packview').scrollIntoView());
      } catch (e) { this.error = e.message; }
    },
    get runningJobs() { return this.jobs.filter(j => j.state === 'running' || j.state === 'cancelling').length; },
    async refreshJobs() { try { this.jobs = (await this.api('/api/jobs')).jobs; } catch (e) { /* ignore */ } },
    async startJob(kind, extra) {
      const b = Object.assign({ kind, paper: this.scope || null, targets: [] }, extra || {});
      try {
        const r = await this.api('/api/jobs', 'POST', b);
        this.jobsOpen = true; this.error = '';
        await this.refreshJobs();
        this.viewLog(r.job);
        this.watchJob(r.job, kind === 'review');
      } catch (e) { this.error = e.message; }
    },
    runKind(kind) {
      if (!kind) return;
      if (kind === 'extract' && !window.confirm('Extracting the Lean evidence runs Docker Lean and can take minutes. Start it?')) return;
      this.startJob(kind, kind === 'extract' ? { confirm: true } : {});
    },
    startPack(targets, paper) {
      const p = paper || this.scope;
      if (!p) { this.error = 'Select a single paper first: a pack belongs to one paper.'; return; }
      this.startJob('review', { paper: p, targets });
    },
    async watchJob(id, openPack) {                       // poll until the job ends, then refresh the list (and show the pack)
      let j;
      try { j = await this.api('/api/jobs/' + id + '?since=' + (this.jobLog.id === id ? this.jobLog.next : 0)); } catch (e) { return; }
      if (this.jobLog.id === id) { this.jobLog.lines.push(...j.log); this.jobLog.next = j.next; this.$nextTick(() => { const el = this.$refs.joblog; if (el) el.scrollTop = el.scrollHeight; }); }
      if (j.state === 'running' || j.state === 'cancelling') return setTimeout(() => this.watchJob(id, openPack), 800);
      await this.refreshJobs();
      if (openPack && j.pack && j.pack.ready) { this.jobsOpen = false; this.openPack(id); }
      else if (openPack && j.state === 'failed') this.error = 'The review pack did not build; see the job log.';
      if (['lock', 'check', 'extract'].includes(j.kind)) this.loadScope();   // they change files the ledger reads
    },
    async viewLog(id) {
      this.jobLog = { id, lines: [], next: 0 };
      try {
        const j = await this.api('/api/jobs/' + id);
        this.jobLog.lines = j.log; this.jobLog.next = j.next;
        if (j.state === 'running' || j.state === 'cancelling') this.watchJob(id, false);
      } catch (e) { this.error = e.message; }
    },
    async cancelJob(id) { try { await this.api('/api/jobs/' + id + '/cancel', 'POST', {}); this.refreshJobs(); } catch (e) { this.error = e.message; } },
    async openPack(id) {                                 // the PDF is fetched with the token and shown from a blob: URL
      try {
        const [job, r] = await Promise.all([this.api('/api/jobs/' + id),
          fetch('/api/packs/' + id + '.pdf', { headers: { Authorization: 'Bearer ' + this.token } })]);
        if (!r.ok) throw new Error('the pack is not available (' + r.status + ')');
        this.closePack();
        this.packView = { id, job, heading: 'Review pack', label: job.pack.paper + ': ' + (job.targets.length ? job.targets.join(', ') : 'all claims'),
                          url: URL.createObjectURL(await r.blob()) };
        this.$nextTick(() => document.querySelector('section.packview').scrollIntoView());
      } catch (e) { this.error = e.message; }
    },
    closePack() { if (this.packView) URL.revokeObjectURL(this.packView.url); this.packView = null; },
    get packStale() {                                    // claims whose statement changed since the pack was built
      this.seenTick;
      if (!this.packView || !this.packView.job || !this.packView.job.pack || !this.data) return [];
      return Object.entries(this.packView.job.pack.bounds).filter(([n, b]) => this.boundOf(n) && this.boundOf(n) !== b).map(([n]) => n);
    },

    statusClass(s) { return s === 'attested' ? 'ok' : s === 'failed' ? 'none' : s === 'skipped' ? 'stale' : ''; },
  };
}

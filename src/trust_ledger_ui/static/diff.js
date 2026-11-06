/* diff: word-level diff of source text, as HTML (<del>/<ins>), for "what changed since the attestation". */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.tldiff = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';
  const ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' };
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ESC[c]);
  const tokens = (s) => String(s).match(/\s+|\w+|[^\s\w]/g) || [];
  const MAX_CELLS = 4000000;

  /* ops: [['=', text], ['-', text], ['+', text]] with neighbouring equal ops merged */
  function diff(a, b) {
    const x = tokens(a), y = tokens(b);
    let p = 0;
    while (p < x.length && p < y.length && x[p] === y[p]) p++;
    let q = 0;
    while (q < x.length - p && q < y.length - p && x[x.length - 1 - q] === y[y.length - 1 - q]) q++;
    const xm = x.slice(p, x.length - q), ym = y.slice(p, y.length - q);
    const ops = [];
    const push = (op, t) => { if (!t.length) return; const last = ops[ops.length - 1]; if (last && last[0] === op) last[1] += t; else ops.push([op, t]); };
    push('=', x.slice(0, p).join(''));
    if (xm.length * ym.length > MAX_CELLS) {            // too large for the exact LCS: show the middle as one replacement
      push('-', xm.join('')); push('+', ym.join(''));
    } else {
      const n = xm.length, m = ym.length;
      const L = Array.from({ length: n + 1 }, () => new Uint32Array(m + 1));
      for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--)
        L[i][j] = xm[i] === ym[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
      let i = 0, j = 0;
      while (i < n && j < m) {
        if (xm[i] === ym[j]) { push('=', xm[i]); i++; j++; }
        else if (L[i + 1][j] >= L[i][j + 1]) { push('-', xm[i]); i++; }
        else { push('+', ym[j]); j++; }
      }
      while (i < n) push('-', xm[i++]);
      while (j < m) push('+', ym[j++]);
    }
    push('=', x.slice(x.length - q).join(''));
    return ops;
  }

  function toHtml(ops) {
    return ops.map(([op, t]) => op === '=' ? esc(t) : op === '-' ? '<del>' + esc(t) + '</del>' : '<ins>' + esc(t) + '</ins>').join('');
  }

  /* an object's changed fields, each as {key, html}; values that are not strings are shown as JSON */
  function fields(oldObj, newObj) {
    const s = (v) => v === undefined || v === null ? '' : typeof v === 'string' ? v : JSON.stringify(v, null, 1);
    const keys = [...new Set([...Object.keys(oldObj || {}), ...Object.keys(newObj || {})])].sort();
    return keys.filter(k => s((oldObj || {})[k]) !== s((newObj || {})[k]))
      .map(k => ({ key: k, html: toHtml(diff(s((oldObj || {})[k]), s((newObj || {})[k]))) }));
  }

  return { diff, toHtml, fields, tokens };
});

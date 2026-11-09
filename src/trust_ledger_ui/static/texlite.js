/* texlite: LaTeX statement text (as found in the ledger: theorem bodies, Pandoc-style back-translations) to HTML,
 * with the mathematics rendered by KaTeX. Not a LaTeX engine: it knows the few text commands those texts use;
 * anything else is shown as source (class "unk") and counted, a formula KaTeX rejects is shown as source (class
 * "norender") and listed in result.failures, so a gap in the rendering is visible and never silent. */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.texlite = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const MATH_ENVS = ['equation', 'align', 'gather', 'multline', 'eqnarray', 'displaymath'];
  const WRAP = { textbf: 'b', emph: 'i', textit: 'i', textsl: 'i', texttt: 'code', underline: 'u', textsc: 'span', textrm: 'span',
                 mbox: 'span', text: 'span', textnormal: 'span', mathrm: 'span', textsuperscript: 'sup', textsubscript: 'sub' };
  const HEAD = { section: 'h3', subsection: 'h4', subsubsection: 'h5', paragraph: 'h4', subparagraph: 'h5' };
  const SYMBOL = { textgreater: '>', textless: '<', textbackslash: '\\', textasciitilde: '~', textasciicircum: '^',
                   ldots: '…', dots: '…', textellipsis: '…', quad: ' ', qquad: '  ', LaTeX: 'LaTeX', TeX: 'TeX',
                   ss: 'ß', ae: 'æ', oe: 'œ', AE: 'Æ', OE: 'Œ', o: 'ø', O: 'Ø', l: 'ł', L: 'Ł', i: 'ı', S: '§', P: '¶',
                   textendash: '–', textemdash: '—', textquoteleft: '‘', textquoteright: '’', textquotedbl: '"',
                   textquotedblleft: '“', textquotedblright: '”', textbar: '|', textunderscore: '_', textdollar: '$', textquotesingle: "'" };
  const IGNORE = new Set(['smallskip', 'medskip', 'bigskip', 'noindent', 'hfill', 'vfill', 'centering', 'raggedright', 'newline',
                          'clearpage', 'newpage', 'leavevmode', 'protect', 'relax', 'small', 'footnotesize', 'normalsize',
                          'large', 'Large', 'tiny', 'scriptsize', 'itshape', 'bfseries', 'rmfamily', 'sffamily', 'ttfamily',
                          'upshape', 'mdseries', 'normalfont', 'hspace', 'vspace', 'bigbreak', 'allowbreak', 'nobreak',
                          'sloppy', 'fussy', 'strut', 'null', 'indent', 'tightlist', 'labelenumi', 'labelitemi', 'item@']);
  const ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' };
  const esc = (s) => s.replace(/[&<>"]/g, (c) => ESC[c]);

  /* pandoc's enumerate labels: \def\labelenumi{(\roman{enumi})} with the item number n */
  function roman(n) { let r = ''; for (const [v, t] of [[1000, 'm'], [900, 'cm'], [500, 'd'], [400, 'cd'], [100, 'c'], [90, 'xc'], [50, 'l'], [40, 'xl'], [10, 'x'], [9, 'ix'], [5, 'v'], [4, 'iv'], [1, 'i']]) while (n >= v) { r += t; n -= v; } return r; }
  function enumLabel(tpl, n) {
    return tpl.replace(/\\(arabic|roman|Roman|alph|Alph)\{enum[iv]+\}/g, (_, f) =>
      f === 'arabic' ? String(n) : f === 'roman' ? roman(n) : f === 'Roman' ? roman(n).toUpperCase()
        : f === 'alph' ? String.fromCharCode(96 + n) : String.fromCharCode(64 + n));
  }

  function stripComments(s) { return s.replace(/(^|[^\\])%.*$/gm, '$1'); }

  /* index just after the balanced {...} group that starts at s[i] === '{'; -1 if unbalanced */
  function groupEnd(s, i) {
    let depth = 0;
    for (let j = i; j < s.length; j++) {
      const c = s[j];
      if (c === '\\') { j++; continue; }
      if (c === '{') depth++;
      else if (c === '}' && --depth === 0) return j + 1;
    }
    return -1;
  }

  /* KaTeX has no psmallmatrix and no multline; \label and friends are not math */
  function fixMath(m) {
    return m
      .replace(/\\begin\{psmallmatrix\}([\s\S]*?)\\end\{psmallmatrix\}/g, '\\bigl(\\begin{smallmatrix}$1\\end{smallmatrix}\\bigr)')
      .replace(/\\(begin|end)\{multline(\*?)\}/g, '\\$1{gather$2}')
      .replace(/\\(begin|end)\{eqnarray(\*?)\}/g, '\\$1{align$2}')
      .replace(/\\(label|nonumber|notag)(\{[^}]*\})?/g, '')
      .replace(/\\(,|;|:|!)\s*\\(,|;|:|!)/g, '\\$1\\$2');
  }

  function render(src, display, ctx) {
    const code = fixMath(src);
    try {
      ctx.rendered++;
      return ctx.katex.renderToString(code, {
        displayMode: display, throwOnError: true, strict: 'ignore', trust: false, output: 'html',
        macros: Object.assign({}, ctx.macros),
      });
    } catch (e) {
      ctx.failures.push({ source: src, error: String(e.message || e).replace(/^KaTeX parse error: /, '').split('\n')[0] });
      return '<code class="norender" title="' + esc(String(e.message || e)) + '">' + esc(src) + '</code>';
    }
  }

  function textRun(t) {
    t = esc(t)
      .replace(/~/g, ' ').replace(/``/g, '“').replace(/''/g, '”')
      .replace(/---/g, '—').replace(/--/g, '–')
      .replace(/\n[ \t]*\n+/g, '</p><p>');
    return t;
  }

  function parse(s, ctx) {
    let out = '', buf = '', i = 0;
    const n = s.length;
    const lists = [];
    const flush = () => { if (buf) { out += textRun(buf); buf = ''; } };
    const emit = (html) => { flush(); out += html; };
    const cmd = /\\([A-Za-z]+)\*?/y;

    while (i < n) {
      const c = s[i];
      if (c === '\\') {
        const d = s[i + 1];
        if (d === '[') { const j = s.indexOf('\\]', i + 2); if (j >= 0) { emit(render(s.slice(i + 2, j), true, ctx)); i = j + 2; continue; } }
        if (d === '(') { const j = s.indexOf('\\)', i + 2); if (j >= 0) { emit(render(s.slice(i + 2, j), false, ctx)); i = j + 2; continue; } }
        cmd.lastIndex = i;
        const m = cmd.exec(s);
        if (!m) {                                   // \& \% \_ \# \$ \{ \} \\ \, \; \  and so on
          if (d === '\\') emit('<br>');
          else if (d !== undefined && '&%_#${}'.includes(d)) buf += d;
          else if (d === ' ' || d === ',' || d === ';' || d === ':' || d === '!') buf += d === '!' ? '' : ' ';
          else if (d !== undefined) emit('<span class="unk">\\' + esc(d) + '</span>');
          i += 2;
          if (d !== '\\' && s.startsWith('{}', i)) i += 2;   // Pandoc writes \_{} : the empty group only ends the symbol
          continue;
        }
        const name = m[1];
        let j = m.index + m[0].length;
        const arg = () => {                         // the {group} that follows, or null
          let k = j; while (k < n && (s[k] === ' ' || s[k] === '\n')) k++;
          if (s[k] !== '{') return null;
          const e = groupEnd(s, k);
          if (e < 0) return null;
          j = e; return s.slice(k + 1, e - 1);
        };
        if (name === 'begin' || name === 'end') {
          const env = arg() || '';
          const base = env.replace('*', '');
          if (name === 'begin' && MATH_ENVS.includes(base)) {
            const endTag = '\\end{' + env + '}';
            const e = s.indexOf(endTag, j);
            if (e >= 0) { emit(render('\\begin{' + env + '}' + s.slice(j, e) + endTag, true, ctx)); i = e + endTag.length; continue; }
          }
          if (base === 'itemize' || base === 'enumerate') {
            if (name === 'begin') { lists.push({ tag: base === 'itemize' ? 'ul' : 'ol', first: true, n: 0, label: null }); emit('<' + lists[lists.length - 1].tag + '>'); }
            else { const l = lists.pop(); if (l) emit((l.first ? '' : '</li>') + '</' + l.tag + '>'); }
          } else if (name === 'begin' && /^(theorem|lemma|proposition|corollary|remark|definition|example|proof|conjecture|claim|assumption)$/.test(base)) {
            let title = ''; if (s[j] === '[') { const e = s.indexOf(']', j); if (e > 0) { title = ' (' + s.slice(j + 1, e) + ')'; j = e + 1; } }
            emit('<div class="env"><b>' + esc(base[0].toUpperCase() + base.slice(1)) + esc(title) + '.</b> ');
          } else if (name === 'end' && /^(theorem|lemma|proposition|corollary|remark|definition|example|proof|conjecture|claim|assumption)$/.test(base)) {
            emit('</div>');
          } else if (!['document', 'center', 'quote', 'widetext', 'minipage', 'abstract'].includes(base)) {
            ctx.unknown.add('\\' + name + '{' + env + '}'); emit('<span class="unk">\\' + name + '{' + esc(env) + '}</span>');
          }
          i = j; continue;
        }
        if (name === 'leandisplay') { const a = arg(); if (a !== null) { emit(render(a, true, ctx)); i = j; continue; } }
        if (name === 'ensuremath') { const a = arg(); if (a !== null) { emit(render(a, false, ctx)); i = j; continue; } }
        if (WRAP[name]) { const a = arg(); if (a !== null) { const t = WRAP[name]; emit('<' + t + '>' + parse(a, ctx).html + '</' + t + '>'); i = j; continue; } }
        if (HEAD[name]) { const a = arg(); if (a !== null) { const t = HEAD[name]; emit('</p><' + t + '>' + parse(a, ctx).html + '</' + t + '><p>'); i = j; continue; } }
        if (name === 'item') {
          const l = lists[lists.length - 1];
          if (l) {
            l.n++;
            const lab = l.tag === 'ol' && l.label ? enumLabel(l.label, l.n) : null;
            emit((l.first ? '' : '</li>') + (lab !== null ? '<li class="lbl"><span class="enumlbl">' + esc(lab) + '</span> '
                                                           : l.moved ? '<li value="' + l.n + '">' : '<li>'));
            l.first = false;
          }
          i = j; continue;
        }
        if (name === 'label' || name === 'index' || name === 'nonumber' || name === 'notag') { arg(); i = j; continue; }
        if (name === 'cite' || name === 'citep' || name === 'citet' || name === 'nocite') { const a = arg(); emit('<span class="cite">[' + esc(a || '') + ']</span>'); i = j; continue; }
        if (name === 'ref' || name === 'eqref' || name === 'cref' || name === 'Cref' || name === 'autoref') {
          const a = arg(); emit('<span class="ref">' + (name === 'eqref' ? '(' : '') + esc(a || '') + (name === 'eqref' ? ')' : '') + '</span>'); i = j; continue;
        }
        if (name === 'footnote' || name === 'footnotetext') { const a = arg(); emit('<span class="fn"> [' + parse(a || '', ctx).html + ']</span>'); i = j; continue; }
        if (name === 'texorpdfstring') { const a = arg(); arg(); if (a !== null) { emit(parse(a, ctx).html); i = j; continue; } }
        if (name === 'def') {                       // \def\name#1{...}: pandoc's list labels (\labelenumi); else nothing to show
          cmd.lastIndex = j; const dm = cmd.exec(s);
          if (dm) {
            j = dm.index + dm[0].length; while (s[j] === '#' || /[0-9]/.test(s[j] || '')) j++;
            const body = arg(), l = lists[lists.length - 1];
            if (/^labelenum[iv]+$/.test(dm[1]) && body !== null && l && l.tag === 'ol' && body.trim() !== '\\arabic{' + dm[1].slice(5) + '}.') l.label = body;
          }
          i = j; continue;
        }
        if (name === 'setcounter' || name === 'addtocounter') {   // \setcounter{enumi}{1}: the next \item is number 2
          const c = arg(), v = parseInt(arg() || '', 10), l = lists[lists.length - 1];
          if (l && l.tag === 'ol' && /^enum[iv]+$/.test(c || '') && !isNaN(v)) { l.n = name === 'setcounter' ? v : l.n + v; l.moved = true; }
          i = j; continue;
        }
        if (name === 'par') { emit('</p><p>'); i = j; continue; }
        if (Object.prototype.hasOwnProperty.call(SYMBOL, name)) {
          buf += SYMBOL[name];
          if (s.startsWith('{}', j)) j += 2;
          i = j; continue;
        }
        if (/^(itemsep|parsep|parskip|topsep|partopsep|parindent)$/.test(name)) {   // a length setting: \itemsep0pt, \parskip=2pt
          const lm = /\s*=?\s*-?[0-9.]+\s*(pt|em|ex|mm|cm|in|bp|sp|mu)?(\s*plus\s*[0-9.]+\s*\w*)?(\s*minus\s*[0-9.]+\s*\w*)?/y;
          lm.lastIndex = j; const mm = lm.exec(s); if (mm) j += mm[0].length;
          i = j; continue;
        }
        if (IGNORE.has(name)) { if (name === 'hspace' || name === 'vspace') arg(); i = j; continue; }
        ctx.unknown.add('\\' + name);
        emit('<span class="unk">\\' + esc(name) + '</span>');
        i = j; continue;
      }
      if (c === '$') {
        if (s[i + 1] === '$') { const j = s.indexOf('$$', i + 2); if (j >= 0) { emit(render(s.slice(i + 2, j), true, ctx)); i = j + 2; continue; } }
        let j = i + 1;
        while (j < n && (s[j] !== '$' || s[j - 1] === '\\')) j++;
        if (j < n) { emit(render(s.slice(i + 1, j), false, ctx)); i = j + 1; continue; }
      }
      if (c === '{' || c === '}') { i++; continue; }   // a bare group (\allowbreak{}, {\em x}) is invisible in LaTeX
      buf += c; i++;
    }
    while (lists.length) { const l = lists.pop(); emit((l.first ? '' : '</li>') + '</' + l.tag + '>'); }
    flush();
    return { html: out };
  }

  /* texlite.toHtml(source, {katex, macros}) -> {html, failures: [{source, error}], unknown: [command], rendered: count} */
  function toHtml(source, opts) {
    const ctx = { katex: opts.katex, macros: opts.macros || {}, failures: [], unknown: new Set(), rendered: 0 };
    /* the ledger's statements are blocks "[label] kind: [title] body", one per labelled environment; a bare
       equation/align has no math delimiters */
    const blocks = stripComments(source || '').split(/\n(?=\s*\[[^\]\n]+\]\s+[A-Za-z*]+:\s)/);
    let html = '';
    for (let text of blocks) {
      let head = '';
      const h = /^\s*\[([^\]]*)\]\s+([A-Za-z*]+):\s*(?:\[([^\]]*)\]\s*)?/.exec(text);
      if (h) {
        const kind = h[2].replace('*', '');
        text = text.slice(h[0].length);
        head = '<div class="stmt-head"><span class="lab">' + esc(h[1]) + '</span> <b>' + esc(kind) + '</b>' +
               (h[3] ? ' (' + esc(h[3]) + ')' : '') + '</div>';
        if (MATH_ENVS.includes(kind)) {
          const body = kind === 'equation' || kind === 'displaymath' ? text : '\\begin{aligned}' + text + '\\end{aligned}';
          html += '<div class="stmt-block">' + head + render(body, true, ctx) + '</div>';
          continue;
        }
      }
      html += '<div class="stmt-block">' + head + '<p>' + parse(text, ctx).html + '</p></div>';
    }
    return { html: html.replace(/<p>\s*<\/p>/g, ''), failures: ctx.failures, unknown: [...ctx.unknown], rendered: ctx.rendered };
  }

  return { toHtml, fixMath };
});

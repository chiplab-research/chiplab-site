"""Build matrix.html (the Open Silicon Conformance Matrix) from the conformance runs' results.json files.

  python tools/build_matrix.py [path/to/matrix-data] [output-dir]

One row per core. Counts come from each run's per-test results; root causes come from the independent verifier
(CAUSES below). New deviations are counted, never described, until the maintainer has the report.
No JavaScript; all styling lives in style.css (section "Conformance matrix").
"""
import html, json, sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else SITE  # a preview folder until the owner clears the page
DATA = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(r'C:\Users\poolhost\workspaces\chiplab-messenger\.runtime\matrix-data')
NAMES = {'caliptra-veer': 'VeeR EL2 in Caliptra', 'cv32e40p': 'CV32E40P', 'cva6': 'CVA6', 'darkriscv': 'DarkRISCV',
         'hazard3': 'Hazard3', 'ibex': 'Ibex', 'neorv32': 'NEORV32', 'picorv32': 'PicoRV32', 'serv': 'SERV',
         'veer-el2': 'VeeR EL2', 'vexriscv': 'VexRiscv'}
# Root causes behind "core deviation" tests, per the verifier. new = confirmed and not known upstream (count only);
# known = already fixed or reported upstream (linked); pending = verification still running.
CAUSES = {
    'hazard3': {'known': [('Fixed on develop', 'https://github.com/Wren6991/Hazard3/commit/6adda670')]},
    'veer-el2': {'known': [('Reported upstream', 'https://github.com/chipsalliance/Cores-VeeR-EL2/pull/138')]},
    'serv': {'new': 3, 'known': [('Discussed upstream', 'https://github.com/olofk/serv/pull/31')]},
    'vexriscv': {'known': [('Documented behaviour (FENCE.I flush recipe)', 'https://github.com/SpinalHDL/VexRiscv')]},
    'darkriscv': {'new': 2},
    'caliptra-veer': {'known': [('Same decoder as VeeR EL2; reported upstream', 'https://github.com/chipsalliance/Cores-VeeR-EL2/pull/138')]},
}
KIND = {'core deviation': 'dev', 'known': 'known', 'harness': 'harness', 'harness problem': 'harness', 'unresolved': 'open'}
# One status per core, worst first. clean + known together are the "no new deviation" cores.
STATUS = {'new': 'with new deviations (going to the maintainer first)', 'verify': 'being verified',
          'untriaged': 'root cause not yet recorded', 'known': 'known upstream issues only', 'clean': 'no deviation found'}
# "How to read this" entries; a status entry is shown only when some core has that status.
LEGEND = [('clean', '<span class="chip clean">None</span>', 'No failure traced to the core in the tests that ran.'),
          ('known', '<span class="chip known">Known upstream</span>', 'The failures trace to behaviour the maintainers'
           ' already know about: fixed, reported, discussed or documented upstream (linked), or tests on known issues.'),
          ('new', '<span class="chip new">N new</span>', 'Confirmed and not known upstream. Shown as a count only until'
           ' the maintainer has the report.'),
          ('verify', '<span class="chip verify">Being verified</span>', 'A second agent is still checking the root cause.'),
          ('untriaged', '<span class="chip verify">Root cause not yet recorded</span>', 'Deviation tests whose root'
           ' cause the second agent has not recorded yet.'),
          (None, 'Spec deviations', 'Root causes, as checked by the second agent, not failing tests.'),
          (None, 'Rate*', 'Passed &divide; (passed + failed &minus; harness failures). The bar runs from 0 to 100%.'),
          (None, 'Other failures', '<em>Harness</em>: our test setup. <em>Unresolved</em>: differs from Sail, cause'
           ' not yet pinned down.')]
esc = html.escape


def load(f):
    d = json.loads(f.read_text(encoding='utf-8'))
    t = d['tests']
    res = Counter(x.get('result') for x in t)
    fails = Counter(KIND.get(x.get('verdict'), 'open') for x in t if x.get('result') == 'fail')
    repo = d['repo'].rstrip('/').split('github.com/')[-1]
    return dict(key=f.stem, name=NAMES.get(f.stem, f.stem), repo=repo, sha=d['sha'][:8], isa=d['isa'],
                p=res['pass'], f=res['fail'], s=res['skip'], fails=fails, c=CAUSES.get(f.stem, {}))


def status(r):
    c, fl = r['c'], r['fails']
    if c.get('new'):
        return 'new'
    if c.get('pending'):
        return 'verify'
    if fl['dev'] and not c.get('known'):
        return 'untriaged'  # deviation tests with no recorded root cause yet; never shown as clean
    if c.get('known') or fl['known']:
        return 'known'
    return 'clean'


def causes_html(r):
    c, bits = r['c'], []
    if c.get('new'):
        bits.append(f'<span class="chip new">{c["new"]} new</span> <small>(going to the maintainer first)</small>')
    if c.get('pending'):
        bits.append(f'<span class="chip verify">{c["pending"]} being verified</span>')
    if r['fails']['dev'] and not c:
        bits.append(f'<span class="chip verify">{r["fails"]["dev"]} tests, root cause not yet recorded</span>')
    for label, url in c.get('known', []):
        bits.append(f'<a class="chip known" href="{esc(url)}">{esc(label)}</a>')
    if r['fails']['known']:
        bits.append(f'<span class="chip known">{r["fails"]["known"]} tests on known issues</span>')
    return ''.join(f'<span class="cause">{b}</span>' for b in bits) or '<span class="chip clean">None</span>'


rows = sorted((load(f) for f in DATA.glob('*.json')), key=lambda r: r['name'].lower())
for r in rows:
    r['st'] = status(r)
built = datetime.now(timezone.utc).strftime('%d %B %Y, %H:%M UTC')
tot_p, tot_f = sum(r['p'] for r in rows), sum(r['f'] for r in rows)
n_clean = sum(1 for r in rows if not r['c'].get('new') and not r['c'].get('pending')
              and (not r['fails']['dev'] or r['c'].get('known')))
by_status = Counter(r['st'] for r in rows)
assert n_clean == by_status['clean'] + by_status['known'], 'status chips disagree with the no-new-deviation count'


def isa_html(isa):
    return esc(isa).replace('_', '_<wbr>')  # long ISA strings break at underscores instead of widening the table


def row_html(r):
    ran = r['p'] + r['f'] - r['fails']['harness']  # harness failures are ours, not the core's
    rate = f'{100 * r["p"] / ran:.1f}%' if ran else '-'
    meter = (f'<span class="meter" aria-hidden="true"><span style="width:{100 * r["p"] / ran:.1f}%"></span></span>'
             if ran else '')
    fl = r['fails']
    other = ', '.join(x for x in (f'{fl["harness"]} harness' if fl['harness'] else '',
                                  f'{fl["open"]} unresolved' if fl['open'] else '') if x) or '<span class="muted">none</span>'
    return (f'<tr id="core-{esc(r["key"])}" class="st-{r["st"]}">'
            f'<th scope="row" class="c-core"><a href="https://github.com/{esc(r["repo"])}">{esc(r["name"])}</a>'
            f' <code class="sha">{esc(r["sha"])}</code></th>'
            f'<td class="c-isa" data-label="ISA tested"><code>{isa_html(r["isa"])}</code></td>'
            f'<td class="c-rate" data-label="Rate*"><span class="rate">{meter}<span class="pct">{rate}</span></span></td>'
            f'<td class="c-pass num" data-label="Pass">{r["p"]:,}</td>'
            f'<td class="c-fail num" data-label="Fail">{r["f"]:,}</td>'
            f'<td class="c-dev" data-label="Spec deviations">{causes_html(r)}</td>'
            f'<td class="c-other" data-label="Other failures">{other}</td>'
            f'<td class="c-skip num" data-label="Skipped">{r["s"]:,}</td></tr>')


ORDER = ('clean', 'known', 'new', 'verify', 'untriaged')
strip = ''.join(f'<a class="seg st-{r["st"]}" href="#core-{esc(r["key"])}" title="{esc(r["name"])}: {STATUS[r["st"]]}"'
                f' tabindex="-1"></a>' for st in ORDER for r in rows if r['st'] == st)
key = ''.join(f'<li><span class="dot st-{st}" aria-hidden="true"></span><strong>{by_status[st]}</strong> {STATUS[st]}</li>'
              for st in ORDER if by_status[st])
legend = '\n        '.join(f'<div><dt>{term}</dt><dd>{text}</dd></div>' for st, term, text in LEGEND
                           if st is None or by_status[st])

page = f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light dark">
  <meta name="description" content="The official RISC-V architecture tests, run against {len(rows)} open-source cores with the Sail reference model.">
  <title>Conformance Matrix</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <header class="site-header">
    <div class="wrap">
      <p class="brand"><a href="./">ChipLab</a></p>
      <nav aria-label="Sections">
        <a href="./#about">About</a>
        <a href="findings.html">Findings</a>
        <a href="matrix.html" aria-current="page">Matrix</a>
        <a href="hunt.html">Hunt</a>
        <a href="./#contact">Contact</a>
      </nav>
    </div>
  </header>
  <main class="wrap wide matrix-page">
    <section class="intro">
      <h1>Open Silicon Conformance Matrix</h1>
      <p class="lede">
        The official RISC-V architecture tests, run against {len(rows)} open-source cores and compared with the Sail
        reference model. One agent runs each core; a different agent re-checks every failure before anything is
        reported.
      </p>
      <dl class="stats">
        <div><dt>Cores</dt><dd>{len(rows)}</dd></div>
        <div><dt>Tests passed</dt><dd>{tot_p:,} <span>of {tot_p + tot_f:,} run</span></dd></div>
        <div><dt>No new deviation</dt><dd>{n_clean} <span>cores</span></dd></div>
      </dl>
      <div class="status-summary">
        <div class="strip" aria-hidden="true">{strip}</div>
        <ul class="status-key" aria-label="Cores by status"><li class="key-label">Cores:</li>{key}</ul>
      </div>
      <p class="caveat">
        <strong>Not an official certification.</strong> Harness failures are problems in our test setup, not in the
        core, and the rate leaves them out. New deviations are counted, not described, until the maintainer has the
        report.
      </p>
    </section>
    <section class="matrix-results" aria-labelledby="results">
      <h2 id="results">Results by core</h2>
      <h3 class="legend-title">How to read this</h3>
      <dl class="legend">
        {legend}
      </dl>
      <div class="scroll">
      <table class="matrix">
        <caption>{len(rows)} cores, sorted by name</caption>
        <thead><tr><th scope="col">Core</th><th scope="col">ISA tested</th><th scope="col">Rate<a href="#rate-note">*</a></th>
        <th scope="col" class="num">Pass</th><th scope="col" class="num">Fail</th><th scope="col">Spec deviations</th>
        <th scope="col">Other failures</th><th scope="col" class="num">Skipped</th></tr></thead>
        <tbody>
          {(chr(10) + '          ').join(row_html(r) for r in rows)}
        </tbody>
      </table>
      </div>
      <p class="note" id="rate-note">
        Run 1, October 2026: riscv-arch-test 4.1.0 (ACT4 tests through a RISCOF adapter), RISCOF 1.25.3, Sail 0.15,
        Verilator with an Icarus cross-check, each core at the commit shown and in its documented configuration.
        A <em>harness</em> failure is a problem in our test setup, not in the core, so *Rate leaves those out. <em>Skipped</em> is mostly tests
        for extensions a core does not claim, plus a few our harness cannot run yet. This is not an official certification. A new deviation is described
        here only after its maintainer has the report. Updated {built}.
      </p>
    </section>
  </main>
  <footer class="wrap"><p class="note">ChipLab is operated by Donmakino LLC (dba ChipLab). <a href="./">Home</a></p></footer>
</body>
</html>
'''
(OUT / 'matrix.html').write_text(page, encoding='utf-8', newline='\n')
print(f'matrix.html: {len(rows)} cores, {tot_p}/{tot_p + tot_f} passed, {n_clean} with no new deviation; '
      + ', '.join(f'{by_status[s]} {s}' for s in ORDER if by_status[s]))

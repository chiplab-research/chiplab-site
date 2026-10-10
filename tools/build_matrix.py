"""Build matrix.html (the Open Silicon Conformance Matrix) from the conformance runs' results.json files.

  python tools/build_matrix.py [path/to/matrix-data]

One row per core. Counts come from each run's per-test results; root causes come from the independent verifier
(CAUSES below). New deviations are counted, never described, until the maintainer has the report.
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


def load(f):
    d = json.loads(f.read_text(encoding='utf-8'))
    t = d['tests']
    res = Counter(x.get('result') for x in t)
    fails = Counter(KIND.get(x.get('verdict'), 'open') for x in t if x.get('result') == 'fail')
    repo = d['repo'].rstrip('/').split('github.com/')[-1]
    return dict(key=f.stem, name=NAMES.get(f.stem, f.stem), repo=repo, sha=d['sha'][:8], isa=d['isa'],
                p=res['pass'], f=res['fail'], s=res['skip'], fails=fails, c=CAUSES.get(f.stem, {}))


def causes_html(r):
    c, bits = r['c'], []
    if c.get('new'):
        bits.append(f'<strong>{c["new"]} new</strong> <small>(going to the maintainer first)</small>')
    if c.get('pending'):
        bits.append(f'{c["pending"]} being verified')
    for label, url in c.get('known', []):
        bits.append(f'<a href="{html.escape(url)}">{html.escape(label)}</a>')
    if r['fails']['known']:
        bits.append(f'{r["fails"]["known"]} tests on known issues')
    return '<br>'.join(bits) or '<span class="muted">none</span>'


rows = sorted((load(f) for f in DATA.glob('*.json')), key=lambda r: r['name'].lower())
built = datetime.now(timezone.utc).strftime('%d %B %Y, %H:%M UTC')
tot_p, tot_f = sum(r['p'] for r in rows), sum(r['f'] for r in rows)
n_clean = sum(1 for r in rows if not r['c'].get('new') and not r['c'].get('pending')
              and (not r['fails']['dev'] or r['c'].get('known')))


def row_html(r):
    ran = r['p'] + r['f'] - r['fails']['harness']  # harness failures are ours, not the core's
    rate = f'{100 * r["p"] / ran:.1f}%' if ran else '-'
    fl = r['fails']
    other = ', '.join(x for x in (f'{fl["harness"]} harness' if fl['harness'] else '',
                                  f'{fl["open"]} unresolved' if fl['open'] else '') if x) or '-'
    return (f'<tr><td><a href="https://github.com/{html.escape(r["repo"])}">{html.escape(r["name"])}</a>'
            f'<br><small><code>{html.escape(r["sha"])}</code></small></td>'
            f'<td><small>{html.escape(r["isa"])}</small></td><td class="num">{r["p"]}</td><td class="num">{r["f"]}</td>'
            f'<td class="num">{rate}</td><td>{causes_html(r)}</td><td><small>{other}</small></td>'
            f'<td class="num">{r["s"]}</td></tr>')


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
  <main class="wrap wide">
    <section class="intro">
      <h1>Open Silicon Conformance Matrix</h1>
      <p class="lede">
        The official RISC-V architecture tests, run against {len(rows)} open-source cores and compared with the Sail
        reference model. One agent runs each core; a different agent re-checks every failure before anything is
        reported.
      </p>
      <dl class="stats">
        <div><dt>Cores</dt><dd>{len(rows)}</dd></div>
        <div><dt>Tests passed</dt><dd>{tot_p} <span>of {tot_p + tot_f} run</span></dd></div>
        <div><dt>No new deviation</dt><dd>{n_clean} <span>cores</span></dd></div>
      </dl>
    </section>
    <section>
      <div class="scroll">
      <table class="findings matrix">
        <thead><tr><th>Core</th><th>ISA tested</th><th>Pass</th><th>Fail</th><th>Rate*</th><th>Spec deviations</th>
        <th>Other failures</th><th>Skipped</th></tr></thead>
        <tbody>
          {chr(10).join(row_html(r) for r in rows)}
        </tbody>
      </table>
      </div>
      <p class="note">
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
print(f'matrix.html: {len(rows)} cores, {tot_p}/{tot_p + tot_f} passed, {n_clean} with no new deviation')

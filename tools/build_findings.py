"""Build findings.html (the ChipLab findings board) from the bughunt filing log.

  python tools/build_findings.py [path/to/FILED.md]

One row per CLAB reference. Public reports show their upstream title and link. Private (security) reports show only
the project and "reported privately": no block, release or details until the maintainers publish a fix.
"""
import html, json, re, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent
FILED = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(r'C:\Users\poolhost\workspaces\bughunt\FILED.md')
# Public findings present in RTL that shipped in silicon or in a tagged release (from each finding's verified record).
SHIPPED = {'earlgrey_1.0.0': ('lowRISC/opentitan', ['31690', '31691', '31692', '31693', '31694', '31695', '31696',
                                                    '31697', '31698', '31699', '31700']),
            # 10-09: same lines as Hazard3 v1.0-rc1, the RP2350's core; #52 (unsigned AMOs) is masked there by Zbb=1.
            'hazard3 v1.0-rc1 (RP2350)': ('Wren6991/Hazard3', ['50', '51'])}


def gh_title(url):
    m = re.match(r'https://github.com/([^/]+/[^/]+)/(issues|pull)/(\d+)', url)
    if not m:
        return None, None
    repo, kind, num = m.groups()
    try:
        out = subprocess.run(['gh', 'api', f'repos/{repo}/issues/{num}', '--jq', '{t: .title, s: .state, r: .state_reason}'],
                             capture_output=True, text=True, timeout=60).stdout
        d = json.loads(out)
        return d['t'], ('fixed' if d.get('r') == 'completed' else d['s'])
    except Exception:
        return None, None


rows = []
for line in FILED.read_text(encoding='utf-8').splitlines():
    if not line.startswith('| CLAB-') and not line.startswith('| (fix for'):
        continue
    cells = [c.strip() for c in line.strip('|').split('|')]
    ref, date, project, _finding, report, status = cells[:6]
    private = '(private)' in project
    project = project.replace(' (private)', '')
    title, state = (None, None) if private else gh_title(report)
    shipped = any(re.search(rf'github\.com/{p}/(issues|pull)/{n}$', report) for _, (p, ns) in SHIPPED.items() for n in ns)
    rows.append(dict(ref=ref, date=date[:10], project=project, private=private, report=report,
                     title=title or ('Fix pull request' if '/pull/' in report else ''),
                     state=state or status, shipped=shipped))

ids = [r for r in rows if r['ref'].startswith('CLAB-')]
# 10-09: private reports are counted, never listed (no project, block or release) until the maintainers publish the fix.
listed = [r for r in rows if not r['private']]
n_public = sum(1 for r in ids if not r['private'])
n_private = sum(1 for r in ids if r['private'])
n_projects = len({r['project'] for r in listed if r['ref'].startswith('CLAB-')})
n_shipped = sum(1 for r in ids if r['shipped'])
n_fixed = sum(1 for r in rows if r['state'] == 'fixed')
built = datetime.now(timezone.utc).strftime('%d %B %Y, %H:%M UTC')

def row_html(r):
    anchor = r['ref'].lower() if r['ref'].startswith('CLAB-') else ''
    if r['private']:
        what = f'Reported privately to the {html.escape(r["project"])} security team. Details are published after the fix.'
        link = ''
    else:
        what = html.escape(r['title'])
        link = f'<a href="{html.escape(r["report"])}">{html.escape(r["report"].split("github.com/")[-1])}</a>'
    badge = '<span class="badge">shipped</span> ' if r['shipped'] else ''
    state = {'open': 'Open', 'closed': 'Closed', 'fixed': 'Fixed', 'submitted': 'Reported'}.get(r['state'], r['state'].capitalize())
    return (f'<tr id="{anchor}"><td class="ref">{html.escape(r["ref"])}</td><td>{html.escape(r["project"])}</td>'
            f'<td>{badge}{what}<br><small>{link}</small></td><td>{state}</td><td class="date">{r["date"]}</td></tr>')

page = f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light dark">
  <meta name="description" content="Bugs ChipLab's AI agents found in open-source hardware, each reproduced independently before it was reported.">
  <title>ChipLab findings</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <header class="site-header">
    <div class="wrap">
      <p class="brand"><a href="./">ChipLab</a></p>
      <nav aria-label="Sections">
        <a href="./#about">About</a>
        <a href="findings.html" aria-current="page">Findings</a>
        <a href="./#contact">Contact</a>
      </nav>
    </div>
  </header>
  <main class="wrap wide">
    <section class="intro">
      <h1>Findings</h1>
      <p class="lede">
        Bugs ChipLab's AI agents found in open-source hardware. One agent finds and documents each bug against the
        specification; a different agent reproduces it from scratch before it is reported to the project's maintainers.
      </p>
      <dl class="stats">
        <div><dt>Reports filed</dt><dd>{len(ids)} <span>{n_public} public, {n_private} private</span></dd></div>
        <div><dt>Projects (public reports)</dt><dd>{n_projects}</dd></div>
        <div><dt>In shipped silicon RTL</dt><dd>{n_shipped} <span>public reports</span></dd></div>
        <div><dt>Fixed upstream</dt><dd>{n_fixed}</dd></div>
      </dl>
      <p class="note">
        Each report carries a <strong>CLAB</strong> reference; this page links to it as
        <code>findings.html#clab-2026-NNN</code>. Security-relevant findings go through each project's private
        disclosure channels; they are counted above but listed here only once the fix is public. Updated {built}.
      </p>
    </section>
    <section>
      <table class="findings">
        <thead><tr><th>Ref</th><th>Project</th><th>Finding</th><th>Status</th><th>Filed</th></tr></thead>
        <tbody>
          {chr(10).join(row_html(r) for r in listed)}
        </tbody>
      </table>
    </section>
  </main>
  <footer class="wrap"><p class="note">ChipLab is operated by Donmakino LLC (dba ChipLab). <a href="./">Home</a></p></footer>
</body>
</html>
'''
(SITE / 'findings.html').write_text(page, encoding='utf-8', newline='\n')
print(f'findings.html: {len(rows)} rows, {len(ids)} refs ({n_public} public, {n_private} private), {n_projects} projects, '
      f'{n_shipped} shipped, {n_fixed} fixed')

#!/usr/bin/env python3
"""Rebuild the demo project of Tidewater Rentals (fictional) from scratch.

Writes the export, then runs the real UnBubble scripts on it into
examples/demo-app/projects/tidewater-rentals/, the layout the console reads:

    python3 examples/demo-app/build_demo.py
    cd ui && UNBUBBLE_PROJECTS_DIR=../examples/demo-app/projects UNBUBBLE_MCP_HOME=/tmp/unbubble-demo-mcp \
        BEFREE_BUBBLE_MCP_CONFIG_DIR=/tmp/unbubble-demo-befree npm run dev

The report date is fixed so a rebuild only changes what the scripts changed. stdlib only.
"""
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
APP = 'tidewater-rentals'
DATE = '2026-10-10'
EXPORT = os.path.join(HERE, APP + '.bubble')
PROJECT = os.path.join(HERE, 'projects', APP)
SKILLS = os.path.join(REPO, 'skills')


def run(*args):
    print('$', ' '.join(os.path.relpath(a, REPO) if os.path.isabs(a) else a for a in args))
    subprocess.run([sys.executable, *args], check=True, cwd=HERE, stdout=subprocess.DEVNULL)


def main():
    run(os.path.join(HERE, 'make_demo_export.py'))
    if os.path.isdir(PROJECT):
        shutil.rmtree(PROJECT)
    for sub in ('audit', 'inventory', 'secrets'):
        os.makedirs(os.path.join(PROJECT, sub))

    audit = os.path.join(SKILLS, 'audit', 'scripts', 'bubble_audit.py')
    common = ['--date', DATE, '--plugin-names', 'plugin-names.json', '--plugin-pricing', 'plugin-pricing.json']
    run(audit, EXPORT, '--lang', 'en', *common,
        '--out', os.path.join(PROJECT, 'audit', APP + '-v1_unused_report_EN.html'),
        '--json', os.path.join(PROJECT, 'audit', APP + '-v1_audit.json'))
    run(audit, EXPORT, '--lang', 'pt', *common,
        '--out', os.path.join(PROJECT, 'audit', APP + '-v1_unused_report.html'))

    run(os.path.join(SKILLS, 'clone', 'scripts', 'bubble_inventory.py'), EXPORT,
        '--outdir', os.path.join(PROJECT, 'inventory'), '--plugin-names', 'plugin-names.json')
    run(os.path.join(SKILLS, 'clone', 'scripts', 'bubble_secrets.py'), EXPORT,
        '--outdir', os.path.join(PROJECT, 'secrets'), '--plugin-names', 'plugin-names.json')

    with open(os.path.join(PROJECT, 'unbubble.json'), 'w', encoding='utf-8') as f:
        json.dump({'version': 1, 'name': 'Tidewater Rentals (demo)'}, f, indent=2)
        f.write('\n')
    print('demo project ->', os.path.relpath(PROJECT, REPO))


if __name__ == '__main__':
    main()

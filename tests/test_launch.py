import hashlib
import json
import re
from pathlib import Path
from conftest import ROOT


def test_launch_limits_and_links():
    x = (ROOT / 'launch/x-post.txt').read_text()
    linkedin = (ROOT / 'launch/linkedin-post.md').read_text()
    assert len(x) <= 280
    assert 120 <= len(linkedin.split()) <= 180
    assert 'https://github.com/grishahq/prove-fix' in x
    assert 'https://github.com/grishahq/prove-fix' in linkedin
    for doc in (ROOT / 'README.md', ROOT / 'media/README.md', ROOT / 'skills/prove-fix/SKILL.md'):
        for link in re.findall(r'\]\(([^)]+)\)', doc.read_text()):
            if '://' not in link and not link.startswith('#'):
                assert (doc.parent / link.split('#')[0]).exists(), (doc, link)


def test_retained_execution_and_render_evidence_is_consistent():
    folder = ROOT / 'media/evidence/demo'
    summary = json.loads((folder / 'summary.json').read_text())
    for item in summary['comparisons']:
        path = folder / item['report']
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item['report_sha256']
        report = json.loads(path.read_text())
        assert report['classification'] == item['classification']
        assert report['snapshots']['non_selected_identical']
        for pair in report['runs']:
            for run in pair.values():
                assert (path.parent / run['stdout']).exists()
                assert (path.parent / run['stderr']).exists()
    rendered = json.loads((ROOT / 'media/render-validation.json').read_text())
    assert 15 <= rendered['duration_seconds'] <= 25
    assert rendered['codec'] == 'h264' and rendered['pixel_format'] == 'yuv420p'
    assert rendered['fast_start_atoms'].index('moov') < rendered['fast_start_atoms'].index('mdat')
    assert rendered['video_sha256'] == hashlib.sha256((ROOT / 'media/prove-fix-demo.mp4').read_bytes()).hexdigest()
    assert rendered['source_reports'] == summary['comparisons']

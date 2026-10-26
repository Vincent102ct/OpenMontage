"""Read-only validation of a separately transferred synthetic P3.5 checkpoint.

Usage: python -B scripts/verify_p35_handoff.py /path/to/extracted-state
Never approves, synthesizes, renders, repairs or rewrites an immutable artifact.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def verify(export: Path) -> dict:
    export = export.resolve()
    manifest = json.loads((export / 'MANIFEST.json').read_bytes())
    require(manifest.get('artifact') == 'p35_synthetic_pending_handoff'
            and manifest.get('schema_version') == '1.0', 'Unknown handoff manifest.')
    project_id = manifest['project_id']
    require(project_id == 'en-proof', 'This checkpoint is limited to synthetic en-proof.')
    expected = manifest['files']
    require(isinstance(expected, dict) and bool(expected), 'Empty file manifest.')
    for name, record in expected.items():
        relative = PurePosixPath(name)
        require(not relative.is_absolute() and '..' not in relative.parts
                and '\\' not in name and ':' not in name
                and relative.parts[:2] == ('projects', project_id), 'Unsafe manifest path.')
        path = export.joinpath(*relative.parts)
        require(not path.is_symlink() and path.resolve().is_relative_to(export)
                and path.is_file(), f'Missing or unsafe exported file: {name}')
        require(path.stat().st_size == record['size'] and digest(path) == record['sha256'],
                f'Exported file hash/size mismatch: {name}')
    actual = {p.relative_to(export).as_posix() for p in (export / 'projects').rglob('*') if p.is_file()}
    require(actual == set(expected), 'Unexpected or missing project data in export.')
    for name, wanted in manifest['source_sha256'].items():
        relative = PurePosixPath(name)
        require(not relative.is_absolute() and '..' not in relative.parts
                and ':' not in name and '\\' not in name, 'Unsafe source path.')
        source = ROOT.joinpath(*relative.parts)
        require(source.resolve().is_relative_to(ROOT) and source.is_file()
                and digest(source) == wanted, f'Checkpoint source bytes differ: {name}')

    from studio.catalog import ApprovedPackages
    from studio.store import ProductionStore
    from studio import scene_staging as staging, story_video as production

    store = ProductionStore(export / 'projects', ApprovedPackages(ROOT))
    detail = store.detail(project_id)
    require('[SYNTHETIC TEST]' in detail['request']['title'], 'Synthetic marker is absent.')
    view, _ = production._current(store, project_id)  # Verifies canon/VB/SP approval and exact fixture digest.
    candidate = staging.read_staging(store, project_id)
    require(candidate['version'] == 'v2' and candidate['status'] == 'awaiting_review'
            and candidate['approval'] is None and not candidate['ready_for_render']
            and len(candidate['review_items']) == 33, 'Candidate is not the 33-item pending v2.')
    require(candidate['reference'] == manifest['candidate'], 'Candidate identity differs.')
    project = export / 'projects' / project_id
    require(not list((project / staging.OUTPUT).rglob('approval.json')),
            'Unexpected visual staging approval.')
    _, _, timed = staging.context(store, project_id, candidate['manifest']['narration'])
    # context verifies the real PCM bytes/sample counts/text hashes of every bound WAV.
    shots = {fmt: [s['shot_id'] for s in value['shots']] for fmt, value in timed.items()}
    require(shots == manifest['shot_ids'], 'Shot IDs/order differ.')
    require({fmt: len(ids) for fmt, ids in shots.items()} == {'short': 13, 'long': 20},
            'Unexpected Short/Long coverage.')
    # Check that verification itself did not write or migrate any project record.
    require(actual == {p.relative_to(export).as_posix() for p in (export / 'projects').rglob('*') if p.is_file()},
            'Verification created a project file.')
    require(all(digest(export / name) == record['sha256'] for name, record in expected.items()),
            'Verification changed an exported file.')
    return {'status': 'PASS', 'project_id': project_id, 'candidate': candidate['reference'],
            'review_items': 33, 'approval': 'PENDING', 'exported_files': len(expected),
            'wav_files': sum(name.endswith('.wav') for name in expected),
            'shots': {fmt: len(ids) for fmt, ids in shots.items()},
            'durations_seconds': {fmt: value['duration_seconds'] for fmt, value in timed.items()},
            'source_files_verified': len(manifest['source_sha256']),
            'approved_plan_version': view['version'], 'full_story_rendered': False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('export', type=Path, help='Extracted state directory containing MANIFEST.json and projects/')
    args = parser.parse_args()
    try:
        result = verify(args.export)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({'status': 'BLOCKED', 'message': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

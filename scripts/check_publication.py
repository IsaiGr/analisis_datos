"""Allowlisted publication checks. Never print suspected secret values."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = frozenset({
    '.gitignore', '.streamlit/config.toml', '.github/workflows/ci.yml',
    '.github/dependabot.yml', 'README.md', 'SECURITY.md', 'requirements.txt',
    'app.py', 'docs/CARGA_LOCAL.md', 'src/__init__.py', 'src/data_pipeline.py',
    'src/dashboard_charts.py', 'src/models.py', 'src/demo_data.py',
    'scripts/check_publication.py', 'tests/test_data_pipeline.py',
    'tests/test_dashboard_charts.py', 'tests/test_coverage_priority.py',
    'tests/test_demo_data.py', 'tests/test_publication.py',
    'tests/integration_dashboard.py',
})
IGNORED_DIRS = frozenset({'.git', '.venv', '__pycache__', '.pytest_cache'})
PATTERNS = {
    'possible GitHub credential': r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})',
    'possible private key': r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
    'possible cloud credential': r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b',
    'personal Windows path': r'[A-Za-z]:[\\/]+Users[\\/]+[A-Za-z0-9]',
    'personal Unix path': r'/(?:home|Users)/[A-Za-z0-9][^/\s]*/',
    'possible personal email': r'\b[A-Za-z0-9._%+-]+@(?:gmail|hotmail|outlook|yahoo)\.[A-Za-z]{2,}\b',
}


def inspect_file(name, content, mode='100644'):
    problems = []
    if name not in ALLOWED:
        problems.append('file outside publication allowlist')
    if mode not in {'100644', '100755'}:
        problems.append('links and submodules are not permitted')
    if len(content) > 1_000_000 or b'\0' in content:
        problems.append('binary or unexpectedly large content')
        return problems
    try:
        decoded = content.decode('utf-8-sig')
    except UnicodeDecodeError:
        return problems + ['not UTF-8 text']
    problems.extend(label for label, pattern in PATTERNS.items() if re.search(pattern, decoded))
    return problems


def publication_files(staged=False):
    if staged:
        listing = subprocess.check_output(['git', 'ls-files', '--stage', '-z'], cwd=ROOT)
        for entry in listing.split(b'\0'):
            if not entry:
                continue
            metadata, encoded_name = entry.split(b'\t', 1)
            mode, blob, stage = metadata.decode().split()
            if stage != '0':
                raise ValueError('Unresolved Git merge; publication stopped.')
            content = subprocess.check_output(['git', 'cat-file', 'blob', blob], cwd=ROOT)
            yield encoded_name.decode('utf-8'), content, mode
    else:
        for path in sorted(ROOT.rglob('*')):
            relative = path.relative_to(ROOT)
            if any(part in IGNORED_DIRS for part in relative.parts):
                continue
            if path.is_symlink():
                yield relative.as_posix(), b'', '120000'
            elif path.is_file():
                yield relative.as_posix(), path.read_bytes(), '100644'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--staged', action='store_true', help='Inspect Git index blobs, not working files.')
    parser.add_argument('--zip', type=Path, help='Create an exclusive archive of checked files outside this folder.')
    args = parser.parse_args()
    entries = list(publication_files(args.staged))
    errors = [(name, issue) for name, content, mode in entries for issue in inspect_file(name, content, mode)]
    missing = ALLOWED.difference(name for name, _, _ in entries)
    errors.extend((name, 'required publication file missing') for name in sorted(missing))
    if errors:
        for name, issue in errors:
            print(f'REVIEW: {name}: {issue}')
        return 1
    print(f'PASS: {len(entries)} allowlisted text files; no detected sensitive patterns.')
    print('Only a pattern/allowlist check; manual content review remains necessary.')
    if args.zip:
        # Normalize '..' before resolve: some Windows sandbox providers retain it.
        destination = Path(os.path.abspath(args.zip)).resolve()
        if destination.is_relative_to(ROOT):
            raise ValueError('Archive must be outside the publication source folder.')
        with zipfile.ZipFile(destination, mode='x', compression=zipfile.ZIP_DEFLATED) as archive:
            for name, content, _ in entries:
                archive.writestr(name, content)
        print(f'Created: {destination.name}')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        sys.exit(f'Publication check could not finish: {type(error).__name__}.')

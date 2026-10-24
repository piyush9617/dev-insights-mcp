import os
from collections import Counter
from pathlib import Path

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP('dev-insights')

ALLOWED_ROOT = Path(os.environ.get('ALLOWED_ROOT', '.')).resolve()
GITHUB_API = 'https://api.github.com'
SKIP_DIRS = {'.git', 'node_modules', '.venv', '__pycache__'}
TEXT_EXT = {'.py', '.js', '.ts', '.java', '.c', '.cpp', '.html', '.css', '.md'}


def _check_repo(owner, repo):
    def ok(s):
        return bool(s) and s.replace('-', '').replace('_', '').replace('.', '').isalnum()
    if not (ok(owner) and ok(repo)):
        raise ValueError('Invalid owner or repo name')


def _get(path, params=None):
    headers = {'Accept': 'application/vnd.github+json'}
    if os.environ.get('GITHUB_TOKEN'):
        headers['Authorization'] = 'Bearer ' + os.environ['GITHUB_TOKEN']
    r = httpx.get(GITHUB_API + path, headers=headers, params=params, timeout=15)
    if r.status_code == 404:
        raise ValueError('Repo not found')
    if r.status_code == 403:
        raise RuntimeError('GitHub rate limit hit. Wait or set GITHUB_TOKEN.')
    r.raise_for_status()
    return r.json()


def safe_path(path):
    p = (ALLOWED_ROOT / path).resolve()
    if p != ALLOWED_ROOT and ALLOWED_ROOT not in p.parents:
        raise PermissionError('Path is outside ALLOWED_ROOT')
    return p


def analyze(root, max_files=5000):
    ext_count, lines, todos, sizes, seen = Counter(), 0, 0, [], 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            seen += 1
            if seen > max_files:
                break
            f = Path(dirpath) / name
            ext = f.suffix.lower() or '(none)'
            ext_count[ext] += 1
            sizes.append((f.stat().st_size, str(f.relative_to(root))))
            if ext in TEXT_EXT:
                text = f.read_text(encoding='utf-8', errors='ignore')
                lines += text.count('\n') + 1
                todos += text.count('TODO') + text.count('FIXME')
        if seen > max_files:
            break
    sizes.sort(reverse=True)
    return {
        'files': min(seen, max_files),
        'by_extension': dict(ext_count.most_common(8)),
        'text_lines': lines,
        'todo_fixme': todos,
        'largest_files': [{'path': p, 'bytes': s} for s, p in sizes[:5]],
    }


@mcp.tool()
def repo_summary(owner: str, repo: str) -> dict:
    """Summarize a public GitHub repo: description, stars, languages, last push, open issues."""
    _check_repo(owner, repo)
    info = _get(f'/repos/{owner}/{repo}')
    langs = _get(f'/repos/{owner}/{repo}/languages')
    return {
        'name': info['full_name'],
        'description': info['description'],
        'stars': info['stargazers_count'],
        'open_issues': info['open_issues_count'],
        'last_push': info['pushed_at'],
        'languages': langs,
    }


@mcp.tool()
def list_issues(owner: str, repo: str, state: str = 'open', limit: int = 10) -> list[dict]:
    """List issues of a public GitHub repo (state: open, closed or all; limit: 1-30)."""
    _check_repo(owner, repo)
    if state not in {'open', 'closed', 'all'}:
        raise ValueError('state must be open, closed or all')
    limit = max(1, min(limit, 30))
    items = _get(f'/repos/{owner}/{repo}/issues', {'state': state, 'per_page': limit})
    return [{'number': i['number'], 'title': i['title'], 'state': i['state'], 'url': i['html_url']}
            for i in items if 'pull_request' not in i]


@mcp.tool()
def analyze_folder(path: str = '.') -> dict:
    """Analyze a local project folder inside ALLOWED_ROOT: file types, lines of code, TODO count, largest files."""
    return analyze(safe_path(path))


if __name__ == '__main__':
    mcp.run()
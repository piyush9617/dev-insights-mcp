import pytest
from server import safe_path, analyze, _check_repo

def test_safe_path_blocks_escape():
    with pytest.raises(PermissionError):
        safe_path('../../etc')

def test_invalid_repo_name_rejected():
    with pytest.raises(ValueError):
        _check_repo('foo; rm -rf', 'bar')

def test_analyze_counts_todo(tmp_path):
    (tmp_path / 'a.py').write_text('# TODO fix\nprint(1)\n')
    out = analyze(tmp_path)
    assert out['files'] == 1 and out['todo_fixme'] == 1
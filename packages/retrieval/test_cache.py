import shutil
from unittest.mock import patch

from retrieve import ROOT, _release_index, load, retrieve


def test_cache_reuses_immutable_revision_and_does_not_leak_mutations(tmp_path):
    _release_index.cache_clear()
    request = {
        "request_id": "req_cache", "data_revision": "psi-20261115-r2",
        "question": "Как вентиляция влияет на горение твердых материалов?",
        "top_k": 12, "selected_investigation_ids": [], "filters": {}, "scenario": None,
    }
    with patch('retrieve.load', wraps=load) as reader:
        original = retrieve(request)
        returned = retrieve(request)
        returned['evidence_bundle']['items'][0]['evidence']['excerpt'] = 'caller mutation'
        assert retrieve(request) == original
        assert reader.call_count == 1
    with patch('retrieve.load', wraps=load) as reader:
        other_release = tmp_path / 'release'
        shutil.copytree(ROOT / 'data/releases/psi-20261115-r2', other_release)
        retrieve(request, release_dir=other_release)
        assert reader.call_count == 1
        assert reader.call_args.args[0] == str(other_release.resolve())
    _release_index.cache_clear()

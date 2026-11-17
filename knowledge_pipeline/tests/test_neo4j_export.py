import json
from datetime import date

import pytest

from knowledge_pipeline.neo4j_export import json_value, read_graph


def test_property_types_are_valid_json():
    result = json_value({"text": "Nguồn", "bytes": b"abc", "date": date(2026, 10, 28),
                         "list": [1, True, None], "infinity": float("inf")})
    json.dumps(result, allow_nan=False)
    assert result["bytes"] == {"$type": "bytes", "base64": "YWJj"}
    assert result["date"]["value"] == "2026-10-28"
    assert result["list"] == [1, True, None]


class FakeTransaction:
    def __init__(self, bad_reference=False):
        self.bad_reference = bad_reference
        self.calls = []

    def run(self, query, **parameters):
        self.calls.append((query, parameters))
        if "labels(n)" in query:
            return [{"element_id": n, "labels": ["Test"], "properties": {"name": n}}
                    for n in ("a", "b", "isolated")]
        return [{"element_id": "r1", "type": "ABOUT", "start": "a",
                 "end": "missing" if self.bad_reference else "b", "properties": {}},
                {"element_id": "r2", "type": "ABOUT", "start": "a",
                 "end": "b", "properties": {"version": 2}}]


def test_export_preserves_isolated_nodes_and_parallel_directed_edges():
    tx = FakeTransaction()
    result = read_graph(tx, "demo-with-special'characters")
    assert len(result["nodes"]) == 3 and len(result["relationships"]) == 2
    assert result["relationships"][0]["start_node"] == "a"
    assert result["relationships"][0]["end_node"] == "b"
    for query, parameters in tx.calls:
        assert parameters["demo_id"] == "demo-with-special'characters"
        assert "demo-with-special" not in query
        assert "CREATE " not in query and "DELETE " not in query


def test_dangling_reference_does_not_produce_an_incomplete_export():
    with pytest.raises(ValueError, match="complete references"):
        read_graph(FakeTransaction(bad_reference=True), None)

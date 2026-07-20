from phantom.agent.snapshot import SnapshotIndex


def fixture():
    return [
        {"backend_id": "b2", "role": "button", "name": "Save", "value": "", "visible": True},
        {"backend_id": "i1", "role": "textbox", "name": "Email", "value": "a@example.test", "visible": True},
        {"backend_id": "hidden", "role": "button", "name": "No", "visible": False},
    ]


def test_snapshot_is_compact_stable_and_filters_hidden():
    index = SnapshotIndex()
    one = index.build("https://example.test", "Example", fixture())
    two = index.build("https://example.test", "Example", fixture())
    assert one["generation"] == 1 and two["generation"] == 2
    assert one["elements"] == [
        {"ref": "e1", "role": "button", "name": "Save", "visible": True},
        {"ref": "e2", "role": "textbox", "name": "Email", "value": "a@example.test", "visible": True},
    ]
    assert "html" not in str(one).lower()


def test_refs_are_generation_scoped_and_explicitly_stale():
    index = SnapshotIndex()
    first = index.build("about:blank", "", fixture())
    assert index.resolve("e1", first["generation"]) == "b2"
    index.build("about:blank", "", fixture())
    try:
        index.resolve("e1", first["generation"])
    except Exception as exc:
        assert getattr(exc, "code", None) == "STALE_REF"
    else:
        raise AssertionError("stale ref accepted")

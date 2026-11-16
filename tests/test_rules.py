from app.matching import Condition, Signature, find_matches, get_field, signature_matches
from app.priority import detection_priority


def sig(id: int, priority: int, conditions: dict[str, str]) -> Signature:
    return Signature(id, f"sig-{id}", priority, [Condition(f, v) for f, v in conditions.items()])


def test_get_field_reads_nested_paths():
    assert get_field({"process": {"name": "cmd.exe"}}, "process.name") == "cmd.exe"


def test_get_field_missing_path():
    assert get_field({"process": "cmd.exe"}, "process.name") is None
    assert get_field({}, "a.b.c") is None


ENCODED_POWERSHELL = sig(1, 3, {"process.name": "powershell.exe", "process.encoded_command": "true"})


def test_matches_when_every_condition_matches():
    incident = {"process": {"name": "powershell.exe", "encoded_command": True}, "extra": 1}
    assert signature_matches(ENCODED_POWERSHELL, incident)


def test_no_match_when_only_some_conditions_match():
    assert not signature_matches(ENCODED_POWERSHELL, {"process": {"name": "powershell.exe"}})


def test_case_sensitive_and_numbers_compared_as_text():
    assert not signature_matches(ENCODED_POWERSHELL, {"process": {"name": "PowerShell.exe", "encoded_command": True}})
    assert signature_matches(sig(2, 1, {"port": "3389"}), {"port": 3389})


def test_objects_arrays_and_null_never_match():
    assert not signature_matches(sig(3, 1, {"tags": "a"}), {"tags": ["a"]})
    assert not signature_matches(sig(3, 1, {"x": "None"}), {"x": None})


def test_signature_without_conditions_never_matches():
    assert not signature_matches(sig(4, 1, {}), {"anything": "x"})


def test_find_matches_returns_nothing_without_a_match():
    assert find_matches([sig(1, 5, {"a": "1"})], {"a": "2"}) == []


def test_multiple_matches_ordered_by_priority_then_specificity_then_id():
    signatures = [
        sig(1, 2, {"a": "1"}),
        sig(2, 4, {"a": "1"}),
        sig(3, 4, {"a": "1", "b": "2"}),
        sig(4, 4, {"a": "1", "b": "2"}),
        sig(5, 5, {"z": "no"}),
    ]
    assert [s.id for s in find_matches(signatures, {"a": "1", "b": "2"})] == [3, 4, 2, 1]


def test_priority_multiplies_importance_and_signature_priority():
    assert detection_priority(5, 5) == 25
    assert detection_priority(5, 1) == 5
    assert detection_priority(1, 1) == 1
    assert detection_priority(3, 4) == 12

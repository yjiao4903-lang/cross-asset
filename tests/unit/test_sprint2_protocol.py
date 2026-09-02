import copy

import pytest

from cross_asset.sprint2.config import config_hash, load_sprint2_config, validate_sprint2_config


def test_frozen_sprint2_protocol_loads_and_hash_is_stable():
    raw = load_sprint2_config()
    protocol, policies = validate_sprint2_config(raw)
    assert len(protocol.universe) == 4
    assert protocol.default_mode == "expanding"
    assert protocol.transaction_cost_bps == (0, 5, 10, 20, 30)
    assert protocol.charge_initial_trade is False
    assert protocol.signal_model_version == "full_model_v0.2"
    assert len(protocol.benchmarks) == 5
    assert len(protocol.outputs) == 7
    assert protocol.preliminary and protocol.partial_universe and not protocol.research_validated
    assert len(policies) == 6
    assert config_hash(raw) == config_hash(raw)


@pytest.mark.parametrize(
    "field,value",
    [
        ("base_cost_bps", 5),
        ("default_mode", "rolling"),
        ("transaction_cost_bps", [0, 5, 10]),
        ("research_validated", True),
        ("charge_initial_trade", True),
        ("signal_model_version", "full_model_v0.1"),
    ],
)
def test_protocol_rejects_tuning_or_release_drift(field, value):
    raw = copy.deepcopy(load_sprint2_config())
    raw["protocol"][field] = value
    with pytest.raises(ValueError):
        validate_sprint2_config(raw)


def test_temporary_plus_45_requires_explicit_flags():
    raw = copy.deepcopy(load_sprint2_config())
    del raw["availability_policies"][0]["temporary"]
    with pytest.raises(ValueError):
        validate_sprint2_config(raw)


def test_implicit_global_availability_rule_is_rejected():
    raw = copy.deepcopy(load_sprint2_config())
    raw["availability_policies"].append({"default": True})
    with pytest.raises(ValueError):
        validate_sprint2_config(raw)


def test_unknown_release_date_is_not_accepted_as_exact():
    raw = copy.deepcopy(load_sprint2_config())
    raw["availability_policies"][0]["rule"] = "release_date"
    with pytest.raises(ValueError):
        validate_sprint2_config(raw)

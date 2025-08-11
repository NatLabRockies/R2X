import json

import pytest
from pint import Quantity

from r2x.api import System
from r2x.config_scenario import Scenario
from r2x.models import MinMax, ThermalStandard, UpDown
from r2x.models.getters import get_ramp_limits
from r2x.plugins.pcm_defaults import update_system
from r2x.runner import run_parser


@pytest.fixture(scope="function")
def test_system(reeds_data_folder, tmp_path):
    config = Scenario.from_kwargs(
        name="ReEDS-TestSystem",
        run_folder=reeds_data_folder,
        output_folder=tmp_path,
        input_model="reeds-US",
        output_model="plexos",
        solve_year=2035,
        weather_year=2012,
        plugins=["pcm_defaults"],
    )
    system, parser = run_parser(config)
    return config, system, parser


def test_update_system(test_system):
    config, system, parser = test_system
    _ = update_system(config=config, parser=parser, system=system)


def test_custom_pcm_defaults(tmp_path):
    config = Scenario.from_kwargs(input_model="infrasys", output_model="sienna")
    system = System(auto_add_composed_components=True)

    gen_01 = ThermalStandard.example()
    system.add_component(gen_01)
    assert gen_01.ramp_limits is None
    assert gen_01.forced_outage_rate is None
    assert gen_01.startup_cost is None

    pcm_defaults = {
        "ThermalStandard": {
            "forced_outage_rate": 4.29,
            "maintenance_rate": 10.0,
            "ramp_limits": {"down": 0.02, "up": 0.02},
            "start_cost_per_MW": 129.0,
            "time_limits": {"down": 12.0, "up": 24.0},
        }
    }
    temp_file = tmp_path / "pcm_data.json"

    # Write the dictionary to the temporary JSON file
    with open(temp_file, "w") as f:
        json.dump(pcm_defaults, f)

    _ = update_system(config, None, system, pcm_defaults_fpath=temp_file)
    assert get_ramp_limits(gen_01) == UpDown(up=2.0, down=2.0)  # 2 MW since example has 100 MW
    assert gen_01.forced_outage_rate
    assert isinstance(gen_01.forced_outage_rate, Quantity)
    assert gen_01.forced_outage_rate.magnitude == 4.29


def test_custom_pcm_defaults_override(tmp_path):
    pcm_defaults = {
        "ThermalStandard": {
            "active_power_limits": {"max": 100.0, "min": 10.0},
            "ramp_limits": {"up": 0.3, "down": 0.3},
            "non_valid_field": 10.0,
        }
    }
    temp_file = tmp_path / "pcm_data.json"

    # Write the dictionary to the temporary JSON file
    with open(temp_file, "w") as f:
        json.dump(pcm_defaults, f)
    config = Scenario.from_kwargs(input_model="infrasys", output_model="sienna")
    system = System(auto_add_composed_components=True)

    gen_01 = ThermalStandard.example()
    gen_01.ramp_limits = UpDown(up=50, down=50)
    system.add_component(gen_01)

    # Make sure that we just override fields that are None
    _ = update_system(config, None, system, pcm_defaults_fpath=temp_file, pcm_defaults_override=False)
    assert get_ramp_limits(gen_01) == UpDown(up=50.0, down=50.0)

    # Now test that we override even the fields that are set
    _ = update_system(config, None, system, pcm_defaults_fpath=temp_file, pcm_defaults_override=True)
    assert get_ramp_limits(gen_01)
    assert gen_01.active_power_limits == MinMax(max=100.0, min=10.0)

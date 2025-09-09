from copy import deepcopy

import h5py
import numpy as np
import pandas as pd
import pytest
from _pytest.logging import LogCaptureFixture
from loguru import logger

from r2x.models import HydroGenerationCost

WEATHER_YEARS = 7


@pytest.fixture
def caplog(caplog: LogCaptureFixture):
    handler_id = logger.add(
        caplog.handler,
        format="{message}",
        level=0,
        filter=lambda record: record["level"].no >= caplog.handler.level,
        enqueue=False,  # Set to 'True' if your test is spawning child processes.
    )
    yield caplog
    logger.remove(handler_id)


@pytest.fixture(scope="function")
def pandas_h5_weather_year(tmp_path):
    fpath = tmp_path / "pandas.h5"
    index = pd.Index(range(WEATHER_YEARS * 8760), name="index")
    data = {f"upv_{number}": np.random.rand(WEATHER_YEARS * 8760) for number in range(3)}
    pandas_data = pd.DataFrame(index=index, data=data)
    pandas_data.to_hdf(fpath, key="df", mode="w", format="fixed")
    return fpath


@pytest.fixture(scope="function")
def pandas_h5_solve_year_and_weather_year(tmp_path):
    fpath = tmp_path / "pandas.h5"

    unique_year_sorted = sorted(set(range(2030, 2050, 10)))
    unique_datetime_sorted = sorted(set(range(WEATHER_YEARS * 8760)))
    multilevel_index = pd.MultiIndex.from_product(
        [unique_year_sorted, unique_datetime_sorted], names=["year", "datetime"]
    )
    data_size = len(multilevel_index)
    data = {f"upv_{number}": np.random.rand(data_size) for number in range(3)}
    pandas_data = pd.DataFrame(index=multilevel_index, data=data)
    pandas_data.to_hdf(fpath, key="df", mode="w", format="fixed")
    return fpath


@pytest.fixture(scope="function")
def h5_without_index_names(tmp_path):
    fpath = tmp_path / "h5_no_index.h5"
    with h5py.File(fpath, "w") as f:
        f.create_dataset("index_0", data=[0])
        f.create_dataset("index_1", data=[0])
        f.create_dataset("columns", data=[0])
        f.create_dataset("index_names", data=[0])
        f.create_dataset("data", data=[0])
    return fpath


@pytest.fixture(scope="function")
def h5_with_index_names_no_datetime(tmp_path):
    fpath = tmp_path / "h5_no_index.h5"
    unique_year_sorted = sorted(set(range(2030, 2050, 10)))
    unique_datetime_sorted = sorted(set(range(WEATHER_YEARS * 8760)))
    data_keys = ["upv_1", "upv_2", "upv_3"]
    data = np.random.rand(WEATHER_YEARS * 8760, len(data_keys))
    with h5py.File(fpath, "w") as f:
        f.create_dataset("index_year", data=unique_year_sorted)
        f.create_dataset("index_datetime", data=unique_datetime_sorted)
        f.create_dataset("columns", data=data_keys)
        f.create_dataset("index_names", data=["year", "datetime"])
        f.create_dataset("data", data=data)
    return fpath


@pytest.fixture
def hydro_energy_reservoir_component():
    return {
        "type": "HydroEnergyReservoir",
        "name": "Reservoir1",
        "available": True,
        "inflow": 10.0,
        "rating": 1.0,
        "base_power": 20.0,
        "initial_energy": 5.0,
        "storage_capacity": 100.0,
        "min_storage_capacity": 10.0,
        "storage_target": 80.0,
        "ramp_limits": {"up": 5.0, "down": 5.0},
        "time_limits": {"min_up": 1, "min_down": 1},
        "bus": {"value": "bus-id-1"},
        "operation_cost": HydroGenerationCost.example().model_dump(round_trip=True, mode="json"),
    }


@pytest.fixture
def hydro_pumped_storage_component():
    return {
        "type": "HydroPumpedStorage",
        "name": "PumpedStorage1",
        "available": True,
        "inflow": 20.0,
        "outflow": 5.0,
        "rating": 100.0,
        "rating_pump": 80.0,
        "base_power": 50.0,
        "initial_energy": 500.0,
        "storage_capacity": {"up": 1000.0, "down": 0.0},
        "storage_target": {"up": 800.0, "down": 0.0},
        "initial_storage": {"up": 500.0, "down": 500.0},
        "pump_efficiency": 0.85,
        "ramp_limits": {"up": 10.0, "down": 10.0},
        "time_limits": {"min_up": 1, "min_down": 1},
        "ramp_limits_pump": {"up": 5.0, "down": 5.0},
        "time_limits_pump": {"min_up": 1, "min_down": 1},
        "bus": {"value": "bus-id-2"},
        "operation_cost": HydroGenerationCost.example().model_dump(round_trip=True, mode="json"),
        "conversion_factor": 1.0,
        "initial_volume": 500.0,
        "pump_load": 100.0,
    }


@pytest.fixture
def old_system_data(hydro_energy_reservoir_component, hydro_pumped_storage_component):
    """Return a system data dict containing both HydroEnergyReservoir and HydroPumpedStorage."""
    return {
        "components": [
            deepcopy(hydro_energy_reservoir_component),
            deepcopy(hydro_pumped_storage_component),
        ]
    }

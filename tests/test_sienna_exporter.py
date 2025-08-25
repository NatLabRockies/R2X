import json
from typing import Any

import pytest
from infrasys.cost_curves import CostCurve, FuelCurve, UnitSystem
from infrasys.function_data import PiecewiseLinearData, QuadraticFunctionData, XYCoords
from infrasys.value_curves import InputOutputCurve, LinearCurve

from r2x.config_scenario import Scenario
from r2x.exporter.sienna import (
    SiennaExporter,
    apply_operation_table_data,
    create_timeseries_pointers,
    get_psy_fields,
)
from r2x.models.costs import ThermalGenerationCost


@pytest.fixture
def scenario_instance(data_folder, tmp_path):
    return Scenario.from_kwargs(
        name="Test Scenario",
        run_folder=data_folder,
        output_folder=tmp_path,
        input_model="infrasys",
        output_model="sienna",
        reference_year=2010,
    )


@pytest.fixture
def sienna_exporter(scenario_instance, infrasys_test_system, tmp_path):
    return SiennaExporter(config=scenario_instance, system=infrasys_test_system, output_folder=tmp_path)


@pytest.mark.sienna
def test_sienna_exporter_instance(sienna_exporter):
    assert isinstance(sienna_exporter, SiennaExporter)


@pytest.mark.sienna
def test_sienna_exporter_run(sienna_exporter, tmp_path):
    exporter = sienna_exporter.run()

    output_files = [
        "gen.csv",
        "bus.csv",
        "timeseries_pointers.json",
        # "storage.csv",  # Storage is also optional
        "reserves.csv",  # Reserve could be optional
        "dc_branch.csv",
        "branch.csv",
    ]

    for file in output_files:
        assert (tmp_path / file).exists(), f"File {file} was not created properly."

    # Check that time series was created correctly
    ts_directory = tmp_path / exporter.ts_directory
    assert any(ts_directory.iterdir())


def test_create_time_series_pointers(sienna_exporter, tmp_path):
    exporter = sienna_exporter

    assert create_timeseries_pointers(
        exporter.config,
        exporter.system,
        output_folder=exporter.config.output_folder,
        reference_year=exporter.year,
    )
    output_fpath = tmp_path / "timeseries_pointers.json"
    assert output_fpath.exists()

    with open(output_fpath) as f:
        pointers = json.load(f)
    assert pointers


def test_sienna_exporter_empty_storage(caplog, sienna_exporter):
    sienna_exporter.process_storage_data()
    assert "No storage devices found" in caplog.text


def test_get_psy_fields():
    fields = get_psy_fields()
    assert isinstance(fields, dict)


def test_apply_operation_table_data_basic():
    sample_component = {
        "operation_cost": ThermalGenerationCost(
            variable=FuelCurve(
                value_curve=LinearCurve(10.0, 12),
                vom_cost=LinearCurve(10.0),
                fuel_cost=0.05,
                power_units=UnitSystem.NATURAL_UNITS,
            )
        ).model_dump(mode="python", serialize_as_any=True)
    }

    updated_component = apply_operation_table_data(sample_component)

    assert "variable_cost" in updated_component
    assert "fuel_price" in updated_component
    assert updated_component["variable_cost"] == 10
    assert updated_component["fuel_price"] == 50  # 0.05 * 1000


def test_apply_operation_table_data_heat_rate():
    sample_component = {
        "operation_cost": ThermalGenerationCost(
            variable=FuelCurve(
                value_curve=InputOutputCurve(
                    function_data=QuadraticFunctionData(
                        constant_term=100, proportional_term=20, quadratic_term=0.5
                    )
                ),
                vom_cost=LinearCurve(10.0),
                fuel_cost=0.05,
                power_units=UnitSystem.NATURAL_UNITS,
            )
        ).model_dump(mode="python", serialize_as_any=True)
    }
    updated_component = apply_operation_table_data(sample_component)

    assert "heat_rate_a0" in updated_component
    assert "heat_rate_a1" in updated_component
    assert "heat_rate_a2" in updated_component
    assert updated_component["heat_rate_a0"] == 100
    assert updated_component["heat_rate_a1"] == 20
    assert updated_component["heat_rate_a2"] == 0.5


def test_apply_operation_table_data_cost_curve():
    cost_curve_component = {
        "operation_cost": ThermalGenerationCost(
            variable=CostCurve(
                value_curve=InputOutputCurve(
                    function_data=PiecewiseLinearData(points=[XYCoords(x=0, y=0), XYCoords(x=50, y=1000)])
                ),
                vom_cost=LinearCurve(10.0),
                power_units=UnitSystem.NATURAL_UNITS,
            )
        ).model_dump(mode="python", serialize_as_any=True)
    }
    updated_component = apply_operation_table_data(cost_curve_component)

    assert "output_point_0" in updated_component
    assert "cost_point_0" in updated_component
    assert updated_component["output_point_0"] == 0
    assert updated_component["cost_point_0"] == 0
    assert updated_component["output_point_1"] == 50
    assert updated_component["cost_point_1"] == 1000


def test_apply_operation_table_data_fuel_curve():
    fuel_curve_component = {
        "operation_cost": ThermalGenerationCost(
            variable=FuelCurve(
                value_curve=InputOutputCurve(
                    function_data=PiecewiseLinearData(
                        points=[XYCoords(x=0, y=0), XYCoords(x=50, y=10), XYCoords(x=100, y=25)]
                    )
                ),
                vom_cost=LinearCurve(10.0),
                power_units=UnitSystem.NATURAL_UNITS,
            )
        ).model_dump(mode="python", serialize_as_any=True)
    }
    updated_component = apply_operation_table_data(fuel_curve_component)

    assert "output_point_0" in updated_component
    assert "heat_rate_avg_0" in updated_component
    assert updated_component["output_point_0"] == 0
    assert updated_component["heat_rate_avg_0"] == 0
    assert updated_component["output_point_1"] == 50
    assert updated_component["heat_rate_incr_1"] == 10


def test_apply_operation_table_data_no_operation_cost():
    component = {"id": "test_component"}
    updated_component = apply_operation_table_data(component)
    assert updated_component == component


def test_apply_operation_table_data_no_variable():
    component = {"operation_cost": {}}
    updated_component = apply_operation_table_data(component)
    assert updated_component == component


def test_apply_operation_table_data_unsupported_curve():
    wrong_curve_component: dict[str, Any] = {
        "operation_cost": ThermalGenerationCost(
            variable=FuelCurve(
                value_curve=InputOutputCurve(
                    function_data=PiecewiseLinearData(
                        points=[XYCoords(x=0, y=0), XYCoords(x=50, y=10), XYCoords(x=100, y=25)]
                    )
                ),
                vom_cost=LinearCurve(10.0),
                power_units=UnitSystem.NATURAL_UNITS,
            )
        ).model_dump(mode="python", serialize_as_any=True)
    }
    wrong_curve_component["operation_cost"]["variable_type"] = "NewValueCurve"
    with pytest.raises(NotImplementedError):
        apply_operation_table_data(wrong_curve_component)


def test_apply_operation_table_data_none_fuel_cost():
    component = {"operation_cost": {"variable": {"fuel_cost": None}}}
    with pytest.raises(AssertionError):
        apply_operation_table_data(component)

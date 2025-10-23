"""Tests for PLEXOS to Sienna validation."""

import pytest
from r2x_plexos.models import PLEXOSBattery, PLEXOSGenerator

from r2x.translations.plexos_to_sienna.validation import validate_input
from r2x_core import System


@pytest.fixture
def empty_system():
    return System(name="empty_test")


@pytest.fixture
def system_with_generators():
    system = System(name="gen_test")
    gen1 = PLEXOSGenerator(name="Coal_Gen", category="Coal")
    gen2 = PLEXOSGenerator(name="Gas_Gen", category="Gas")
    gen3 = PLEXOSGenerator(name="Unknown_Gen", category="UnknownCategory")
    gen4 = PLEXOSGenerator(name="No_Category_Gen", category=None)

    system.add_component(gen1)
    system.add_component(gen2)
    system.add_component(gen3)
    system.add_component(gen4)

    return system


@pytest.fixture
def system_with_batteries():
    system = System(name="battery_test")
    battery = PLEXOSBattery(name="Battery1")
    system.add_component(battery)
    return system


def test_validate_empty_system(empty_system):
    result = validate_input(empty_system)

    assert result.is_ok()
    report = result.unwrap()
    assert report.has_errors
    assert "no components" in report.summary().lower()


def test_validate_system_no_name():
    system = System(name="")
    gen = PLEXOSGenerator(name="Gen1", category="Coal")
    system.add_component(gen)

    result = validate_input(system)

    assert result.is_ok()
    report = result.unwrap()
    assert report.has_warnings
    assert "no name" in report.summary().lower()


def test_validate_generators_with_unknown_category(system_with_generators):
    result = validate_input(system_with_generators)

    assert result.is_ok()
    report = result.unwrap()
    assert report.has_errors
    summary = report.summary()
    assert "UnknownCategory" in summary or "unknown" in summary.lower()


def test_validate_generator_missing_category(system_with_generators):
    result = validate_input(system_with_generators)

    assert result.is_ok()
    report = result.unwrap()
    assert report.has_errors
    summary = report.summary()
    assert "missing category" in summary.lower() or "No_Category_Gen" in summary


def test_validate_generators_suggest_closest_match(system_with_generators):
    result = validate_input(system_with_generators)

    assert result.is_ok()
    report = result.unwrap()
    summary = report.summary()
    assert "error" in summary.lower()


def test_validate_batteries(system_with_batteries):
    result = validate_input(system_with_batteries)

    assert result.is_ok()
    report = result.unwrap()
    assert not report.has_errors


def test_validate_from_file_path(tmp_path):
    system = System(name="test")
    gen = PLEXOSGenerator(name="Gen1", category="Coal")
    system.add_component(gen)

    file_path = tmp_path / "system.json"
    system.to_json(file_path)

    result = validate_input(str(file_path))

    assert result.is_ok()
    report = result.unwrap()
    assert not report.has_errors


def test_validate_system_with_valid_generators():
    from r2x.translations.plexos_to_sienna.mappings import initialize_all_mappings

    initialize_all_mappings()

    system = System(name="valid_test")
    gen1 = PLEXOSGenerator(name="Coal_Gen", category="Coal")
    gen2 = PLEXOSGenerator(name="Gas_Gen", category="Gas")
    system.add_component(gen1)
    system.add_component(gen2)

    result = validate_input(system)

    assert result.is_ok()
    report = result.unwrap()
    assert not report.has_errors


def test_validate_multiple_errors():
    system = System(name="")
    gen1 = PLEXOSGenerator(name="Bad1", category="Unknown1")
    gen2 = PLEXOSGenerator(name="Bad2", category="Unknown2")
    gen3 = PLEXOSGenerator(name="Bad3", category=None)
    system.add_component(gen1)
    system.add_component(gen2)
    system.add_component(gen3)

    result = validate_input(system)

    assert result.is_ok()
    report = result.unwrap()
    assert report.has_errors
    assert len(report.errors) >= 3


def test_validation_report_to_dict():
    system = System(name="test")
    gen = PLEXOSGenerator(name="Gen1", category="UnknownCat")
    system.add_component(gen)

    result = validate_input(system)
    assert result.is_ok()

    report = result.unwrap()
    report_dict = report.to_dict()

    assert "errors" in report_dict
    assert "warnings" in report_dict
    assert "has_errors" in report_dict
    assert report_dict["has_errors"] is True

import json
from importlib.resources import files
from pathlib import Path

from infrasys.time_series_manager import TimeSeriesManager
from infrasys.time_series_models import TimeSeriesStorageType
from infrasys.utils.sqlite import create_in_memory_db
from r2x_plexos import PLEXOSConfig
from r2x_plexos.exporter import PLEXOSExporter
from r2x_sienna.config import SiennaConfig
from r2x_sienna.parser import SiennaParser
from r2x_sienna.upgrader.data_upgrader import SiennaUpgrader
from r2x_sienna.upgrader.upgrade_steps import *  # noqa: F403

from r2x_core import Rule, System, TranslationContext, apply_rules_to_context
from r2x_core.store import DataStore
from r2x_core.upgrader_utils import run_upgrade_step
from r2x_sienna_to_plexos import SiennaToPlexosConfig
from r2x_sienna_to_plexos.getters_utils import (
    ensure_battery_node_memberships,
    ensure_generator_node_memberships,
    ensure_head_storage_generator_membership,
    ensure_interface_line_memberships,
    ensure_node_zone_memberships,
    ensure_region_node_memberships,
    ensure_reserve_battery_memberships,
    ensure_reserve_generator_memberships,
    ensure_tail_storage_generator_membership,
    ensure_transformer_node_memberships,
)


class SiennaToPlexosTranslation:
    def __init__(
        self,
        sienna_file: str,
        output_folder: str,
        case_name: str,
        model_year: int = 2029,
        scenario: str = "Base",
        system_base_power: float = 100.0,
        skip_validation: bool = False,
        exclude_defaults: bool = True,
    ):
        """
        Initialize the Sienna to PLEXOS translation.

        Args:
            sienna_file: Path to the Sienna system JSON file
            output_folder: Path to the directory where output files will be saved
            case_name: Name of the case (used for output file naming)
            model_year: Model year for the Sienna system (default: 2029)
            scenario: Scenario name (default: "Base")
            system_base_power: System base power in MVA (default: 100.0)
            skip_validation: Skip validation during parsing (default: False)
            exclude_defaults: Exclude default values in PLEXOS export (default: True)
        """
        self.sienna_file = sienna_file
        self.output_folder = output_folder
        self.case_name = case_name
        self.model_year = model_year
        self.scenario = scenario
        self.system_base_power = system_base_power
        self.skip_validation = skip_validation
        self.exclude_defaults = exclude_defaults

    def run_sienna_upgrader(self, sienna_data: dict):
        """Run the Sienna upgrader on the provided data."""
        upgrader = SiennaUpgrader(path=self.sienna_file)

        for step in upgrader.list_steps():
            run_upgrade_step(step, data=sienna_data)

    def run(self, run_upgrader: bool = False):
        """
        Execute the Sienna to PLEXOS translation.

        Args:
            run_upgrader: Whether to run the Sienna upgrader before parsing (default: False)
        """
        with open(self.sienna_file) as f:
            sienna_data = json.load(f)

        if run_upgrader:
            self.run_sienna_upgrader(sienna_data)

        config = SiennaConfig(
            model_year=self.model_year,
            system_name=self.case_name,
            json_path=self.sienna_file,
            scenario=self.scenario,
            system_base_power=self.system_base_power,
            skip_validation=self.skip_validation,
        )
        data_store = DataStore()
        parser = SiennaParser(
            config=config,
            data_store=data_store,
            name=self.case_name,
            skip_validation=self.skip_validation,
        )
        stdin_payload = json.dumps(sienna_data)
        sienna_sys = parser.build_system(stdin_payload=stdin_payload)

        tmp_dir = Path(self.output_folder) / f"{self.case_name}_tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)

        sienna_sys.convert_storage(
            time_series_directory=tmp_dir,
            time_series_storage_type=TimeSeriesStorageType.ARROW,
            permanent=True,
        )

        connection = create_in_memory_db()
        ts_manager = TimeSeriesManager(
            connection,
            time_series_directory=tmp_dir,
            time_series_storage_type=TimeSeriesStorageType.ARROW,
            permanent=True,
        )

        rules_path = files("r2x_sienna_to_plexos.config") / "rules.json"
        rules_data = json.loads(rules_path.read_text())
        rules = Rule.from_records(rules_data)

        plexos_sys = System(
            name="PLEXOS",
            auto_add_composed_components=True,
            time_series_manager=ts_manager,
        )
        context = TranslationContext(
            source_system=sienna_sys,
            target_system=plexos_sys,
            config=SiennaToPlexosConfig(),
            rules=rules,
        )

        apply_rules_to_context(context)

        ensure_region_node_memberships(context)
        ensure_generator_node_memberships(context)
        ensure_battery_node_memberships(context)
        ensure_node_zone_memberships(context)
        ensure_reserve_battery_memberships(context)
        ensure_reserve_generator_memberships(context)
        ensure_transformer_node_memberships(context)
        ensure_interface_line_memberships(context)
        ensure_head_storage_generator_membership(context)
        ensure_tail_storage_generator_membership(context)

        plexos_config = PLEXOSConfig(model_name=f"{self.case_name}_ToPLEXOS")
        output_path = Path(self.output_folder) / f"{self.case_name}_results"
        output_path.mkdir(parents=True, exist_ok=True)

        exporter = PLEXOSExporter(
            plexos_config,
            plexos_sys,
            output_path=str(output_path),
            exclude_defaults=self.exclude_defaults,
        )

        plexos_exported_sys = exporter.export()

        return plexos_exported_sys

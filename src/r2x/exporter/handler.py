"""Exporter base class."""

import string
from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import infrasys
import numpy as np
import pandas as pd
from infrasys import Component, SingleTimeSeries
from infrasys.time_series_models import TimeSeriesData
from loguru import logger
from numpy.typing import NDArray
from pint import Quantity

from r2x.api import System
from r2x.config_scenario import Scenario
from r2x.config_models import get_year
from r2x.exporter.utils import modify_components
from r2x.parser.handler import file_handler

OUTPUT_FNAME = "{self.weather_year}"


class BaseExporter(ABC):
    """Class that defines the shared methods of parsers.

    Note
    ----
    This class is meant to be use for developing new parsers. Do not use it directly.

    Attributes
    ----------
    config:
        Scenario configuration
    system:
        System class
    output_foder:
        output folder path

    Methods
    -------
    run()
        Sequentially run methods from the exporter
    get_data(key='load')
        Return the parsed data for load.
    read_file(fpath="load.csv")
        Read load data.
    export_data_files(time_series_folder="Data")
        Save time series data files.
    """

    def __init__(
        self, config: Scenario, system: System, output_folder: Path, ts_directory: str = "Data"
    ) -> None:
        self.config = config
        self.system = system
        self.output_folder = output_folder
        self.input_model = config.input_model
        self.ts_directory = Path(ts_directory)
        self.time_series_objects: dict[str, list[Any]] = defaultdict(list)
        self.time_series_name_by_type: dict[str, list[Any]] = defaultdict(list)
        self._handle_data_folder(config.output_folder, self.ts_directory)

    def _handle_data_folder(self, output_folder: str | Path, folder_name: str | Path) -> None:
        fpath = Path(output_folder) / folder_name
        if not fpath.exists():
            fpath.mkdir()
        return

    @abstractmethod
    def run(self, *args, **kwargs) -> "BaseExporter":
        """Run the exporter methods in sequence.

        This methods needs to be implemented by any exporter and it's content
        change based on the order the data is being exported.
        """

    def read_file(self, fpath: Path | str, filter_func: list[Callable] | None = None, **kwargs):
        """Read input model data from the file system.

        Currently supported formats:
            - .csv
            - .h5
        More to come!

        Parameters
        ----------
        fpath: Path, str
            Absolute location of the file in the system
        filter_func: List
            Filter functions to apply

        """
        data = file_handler(fpath, **kwargs)
        if data is None:
            return

        if isinstance(filter_func, list):
            for func in filter_func:
                data = func(data, **kwargs)
        return data

    def export_data_files(self, year: int, time_series_folder: str = "Data") -> None:
        """Export all time series objects attached to components.

        This method assumes that `self.config.weather_year and `self.output_folder` exist.

        Parameters
        ----------
        time_series_folder: str
            Folder name to save time series data
        """
        assert year is not None
        config_dict = self.config.__dict__
        config_dict["year"] = year
        for component in self.system.iter_all_components():
            if self.system.has_time_series(component):
                for ts_metadata in self.system.time_series.list_time_series_metadata(component):
                    ts_component_name = f"{component.__class__.__name__}_{ts_metadata.name}"
                    try:
                        self.time_series_objects[ts_component_name].append(
                            self.system.get_time_series(component, name=ts_metadata.name)
                        )
                    except:  # noqa: E722
                        continue
                    self.time_series_name_by_type[ts_component_name].append(component.name)

        component_lengths = {
            component_type: {ts.length}
            for component_type, time_series in self.time_series_objects.items()
            for ts in time_series
        }

        inconsistent_lengths = [
            (component_type, length_set)
            for component_type, length_set in component_lengths.items()
            if len(length_set) != 1
        ]
        if inconsistent_lengths:
            raise ValueError(f"Multiple lengths found for components time series: {inconsistent_lengths}")

        datetime_arrays = {
            component_type: (
                np.datetime_as_string(
                    pd.date_range(
                        start=f"1/1/{year}",
                        periods=ts.length,
                        freq=f"{int(ts.resolution.total_seconds() / 60)}min",  # Convert resolution to minutes
                    ),
                    unit="m",
                ),
                time_series,
            )
            for component_type, time_series in self.time_series_objects.items()
            for ts in time_series
        }
        csv_fpath = self.output_folder / time_series_folder

        # Use string substitution to dynamically change the output csv fnames
        csv_fname = config_dict.get("time_series_fname", "${component_type}_${name}_${year}.csv")
        logger.trace("Using {} as time_series name", csv_fname)
        string_template = string.Template(csv_fname)

        for component_type, (datetime_array, time_series) in datetime_arrays.items():
            time_series_arrays = list(
                map(lambda x: x.data.magnitude if isinstance(x.data, Quantity) else x.data, time_series)
            )
            config_dict["component_type"] = component_type
            csv_fname = string_template.safe_substitute(config_dict)
            csv_table = np.column_stack([datetime_array, *time_series_arrays])
            header = '"DateTime",' + ",".join(
                [f'"{name}"' for name in self.time_series_name_by_type[component_type]]
            )

            np.savetxt(
                csv_fpath / csv_fname,
                csv_table,
                header=header,
                delimiter=",",
                comments="",
                fmt="%s",
            )

        return

    @staticmethod
    def time_series_to_csv(
        config: Scenario,
        system: System,
        output_folder: str | Path | None = None,
        reference_year: int | None = None,
        time_series_folder: str = "Data",
        time_series_fname: str | None = None,
        time_series_type: type[SingleTimeSeries] = SingleTimeSeries,
        name: str | None = None,
        **user_attributes: str,
    ):
        """Export time series objects to CSV files.

        Parameters
        ----------
        config : Scenario
            The scenario configuration object containing output settings.
        system : System
            The system containing the components and time series data.
        output_folder : str | Path | None, optional
            The directory where CSV files should be saved (default is `config.output_folder`).
        reference_year : int | None, optional
            The reference year for time series generation (default is inferred from `config`).
        time_series_folder : Literal["Data"], optional
            Subfolder for storing time series files (default is "Data").
        time_series_fname : Literal["${component_type}_${name}_${year}.csv"] | None, optional
            Filename pattern for output CSV files (default is "${component_type}_${name}_${year}.csv").
        **user_attributes : str
            Additional filtering attributes for selecting time series data.

        See Also
        --------
        create_time_series_arrays
        check_time_series_length_consistency
        """
        logger.info("Exporting time series objects to csv.")
        output_folder = output_folder or config.output_folder
        assert output_folder is not None
        if isinstance(output_folder, str):
            output_folder = Path(output_folder)

        if not reference_year:
            assert config.output_config is not None
            reference_year = get_year(config.output_config)
        assert reference_year is not None

        time_series_fname = time_series_fname or "${component_type}_${name}_${year}.csv"

        time_series_list: defaultdict[str, list[TimeSeriesData]] = defaultdict(list)
        time_series_headers = defaultdict(list)
        for component in system.get_components(
            Component,
            filter_func=lambda x: system.has_time_series(
                x,
                time_series_type=time_series_type,
                name=name,
                **user_attributes,
            ),
        ):
            for ts_metadata in system.time_series.list_time_series_metadata(
                component, time_series_type=time_series_type, name=name, **user_attributes
            ):
                ts_component_name = f"{component.__class__.__name__}_{ts_metadata.name}"
                time_series_headers[ts_component_name].append(component.name)
                time_series_list[ts_component_name].append(
                    system._time_series_mgr._get_by_metadata(ts_metadata)
                )

        if check_time_series_length_consistency(time_series_list):
            msg = "Multiple lengths not supported for the same component type."
            raise NotImplementedError(msg)

        time_series_arrays = create_time_series_arrays(reference_year, time_series_list)

        # Use string substitution to dynamically change the output csv fnames
        string_template = string.Template(time_series_fname)
        logger.trace("Using {} as time_series name", time_series_fname)
        output_csv_fpath = output_folder / time_series_folder
        if not output_csv_fpath.exists():
            output_csv_fpath.mkdir(exist_ok=True)

        fname_substitution_dict = {"name": config.name, "year": reference_year}
        for component_type, (datetime_array, time_series) in time_series_arrays.items():
            time_series_arrays_no_pint = list(
                map(
                    lambda x: x.data.magnitude if isinstance(x.data, Quantity) else x.data,
                    time_series,
                )
            )
            fname_substitution_dict["component_type"] = component_type
            csv_fname = string_template.safe_substitute(fname_substitution_dict)
            csv_table = np.column_stack([datetime_array, *time_series_arrays_no_pint])
            header = '"DateTime",' + ",".join([f'"{name}"' for name in time_series_headers[component_type]])

            np.savetxt(
                output_csv_fpath / csv_fname,
                csv_table,
                header=header,
                delimiter=",",
                comments="",
                fmt="%s",
            )
        return


def create_time_series_arrays(
    year: int,
    time_series_list: defaultdict[str, list[Any]],
    strftime_format: Literal["%Y-%m-%dT%H:%M"] = "%Y-%m-%dT%H:%M",
) -> dict[str, tuple[NDArray[np.str_], list[SingleTimeSeries]]]:
    """Generate time series arrays with formatted timestamps.

    Parameters
    ----------
    year : int
        The year for which the time series is generated.
    time_series_list : dict[str, list[SingleTimeSeries]]
        Dictionary mapping component types to lists of time series.
    strftime_format : Literal["%Y-%m-%dT%H:%M"], optional
        Format string for datetime conversion (default is ISO 8601).

    Returns
    -------
    dict[str, tuple[NDArray[np.str_], SingleTimeSeries]]
        Dictionary mapping component types to tuples containing formatted time arrays and time series data.

    Examples
    --------
    >>> from datetime import timedelta, datetime
    >>> import numpy as np
    >>> from infrasys import SingleTimeSeries
    >>> ts1 = SingleTimeSeries(
    ...     data=np.array([1.0, 2.0, 3.0]), resolution=timedelta(minutes=30), intial_time=datetime(2025, 1, 1)
    ... )
    >>> ts2 = SingleTimeSeries(
    ...     data=np.array([4.0, 5.0, 6.0]),
    ...     resolution=timedelta(minutes=30),
    ...     initial_time=datetime(2025, 1, 1),
    ... )
    >>> time_series_dict = {"solar": [ts1, ts2]}
    >>> create_time_series_arrays(2025, time_series_dict)
    {'solar': (array(['2025-01-01T00:00', '2025-01-01T00:30', '2025-01-01T01:00'], dtype='<U16'),
               <__main__.SingleTimeSeries object at ...>)}
    """
    return {
        component_type: (
            np.array(
                [
                    (
                        datetime(year, 1, 1) + timedelta(minutes=i * (ts.resolution.total_seconds() // 60))
                    ).strftime(strftime_format)
                    for i in range(ts.length)  # type: ignore
                ]
            ),
            time_series,
        )
        for component_type, time_series in time_series_list.items()
        for ts in time_series
    }


def check_time_series_length_consistency(time_series_dict: dict[str, list[Any]]) -> bool:
    """Check if all time series within each component type have consistent lengths.

    Parameters
    ----------
    time_series_dict : dict[str, list[SingleTimeSeries]]
        Dictionary mapping component types to lists of time series.

    Returns
    -------
    bool
        True if there is any inconsistency in lengths, False otherwise.

    Examples
    --------
    >>> from infrasys import SingleTimeSeries
    >>> ts1 = SingleTimeSeries.from_array(
    ...     data=np.array([1.0, 2.0, 3.0]),
    ...     resolution=timedelta(minutes=30),
    ...     initial_time=datetime(2025, 1, 1),
    ... )
    >>> ts2 = SingleTimeSeries.from_array(
    ...     data=np.array([4.0, 5.0]), resolution=timedelta(minutes=30), initial_time=datetime(2025, 1, 1)
    ... )
    >>> time_series_dict = {"solar": [ts1, ts2]}
    >>> check_time_series_length_consistency(time_series_dict)
    True

    >>> ts3 = SingleTimeSeries.from_array(
    ...     data=np.array([7.0, 8.0, 9.0]),
    ...     resolution=timedelta(minutes=30),
    ...     initial_time=datetime(2025, 1, 1),
    ... )
    >>> time_series_dict = {"solar": [ts1, ts3]}
    >>> check_time_series_length_consistency(time_series_dict)
    False
    """
    component_lengths = {
        component_type: {ts.length for ts in time_series}
        for component_type, time_series in time_series_dict.items()
    }
    return any(len(length_set) != 1 for length_set in component_lengths.values())


def get_export_records(component_list: list[dict[str, Any]], *update_funcs: Callable) -> list[dict[str, Any]]:
    """Apply update functions to a list of components and return the modified list.

    Parameters
    ----------
    component_list : list[dict[str, Any]]
        A list of dictionaries representing components to be updated.
    *update_funcs : Callable
        Variable number of update functions to be applied to each component.

    Returns
    -------
    list[dict[str, Any]]
        A list of updated component dictionaries.

    Examples
    --------
    >>> def update_name(component):
    ...     component["name"] = component["name"].upper()
    ...     return component
    >>> def add_prefix(component):
    ...     component["id"] = f"PREFIX_{component['id']}"
    ...     return component
    >>> components = [{"id": "001", "name": "Component A"}, {"id": "002", "name": "Component B"}]
    >>> updated_components = get_export_records(components, update_name, add_prefix)
    >>> updated_components
    [{'id': 'PREFIX_001', 'name': 'COMPONENT A'}, {'id': 'PREFIX_002', 'name': 'COMPONENT B'}]
    """
    update_functions = modify_components(*update_funcs)
    return [update_functions(component) for component in component_list]


def get_export_properties(component, *update_funcs: Callable) -> dict[str, Any]:
    """Apply update functions to a single component and return the modified component.

    Parameters
    ----------
    component : dict[str, Any]
        A dictionary representing a component to be updated.
    *update_funcs : Callable
        Variable number of update functions to be applied to the component.

    Returns
    -------
    dict[str, Any]
        The updated component dictionary.

    Examples
    --------
    >>> def update_status(component):
    ...     component["status"] = "active"
    ...     return component
    >>> def add_timestamp(component):
    ...     from datetime import datetime
    ...
    ...     component["last_updated"] = datetime.now().isoformat()
    ...     return component
    >>> component = {"id": "003", "name": "Component C"}
    >>> updated_component = get_export_properties(component, update_status, add_timestamp)
    >>> updated_component
    {'id': '003', 'name': 'Component C', 'status': 'active', 'last_updated': '2024-09-27T10:30'}
    """
    update_functions = modify_components(*update_funcs)
    return update_functions(component)


def get_exporter(
    config: Scenario,
    system: infrasys.system.System,
    exporter_class,
    filter_funcs: list[Callable] | None = None,
    **kwargs,
) -> BaseExporter:
    """Return exporter instance.


    Parameters
    ----------
    config
        Scenario configuration class
    system
        Infrasys system
    filter_func:
        Functions that will applied to read_data process

    Other Parameters
    ----------------
    kwargs
        year
            For filtering by solve year
        year_column
            To change the column to apply the filter
        column_mapping
            For renaming columns

    See Also
    --------
    BaseExporter
    pl_filter_year
    pl_lower_case
    pl_rename
    """
    logger.debug("Getting {} instance.", exporter_class.__name__)

    exporter: BaseExporter = exporter_class(
        config=config, system=system, output_folder=config.output_folder, **kwargs
    )

    # Functions relative to the parser.
    # NOTE: At some point we are going to migrate this out, but this sound like a good standard set
    # if filter_funcs is None:
    #     logger.trace("Using default filter functions")
    #     filter_funcs = [pl_lowercase, pl_rename, pl_filter_year]

    exporter.run(
        config=config,
        filter_func=filter_funcs,
        **{**config.input_config.__dict__, **kwargs},
    )

    return exporter

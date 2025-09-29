# Plugins

R2X provides a flexible plugin system that allows users to extend and customize the translation process between different models. Plugins can modify system data, add new components, or apply specific configurations during the translation workflow.

## Plugin Architecture

The plugin system in R2X is designed to be modular and extensible. Each plugin is a Python module that implements specific functions to interact with the translation process.

### Plugin Structure

A valid R2X plugin must implement at least one of the following functions:

- `cli_arguments(parser: ArgumentParser)`: Adds command-line arguments specific to the plugin
- `update_system(config: Scenario, system: System, parser: BaseParser, **kwargs) -> System`: Modifies the system during translation

### Plugin Discovery

Plugins are automatically discovered from the [`r2x.plugins`](src/r2x/plugins) package. The plugin system uses the [`valid_plugin_list`](src/r2x/plugins/utils.py) function to validate and load plugins.

```{eval-rst}
r2x.plugins.utils.valid_plugin_list
```

```{eval-rst}
r2x.plugins.utils.validate_plugin
```

## Available Plugins

### PCM Defaults

Augments the data model with Production Cost Model (PCM) defaults for generator parameters.

```{eval-rst}
r2x.plugins.pcm_defaults
```

### Break Generators

Disaggregates and aggregates generators based on capacity thresholds compared to WECC database standards.

```{eval-rst}
r2x.plugins.break_gens
```

### Emission Cap

Adds annual carbon emission constraints to the model, particularly useful for PLEXOS output models.

```{eval-rst}
r2x.plugins.emission_cap
```

### Hurdle Rate

Applies hurdle rates between transmission regions, modifying line impedances for ReEDS to PLEXOS translations.

```{eval-rst}
r2x.plugins.hurdle_rate
```

### CCS Credit

Implements Carbon Capture and Storage (CCS) incentives by calculating capture incentives and rates.

```{eval-rst}
r2x.plugins.ccs_credit
```

### Cambium Configuration

Applies Cambium-specific configurations including plant derating and fixed load assignments.

```{eval-rst}
r2x.plugins.cambium
```

### Imports

Creates time series representations for imports, currently processing Canadian imports from ReEDS.

```{eval-rst}
r2x.plugins.imports
```

### Electrolyzer

Handles electrolyzer-specific configurations and modeling requirements.

```{eval-rst}
r2x.plugins.electrolyzer
```

## Using Plugins

### Configuration File

Plugins can be specified in the configuration YAML file:

```yaml
input_model: reeds-US
output_model: plexos
solve_year: 2050
weather_year: 2012
plugins:
  - pcm_defaults
  - emission_cap
  - hurdle_rate
```

### Command Line Interface

Plugins can also be specified via the command line:

```console
r2x run --input-model reeds-US --output-model plexos --plugins pcm_defaults emission_cap hurdle_rate
```

### Plugin-Specific Arguments

Many plugins accept additional arguments that can be passed through the CLI:

```console
r2x -vv run -i <input_run_path> --input-model reeds-US --output-model plexos --plugins break_gens
```

```console
r2x -vv run -i <input_run_path>--input-model reeds-US --output-model plexos --plugins hurdle_rate
```

# Plugin Management System | R2X v2.0.0

Starting with R2X v2.0.0, a new plugin management system has been introduced that provides enhanced functionality and easier distribution of plugins through the `r2x-plugin` ecosystem.

### External Plugin Management

The new system allows plugins to be developed, distributed, and installed independently from the core R2X package using the [`r2x-plugin`](https://github.com/NREL/r2x-plugin) framework.

#### Key Features

- **Independent Development**: Plugins can be developed in separate repositories
- **Version Management**: Plugins can have their own versioning independent of R2X core
- **Easy Distribution**: Plugins can be distributed via PyPI or directly from Git repositories
- **Plugin Discovery**: Automatic discovery of installed external plugins
- **Dependency Management**: Plugins can specify their own dependencies

### Installing External Plugins

External plugins can be installed using pip:

```console
# Install from PyPI
pip install r2x-plugin-example

# Install from Git repository
pip install git+https://github.com/NREL/r2x-plugin.git

# Install specific version
pip install r2x-plugin-example==1.0.0
```

### Official NREL Plugins

- **[r2x-sienna](https://github.nrel.gov/PCM/r2x-sienna)**: Provides Sienna.jl exporter/parser functionality and enables Sienna to PLEXOS translation workflows.

- **[r2x-plexos](https://github.nrel.gov/PCM/r2x-plexos)**: Enhanced PLEXOS exporter/parser with additional functionality and PLEXOS to Sienna translation capabilities for comprehensive cross-platform model conversion.

- **[r2x-reeds](https://github.com/NREL/r2x-reeds)**: Optimized ReEDS data handling plugin that provides streamlined and efficient methods for processing ReEDS model outputs and inputs.

- **[r2x-ssc](https://github.nrel.gov/PCM/r2x-ssc)**: Solar and wind resource plugin that performs functionality similar to reV, enabling streamlined and efficient extraction of wind and solar resource data for power system modeling.

These specialized plugins extend R2X's capabilities for specific modeling frameworks and data processing workflows. Each plugin is maintained as a separate package and can be installed independently based on your modeling requirements.

For more information on developing and using external plugins, see the [r2x-plugin package](https://github.com/NREL/r2x-plugin).

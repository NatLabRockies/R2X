# R2X PLEXOS to Sienna Translator

This package provides translation capabilities from PLEXOS XML database files to Sienna PowerSystems format.

## Usage

### Basic Translation

```python
from r2x_plexos_to_sienna import PlexosToSiennaTranslation
from r2x_core.logger import setup_logging

# Advanced logging
# setup_logging(
#     level="DEBUG",
#     fmt="<green>{time:YYYY-MM-DD HH:mm:ss}</green> <level>{extra[short_level]:<4}</level> {message}",
#     log_file="debug.log"
# )

# Define input file
xml_path = "/path/to/xml"

# Step to extract desired model name (important to locate time series, otherwise sets a default)
#
db = PlexosDB.from_xml(xml_path)
model_names = db.list_objects_by_class(ClassEnum.Model)

# Create translator instance
translator = PlexosToSiennaTranslation(
    xml_path=xml_path,
    model_name=model_names[1] if model_names else "Base", # model_2012
)
# Run the translation
translator.run()
```

## Configuration

The translator uses configuration rules defined in `config/rules.json` to map PLEXOS objects to Sienna PowerSystems components.

## Output

The translation produces Sienna PowerSystems-compatible JSON files in the specified output directory.

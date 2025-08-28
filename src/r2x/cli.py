"""R2X CLI.

This scripts contains most of the logic on how we call different parts of R2X using the CLI.
"""

import sys
import traceback

from .cli_functions import base_cli
from .logger import setup_logging
from .runner import init, run, create_plugin_template
from .utils import read_user_dict


def cli() -> None:
    """CLI main entry point for R2X."""
    parser = base_cli()
    args, remaining_args = parser.parse_known_args()

    if "--help" in remaining_args or len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(0)

    args = parser.parse_args()

    cli_args = {k: v for k, v in vars(args).items() if v is not None}
    user_dict = cli_args.pop("user_config", None)
    setup_logging(verbosity=cli_args["verbose"])

    if user_dict is not None:
        user_dict = read_user_dict(user_dict)

    if cli_args.get("pdb"):
        import pdb

        try:
            pdb.run("cli_commands(cli_args, user_dict)", globals=globals(), locals=locals())
        except Exception:
            traceback.print_exc()
            pdb.post_mortem()
    else:
        cli_commands(cli_args, user_dict)
    return None


def cli_commands(cli_args: dict, user_dict: dict | None = None) -> None:
    """Run the different translation for a configuration.

    If the config object is Configuration class, we run all the different
    Scenarios in parallel using multiprocessing.

    Parameters
    ----------
    config
        Configuration

    Other Parameters
    ----------------
    kwargs
        arguments passed for convenience.
    """
    if cli_args["command"] == "run":
        run(cli_args, user_dict=user_dict)
    elif cli_args["command"] == "init":
        init(cli_args)
    elif cli_args["command"] == "plugin":

        plugin_name =cli_args.get("plugin_name",None)
        plugin_path = cli_args.get("plugin_path",None)

        if not plugin_name:
            msg = "Please provide a plugin name."
            raise(ValueError(msg))
        if not plugin_path:
            msg = "Please provide a plugin path."
            raise(ValueError(msg))

        create_plugin_template(plugin_name, plugin_path)
    else:
        raise NotImplementedError
    return

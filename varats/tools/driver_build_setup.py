"""
Driver module for `vara-buildsetup`.
"""

import typing as tp
import argparse
import os
import sys
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

from varats.gui.buildsetup_window import BuildSetup
from varats.settings import get_value_or_default, CFG, save_config
from varats.vara_manager import BuildType
from varats.tools.research_tools.vara import VaRA
from varats.utils.cli_util import initialize_logger_config
from varats.tools.research_tools.research_tool import (ResearchTool,
                                                       SpecificCodeBase)


class VaRATSSetup:
    """
    Start VaRA-TS grafical user interface for setting up VaRA.
    """

    def __init__(self) -> None:
        if hasattr(Qt, 'AA_EnableHighDpiScaling'):
            QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
            QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

        self.app = QApplication(sys.argv)
        self.main_window = BuildSetup()

    def main(self) -> None:
        """
        Start VaRA setup GUI
        """
        sys.exit(self.app.exec_())


def update_term(text: str, enable_inline: bool = False) -> None:
    """
    Print/Update terminal text with/without producing new lines.

    Args:
        text: output text that should be printed
        enable_inline: print lines without new lines
    """
    text = text.replace(os.linesep, '').strip()
    if not text:
        return
    if enable_inline:
        _, columns = os.popen('/bin/stty size', 'r').read().split()
        print(text, end=(int(columns) - len(text) - 1) * ' ' + '\r', flush=True)
    else:
        print(text)


def parse_string_to_build_type(build_type: str) -> BuildType:
    """
    Convert a string into a BuildType

    Args:
        build_type: VaRA build configuration

    Test:
    >>> parse_string_to_build_type("DBG")
    <BuildType.DBG: 1>

    >>> parse_string_to_build_type("PGO")
    <BuildType.PGO: 4>

    >>> parse_string_to_build_type("DEV")
    <BuildType.DEV: 2>

    >>> parse_string_to_build_type("random string")
    <BuildType.DEV: 2>

    >>> parse_string_to_build_type("oPt")
    <BuildType.OPT: 3>

    >>> parse_string_to_build_type("OPT")
    <BuildType.OPT: 3>

    >>> parse_string_to_build_type("DEV-SAN")
    <BuildType.DEV_SAN: 5>
    """
    build_type = build_type.upper()
    if build_type == "DBG":
        return BuildType.DBG
    if build_type == "DEV":
        return BuildType.DEV
    if build_type == "OPT":
        return BuildType.OPT
    if build_type == "PGO":
        return BuildType.PGO
    if build_type == "DEV-SAN":
        return BuildType.DEV_SAN

    return BuildType.DEV


def main() -> None:
    """
    Build VaRA on cli.
    """
    initialize_logger_config()
    parser = argparse.ArgumentParser("vara-buildsetup")

    parser.add_argument("-c",
                        "--config",
                        action="store_true",
                        default=False,
                        help="Only create a VaRA config file.")
    parser.add_argument("-i",
                        "--init",
                        action="store_true",
                        default=False,
                        help="Initializes VaRA and all components.")
    parser.add_argument("-u",
                        "--update",
                        action="store_true",
                        default=False,
                        help="Updates VaRA and all components.")
    parser.add_argument("-b",
                        "--build",
                        help="Builds VaRA and all components.",
                        action="store_true",
                        default=False)
    parser.add_argument(
        "--buildtype",
        default="dev",
        choices=['dev', 'opt', 'pgo', 'dbg', 'dev-san'],
        nargs="?",
        help="Build type to use for the tool build configuration.")
    parser.add_argument("researchtool",
                        help="The research tool one wants to setup",
                        choices=["VaRA", "vara"])
    parser.add_argument("sourcelocation",
                        help="Folder to store tool sources. (Optional)",
                        nargs='?',
                        default=None)
    parser.add_argument("installprefix",
                        default=None,
                        nargs='?',
                        help="Folder to install LLVM. (Optional)")
    parser.add_argument("--version",
                        default=None,
                        nargs="?",
                        help="Version to download.")

    args = parser.parse_args()

    if not (args.config or args.init or args.update or args.build):
        parser.error(
            "At least one argument of --config, --init, --update or --build " +
            "must be given.")

    if args.config:
        save_config()
        return

    if args.researchtool == "VaRA" or args.researchtool == "vara":
        tool = VaRA(__get_source_location(args.sourcelocation))

    if args.init:
        __build_setup_init(tool, args.sourcelocation, args.installprefix,
                           args.version)
    if args.update:
        tool.upgrade()
    if args.build:
        build_type = parse_string_to_build_type(args.buildtype)
        tool.build(build_type, __get_install_prefix(tool, args.installprefix))
        if tool.verify_install(__get_install_prefix(tool, args.installprefix)):
            print(f"{tool.name} was correctly installed.")
        else:
            print(f"Could not install {tool.name} correctly.")


def __build_setup_init(tool: ResearchTool[SpecificCodeBase],
                       raw_source_location: tp.Optional[str],
                       raw_install_prefix: tp.Optional[str],
                       version: tp.Optional[int]) -> None:

    tool.setup(__get_source_location(raw_source_location),
               install_prefix=__get_install_prefix(tool, raw_install_prefix),
               version=version)


def __get_source_location(raw_source_location: tp.Optional[str]) -> Path:
    if raw_source_location is None:
        src_folder = Path(
            get_value_or_default(CFG["vara"], "llvm_source_dir",
                                 str(os.getcwd()) + "/tools_src/"))
    else:
        src_folder = Path(raw_source_location)

    if not src_folder.exists():
        src_folder.mkdir(parents=True)

    return src_folder


def __get_install_prefix(tool: ResearchTool[SpecificCodeBase],
                         raw_install_prefix: tp.Optional[str]) -> Path:
    if raw_install_prefix is None:
        install_prefix = Path(
            get_value_or_default(CFG["vara"], "llvm_install_dir",
                                 str(os.getcwd()) + f"/tools/{tool.name}/"))
    else:
        install_prefix = Path(raw_install_prefix)

    if not install_prefix.exists():
        install_prefix.mkdir(parents=True)

    return install_prefix


if __name__ == '__main__':
    main()

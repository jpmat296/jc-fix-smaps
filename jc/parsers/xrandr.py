"""jc - JSON CLI output utility `xrandr` command output parser

Options supported:

Usage (module):

    import jc.parsers.xrandr
    result = jc.parsers.xrandr.parse(xrandr_command_output)

Schema:
    {
     "screens": [
      {
       "screen_number": 0,
       "minimum_width": 8,
       "minimum_height": 8,
       "current_width": 1920,
       "current_height": 1080,
       "maximum_width": 32767,
       "maximum_height": 32767,
       "associated_device": {
        "associated_modes": [
         {
          "resolution_width": 1920,
          "resolution_height": 1080,
          "is_high_resolution": false,
          "frequencies": [
           {
            "frequency": 60.03,
            "is_current": true,
            "is_preferred": true
           },
           {
            "frequency": 59.93,
            "is_current": false,
            "is_preferred": false
           }
          ]
         },
         {
          "resolution_width": 1680,
          "resolution_height": 1050,
          "is_high_resolution": false,
          "frequencies": [
           {
            "frequency": 59.88,
            "is_current": false,
            "is_preferred": false
           }
          ]
         }
        ],
        "is_connected": true,
        "is_primary": true,
        "device_name": "eDP1",
        "resolution_width": 1920,
        "resolution_height": 1080,
        "offset_width": 0,
        "offset_height": 0,
        "dimension_width": 310,
        "dimension_height": 170
       }
      }
     ],
     "unassociated_devices": []
    }
Translated from:
    Screen 0: minimum 8 x 8, current 1920 x 1080, maximum 32767 x 32767
    eDP1 connected primary 1920x1080+0+0 (normal left inverted right x axis y axis) 310mm x 170mm
       1920x1080     60.03*+  59.93
       1680x1050     59.88
Examples:

    $ xrandr | jc --xrandr
"""
import re
from typing import Dict, List, Iterator, Optional, Union

import jc.utils


class info:
    """Provides parser metadata (version, author, etc.)"""

    version = "1.9"
    description = "`xrandr` command parser"
    author = "Kevin Lyter"
    author_email = "lyter_git at sent.com"

    # compatible options: linux, darwin, cygwin, win32, aix, freebsd
    compatible = ["linux", "darwin", "cygwin", "aix", "freebsd"]
    magic_commands = ["xrandr"]


__version__ = info.version

# ScreenLine = Dict[str, int]
# DeviceLine = Dict[str, int | bool | str]
# ModeLine = Dict[str, int]

try:
    from typing import TypedDict

    Frequency = TypedDict(
        "Frequency",
        {
            "frequency": float,
            "is_current": bool,
            "is_preferred": bool,
        },
    )
    Mode = TypedDict(
        "Mode",
        {
            "resolution_width": int,
            "resolution_height": int,
            "is_high_resolution": bool,
            "frequencies": List[Frequency],
        },
    )
    Device = TypedDict(
        "Device",
        {
            "device_name": str,
            "is_connected": bool,
            "is_primary": bool,
            "resolution_width": int,
            "resolution_height": int,
            "offset_width": int,
            "offset_height": int,
            "dimension_width": int,
            "dimension_height": int,
            "associated_modes": List[Mode],
        },
    )
    Screen = TypedDict(
        "Screen",
        {
            "screen_number": int,
            "minimum_width": int,
            "minimum_height": int,
            "current_width": int,
            "current_height": int,
            "maximum_width": int,
            "maximum_height": int,
            "associated_device": Device,
        },
    )
    Response = TypedDict(
        "Response",
        {
            "screens": List[Screen],
            "unassociated_devices": List[Device],
        },
    )
except ImportError:
    Screen = Dict[str, int | str]
    Device = Dict[str, str | int | bool]
    Frequency = Dict[str, float | bool]
    Mode = Dict[str, int | bool | List[Frequency]]
    Response = Dict[str, Device | Mode | Screen]


def _process(proc_data):
    """
    Final processing to conform to the schema.

    Parameters:

        proc_data:   (List of Dictionaries) raw structured data to process

    Returns:

        List of Dictionaries. Structured data to conform to the schema.
    """
    for entry in proc_data:
        int_list = ["links", "size"]
        for key in entry:
            if key in int_list:
                entry[key] = jc.utils.convert_to_int(entry[key])

        if "date" in entry:
            # to speed up processing only try to convert the date if it's not the default format
            if not re.match(
                r"[a-zA-Z]{3}\s{1,2}\d{1,2}\s{1,2}[0-9:]{4,5}", entry["date"]
            ):
                ts = jc.utils.timestamp(entry["date"])
                entry["epoch"] = ts.naive
                entry["epoch_utc"] = ts.utc

    return proc_data


_screen_pattern = (
    r"Screen (?P<screen_number>\d+): "
    + "minimum (?P<minimum_width>\d+) x (?P<minimum_height>\d+), "
    + "current (?P<current_width>\d+) x (?P<current_height>\d+), "
    + "maximum (?P<maximum_width>\d+) x (?P<maximum_height>\d+)"
)


def _parse_screen(next_lines: List[str]) -> Optional[Screen]:
    next_line = next_lines.pop()
    result = re.match(_screen_pattern, next_line)
    if not result:
        next_lines.append(next_line)
        return None

    raw_matches = result.groupdict()
    screen: Screen = {}
    for k, v in raw_matches.items():
        screen[k] = int(v)

    if next_lines:
        device: Optional[Device] = _parse_device(next_lines)
        if device:
            screen["associated_device"] = device

    return screen


# eDP1 connected primary 1920x1080+0+0 (normal left inverted right x axis y axis)
#       310mm x 170mm
# regex101 demo link
# https://regex101.com/r/5ZQEDC/1
_device_pattern = (
    r"(?P<device_name>.+) "
    + "(?P<is_connected>(connected|disconnected)) ?"
    + "(?P<is_primary> primary)? ?"
    + "((?P<resolution_width>\d+)x(?P<resolution_height>\d+)"
    + "\+(?P<offset_width>\d+)\+(?P<offset_height>\d+))? "
    + "\(normal left inverted right x axis y axis\)"
    + "( ((?P<dimension_width>\d+)mm x (?P<dimension_height>\d+)mm)?)?"
)


def _parse_device(next_lines: List[str]) -> Optional[Device]:
    if not next_lines:
        return None

    next_line = next_lines.pop()
    result = re.match(_device_pattern, next_line)
    if not result:
        next_lines.append(next_line)
        return None

    matches = result.groupdict()

    device: Device = {
        "associated_modes": [],
        "is_connected": matches["is_connected"] == "connected",
        "is_primary": matches["is_primary"] is not None
        and len(matches["is_primary"]) > 0,
        "device_name": matches["device_name"],
    }
    for k, v in matches.items():
        if k not in {"is_connected", "is_primary", "device_name"}:
            try:
                if v:
                    device[k] = int(v)
            except ValueError:
                print(f"Error: {next_line} : {k} - {v} is not int-able")

    while next_lines:
        next_line = next_lines.pop()
        next_mode: Optional[Mode] = _parse_mode(next_line)
        if next_mode:
            device["associated_modes"].append(next_mode)
        else:
            next_lines.append(next_line)
            break
    return device


# 1920x1080i     60.03*+  59.93
# 1920x1080     60.00 +  50.00    59.94
_mode_pattern = r"\s*(?P<resolution_width>\d+)x(?P<resolution_height>\d+)(?P<is_high_resolution>i)?\s+(?P<rest>.*)"
_frequencies_pattern = r"(((?P<frequency>\d+\.\d+)(?P<star>\*| |)(?P<plus>\+?)?)+)"


def _parse_mode(line: str) -> Optional[Mode]:
    result = re.match(_mode_pattern, line)
    frequencies: List[Frequency] = []
    if not result:
        return None

    d = result.groupdict()
    resolution_width = int(d["resolution_width"])
    resolution_height = int(d["resolution_height"])
    is_high_resolution = d["is_high_resolution"] is not None

    mode: Mode = {
        "resolution_width": resolution_width,
        "resolution_height": resolution_height,
        "is_high_resolution": is_high_resolution,
        "frequencies": frequencies,
    }

    result = re.finditer(_frequencies_pattern, d["rest"])
    if not result:
        return mode

    for match in result:
        d = match.groupdict()
        frequency = float(d["frequency"])
        is_current = len(d["star"]) > 0
        is_preferred = len(d["plus"]) > 0
        f: Frequency = {
            "frequency": frequency,
            "is_current": is_current,
            "is_preferred": is_preferred,
        }
        mode["frequencies"].append(f)
    return mode


def parse(data: str, raw=False, quiet=False):
    """
    Main text parsing function

    Parameters:

        data:        (string)  text data to parse
        raw:         (boolean) output preprocessed JSON if True
        quiet:       (boolean) suppress warning messages if True

    Returns:

        List of Dictionaries. Raw or processed structured data.
    """
    if not quiet:
        jc.utils.compatibility(__name__, info.compatible)

    warned = False
    parent = ""
    next_is_parent = False
    new_section = False

    linedata = data.splitlines()
    linedata.reverse()  # For popping

    result: Response = {"screens": [], "unassociated_devices": []}
    if jc.utils.has_data(data):
        result: Response = {"screens": [], "unassociated_devices": []}
        while linedata:
            screen = _parse_screen(linedata)
            if screen:
                result["screens"].append(screen)
            else:
                device = _parse_device(linedata)
                if device:
                    result["unassociated_devices"].append(device)
    return result

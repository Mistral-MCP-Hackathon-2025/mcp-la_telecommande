"""OS information helpers.

Parsing and heuristics used by diagnostic tools to identify distro and pkg manager.
"""

from __future__ import annotations

import re


def parse_os_release(text: str) -> dict[str, str | None]:
    """Parse /etc/os-release content into a small dict.

    Extract common fields and strip optional quotes.
    """
    fields = {k: None for k in ("ID", "VERSION_ID", "NAME", "PRETTY_NAME")}
    line_re = re.compile(r"^([A-Z_]+)=(.*)$")
    for line in text.splitlines():
        m = line_re.match(line.strip())
        if not m:
            continue
        k, v = m.group(1), m.group(2)
        if k not in fields:
            continue
        # Remove optional surrounding quotes
        if len(v) >= 2 and ((v[0] == v[-1] == '"') or (v[0] == v[-1] == "'")):
            v = v[1:-1]
        fields[k] = v
    return {
        "id": fields["ID"],
        "version_id": fields["VERSION_ID"],
        "name": fields["NAME"],
        "pretty_name": fields["PRETTY_NAME"],
    }


def detect_pkg_manager(out_which: str) -> str | None:
    """Given a combined output of several `command -v` checks, infer a package manager."""
    for mgr in ("apt", "dnf", "yum", "zypper", "pacman", "apk"):
        if re.search(rf"\b{mgr}\b", out_which):
            return mgr
    return None

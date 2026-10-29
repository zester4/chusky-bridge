"""chusky-bridge command line tools.

chusky-bridge validate <dir>         validate every manifest under a directory (exit 1 on any error)
chusky-bridge catalog search <text>  search the system catalog
chusky-bridge check-config           verify required server configuration
chusky-bridge version
"""

import argparse
import json
import sys
from pathlib import Path

from chusky_bridge import __version__
from chusky_bridge.catalog import search_catalog
from chusky_bridge.connectors import validate_manifest_operations
from chusky_bridge.connectors.base import ConnectorError
from chusky_bridge.mcp.manifest import ManifestError, parse_manifest
from chusky_bridge.services import check_manifest


def validate_directory(directory: Path) -> int:
    paths = sorted(directory.rglob("*.yaml"))
    if not paths:
        print(f"no manifests found under {directory}")
        return 1
    failures = 0
    for path in paths:
        try:
            parsed = parse_manifest(path.read_text(encoding="utf-8"))
            if parsed.manifest.connector.status == "template":
                validate_manifest_operations(parsed.manifest)
                print(f"TEMPLATE  {path}  (valid; activate after discovery)")
                continue
            check_manifest(parsed)
            print(f"OK        {path}  ({parsed.manifest.connector.type}, {len(parsed.manifest.operations)} ops)")
        except (ManifestError, ConnectorError) as exc:
            failures += 1
            print(f"ERROR     {path}  {exc}")
    return 1 if failures else 0


def check_config() -> int:
    from chusky_bridge.config import require_server_config

    try:
        require_server_config()
    except RuntimeError as exc:
        print(f"ERROR  {exc}")
        return 1
    print("OK     configuration is complete")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="chusky-bridge", description="Chusky Bridge tools")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="validate manifests under a directory")
    validate.add_argument("directory", type=Path)

    catalog = sub.add_parser("catalog", help="search the system catalog")
    catalog_sub = catalog.add_subparsers(dest="catalog_command", required=True)
    search = catalog_sub.add_parser("search", help="search by name, vendor, category, or notes")
    search.add_argument("query", nargs="?", default="")
    search.add_argument("--json", action="store_true", help="print JSON")

    sub.add_parser("check-config", help="verify required server configuration")
    sub.add_parser("version", help="print the version")

    args = parser.parse_args(argv)
    if args.command == "validate":
        return validate_directory(args.directory)
    if args.command == "catalog":
        rows = search_catalog(q=args.query)
        if args.json:
            print(json.dumps(rows, indent=2))
        else:
            for row in rows:
                print(f"{row['name']:<48} {row['adapter']:<14} {row['adapter_status']}")
            print(f"{len(rows)} result(s)")
        return 0
    if args.command == "check-config":
        return check_config()
    if args.command == "version":
        print(__version__)
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())

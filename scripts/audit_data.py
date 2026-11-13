"""Audit the knowledge base before building an index."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

from app.rag.audit import audit_documents, write_audit_report  # noqa: E402


def _display(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="dokumen", help="Folder dokumen sumber")
    parser.add_argument("--out", default="data/audit", help="Folder output laporan")
    parser.add_argument(
        "--fail-on-warnings",
        action="store_true",
        help="Keluar dengan kode 1 jika ada warning",
    )
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    root = (ROOT / args.root).resolve() if not Path(args.root).is_absolute() else Path(args.root)
    out = (ROOT / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)

    result = audit_documents(root)
    json_path, markdown_path = write_audit_report(result, out)

    stats = result.stats
    print("Audit knowledge base")
    print(f"  Dokumen       : {stats['total_documents']}")
    print(f"  Aktif         : {stats['active_documents']}")
    print(f"  Status        : {stats['by_status']}")
    print(f"  Kategori aktif: {stats['active_by_category']}")
    print(f"  Kategori semua: {stats['by_category']}")
    print(f"  Error         : {stats['error_count']}")
    print(f"  Warning       : {stats['warning_count']}")
    print(f"  Laporan JSON  : {_display(json_path)}")
    print(f"  Laporan MD    : {_display(markdown_path)}")

    for issue in result.errors:
        print(f"  ERROR   [{issue.code}] {issue.source_path or '-'}: {issue.message}")
    for issue in result.warnings:
        print(f"  WARNING [{issue.code}] {issue.source_path or '-'}: {issue.message}")

    if result.has_errors():
        return 1
    if args.fail_on_warnings and result.warnings:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

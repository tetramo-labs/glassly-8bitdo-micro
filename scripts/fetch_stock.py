"""Download only the pinned stock package. No device access or updater execution."""
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def main():
    source = json.loads((ROOT / "sources.lock.json").read_text())["stock"]
    dest = ROOT / source["path"]
    if dest.exists():
        data = dest.read_bytes()
    else:
        with urllib.request.urlopen(source["url"], timeout=30) as response:
            data = response.read(source["size"] + 1)
    if len(data) != source["size"] or hashlib.sha256(data).hexdigest() != source["sha256"]:
        raise SystemExit("Stock SHA256/size mismatch; nothing written")
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("xb") as out:
            out.write(data)
    print(f"Verified {dest}")
    if not source["catalog_md5_matches"]:
        print("Vendor catalog MD5 differs from downloaded bytes; see docs/findings.md.")


if __name__ == "__main__":
    main()

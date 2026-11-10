# SPDX-License-Identifier: MIT
"""Download VIIRS VNP46A2 (or another VNP46 product) granules over Ghana for one year.

Granule links come from NASA's public CMR catalogue; the files come from LAADS
DAAC with the Earthdata bearer token in EARTHDATA_TOKEN (source `.env`).
Existing files at the listed size are skipped. Ghana's box (-3.3, 4.7, 1.2, 11.2)
spans tiles h17-h18 x v07-v08.

Usage: viirs_vnp46_ghana.py OUT_DIR YEAR [SHORT_NAME [TILE]]  (TILE like h17v08 keeps one tile)
"""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

CMR = "https://cmr.earthdata.nasa.gov/search/granules.json"
BOX = "-3.3,4.7,1.2,11.2"


def _list(short: str, year: int) -> list[tuple[str, float]]:
	out: list[tuple[str, float]] = []
	page = 1
	while True:
		q = {
			"short_name": short,
			"bounding_box": BOX,
			"temporal": f"{year}-01-01T00:00:00Z,{year}-12-31T23:59:59Z",
			"page_size": 500,
			"page_num": page,
		}
		entries = json.load(urllib.request.urlopen(f"{CMR}?{urllib.parse.urlencode(q)}", timeout=60))["feed"]["entry"]
		if not entries:
			return out
		for e in entries:
			url = next(l["href"] for l in e["links"] if l["href"].startswith("https") and l["href"].endswith(".h5"))
			out.append((url, float(e["granule_size"])))
		page += 1


def _fetch(args: tuple[str, Path, str]) -> int:
	url, dest, token = args
	if dest.exists() and dest.stat().st_size > 1_000_000:
		return 0
	tmp = dest.with_suffix(".part")
	for _ in range(4):
		try:
			req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
			with urllib.request.urlopen(req, timeout=180) as r, open(tmp, "wb") as f:
				while chunk := r.read(1 << 20):
					f.write(chunk)
			with open(tmp, "rb") as f:
				assert f.read(8) == b"\x89HDF\r\n\x1a\n", f"{url}: not an HDF5 file"
			tmp.replace(dest)
			return dest.stat().st_size
		except Exception:
			continue
	raise RuntimeError(f"failed after 4 attempts: {url}")


def main(argv: list[str]) -> int:
	out, year = Path(argv[0]), int(argv[1])
	short = argv[2] if len(argv) > 2 else "VNP46A2"
	tile = argv[3] if len(argv) > 3 else ""
	token = os.environ.get("EARTHDATA_TOKEN", "")
	assert token, "EARTHDATA_TOKEN is not set; source .env first"
	out.mkdir(parents=True, exist_ok=True)
	granules = [g for g in _list(short, year) if tile in g[0]]
	print(f"{len(granules)} granules, ~{sum(s for _, s in granules) / 1e3:.1f} GB", flush=True)
	jobs = [(u, out / u.rsplit("/", 1)[1], token) for u, _ in granules]
	done = 0
	with ThreadPoolExecutor(8) as pool:
		for i, n in enumerate(pool.map(_fetch, jobs), 1):
			done += n
			if i % 100 == 0:
				print(f"{i}/{len(jobs)} {done / 1e9:.2f} GB", flush=True)
	print(f"done: {len(jobs)} granules", flush=True)
	return 0


if __name__ == "__main__":
	sys.exit(main(sys.argv[1:]))

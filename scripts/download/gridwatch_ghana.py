# SPDX-License-Identifier: MIT
"""Mirror nLine's public GridWatch Ghana parquet partitions for a year range.

The bucket `nline-public-data` is anonymous-readable; nLine's client only checks
an API key against nline.io before reading it. This validates `NLINE_API_KEY`
from the environment the same way, then mirrors `ghana/gridwatch_data/parquet/`
day partitions for the requested years, skipping files already present at the
listed size. 2019-2023 is the span `12-quality.md` §5 names for viirs_detection.

Usage: gridwatch_ghana.py OUT_DIR [FIRST_YEAR LAST_YEAR]
"""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BUCKET = "nline-public-data"
PREFIX = "ghana/gridwatch_data/parquet/"
API = "https://nline.io/api/public-data"


def _validate(key: str) -> None:
	req = urllib.request.Request(
		API, json.dumps({"action": "validate", "apiKey": key}).encode(), {"content-type": "application/json"}
	)
	assert json.load(urllib.request.urlopen(req, timeout=30)).get("valid") is True, "nLine key not valid"


def _list() -> list[tuple[str, int]]:
	out: list[tuple[str, int]] = []
	token = None
	while True:
		q = {"prefix": PREFIX, "maxResults": 1000, "fields": "nextPageToken,items(name,size)"}
		if token:
			q["pageToken"] = token
		url = f"https://storage.googleapis.com/storage/v1/b/{BUCKET}/o?{urllib.parse.urlencode(q)}"
		page = json.load(urllib.request.urlopen(url, timeout=60))
		out += [(i["name"], int(i["size"])) for i in page.get("items", [])]
		token = page.get("nextPageToken")
		if not token:
			return out


def _fetch(args: tuple[str, int, Path]) -> int:
	name, size, dest = args
	if dest.exists() and dest.stat().st_size == size:
		return 0
	dest.parent.mkdir(parents=True, exist_ok=True)
	url = f"https://storage.googleapis.com/{BUCKET}/{urllib.parse.quote(name)}"
	tmp = dest.with_suffix(dest.suffix + ".part")
	for _ in range(4):
		try:
			with urllib.request.urlopen(url, timeout=120) as r, open(tmp, "wb") as f:
				while chunk := r.read(1 << 20):
					f.write(chunk)
			assert tmp.stat().st_size == size, f"{name}: got {tmp.stat().st_size}, listed {size}"
			tmp.replace(dest)
			return size
		except Exception:
			continue
	raise RuntimeError(f"failed after 4 attempts: {name}")


def main(argv: list[str]) -> int:
	out = Path(argv[0])
	first, last = (int(argv[1]), int(argv[2])) if len(argv) >= 3 else (2019, 2023)
	key = os.environ.get("NLINE_API_KEY", "")
	assert key, "NLINE_API_KEY is not set; source .env first"
	_validate(key)
	todo = []
	for name, size in _list():
		if "day=" not in name or not name.endswith(".parquet"):
			continue
		year = int(name.split("day=")[1][:4])
		if first <= year <= last:
			todo.append((name, size, out / name.removeprefix(PREFIX)))
	print(f"{len(todo)} files, {sum(s for _, s, _ in todo) / 1e9:.2f} GB for {first}-{last}", flush=True)
	done = 0
	with ThreadPoolExecutor(16) as pool:
		for i, n in enumerate(pool.map(_fetch, todo), 1):
			done += n
			if i % 500 == 0:
				print(f"{i}/{len(todo)} {done / 1e9:.2f} GB", flush=True)
	print(f"done: {len(todo)} files", flush=True)
	return 0


if __name__ == "__main__":
	sys.exit(main(sys.argv[1:]))

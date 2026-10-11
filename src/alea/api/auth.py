# SPDX-License-Identifier: MIT
"""API keys, tiers and the authentication dependency.

Three decisions here, each of which the specification gets wrong and each of
which is expensive to reverse.

**Keys are hashed at rest.** The specification's ``VALID_KEYS`` is a list of
plaintext keys -- a credential leak waiting to happen, and one that survives in
every backup and every ``pg_dump``. Here a key is minted, its secret hashed with
scrypt, and the plaintext returned exactly once. Nothing can recover it; a lost
key is revoked and reissued.

**A presented key carries its own lookup id.** ``alea_<key_id>_<secret>``. The
id selects the row and the secret is verified against that row's hash, so
authentication is one indexed lookup plus one scrypt -- not a scan over every
stored key, and not a deterministic hash of the secret sitting in the table for
an offline cracker to grind against.

**Revocation is a state, not a deletion.** A revoked key keeps its row, so a
request against a revoked key is distinguishable from one against a key that
never existed. Collapsing the two makes "my key stopped working" unanswerable:
the operator cannot tell a revoked credential from a typo, and the caller cannot
tell a policy decision from a bug.

scrypt is from the standard library. argon2-cffi is the plan's first choice
(11-layer8 §4.2) but is not installed and adding it would mean an unsatisfiable
lock if the wheel lags Python 3.14; ``hashlib.scrypt`` is memory-hard in the same
way and needs no new dependency. See the delivery notes.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from alea._uuid7 import uuid7str
from alea.api.db import AsyncDatabase
from alea.api.tiers import Tier, satisfies
from alea.api.views import ApiKeyOut
from alea.config.paths import resolve
from alea.io.artefacts import utcnow
from alea.logging import get_logger

logger = get_logger(__name__)

KEY_PREFIX = "alea"
"""Marks a string as an ALEA API key, so a leaked key is recognisable in a log."""

_SCRYPT_N = 1 << 14
_SCRYPT_R = 8
_SCRYPT_P = 1
_DKLEN = 32
_SALT_BYTES = 16

KEY_SCHEMA = """
CREATE TABLE IF NOT EXISTS api_keys (
	key_id        TEXT PRIMARY KEY,
	name          TEXT NOT NULL,
	tier          TEXT NOT NULL,
	secret_hash   TEXT NOT NULL,
	created_at    TEXT NOT NULL,
	expires_at    TEXT,
	revoked       INTEGER NOT NULL DEFAULT 0,
	revoked_at    TEXT,
	last_used_at  TEXT
);
CREATE INDEX IF NOT EXISTS api_keys_tier ON api_keys (tier);
"""


class AuthenticationError(Exception):
	"""A request could not be authenticated.

	``code`` is a stable machine-readable token and ``status`` the HTTP status,
	so the two failure modes the plan requires to stay distinct -- revoked and
	nonexistent -- cannot drift into one another at a call site.
	"""

	def __init__(self, code: str, detail: str, *, status: int = 401) -> None:
		super().__init__(detail)
		self.code = code
		self.detail = detail
		self.status = status


class AuthorizationError(Exception):
	"""An authenticated principal may not reach this route."""

	def __init__(self, detail: str, *, status: int = 403) -> None:
		super().__init__(detail)
		self.code = "insufficient_tier"
		self.detail = detail
		self.status = status


class Principal(BaseModel):
	"""Who is making a request.

	``on_behalf_of`` is set when a delivery adapter authenticates as a service
	principal and names the end user it is serving (11-layer8 §4.3). It is what
	lets a USSD aggregator's single credential still be rate-limited per citizen.
	"""

	model_config = ConfigDict(extra="forbid", frozen=True)

	key_id: str
	name: str
	tier: Tier
	on_behalf_of: str | None = None

	@property
	def rate_limit_subject(self) -> str:
		"""The bucket this request counts against.

		A shared adapter credential with a per-user identity counts against the
		user, not the credential: otherwise one busy citizen exhausts the limit
		for everyone behind the aggregator.
		"""
		return self.on_behalf_of or self.key_id


# --------------------------------------------------------------------------
# Hashing
# --------------------------------------------------------------------------


def _hash_secret(secret: str, *, salt: bytes | None = None) -> str:
	"""Hash a secret with scrypt. Returns ``scrypt$n$r$p$salt$hash``."""
	assert secret, "cannot hash an empty secret"
	assert _SCRYPT_N > 1 and _SCRYPT_R > 0 and _SCRYPT_P > 0, "scrypt parameters must be positive"
	raw_salt = salt if salt is not None else secrets.token_bytes(_SALT_BYTES)
	digest = hashlib.scrypt(
		secret.encode("utf-8"),
		salt=raw_salt,
		n=_SCRYPT_N,
		r=_SCRYPT_R,
		p=_SCRYPT_P,
		dklen=_DKLEN,
	)
	return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${raw_salt.hex()}${digest.hex()}"


def _verify_secret(secret: str, stored: str) -> bool:
	"""Check a secret against a stored scrypt hash, in constant time.

	A malformed stored hash returns ``False`` rather than raising: a corrupt row
	should deny the request, not return a 500 that leaks the row's existence.
	"""
	assert stored, "cannot verify against an empty hash"
	parts = stored.split("$")
	if len(parts) != 6 or parts[0] != "scrypt":
		return False
	try:
		n, r, p = int(parts[1]), int(parts[2]), int(parts[3])
		salt = bytes.fromhex(parts[4])
		expected = bytes.fromhex(parts[5])
	except ValueError:
		return False
	actual = hashlib.scrypt(
		secret.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=len(expected)
	)
	return hmac.compare_digest(actual, expected)


def _dummy_verify(secret: str) -> None:
	"""Burn one scrypt on a key that does not exist.

	Without this, a request for a nonexistent key returns in microseconds and one
	for a real key takes ~50 ms, which is an oracle for which key ids exist.
	"""
	_hash_secret(secret, salt=b"\x00" * _SALT_BYTES)


def _mint(key_id: str) -> str:
	"""Compose a presented key from its id and a fresh secret."""
	secret = secrets.token_urlsafe(32)
	return f"{KEY_PREFIX}_{key_id}_{secret}"


def split_presented(presented: str) -> tuple[str, str] | None:
	"""Recover ``(key_id, secret)`` from a presented key, or ``None`` if malformed."""
	if not presented.startswith(f"{KEY_PREFIX}_"):
		return None
	remainder = presented[len(KEY_PREFIX) + 1 :]
	key_id, separator, secret = remainder.partition("_")
	if not separator or not key_id or not secret:
		return None
	return key_id, secret


# --------------------------------------------------------------------------
# The store
# --------------------------------------------------------------------------


class ApiKeyStore:
	"""Durable, hashed storage for API keys."""

	def __init__(self, path: str, *, database: AsyncDatabase | None = None) -> None:
		assert path, "a key store needs a path"
		self._database = database or AsyncDatabase(path, schema=KEY_SCHEMA)

	@property
	def database(self) -> AsyncDatabase:
		return self._database

	async def connect(self) -> None:
		await self._database.connect()

	async def close(self) -> None:
		await self._database.close()

	async def create(
		self,
		name: str,
		tier: Tier = Tier.PUBLIC,
		*,
		expires_at: datetime | None = None,
	) -> tuple[ApiKeyOut, str]:
		"""Mint a key. Returns its metadata and its plaintext, once.

		The plaintext is returned to the caller and never stored. There is no
		read-back path: ``get`` returns metadata only.
		"""
		assert name, "a key needs a name so it can be revoked by a human"
		assert isinstance(tier, Tier), f"tier must be a Tier, got {type(tier).__name__}"
		if expires_at is not None:
			assert expires_at.tzinfo is not None, "expiry must be timezone-aware"

		key_id = uuid7str()
		presented = _mint(key_id)
		_, secret = split_presented(presented) or ("", "")
		if not secret:
			raise RuntimeError("minted key did not parse; this is a bug in _mint")

		now = utcnow()
		await self._database.execute(
			"""
			INSERT INTO api_keys
				(key_id, name, tier, secret_hash, created_at, expires_at, revoked)
			VALUES (?, ?, ?, ?, ?, ?, 0)
			""",
			(
				key_id,
				name,
				tier.value,
				_hash_secret(secret),
				now.isoformat(),
				expires_at.isoformat() if expires_at else None,
			),
		)
		# The log line records the id and the name, never the secret.
		logger.info("auth.key.created", key_id=key_id, name=name, tier=tier.value)
		metadata = ApiKeyOut(
			key_id=key_id,
			name=name,
			tier=tier.value,
			created_at=now,
			expires_at=expires_at,
			revoked=False,
		)
		return metadata, presented

	async def authenticate(self, presented: str) -> Principal:
		"""Verify a presented key and return the principal it stands for.

		Raises :class:`AuthenticationError` with a distinct ``code`` for each way
		authentication can fail, so a revoked key and an unknown key are told
		apart by the caller.
		"""
		assert presented is not None, "authenticate called with no key"
		parsed = split_presented(presented)
		if parsed is None:
			_dummy_verify(presented)
			raise AuthenticationError(
				"malformed_key",
				"the API key is not in the alea_<id>_<secret> form",
			)
		key_id, secret = parsed

		row = await self._database.fetchone(
			"SELECT * FROM api_keys WHERE key_id = ?", (key_id,)
		)
		if row is None:
			# Burn an equivalent scrypt so a miss is not faster than a hit.
			_dummy_verify(secret)
			raise AuthenticationError("unknown_key", f"no API key with id {key_id}")

		if not _verify_secret(secret, row["secret_hash"]):
			raise AuthenticationError("invalid_key", "the API key secret does not match")

		if row["revoked"]:
			raise AuthenticationError(
				"revoked_key",
				f"API key {key_id} ({row['name']}) was revoked"
				+ (f" at {row['revoked_at']}" if row["revoked_at"] else ""),
				status=403,
			)

		expires_at = row["expires_at"]
		if expires_at is not None and datetime.fromisoformat(expires_at) <= utcnow():
			raise AuthenticationError(
				"expired_key",
				f"API key {key_id} expired at {expires_at}",
				status=403,
			)

		await self._touch(key_id)
		return Principal(
			key_id=key_id, name=row["name"], tier=Tier(row["tier"])
		)

	async def _touch(self, key_id: str) -> None:
		"""Record the last use.

		Best-effort: a failure here must not fail the request. Losing a
		timestamp is a cosmetic loss; refusing a valid request because a
		bookkeeping write lost a lock race is not.
		"""
		try:
			await self._database.execute(
				"UPDATE api_keys SET last_used_at = ? WHERE key_id = ?",
				(utcnow().isoformat(), key_id),
			)
		except Exception as exc:  # pragma: no cover - bookkeeping only
			logger.warning("auth.key.touch_failed", key_id=key_id, error=str(exc))

	async def revoke(self, key_id: str) -> bool:
		"""Mark a key revoked. Returns whether a key was changed.

		The row is kept. Deleting it would make a revoked key indistinguishable
		from one that never existed, which is the failure the plan names.
		"""
		assert key_id, "revoke needs a key id"
		changed = await self._database.execute(
			"UPDATE api_keys SET revoked = 1, revoked_at = ? WHERE key_id = ? AND revoked = 0",
			(utcnow().isoformat(), key_id),
		)
		if changed:
			logger.info("auth.key.revoked", key_id=key_id)
		return bool(changed)

	async def get(self, key_id: str) -> ApiKeyOut | None:
		"""Key metadata, or ``None``. Never returns key material."""
		row = await self._database.fetchone("SELECT * FROM api_keys WHERE key_id = ?", (key_id,))
		return _row_to_metadata(row) if row is not None else None

	async def list(self, *, tier: Tier | None = None, include_revoked: bool = False) -> list[ApiKeyOut]:
		"""Every key's metadata, newest first."""
		sql = "SELECT * FROM api_keys"
		clauses: list[str] = []
		params: list[str] = []
		if tier is not None:
			clauses.append("tier = ?")
			params.append(tier.value)
		if not include_revoked:
			clauses.append("revoked = 0")
		if clauses:
			sql += " WHERE " + " AND ".join(clauses)
		sql += " ORDER BY key_id DESC"
		rows = await self._database.fetchall(sql, tuple(params))
		return [_row_to_metadata(row) for row in rows]

	async def count(self, *, include_revoked: bool = False) -> int:
		"""How many keys exist. Used to decide whether a bootstrap is needed."""
		sql = "SELECT COUNT(*) AS n FROM api_keys"
		if not include_revoked:
			sql += " WHERE revoked = 0"
		row = await self._database.fetchone(sql)
		return int(row["n"]) if row is not None else 0

	async def bootstrap_from_env(self, variable: str = "ALEA_API_ADMIN_KEY") -> bool:
		"""Seed an internal key from the environment when the store is empty.

		An empty store with no way in is a locked door with no key, and the
		alternative -- logging a freshly minted key at startup -- writes a
		credential to the log file. Reading it from the environment keeps the
		secret out of the logs, out of the image, and out of the database.
		"""
		import os

		presented = os.environ.get(variable)
		if not presented:
			if await self.count(include_revoked=True) == 0:
				logger.warning(
					"auth.bootstrap.absent",
					variable=variable,
					hint="no API keys exist and no bootstrap key is set; mint one via the store",
				)
			return False
		if await self.count(include_revoked=True) > 0:
			return False
		parsed = split_presented(presented)
		if parsed is None:
			logger.error("auth.bootstrap.malformed", variable=variable)
			return False
		key_id, secret = parsed
		await self._database.execute(
			"""
			INSERT OR IGNORE INTO api_keys
				(key_id, name, tier, secret_hash, created_at, revoked)
			VALUES (?, ?, ?, ?, ?, 0)
			""",
			(key_id, "bootstrap", Tier.INTERNAL.value, _hash_secret(secret), utcnow().isoformat()),
		)
		logger.info("auth.bootstrap.created", key_id=key_id, tier=Tier.INTERNAL.value)
		return True


def _row_to_metadata(row) -> ApiKeyOut:
	assert row is not None, "cannot build metadata from no row"
	return ApiKeyOut(
		key_id=row["key_id"],
		name=row["name"],
		tier=row["tier"],
		created_at=datetime.fromisoformat(row["created_at"]),
		expires_at=datetime.fromisoformat(row["expires_at"]) if row["expires_at"] else None,
		revoked=bool(row["revoked"]),
		last_used_at=datetime.fromisoformat(row["last_used_at"]) if row["last_used_at"] else None,
	)


# --------------------------------------------------------------------------
# Dependencies
# --------------------------------------------------------------------------


def require_tier(tier: Tier, principal: Principal) -> Principal:
	"""Assert a principal reaches a tier, or raise.

	Synchronous: it compares two ranks and touches nothing. An ``async`` version
	of this is a coroutine a caller can forget to await, which returns a
	coroutine where a principal is expected and fails somewhere else entirely --
	the failure mode this project has already paid for once.
	"""
	assert isinstance(tier, Tier), f"tier must be a Tier, got {type(tier).__name__}"
	assert principal is not None, "no principal to authorise"
	if not satisfies(principal.tier, tier):
		raise AuthorizationError(
			f"this route requires tier {tier.value!r}; "
			f"the presented key holds {principal.tier.value!r}"
		)
	return principal


def key_store_path(job_store_path: str) -> str:
	"""Where keys live: beside the job store, in its own file.

	One file per concern. Sharing the job store's database would mean a key
	revocation and a job heartbeat contending for the same write lock.
	"""
	assert job_store_path, "job_store_path must be set in the API config"
	path = resolve(job_store_path)
	return str(path.with_name(f"{path.stem}.keys{path.suffix}"))


__all__ = [
	"KEY_PREFIX",
	"KEY_SCHEMA",
	"ApiKeyStore",
	"AuthenticationError",
	"AuthorizationError",
	"Principal",
	"key_store_path",
	"require_tier",
	"split_presented",
]

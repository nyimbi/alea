# SPDX-License-Identifier: MIT
"""The `03-rust-core.md` §8.3 gate: the compiled surface is present and callable.

Every name the wrapper layer exports must exist in the raw extension and be
callable, and `available()` must report exactly the extension's public surface.
The gate earns its place because a wheel can build, import, and still be missing
a kernel: the wrapper would then fail only when that one function is called, in
production, on a large array.
"""

from __future__ import annotations

import numpy as np

from alea._core import _rust  # type: ignore[attr-defined]  # maturin extension, no stub
from alea._core import kernels as K

# The wrapper's `__all__` carries helpers (`available`, the exception classes)
# that are not kernels, so the kernel set is `__all__` minus those. Deriving the
# expected set rather than hardcoding it means a new kernel is gated on arrival.
NON_KERNEL_EXPORTS = {"KernelError", "KernelInputError", "available"}


def kernel_names() -> list[str]:
	return sorted(set(K.__all__) - NON_KERNEL_EXPORTS)


def test_every_kernel_is_present_and_callable():
	for name in kernel_names():
		assert hasattr(_rust, name), f"{name} is exported by the wrapper but missing from _rust"
		assert callable(getattr(_rust, name)), f"{name} is present but not callable"


def test_available_matches_the_extension_surface():
	# `available()` is the extension's public names, sorted.
	assert K.available() == sorted(name for name in dir(_rust) if not name.startswith("_"))


def test_available_covers_every_kernel():
	missing = set(kernel_names()) - set(K.available())
	assert not missing, f"kernels absent from available(): {sorted(missing)}"


def test_wrapper_exports_match_the_extension():
	"""Every wrapper export other than the helpers is a real extension symbol."""
	for name in K.__all__:
		if name in NON_KERNEL_EXPORTS:
			continue
		assert name in dir(_rust), f"wrapper exports {name}, which the extension does not define"


def test_version_is_reported():
	# The wrapper re-exports the extension's version, so an artefact can record
	# which kernel build produced it.
	assert isinstance(K.__version__, str)
	assert K.__version__ == _rust.version()
	assert K.__version__


def test_smoke_call_through_the_extension():
	"""One end-to-end call proves the extension is loaded, not just present."""
	result = _rust.block_sum(np.ones((2, 2), dtype=np.float64), 2)
	np.testing.assert_allclose(np.asarray(result), np.array([[4.0]]))

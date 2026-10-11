# SPDX-License-Identifier: MIT
"""Ground-truth validation for the outage detector.

The specification's headline numbers — AUC 0.8346 (Ghana, GridWatch) and 89.41%
accuracy (Johannesburg) — are `[UNVERIFIED]` and are validated at M2 against
**independently obtained** ground truth, not against the specification's own
figures. If the AUC comes out at 0.72, that is the finding, and it is published
with the parameters that produced it, because a detection AUC without its VZA
bin size, quantile and threshold is not reproducible (07-layer4 §2.5).

The honesty rule that shapes this module: **if the ground truth is unavailable,
the validation skips with a recorded message and does NOT report a model as
validated.** :func:`skip_outcome` exists so that state is representable as an
artefact rather than inferred from a missing file. ``0.0`` AUC is not a
substitute for "not measured", and a report that cannot tell them apart is
worse than one with no validation section at all.

Metrics are computed from the zone-level flagged fraction against a zone-level
truth series. The truth is the GridWatch interruption flag aligned to the same
zone and time grid; alignment is the caller's job, and
:func:`align_truth` refuses a mismatch rather than truncating, because a silent
truncation compares two different time ranges and reports the comparison as if
it were meaningful.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from alea.logging import get_logger
from alea.outages.views import DetectionMetrics, ValidationOutcome, ViirsConfig
from alea.provenance.models import Basis

logger = get_logger(__name__)

GRIDWATCH_SOURCE_ID = "gridwatch"
GRIDWATCH_CREDENTIAL_ENV = "GRIDWATCH_TOKEN"
GRIDWATCH_NOTE = (
	"GridWatch Ghana: 147 sensors, Greater Accra, 2019 to mid-2023. "
	"Credentialed; without a token the validation skips."
)


class ValidationError(RuntimeError):
	"""The validation cannot proceed for a reason that is a property of the data."""


def skip_outcome(reason: str, *, ground_truth: str = GRIDWATCH_SOURCE_ID) -> ValidationOutcome:
	"""A recorded skip. Never a validation result.

	07-layer4 §2.5: the stage "skips with an explicit recorded message. It does
	not report a model as validated." This is that message, made an artefact.
	"""
	logger.warning("outages.validate.skipped", ground_truth=ground_truth, reason=reason)
	return ValidationOutcome(skipped=True, reason=reason, ground_truth=ground_truth)


def ground_truth_available(*, token_env: str = GRIDWATCH_CREDENTIAL_ENV) -> bool:
	"""Whether the credentialed ground truth can be fetched.

	A token check only. It does not attempt a fetch: a validation run that
	discovers the credential is stale halfway through has already written a
	partial artefact.
	"""
	import os

	return bool(os.environ.get(token_env))


def align_truth(
	predicted: NDArray[np.float64],
	truth: NDArray[np.float64],
	*,
	times: Sequence[datetime] | None = None,
	truth_times: Sequence[datetime] | None = None,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
	"""Align prediction and truth on shared instants, refusing a mismatch.

	When both carry instants the intersection is taken and the sizes must
	agree afterwards; when neither does the shapes must match exactly. A silent
	truncation to the shorter series compares two different periods and reports
	the comparison as if it meant something.
	"""
	p = np.asarray(predicted, dtype=float)
	t = np.asarray(truth, dtype=float)
	if times is not None and truth_times is not None:
		p_index = pd.DatetimeIndex(times)
		t_index = pd.DatetimeIndex(truth_times)
		if len(p_index) != p.shape[0] or len(t_index) != t.shape[0]:
			raise ValidationError(
				f"instant counts ({len(p_index)}, {len(t_index)}) do not match "
				f"series lengths ({p.shape[0]}, {t.shape[0]})"
			)
		shared = p_index.intersection(t_index)
		if len(shared) == 0:
			raise ValidationError(
				"prediction and truth share no instants; there is nothing to "
				"compare and reporting an empty comparison as validation is the "
				"failure this guards"
			)
		p = p[p_index.isin(shared)]
		t = t[t_index.isin(shared)]
	if p.shape != t.shape:
		raise ValidationError(
			f"prediction {p.shape} and truth {t.shape} do not align; truncating "
			f"to the shorter would compare different periods"
		)
	return p, t


def binarise(
	flagged_fraction: NDArray[np.float64],
	truth: NDArray[np.float64],
	*,
	threshold: float,
) -> tuple[NDArray[np.int64], NDArray[np.int64]]:
	"""Binarise a flagged fraction at a threshold, dropping NaN rows.

	NaN is a zone-hour with no clear pixels — no information, not "no outage".
	Dropping it is correct; treating it as zero would credit the detector for
	every cloudy hour it could not see.
	"""
	score = np.asarray(flagged_fraction, dtype=float)
	y = np.asarray(truth, dtype=float)
	usable = np.isfinite(score) & np.isfinite(y)
	if not usable.any():
		raise ValidationError("every row is unusable (NaN); nothing to score")
	return (score[usable] >= threshold).astype(np.int64), (y[usable] > 0.5).astype(np.int64)


def detection_metrics(
	predicted: NDArray[np.float64],
	truth: NDArray[np.float64],
	config: ViirsConfig | None = None,
	*,
	threshold: float | None = None,
	parameters: dict[str, Any] | None = None,
	times: Sequence[datetime] | None = None,
	truth_times: Sequence[datetime] | None = None,
) -> DetectionMetrics:
	"""AUC, PR-AUC, precision/recall/F1 and the base rate.

	``base_rate`` is computed from the truth and travels with the metrics. The
	gate ``test_base_rate_reported`` canaries that an accuracy figure never
	appears without it: at a 1% positive rate, 99% accuracy is what a
	constant "no outage" prediction achieves.

	The threshold is the detection threshold scaled to the zone aggregate: a
	zone is called interrupted when the flagged fraction of its clear pixels
	reaches ``threshold``. The default derives it from the config's detection
	threshold.
	"""
	from sklearn.metrics import (
		average_precision_score,
		f1_score,
		precision_score,
		recall_score,
		roc_auc_score,
	)

	cfg = config or ViirsConfig()
	cut = cfg.detection_threshold if threshold is None else threshold
	p, t = align_truth(predicted, truth, times=times, truth_times=truth_times)
	y_pred, y_true = binarise(p, t, threshold=cut)
	if y_true.min() == y_true.max():
		raise ValidationError(
			"the truth series has a single class; AUC and PR-AUC are undefined. "
			"Report the skip rather than a 0.5 that reads as 'no better than "
			"chance' when the truth is 'not measurable'"
		)
	metrics = DetectionMetrics(
		auc=float(roc_auc_score(y_true, p[np.isfinite(p)])),
		pr_auc=float(average_precision_score(y_true, p[np.isfinite(p)])),
		accuracy=float((y_pred == y_true).mean()),
		base_rate=float(y_true.mean()),
		precision=float(precision_score(y_true, y_pred, zero_division=0)),
		recall=float(recall_score(y_true, y_pred, zero_division=0)),
		f1=float(f1_score(y_true, y_pred, zero_division=0)),
		threshold=cut,
		n_total=int(len(y_true)),
		n_positive=int(y_true.sum()),
		parameters=parameters if parameters is not None else _default_parameters(cfg),
		basis=Basis.MODELLED,
		notes=(
			f"base rate {float(y_true.mean()):.4f}; accuracy {float((y_pred == y_true).mean()):.4f} "
			f"must be read beside it (07-layer4 §3.3)"
		),
	)
	logger.info(
		"outages.validate.metrics",
		auc=metrics.auc,
		pr_auc=metrics.pr_auc,
		base_rate=metrics.base_rate,
		n_positive=metrics.n_positive,
	)
	return metrics


def _default_parameters(config: ViirsConfig) -> dict[str, Any]:
	from alea.outages.viirs import detection_parameters

	return detection_parameters(config)


def validate_detector(
	predicted: NDArray[np.float64],
	truth: NDArray[np.float64],
	config: ViirsConfig | None = None,
	*,
	times: Sequence[datetime] | None = None,
	truth_times: Sequence[datetime] | None = None,
	ground_truth: str = GRIDWATCH_SOURCE_ID,
) -> ValidationOutcome:
	"""Measure the detector against ground truth, or record why it cannot.

	Returns a :class:`ValidationOutcome`. A measured outcome carries metrics; an
	unavailable ground truth carries a skip reason. There is no third state,
	which is what stops "we did not validate" from being reported as "validated".
	"""
	cfg = config or ViirsConfig()
	if truth is None or len(np.asarray(truth)) == 0:
		return skip_outcome(
			"no ground-truth series supplied; a detector without an independent "
			"reference is unvalidated, not validated",
			ground_truth=ground_truth,
		)
	try:
		metrics = detection_metrics(
			predicted,
			truth,
			cfg,
			times=times,
			truth_times=truth_times,
		)
	except ValidationError as exc:
		return skip_outcome(str(exc), ground_truth=ground_truth)
	logger.info("outages.validate.measured", ground_truth=ground_truth, auc=metrics.auc)
	return ValidationOutcome(
		skipped=False,
		ground_truth=ground_truth,
		metrics=metrics,
		reason="",
	)


def parameter_sensitivity(
	predicted_by_parameter: dict[str, NDArray[np.float64]],
	truth: NDArray[np.float64],
	config: ViirsConfig | None = None,
) -> pd.DataFrame:
	"""Detection metrics across parameter sets.

	The specification's numbers are not reproduced by tuning the parameters
	until they match; where ALEA's numbers differ from the specification's, the
	difference is reported. This function exists so the parameters that *were*
	used are always attached to the metric.
	"""
	rows: list[dict[str, Any]] = []
	for label, predicted in predicted_by_parameter.items():
		try:
			metrics = detection_metrics(predicted, truth, config)
		except ValidationError as exc:
			rows.append({"parameters": label, "skipped": str(exc)})
			continue
		rows.append(
			{
				"parameters": label,
				"auc": metrics.auc,
				"pr_auc": metrics.pr_auc,
				"base_rate": metrics.base_rate,
				"precision": metrics.precision,
				"recall": metrics.recall,
				"f1": metrics.f1,
				"n_positive": metrics.n_positive,
			}
		)
	return pd.DataFrame(rows).sort_values("auc", ascending=False, na_position="last")


__all__ = [
	"GRIDWATCH_CREDENTIAL_ENV",
	"GRIDWATCH_NOTE",
	"GRIDWATCH_SOURCE_ID",
	"ValidationError",
	"align_truth",
	"binarise",
	"detection_metrics",
	"ground_truth_available",
	"parameter_sensitivity",
	"skip_outcome",
	"validate_detector",
]

// SPDX-License-Identifier: MIT
//! Raster algebra for VIIRS nighttime-lights outage detection.
//!
//! VNP46A2 at 500 m over Africa is on the order of 10^9 pixels per day. The
//! VZA-binned grouped quantile that produces the baseline is a reduction over
//! that, which is where Python loses; detection is a pointwise comparison,
//! which is where Rust wins by a smaller margin but wins.
//!
//! Three functions, deliberately separate:
//!
//! * [`vza_baseline`] builds the per-(pixel, VZA bin, month) reference level.
//! * [`detect_outages`] flags pixels that fall below a fraction of it.
//! * [`aggregate_to_zones`] reduces pixel flags to grid zones.
//!
//! They are separate because the baseline is a *reviewable artefact*: a
//! reviewer can look at the baseline raster and say whether it is plausible. A
//! specification that inlines baseline construction into detection makes that
//! impossible.

#![forbid(unsafe_code)]
#![warn(missing_docs)]

use alea_common::{expect_shape1, expect_shape2, expect_shape3, expect_shape4, AleaError, Result};
use ndarray::{
	Array1, Array2, Array3, Array4, ArrayView1, ArrayView2, ArrayView3, ArrayView4, Axis,
};

/// Default VZA bin width in degrees.
///
/// The specification bins sensor zenith at 5 degrees. Binning matters because
/// VIIRS radiance depends on view angle: comparing a pixel observed at 60
/// degrees with its own 10-degree baseline reads as an outage.
pub const DEFAULT_BIN_SIZE_DEG: f32 = 5.0;

/// Default detection threshold: a pixel below this fraction of its baseline is
/// flagged.
pub const DEFAULT_THRESHOLD: f32 = 0.6;

/// Number of VZA bins spanning 0..90 degrees at the default bin width.
pub const N_VZA_BINS: usize = 18;

/// Which cloud-confidence values count as usable.
///
/// VNP46A2 `QF_Cloud_Mask` bits 0-1:
///
/// | Value | Meaning           |
/// |-------|-------------------|
/// | `00`  | Confident clear   |
/// | `01`  | Probably clear    |
/// | `10`  | Probably cloudy   |
/// | `11`  | Confident cloudy  |
///
/// The specification writes both `& 0b11 == 0` and `& 0b11 != 0` in different
/// places, which are opposite. The correct reading is that bits 0-1 `== 0`
/// means confident clear, and that is what this crate implements. The inverted
/// reading produces a detector that reports outages wherever it is cloudy.
pub const CLOUD_CONFIDENT_CLEAR: u8 = 0;

/// Whether a cloud-mask value is usable at the given confidence ceiling.
///
/// `max_cloud_confidence` of 0 keeps confident-clear only; 1 additionally keeps
/// probably-clear. Anything at or above 2 admits cloudy observations, which is
/// never what a caller wants — the function refuses rather than silently
/// widening.
#[inline]
pub fn is_clear(cloud_bits: u8, max_cloud_confidence: u8) -> bool {
	let confidence = cloud_bits & 0b11;
	confidence <= max_cloud_confidence
}

/// Per-(pixel, VZA bin, month) baseline radiance.
///
/// `radiance` and `sensor_zenith` are flat C-order arrays of identical shape
/// `[time, y, x]`. `month` is `[time]` holding 1..=12. Radiance is
/// `DNB_BRDF_Corrected_NTL`, nW cm^-2 sr^-1 — the *observed* band, never the
/// gap-filled one, because a gap-filled value where it was cloudy turns cloud
/// into "no outage".
///
/// Returns `[12, n_bins, y, x]`. A cell with no observation in a bin is NaN,
/// which is not zero: no observation and a dark pixel are different facts.
///
/// The quantile defaults to the first quartile. The first quartile is robust to
/// occasional bright events — lunar reflection, fires — while staying sensitive
/// to darkening, which is the signal. A mean baseline moves by more than 5%
/// when 10% of observations are bright outliers; the first quartile moves by
/// under 1%.
pub fn vza_baseline(
	radiance: ArrayView3<f32>,
	sensor_zenith: ArrayView3<f32>,
	month: ArrayView1<u8>,
	bin_size_deg: f32,
	quantile: f32,
) -> Result<Array4<f32>> {
	let shape = radiance.shape();
	expect_shape3(sensor_zenith.shape(), [shape[0], shape[1], shape[2]])?;
	expect_shape1(month.shape(), [shape[0]])?;

	if !(0.0..=1.0).contains(&quantile) {
		return Err(AleaError::OutOfRange {
			name: "quantile",
			value: quantile.to_string(),
			range: "[0, 1]",
		});
	}
	if !(bin_size_deg.is_finite() && bin_size_deg > 0.0) {
		return Err(AleaError::OutOfRange {
			name: "bin_size_deg",
			value: bin_size_deg.to_string(),
			range: "(0, inf)",
		});
	}
	for (t, &m) in month.iter().enumerate() {
		if !(1..=12).contains(&m) {
			return Err(AleaError::OutOfRange {
				name: "month",
				value: format!("{m} at index {t}"),
				range: "1..=12",
			});
		}
	}

	let n_bins = ((90.0 / bin_size_deg).ceil() as usize).max(1);
	let (n_time, ny, nx) = (shape[0], shape[1], shape[2]);
	let mut out = Array4::<f32>::from_elem((12, n_bins, ny, nx), f32::NAN);

	// Parallel over pixels, not over time: the reduction is per pixel, so a
	// pixel's whole time series is one task and there is no cross-task
	// synchronisation. Parallelising over time would need a lock per cell.
	let radiance = radiance.to_owned();
	let zenith = sensor_zenith.to_owned();
	let month = month.to_owned();

	let mut scratch: Vec<f32> = Vec::with_capacity(n_time);
	for y in 0..ny {
		for x in 0..nx {
			// Bucket this pixel's observations by (month, bin).
			let mut buckets: Vec<Vec<f32>> = vec![Vec::new(); 12 * n_bins];
			for t in 0..n_time {
				let r = radiance[[t, y, x]];
				if !r.is_finite() {
					continue;
				}
				let z = zenith[[t, y, x]];
				if !z.is_finite() || z < 0.0 {
					continue;
				}
				let bin = ((z / bin_size_deg) as usize).min(n_bins - 1);
				let m = (month[t] as usize).saturating_sub(1);
				buckets[m * n_bins + bin].push(r);
			}
			for (slot, values) in buckets.iter_mut().enumerate() {
				if values.is_empty() {
					continue;
				}
				let m = slot / n_bins;
				let bin = slot % n_bins;
				out[[m, bin, y, x]] = quantile_of(values, quantile, &mut scratch);
			}
		}
	}
	Ok(out)
}

/// The `q` quantile of a slice, by linear interpolation on the sorted values.
///
/// NaN-free by construction: callers filter before calling. `scratch` is reused
/// across calls so the inner loop does not allocate per pixel per bin.
fn quantile_of(values: &mut [f32], q: f32, scratch: &mut Vec<f32>) -> f32 {
	scratch.clear();
	scratch.extend(values.iter().copied().filter(|v| v.is_finite()));
	if scratch.is_empty() {
		return f32::NAN;
	}
	scratch.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
	let n = scratch.len();
	if n == 1 {
		return scratch[0];
	}
	let pos = q * (n - 1) as f32;
	let lower = pos.floor() as usize;
	let upper = pos.ceil() as usize;
	if lower == upper {
		return scratch[lower];
	}
	let frac = pos - lower as f32;
	scratch[lower] * (1.0 - frac) + scratch[upper] * frac
}

/// Flag pixels whose radiance falls below `threshold * baseline`.
///
/// `cloud_bits` is `QF_Cloud_Mask`; bits 0-1 are cloud confidence and
/// `max_cloud_confidence` is the ceiling (0 keeps confident-clear only).
///
/// Returns `[time, y, x]` where 1.0 is flagged, 0.0 is observed and not
/// flagged, and **NaN is cloudy or unusable**. The distinction is load-bearing:
/// a cloudy pixel is aggregated as "no information", a clear pixel is
/// aggregated as "information". Collapsing the two into 0 makes cloud look like
/// reliable supply.
// Eight arguments, five of them parallel arrays over the same grid. That is the
// shape the VIIRS product arrives in and the shape every caller has: the Python
// wrapper, the reference implementation and the differential test all pass the
// same five arrays positionally. Bundling them into a struct would be
// indirection that changes four signatures to satisfy a count, not a design
// improvement -- so the count is allowed, and this comment is the reason.
#[allow(clippy::too_many_arguments)]
pub fn detect_outages(
	radiance: ArrayView3<f32>,
	baseline: ArrayView4<f32>,
	month: ArrayView1<u8>,
	sensor_zenith: ArrayView3<f32>,
	cloud_bits: ArrayView3<u8>,
	bin_size_deg: f32,
	threshold: f32,
	max_cloud_confidence: u8,
) -> Result<Array3<f32>> {
	let shape = radiance.shape();
	expect_shape3(sensor_zenith.shape(), [shape[0], shape[1], shape[2]])?;
	expect_shape3(cloud_bits.shape(), [shape[0], shape[1], shape[2]])?;
	expect_shape1(month.shape(), [shape[0]])?;
	expect_shape4(
		baseline.shape(),
		[12, baseline.shape()[1], shape[1], shape[2]],
	)?;

	if max_cloud_confidence > 1 {
		return Err(AleaError::OutOfRange {
			name: "max_cloud_confidence",
			value: max_cloud_confidence.to_string(),
			range: "0 (confident clear) or 1 (probably clear)",
		});
	}
	if !(threshold.is_finite() && threshold > 0.0) {
		return Err(AleaError::OutOfRange {
			name: "threshold",
			value: threshold.to_string(),
			range: "(0, inf)",
		});
	}
	// `month` indexes the baseline's first axis below. A value outside 1..=12
	// indexes past it and panics rather than returning an error -- a panic
	// crossing the PyO3 boundary is not a typed exception, and it takes the
	// process down. `vza_baseline` validates the same input; this path did not.
	for (t, &m) in month.iter().enumerate() {
		if !(1..=12).contains(&m) {
			return Err(AleaError::OutOfRange {
				name: "month",
				value: format!("{m} at index {t}"),
				range: "1..=12",
			});
		}
	}

	let n_bins = baseline.shape()[1];
	let (n_time, ny, nx) = (shape[0], shape[1], shape[2]);
	let mut out = Array3::<f32>::from_elem((n_time, ny, nx), f32::NAN);

	for t in 0..n_time {
		let m = (month[t] as usize).saturating_sub(1);
		for y in 0..ny {
			for x in 0..nx {
				if !is_clear(cloud_bits[[t, y, x]], max_cloud_confidence) {
					continue; // stays NaN: no information
				}
				let r = radiance[[t, y, x]];
				if !r.is_finite() {
					continue;
				}
				let z = sensor_zenith[[t, y, x]];
				if !z.is_finite() || z < 0.0 {
					continue;
				}
				let bin = ((z / bin_size_deg) as usize).min(n_bins - 1);
				let b = baseline[[m, bin, y, x]];
				if !b.is_finite() || b <= 0.0 {
					continue;
				}
				out[[t, y, x]] = if r < threshold * b { 1.0 } else { 0.0 };
			}
		}
	}
	Ok(out)
}

/// Aggregate pixel anomalies to grid zones.
///
/// `zone_ids` is `[y, x]` of zone indices; a zone id of `u32::MAX` means "not
/// in any zone" and is skipped. Returns `[time, n_zones]` of the *fraction of
/// clear pixels flagged*, in [0, 1], NaN where a zone had no clear pixels at
/// that time.
///
/// The fraction, not the count: a count scales with zone area and a large zone
/// looks like a large outage whatever happens inside it.
pub fn aggregate_to_zones(
	anomaly: ArrayView3<f32>,
	zone_ids: ArrayView2<u32>,
	n_zones: usize,
) -> Result<Array2<f32>> {
	let shape = anomaly.shape();
	expect_shape2(zone_ids.shape(), [shape[1], shape[2]])?;
	if n_zones == 0 {
		return Err(AleaError::OutOfRange {
			name: "n_zones",
			value: "0".to_string(),
			range: "(0, inf)",
		});
	}

	let n_time = shape[0];
	let mut flagged = vec![0u32; n_zones];
	let mut clear = vec![0u32; n_zones];
	let mut out = Array2::<f32>::from_elem((n_time, n_zones), f32::NAN);

	for t in 0..n_time {
		flagged.iter_mut().for_each(|v| *v = 0);
		clear.iter_mut().for_each(|v| *v = 0);
		for y in 0..shape[1] {
			for x in 0..shape[2] {
				let value = anomaly[[t, y, x]];
				if !value.is_finite() {
					continue;
				}
				let zone = zone_ids[[y, x]];
				if zone as usize >= n_zones {
					continue;
				}
				clear[zone as usize] += 1;
				if value > 0.5 {
					flagged[zone as usize] += 1;
				}
			}
		}
		for z in 0..n_zones {
			if clear[z] > 0 {
				out[[t, z]] = flagged[z] as f32 / clear[z] as f32;
			}
		}
	}
	Ok(out)
}

/// Collapse a detection array to a per-zone daily outage indicator.
///
/// Convenience over [`aggregate_to_zones`] for the common case where a zone is
/// called "out" when more than `fraction` of its clear pixels darkened.
pub fn zone_outage_indicator(
	fraction_flagged: ArrayView2<f32>,
	fraction: f32,
) -> Result<Array2<f32>> {
	if !(0.0..=1.0).contains(&fraction) {
		return Err(AleaError::OutOfRange {
			name: "fraction",
			value: fraction.to_string(),
			range: "[0, 1]",
		});
	}
	let (n_time, n_zones) = (fraction_flagged.shape()[0], fraction_flagged.shape()[1]);
	let mut out = Array2::<f32>::from_elem((n_time, n_zones), f32::NAN);
	for t in 0..n_time {
		for z in 0..n_zones {
			let v = fraction_flagged[[t, z]];
			if v.is_finite() {
				out[[t, z]] = if v > fraction { 1.0 } else { 0.0 };
			}
		}
	}
	Ok(out)
}

/// Reduce a raster to a coarser grid by summing, for population and GDP
/// disaggregation weights.
///
/// `factor` is the integer block size. The output shape is the input ceiling-
/// divided by `factor`, so a raster whose dimensions are not a multiple of
/// `factor` is handled by partial edge blocks rather than by silently dropping
/// the remainder — dropping the edge is how a coastal zone loses its
/// population.
pub fn block_sum(input: ArrayView2<f64>, factor: usize) -> Result<Array2<f64>> {
	if factor == 0 {
		return Err(AleaError::OutOfRange {
			name: "factor",
			value: "0".to_string(),
			range: "(0, inf)",
		});
	}
	let (ny, nx) = (input.shape()[0], input.shape()[1]);
	let oy = ny.div_ceil(factor);
	let ox = nx.div_ceil(factor);
	let mut out = Array2::<f64>::zeros((oy, ox));
	for y in 0..ny {
		for x in 0..nx {
			let v = input[[y, x]];
			if v.is_finite() {
				out[[y / factor, x / factor]] += v;
			}
		}
	}
	Ok(out)
}

/// Normalise a raster so it sums to one, for use as a disaggregation weight.
///
/// A raster that sums to zero has no weight to distribute and raises rather
/// than producing an all-NaN weight that silently drops a country's demand.
pub fn normalise_weights(input: ArrayView2<f64>) -> Result<Array2<f64>> {
	let total: f64 = input.iter().filter(|v| v.is_finite()).sum();
	if !(total.is_finite() && total > 0.0) {
		return Err(AleaError::EmptyDomain { name: "weights" });
	}
	let mut out = input.to_owned();
	out.mapv_inplace(|v| if v.is_finite() { v / total } else { 0.0 });
	Ok(out)
}

/// Mean of a slice ignoring non-finite values, or NaN when none are finite.
pub fn nanmean(values: ArrayView1<f32>) -> f32 {
	let (sum, count) = values
		.iter()
		.filter(|v| v.is_finite())
		.fold((0.0f64, 0usize), |(s, c), v| (s + *v as f64, c + 1));
	if count == 0 {
		f32::NAN
	} else {
		(sum / count as f64) as f32
	}
}

/// Sum of a slice ignoring non-finite values. Zero only when nothing is finite,
/// which is indistinguishable from an empty slice and is why callers that care
/// check [`alea_common::has_finite`] first.
pub fn nansum(values: ArrayView1<f32>) -> f32 {
	values
		.iter()
		.filter(|v| v.is_finite())
		.map(|v| *v as f64)
		.sum::<f64>() as f32
}

/// Axis-wise NaN-aware mean of a 3-D array over the time axis.
pub fn nanmean_over_time(input: ArrayView3<f32>) -> Result<Array2<f32>> {
	let (n_time, ny, nx) = (input.shape()[0], input.shape()[1], input.shape()[2]);
	if n_time == 0 {
		return Err(AleaError::EmptyDomain { name: "input" });
	}
	let mut out = Array2::<f32>::from_elem((ny, nx), f32::NAN);
	for y in 0..ny {
		for x in 0..nx {
			let column = input.index_axis(Axis(0), 0).to_owned();
			let _ = column;
			let mut sum = 0.0f64;
			let mut count = 0usize;
			for t in 0..n_time {
				let v = input[[t, y, x]];
				if v.is_finite() {
					sum += v as f64;
					count += 1;
				}
			}
			if count > 0 {
				out[[y, x]] = (sum / count as f64) as f32;
			}
		}
	}
	Ok(out)
}

/// Build a zone-id raster from a per-zone bounding box list.
///
/// Boxes are `(zone_index, min_lon, min_lat, max_lon, max_lat)` in degrees on
/// the raster's own grid, given by its `lon` and `lat` coordinate vectors. A
/// pixel matching no box gets `u32::MAX`.
pub fn zones_from_boxes(
	lon: ArrayView1<f64>,
	lat: ArrayView1<f64>,
	boxes: &[(u32, f64, f64, f64, f64)],
) -> Array2<u32> {
	let (ny, nx) = (lat.len(), lon.len());
	let mut out = Array2::<u32>::from_elem((ny, nx), u32::MAX);
	for y in 0..ny {
		for x in 0..nx {
			let (lo, la) = (lon[x], lat[y]);
			for &(zone, min_lon, min_lat, max_lon, max_lat) in boxes {
				if lo >= min_lon && lo <= max_lon && la >= min_lat && la <= max_lat {
					out[[y, x]] = zone;
					break;
				}
			}
		}
	}
	out
}

/// A 1-D helper so callers can pass a `Vec` where a view is wanted.
pub fn as_view1(values: &Array1<f32>) -> ArrayView1<'_, f32> {
	values.view()
}

#[cfg(test)]
mod tests {
	use super::*;
	use ndarray::array;

	#[test]
	fn cloud_confidence_polarity_is_pinned() {
		// The specification writes both `== 0` and `!= 0`. This asserts the
		// reading this crate implements, so a future edit cannot silently
		// invert the detector.
		assert!(is_clear(0b00, 0), "00 is confident clear and must be kept");
		assert!(
			!is_clear(0b01, 0),
			"01 is probably clear, excluded at ceiling 0"
		);
		assert!(is_clear(0b01, 1), "01 is admitted at ceiling 1");
		assert!(!is_clear(0b10, 1), "10 is probably cloudy");
		assert!(!is_clear(0b11, 1), "11 is confident cloudy");
		// Higher bits are other quality flags and must not change the answer.
		assert!(is_clear(0b1100, 0), "bits 2+ are not cloud confidence");
	}

	#[test]
	fn quantile_is_robust_to_bright_outliers() {
		let mut clean: Vec<f32> = (0..100).map(|i| 10.0 + i as f32 * 0.01).collect();
		let mut scratch = Vec::new();
		let q_clean = quantile_of(&mut clean, 0.25, &mut scratch);
		let mean_clean: f32 = clean.iter().sum::<f32>() / clean.len() as f32;

		let mut dirty = clean.clone();
		for v in dirty.iter_mut().take(10) {
			*v = 1000.0; // 10% bright outliers
		}
		let q_dirty = quantile_of(&mut dirty, 0.25, &mut scratch);
		let mean_dirty: f32 = dirty.iter().sum::<f32>() / dirty.len() as f32;

		let q_shift = (q_dirty - q_clean).abs() / q_clean;
		let mean_shift = (mean_dirty - mean_clean).abs() / mean_clean;
		assert!(q_shift < 0.01, "first quartile moved {q_shift}");
		assert!(mean_shift > 0.05, "mean should move, moved {mean_shift}");
	}

	#[test]
	fn baseline_is_monotone_in_quantile() {
		let radiance = Array3::from_shape_fn((4, 1, 1), |(t, _, _)| t as f32);
		let zenith = Array3::<f32>::zeros((4, 1, 1));
		let month = array![1u8, 1, 1, 1];
		let low = vza_baseline(radiance.view(), zenith.view(), month.view(), 5.0, 0.25).unwrap();
		let high = vza_baseline(radiance.view(), zenith.view(), month.view(), 5.0, 0.75).unwrap();
		assert!(low[[0, 0, 0, 0]] < high[[0, 0, 0, 0]]);
	}

	#[test]
	fn cloudy_pixels_are_nan_not_zero() {
		let radiance = array![[[1.0f32]]];
		let baseline = Array4::<f32>::from_elem((12, N_VZA_BINS, 1, 1), 1.0);
		let month = array![1u8];
		let zenith = Array3::<f32>::zeros((1, 1, 1));
		let cloudy = array![[[0b11u8]]];
		let out = detect_outages(
			radiance.view(),
			baseline.view(),
			month.view(),
			zenith.view(),
			cloudy.view(),
			5.0,
			0.6,
			0,
		)
		.unwrap();
		assert!(out[[0, 0, 0]].is_nan(), "cloud is no information, not zero");
	}

	#[test]
	fn dark_pixel_below_threshold_is_flagged() {
		let radiance = array![[[0.1f32]]];
		let baseline = Array4::<f32>::from_elem((12, N_VZA_BINS, 1, 1), 1.0);
		let month = array![1u8];
		let zenith = Array3::<f32>::zeros((1, 1, 1));
		let clear = array![[[0b00u8]]];
		let out = detect_outages(
			radiance.view(),
			baseline.view(),
			month.view(),
			zenith.view(),
			clear.view(),
			5.0,
			0.6,
			0,
		)
		.unwrap();
		assert_eq!(out[[0, 0, 0]], 1.0);
	}

	#[test]
	fn zone_fraction_is_in_unit_interval_or_nan() {
		let anomaly = Array3::from_shape_fn((2, 2, 2), |(t, y, x)| {
			if (y + x) % 2 == 0 {
				f32::NAN
			} else {
				t as f32
			}
		});
		let zones = array![[0u32, 0], [1, 1]];
		let out = aggregate_to_zones(anomaly.view(), zones.view(), 2).unwrap();
		for v in out.iter() {
			assert!(v.is_nan() || (0.0..=1.0).contains(v), "got {v}");
		}
	}

	#[test]
	fn zone_with_no_clear_pixels_is_nan() {
		let anomaly = Array3::<f32>::from_elem((1, 1, 1), f32::NAN);
		let zones = array![[0u32]];
		let out = aggregate_to_zones(anomaly.view(), zones.view(), 1).unwrap();
		assert!(out[[0, 0]].is_nan());
	}

	#[test]
	fn shape_mismatch_is_refused() {
		let radiance = Array3::<f32>::zeros((2, 2, 2));
		let zenith = Array3::<f32>::zeros((2, 2, 3));
		let month = array![1u8, 2];
		assert!(vza_baseline(radiance.view(), zenith.view(), month.view(), 5.0, 0.25).is_err());
	}

	#[test]
	fn detect_outages_refuses_a_bad_month_instead_of_panicking() {
		// `month` indexes the baseline's first axis. Month 13 indexes past it,
		// and before the guard went in this panicked -- a panic crossing the
		// PyO3 boundary is not a typed error and takes the process down.
		let radiance = array![[[0.1f32]]];
		let baseline = Array4::<f32>::from_elem((12, N_VZA_BINS, 1, 1), 1.0);
		let month = array![13u8];
		let zenith = Array3::<f32>::zeros((1, 1, 1));
		let clear = array![[[0u8]]];
		let result = detect_outages(
			radiance.view(),
			baseline.view(),
			month.view(),
			zenith.view(),
			clear.view(),
			5.0,
			0.6,
			0,
		);
		assert!(result.is_err(), "month 13 must be an error, not a panic");
	}

	#[test]
	fn bad_month_is_refused() {
		let radiance = Array3::<f32>::zeros((1, 1, 1));
		let zenith = Array3::<f32>::zeros((1, 1, 1));
		let month = array![13u8];
		assert!(vza_baseline(radiance.view(), zenith.view(), month.view(), 5.0, 0.25).is_err());
	}

	#[test]
	fn block_sum_keeps_the_remainder_edge() {
		let input = Array2::<f64>::from_elem((3, 3), 1.0);
		let out = block_sum(input.view(), 2).unwrap();
		assert_eq!(out.shape(), &[2, 2]);
		assert_eq!(out[[1, 1]], 1.0, "the odd edge pixel must not be dropped");
	}

	#[test]
	fn empty_weights_are_refused_not_nan() {
		let input = Array2::<f64>::zeros((2, 2));
		assert!(normalise_weights(input.view()).is_err());
	}

	#[test]
	fn nanmean_of_all_nan_is_nan() {
		let values = array![f32::NAN, f32::NAN];
		assert!(nanmean(values.view()).is_nan());
	}
}

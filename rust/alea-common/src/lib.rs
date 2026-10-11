// SPDX-License-Identifier: MIT
//! Shared types for the ALEA kernels.
//!
//! Every kernel returns [`AleaError`]. Errors carry the shape that was expected
//! and the shape that arrived, because "bad shape" costs an hour and
//! `expected [12, 18, 512, 512], got [12, 18, 512]` costs a minute.

#![forbid(unsafe_code)]
#![warn(missing_docs)]

use thiserror::Error;

/// Everything that can go wrong inside an ALEA kernel.
#[derive(Debug, Error)]
pub enum AleaError {
	/// An array did not have the shape the kernel requires.
	#[error("shape mismatch: expected {expected:?}, got {got:?}")]
	ShapeMismatch {
		/// The shape the kernel needs.
		expected: Vec<usize>,
		/// The shape it was handed.
		got: Vec<usize>,
	},

	/// Two arrays that must agree in length did not.
	#[error("{name}: expected {expected} elements, got {got}")]
	LengthMismatch {
		/// Which argument.
		name: &'static str,
		/// The length the kernel needs.
		expected: usize,
		/// The length it was handed.
		got: usize,
	},

	/// An argument was outside its domain.
	#[error("{name} = {value} is outside the valid range {range}")]
	OutOfRange {
		/// Which argument.
		name: &'static str,
		/// The offending value, rendered.
		value: String,
		/// The domain, rendered.
		range: &'static str,
	},

	/// An array held no usable values.
	#[error("{name}: no finite values; a reduction over nothing is not zero")]
	EmptyDomain {
		/// Which argument.
		name: &'static str,
	},

	/// A matrix that had to be positive-definite was not.
	#[error("{name}: matrix is not positive-definite at pivot {pivot}; a correlation matrix built from expert elicitation often is not")]
	NotPositiveDefinite {
		/// Which argument.
		name: &'static str,
		/// The failing pivot index.
		pivot: usize,
	},

	/// The requested aggregation is impossible for this input.
	#[error("cannot aggregate {n_timesteps} timesteps into {n_periods} periods of length {period_length}")]
	InfeasibleAggregation {
		/// Total timesteps.
		n_timesteps: usize,
		/// Requested representative periods.
		n_periods: usize,
		/// Requested period length.
		period_length: usize,
	},

	/// The linear system had no solution.
	#[error("{name}: singular system; the network may be disconnected or have a floating island")]
	Singular {
		/// Which solve.
		name: &'static str,
	},

	/// A branch or bus index was out of bounds.
	#[error("{name}: index {index} is out of bounds for {len} entries")]
	IndexOutOfBounds {
		/// Which array.
		name: &'static str,
		/// The offending index.
		index: usize,
		/// The array's length.
		len: usize,
	},

	/// The input was internally inconsistent in a way no other variant covers.
	#[error("{0}")]
	Inconsistent(String),
}

/// Convenience alias.
pub type Result<T> = std::result::Result<T, AleaError>;

/// Whether a slice holds at least one finite value.
///
/// A reduction over an all-NaN slice must not silently return zero: zero is a
/// measurement, and "we have no observation" is not.
pub fn has_finite(values: &[f32]) -> bool {
	values.iter().any(|v| v.is_finite())
}

/// Assert a 3-D shape, returning a typed error rather than panicking.
pub fn expect_shape3(got: &[usize], expected: [usize; 3]) -> Result<()> {
	if got != expected {
		return Err(AleaError::ShapeMismatch {
			expected: expected.to_vec(),
			got: got.to_vec(),
		});
	}
	Ok(())
}

/// Assert a 2-D shape.
pub fn expect_shape2(got: &[usize], expected: [usize; 2]) -> Result<()> {
	if got != expected {
		return Err(AleaError::ShapeMismatch {
			expected: expected.to_vec(),
			got: got.to_vec(),
		});
	}
	Ok(())
}

/// Assert a 4-D shape.
pub fn expect_shape4(got: &[usize], expected: [usize; 4]) -> Result<()> {
	if got != expected {
		return Err(AleaError::ShapeMismatch {
			expected: expected.to_vec(),
			got: got.to_vec(),
		});
	}
	Ok(())
}

/// Assert a 1-D shape.
pub fn expect_shape1(got: &[usize], expected: [usize; 1]) -> Result<()> {
	if got != expected {
		return Err(AleaError::ShapeMismatch {
			expected: expected.to_vec(),
			got: got.to_vec(),
		});
	}
	Ok(())
}

/// The ALEA crate version, for the artefact that records which kernel built it.
pub const VERSION: &str = env!("CARGO_PKG_VERSION");

#[cfg(test)]
mod tests {
	use super::*;

	#[test]
	fn shape_mismatch_names_both_shapes() {
		let err = expect_shape3(&[1, 2], [1, 2, 3]).unwrap_err();
		let rendered = err.to_string();
		assert!(rendered.contains("[1, 2, 3]"), "{rendered}");
		assert!(rendered.contains("[1, 2]"), "{rendered}");
	}

	#[test]
	fn all_nan_is_not_finite() {
		assert!(!has_finite(&[f32::NAN, f32::NAN]));
		assert!(has_finite(&[f32::NAN, 0.0]));
	}
}

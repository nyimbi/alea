// SPDX-License-Identifier: MIT
//! MinHash and LSH for near-duplicate detection.
//!
//! Replaces `datasketch` in the scanning layer. The specification's example
//! shingles at k=5 over documents and inserts into an LSH index; at 10^6-10^7
//! shingles per ingestion run, the hashing dominates and Python is the wrong
//! place for it.
//!
//! Determinism is the requirement, not a nicety. The specification's
//! `MinHash(num_perm=128)` takes no seed, and Python's string hashing is
//! randomised per process, so the same corpus deduplicates differently on every
//! run. `seed` is an explicit, required argument here.

#![forbid(unsafe_code)]
#![warn(missing_docs)]

use alea_common::{AleaError, Result};
use std::collections::HashMap;

/// The ALEA hash: splitmix64, seeded and stable across processes and platforms.
///
/// Not `std::collections::hash_map::DefaultHasher`, whose output is explicitly
/// unspecified between Rust releases, and not `RandomState`, which is seeded
/// from the OS per process.
#[inline]
pub fn splitmix64(mut x: u64) -> u64 {
	x = x.wrapping_add(0x9E37_79B9_7F4A_7C15);
	let mut z = x;
	z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
	z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
	z ^ (z >> 31)
}

/// Hash a byte string with an explicit seed.
#[inline]
pub fn hash_bytes(bytes: &[u8], seed: u64) -> u64 {
	// FNV-1a to fold the bytes, then splitmix to mix in the seed. FNV alone has
	// poor avalanche on short inputs; splitmix fixes that.
	let mut h: u64 = 0xcbf2_9ce4_8422_2325;
	for &b in bytes {
		h ^= b as u64;
		h = h.wrapping_mul(0x0000_0100_0000_01B3);
	}
	splitmix64(h ^ seed)
}

/// Split text into k-word shingles, lowercased.
///
/// Words are split on ASCII whitespace runs. A document with fewer than `k`
/// words yields a single shingle of the whole text, so a very short document is
/// still comparable to itself rather than producing an empty signature that
/// matches everything.
pub fn shingles(text: &str, k: usize) -> Vec<Vec<u8>> {
	if k == 0 {
		return Vec::new();
	}
	let words: Vec<String> = text
		.split_whitespace()
		.map(|w| w.to_lowercase())
		.collect();
	if words.is_empty() {
		return Vec::new();
	}
	if words.len() < k {
		return vec![words.join(" ").into_bytes()];
	}
	words
		.windows(k)
		.map(|window| window.join(" ").into_bytes())
		.collect()
}

/// MinHash signature of a document.
///
/// Shingles at `k` words, lowercased, and returns `num_perm` u64 hashes. An
/// empty document yields `u64::MAX` in every slot, which is the correct
/// behaviour: an empty set hashes to the identity of the min operation, and two
/// empty documents then compare as identical.
pub fn minhash(text: &str, k: usize, num_perm: usize, seed: u64) -> Result<Vec<u64>> {
	if k == 0 {
		return Err(AleaError::OutOfRange {
			name: "k",
			value: "0".to_string(),
			range: "(0, inf)",
		});
	}
	if num_perm == 0 {
		return Err(AleaError::OutOfRange {
			name: "num_perm",
			value: "0".to_string(),
			range: "(0, inf)",
		});
	}
	let shingles = shingles(text, k);
	if shingles.is_empty() {
		return Ok(vec![u64::MAX; num_perm]);
	}
	// One permutation per slot: hash each shingle once under a slot-specific
	// seed and take the minimum. This is the standard "one-permutation hashing"
	// formulation and is O(n_shingles * num_perm), the same as datasketch.
	let mut signature = vec![u64::MAX; num_perm];
	for shingle in &shingles {
		let base = hash_bytes(shingle, seed);
		for (slot, sig) in signature.iter_mut().enumerate() {
			let h = splitmix64(base ^ (slot as u64).wrapping_mul(0x9E37_79B9_7F4A_7C15));
			if h < *sig {
				*sig = h;
			}
		}
	}
	Ok(signature)
}

/// The Jaccard similarity two MinHash signatures estimate.
///
/// Returns NaN when either signature is empty, because a similarity to nothing
/// is not zero.
pub fn jaccard_estimate(a: &[u64], b: &[u64]) -> f64 {
	if a.len() != b.len() {
		return f64::NAN;
	}
	if a.is_empty() {
		return f64::NAN;
	}
	let matches = a.iter().zip(b).filter(|(x, y)| x == y).count();
	matches as f64 / a.len() as f64
}

/// Band and row counts for a target threshold.
///
/// `bands * rows == num_perm`. The chosen split maximises the probability that
/// a pair at `threshold` collides, which is the standard LSH optimisation: the
/// probability of a band collision is `1 - (1 - s^rows)^bands`.
pub fn optimal_bands_rows(threshold: f64, num_perm: usize) -> (usize, usize) {
	let mut best = (1usize, num_perm);
	let mut best_score = f64::NEG_INFINITY;
	for bands in 1..=num_perm {
		if num_perm % bands != 0 {
			continue;
		}
		let rows = num_perm / bands;
		// Score: separation between the collision probability at the threshold
		// and at a clearly-different similarity. Maximising the gap puts the
		// step where the caller asked for it.
		let at = 1.0 - (1.0 - threshold.powi(rows as i32)).powi(bands as i32);
		let off = 1.0 - (1.0 - (threshold * 0.5).powi(rows as i32)).powi(bands as i32);
		let score = at - off;
		if score > best_score {
			best_score = score;
			best = (bands, rows);
		}
	}
	best
}

/// An LSH index over MinHash signatures.
///
/// Banded: each signature is split into `bands` contiguous rows of `rows` each,
/// and two signatures are candidates when any band matches exactly. Candidate
/// pairs are then filtered by the estimated Jaccard similarity.
#[derive(Debug, Clone)]
pub struct LshIndex {
	threshold: f64,
	num_perm: usize,
	seed: u64,
	bands: usize,
	rows: usize,
	tables: Vec<HashMap<u64, Vec<String>>>,
	signatures: HashMap<String, Vec<u64>>,
}

impl LshIndex {
	/// Build an index. `threshold` is in (0, 1); band and row counts are derived
	/// from it and `num_perm`, never passed, because a caller-chosen split that
	/// does not multiply to `num_perm` is a silent hole in the index.
	pub fn new(threshold: f64, num_perm: usize, seed: u64) -> Self {
		let (bands, rows) = optimal_bands_rows(threshold.clamp(0.01, 0.99), num_perm);
		Self {
			threshold,
			num_perm,
			seed,
			bands,
			rows,
			tables: vec![HashMap::new(); bands],
			signatures: HashMap::new(),
		}
	}

	/// The derived band count.
	pub fn bands(&self) -> usize {
		self.bands
	}

	/// The derived rows per band.
	pub fn rows(&self) -> usize {
		self.rows
	}

	/// The seed this index was built with.
	pub fn seed(&self) -> u64 {
		self.seed
	}

	/// How many documents are indexed.
	pub fn len(&self) -> usize {
		self.signatures.len()
	}

	/// Whether the index holds nothing.
	pub fn is_empty(&self) -> bool {
		self.signatures.is_empty()
	}

	/// The band key for one band of a signature.
	fn band_key(&self, signature: &[u64], band: usize) -> u64 {
		let mut key = splitmix64(band as u64 ^ self.seed);
		for slot in band * self.rows..(band + 1) * self.rows {
			key = splitmix64(key ^ signature[slot]);
		}
		key
	}

	/// Insert a document and return the ids of near-duplicates already present.
	///
	/// The duplicate set is *returned*, not merely queried, so the caller cannot
	/// forget to check and index a duplicate.
	pub fn insert(&mut self, id: &str, signature: &[u64]) -> Vec<String> {
		if signature.len() != self.num_perm {
			return Vec::new();
		}
		let mut candidates: Vec<String> = Vec::new();
		for band in 0..self.bands {
			let key = self.band_key(signature, band);
			if let Some(ids) = self.tables[band].get(&key) {
				candidates.extend(ids.iter().cloned());
			}
		}
		candidates.sort();
		candidates.dedup();

		let mut duplicates: Vec<String> = candidates
			.into_iter()
			.filter(|other| {
				self.signatures
					.get(other)
					.map(|sig| jaccard_estimate(sig, signature) >= self.threshold)
					.unwrap_or(false)
			})
			.collect();
		duplicates.sort();

		for band in 0..self.bands {
			let key = self.band_key(signature, band);
			self.tables[band].entry(key).or_default().push(id.to_string());
		}
		self.signatures.insert(id.to_string(), signature.to_vec());
		duplicates
	}

	/// Ids whose estimated similarity to `signature` meets the threshold.
	pub fn query(&self, signature: &[u64]) -> Vec<String> {
		if signature.len() != self.num_perm {
			return Vec::new();
		}
		let mut candidates: Vec<String> = Vec::new();
		for band in 0..self.bands {
			let key = self.band_key(signature, band);
			if let Some(ids) = self.tables[band].get(&key) {
				candidates.extend(ids.iter().cloned());
			}
		}
		candidates.sort();
		candidates.dedup();
		let mut hits: Vec<String> = candidates
			.into_iter()
			.filter(|other| {
				self.signatures
					.get(other)
					.map(|sig| jaccard_estimate(sig, signature) >= self.threshold)
					.unwrap_or(false)
			})
			.collect();
		hits.sort();
		hits
	}

	/// The exact Jaccard of two indexed documents' shingle sets is not
	/// recoverable from signatures; this returns the signature estimate.
	pub fn similarity(&self, a: &str, b: &str) -> f64 {
		match (self.signatures.get(a), self.signatures.get(b)) {
			(Some(x), Some(y)) => jaccard_estimate(x, y),
			_ => f64::NAN,
		}
	}
}

/// Deduplicate a corpus, returning groups of ids that are near-duplicates.
///
/// The first id in each group, in input order, is the representative. Input
/// order is respected rather than sorted, because the caller's order carries
/// meaning — an official announcement ingested before a news report of it
/// should be the one kept.
pub fn deduplicate(
	documents: &[(String, String)],
	k: usize,
	num_perm: usize,
	threshold: f64,
	seed: u64,
) -> Result<Vec<Vec<String>>> {
	let mut index = LshIndex::new(threshold, num_perm, seed);
	let mut groups: Vec<Vec<String>> = Vec::new();
	let mut membership: HashMap<String, usize> = HashMap::new();

	for (id, text) in documents {
		let signature = minhash(text, k, num_perm, seed)?;
		let duplicates = index.insert(id, &signature);
		let existing = duplicates
			.iter()
			.filter_map(|d| membership.get(d).copied())
			.min();
		match existing {
			Some(group) => {
				groups[group].push(id.clone());
				membership.insert(id.clone(), group);
			}
			None => {
				membership.insert(id.clone(), groups.len());
				groups.push(vec![id.clone()]);
			}
		}
	}
	Ok(groups)
}

#[cfg(test)]
mod tests {
	use super::*;

	#[test]
	fn identical_documents_always_collide() {
		let text = "the quick brown fox jumps over the lazy dog and keeps going";
		let a = minhash(text, 5, 128, 7).unwrap();
		let b = minhash(text, 5, 128, 7).unwrap();
		assert_eq!(a, b);
		assert!((jaccard_estimate(&a, &b) - 1.0).abs() < 1e-12);
	}

	#[test]
	fn the_same_text_hashes_identically_under_a_different_seed_only_in_value() {
		let text = "alpha beta gamma delta epsilon zeta eta theta";
		let a = minhash(text, 3, 64, 1).unwrap();
		let b = minhash(text, 3, 64, 2).unwrap();
		assert_ne!(a, b, "the seed must change the signature");
		let a2 = minhash(text, 3, 64, 1).unwrap();
		assert_eq!(a, a2, "and must not change it between calls");
	}

	#[test]
	fn similar_documents_score_high_and_different_ones_low() {
		let base = "africa power pool interconnection transmission line capacity \
		            expansion planning horizon renewable generation";
		let near = "africa power pool interconnection transmission line capacity \
		            expansion planning horizon renewable generation added";
		let far = "completely unrelated text about maritime shipping logistics \
		           and container throughput at the port";
		let a = minhash(base, 3, 256, 0).unwrap();
		let b = minhash(near, 3, 256, 0).unwrap();
		let c = minhash(far, 3, 256, 0).unwrap();
		let sim_near = jaccard_estimate(&a, &b);
		let sim_far = jaccard_estimate(&a, &c);
		assert!(sim_near > 0.5, "near-duplicates scored {sim_near}");
		assert!(sim_far < 0.1, "unrelated documents scored {sim_far}");
	}

	#[test]
	fn estimate_error_falls_with_more_permutations() {
		let base = "one two three four five six seven eight nine ten eleven twelve";
		let other = "one two three four five six seven eight nine ten eleven thirteen";
		let mut previous = f64::NAN;
		for num_perm in [16usize, 64, 256, 1024] {
			let a = minhash(base, 2, num_perm, 0).unwrap();
			let b = minhash(other, 2, num_perm, 0).unwrap();
			let estimate = jaccard_estimate(&a, &b);
			// The true Jaccard here is 10/13 = 0.769.
			let error = (estimate - 10.0 / 13.0).abs();
			if previous.is_finite() {
				assert!(error <= previous + 0.1, "error grew: {error} > {previous}");
			}
			previous = error;
		}
	}

	#[test]
	fn empty_document_does_not_match_everything() {
		let empty = minhash("", 3, 64, 0).unwrap();
		assert!(empty.iter().all(|v| *v == u64::MAX));
		let text = minhash("a real document with actual words in it", 3, 64, 0).unwrap();
		assert!(jaccard_estimate(&empty, &text) < 0.2);
	}

	#[test]
	fn short_document_still_hashes() {
		let short = minhash("hi", 5, 32, 0).unwrap();
		assert_eq!(short.len(), 32);
		assert!(short.iter().any(|v| *v != u64::MAX));
	}

	#[test]
	fn zero_k_or_num_perm_is_refused() {
		assert!(minhash("text", 0, 64, 0).is_err());
		assert!(minhash("text", 3, 0, 0).is_err());
	}

	#[test]
	fn bands_times_rows_is_num_perm() {
		for num_perm in [64usize, 128, 256] {
			for threshold in [0.3f64, 0.5, 0.7, 0.9] {
				let (bands, rows) = optimal_bands_rows(threshold, num_perm);
				assert_eq!(bands * rows, num_perm);
				assert!(bands >= 1 && rows >= 1);
			}
		}
	}

	#[test]
	fn index_finds_near_duplicates_and_not_others() {
		let mut index = LshIndex::new(0.5, 128, 0);
		let a = minhash(
			"kenya geothermal expansion adds three hundred megawatts to the grid",
			3,
			128,
			0,
		)
		.unwrap();
		let b = minhash(
			"kenya geothermal expansion adds three hundred megawatts to the grid now",
			3,
			128,
			0,
		)
		.unwrap();
		let c = minhash(
			"namibia solar tender attracts eleven bidders for the first phase",
			3,
			128,
			0,
		)
		.unwrap();
		assert!(index.insert("a", &a).is_empty());
		let dups = index.insert("b", &b);
		assert_eq!(dups, vec!["a".to_string()]);
		assert!(index.insert("c", &c).is_empty());
	}

	#[test]
	fn deduplicate_groups_by_input_order() {
		let documents = vec![
			("official".to_string(), "ghana grid company announces a tariff review for the coming quarter".to_string()),
			("news".to_string(), "ghana grid company announces a tariff review for the coming quarter".to_string()),
			("other".to_string(), "tanzania signs a power purchase agreement for a wind farm".to_string()),
		];
		let groups = deduplicate(&documents, 3, 128, 0.5, 0).unwrap();
		assert_eq!(groups.len(), 2);
		assert_eq!(groups[0][0], "official", "the first in input order is kept");
		assert!(groups[0].contains(&"news".to_string()));
	}

	#[test]
	fn determinism_across_seeds_is_explicit_not_accidental() {
		// The same corpus and seed must give the same grouping, twice, in the
		// same process. Cross-process determinism is covered by the CI job.
		let documents = vec![
			("x".to_string(), "repeated words repeated words repeated words here".to_string()),
			("y".to_string(), "repeated words repeated words repeated words here".to_string()),
		];
		let first = deduplicate(&documents, 3, 64, 0.5, 42).unwrap();
		let second = deduplicate(&documents, 3, 64, 0.5, 42).unwrap();
		assert_eq!(first, second);
	}

	#[test]
	fn splitmix_has_no_obvious_fixed_point() {
		assert_ne!(splitmix64(0), 0);
		assert_ne!(splitmix64(1), 1);
		let a = splitmix64(12345);
		let b = splitmix64(12346);
		assert!(a.abs_diff(b) > 1_000_000, "adjacent inputs must not be adjacent");
	}
}

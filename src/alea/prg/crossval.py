# SPDX-License-Identifier: MIT
"""Cross-validation rules: conditions that span more than one parameter.

WHY this is a separate module from ``graph.consistency``. ``consistency``
checks each *equation* against its own tolerance. A cross-validation rule is
not an equation: it relates two parameters that no equation couples -- a carbon
price and a retirement date, a reserve margin and a renewable target -- and the
graph is internally consistent whether or not the rule holds. ``alea_prg.md``
§25 is explicit that these sit "beyond equation-level consistency", which is
exactly why they need their own home: an equation-level check cannot report a
finding about a relationship no equation states.

WHY the rule is declared as text and parsed, not written as Python. The spec's
rules are conditions over named parameters with a severity and a message:

    if carbon_price > 100 and coal_retirement_schedule > 2045: warning

A rule stored as a callable would be unreviewable by the person who owns the
policy, and the graph's whole design principle is that the YAML a human edits
and the object the engine runs are the same artefact. So the condition is
parsed from the same text a reader sees, through Python's ``ast`` with a
whitelist -- the *same* whitelist discipline as the DSL, extended with the
comparison and boolean operators a condition needs, which is the one place the
DSL's arithmetic-only grammar does not reach.

WHY a rule that cannot be evaluated is a finding, not a skip. A condition
naming a parameter the graph does not hold, or one whose value the scenario
does not carry, is a rule the check could not run -- and a check that silently
dropped it would report "no cross-validation findings" for a rule it never
tested, which is the same clean-bill-of-health failure ``units.undecidable``
exists to prevent. So the register is carried alongside the verdicts: the
caller sees how many rules were evaluated and which were not.

WHY the severity is a tier and not a boolean. The spec's three severities are
not decoration: ``error`` is a scenario a reviewer should refuse, ``warning`` is
one worth a second look, and ``info`` is recorded and blocks nothing. Collapsing
them to "violated" would make the check unusable as a gate, because the one
severity that must stop a run would be indistinguishable from the one that must
not.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Mapping

from alea.prg.dsl import DslError

if TYPE_CHECKING:  # pragma: no cover - typing only
	from alea.prg.graph import ParameterGraph

__all__ = [
	"CrossValidationFinding",
	"CrossValidationReport",
	"CrossValidationRule",
	"Severity",
	"evaluate_condition",
	"parse_rule",
	"rules_from_document",
	"run_rules",
]


class Severity(StrEnum):
	"""How a violated rule should be treated.

	The spec's three tiers, and the order is the ranking: ``ERROR`` is a
	scenario a reviewer should refuse, ``WARNING`` is one worth a second look,
	``INFO`` is recorded and never blocks.
	"""

	ERROR = "error"
	WARNING = "warning"
	INFO = "info"


#: The comparison operators a condition may use, mapped to their callables.
#: A whitelist, not ``eval``: the alternative to naming what is allowed is
#: running whatever the YAML contains.
_COMPARISONS: dict[type[ast.cmpop], Any] = {
	ast.Lt: lambda a, b: a < b,
	ast.LtE: lambda a, b: a <= b,
	ast.Gt: lambda a, b: a > b,
	ast.GtE: lambda a, b: a >= b,
	ast.Eq: lambda a, b: a == b,
	ast.NotEq: lambda a, b: a != b,
}

#: The AST nodes a condition may contain. Arithmetic is deliberately *absent*:
#: a condition is a comparison over named parameters, and an expression like
#: ``a * b > c`` is an equation the graph should state, not a rule buried in a
#: condition where nothing checks it dimensionally. Naming the allowed set is
#: what makes this safe without ``eval``.
#:
#: ``USub``/``UAdd`` are here because ``-1.5`` parses as ``USub(Constant(1.5))``,
#: and a parameter whose declared range is ``(-3.0, 0.0)`` -- ``price_elasticity``
#: is one -- has to be comparable against a negative number. They are *not*
#: general negation: :func:`_eval` accepts them only on a constant, so ``-a``
#: stays out and no arithmetic enters the grammar through the back door.
_ALLOWED = (
	ast.Expression,
	ast.BoolOp,
	ast.And,
	ast.Or,
	ast.UnaryOp,
	ast.Not,
	ast.USub,
	ast.UAdd,
	ast.Compare,
	ast.Name,
	ast.Constant,
	ast.Load,
	*_COMPARISONS,
)

#: ``if <condition>: <severity>`` -- the spec's declaration form, verbatim.
_RULE = re.compile(
	r"^\s*(?:if\s+)?(?P<condition>.+?)\s*:\s*(?P<severity>\w+)\s*$",
	re.IGNORECASE,
)


@dataclass(frozen=True)
class CrossValidationRule:
	"""One declared rule: a condition, what it means, and how to treat it."""

	id: str
	condition: str
	"""The condition as text, so the rule renders as the author wrote it."""

	severity: Severity
	message: str
	suggestion: str = ""
	parameters: frozenset[str] = frozenset()
	"""Every parameter the condition names, read off the parsed tree."""

	def __str__(self) -> str:
		return f"{self.id} [{self.severity.value}]: if {self.condition} -- {self.message}"


@dataclass(frozen=True)
class CrossValidationFinding:
	"""One rule that a scenario violates, or one that could not be run."""

	rule: CrossValidationRule
	detail: str = ""

	@property
	def severity(self) -> Severity:
		return self.rule.severity

	@property
	def evaluated(self) -> bool:
		"""Whether the condition was actually run.

		``False`` for a rule naming a parameter the scenario does not carry. A
		finding with ``evaluated=False`` is not a violation -- it is a rule the
		check could not decide, and reporting it as a pass is the failure this
		field exists to prevent.
		"""
		return not self.detail

	def __str__(self) -> str:
		if self.detail:
			return f"{self.rule.id} [{self.rule.severity.value}]: {self.detail}"
		head = f"{self.rule.id} [{self.rule.severity.value}]: {self.rule.message}"
		if self.rule.suggestion:
			head += f" (try: {self.rule.suggestion})"
		return head


@dataclass(frozen=True)
class CrossValidationReport:
	"""Every rule's verdict, with the counts that say how much was covered."""

	findings: tuple[CrossValidationFinding, ...]
	rules: tuple[CrossValidationRule, ...]
	"""Every rule considered, so a caller can see the denominator."""

	def of_severity(self, severity: Severity) -> tuple[CrossValidationFinding, ...]:
		return tuple(f for f in self.findings if f.severity is severity)

	@property
	def violations(self) -> tuple[CrossValidationFinding, ...]:
		"""Rules a scenario violated, excluding the ones that could not run."""
		return tuple(f for f in self.findings if f.evaluated)

	@property
	def undecided(self) -> tuple[CrossValidationFinding, ...]:
		"""Rules the scenario did not carry the parameters to evaluate."""
		return tuple(f for f in self.findings if not f.evaluated)

	@property
	def blocks(self) -> bool:
		"""Whether any ``error``-severity rule was violated.

		The one question a gate asks, answered without the caller having to
		know which severities block.
		"""
		return any(f.severity is Severity.ERROR for f in self.violations)

	def summary(self) -> str:
		if not self.rules:
			return "no cross-validation rules declared"
		if not self.findings:
			return f"all {len(self.rules)} cross-validation rule(s) hold"
		parts: list[str] = []
		for severity in (Severity.ERROR, Severity.WARNING, Severity.INFO):
			count = len(self.of_severity(severity))
			if count:
				parts.append(f"{count} {severity.value}")
		head = ", ".join(parts)
		if self.undecided:
			head += f"; {len(self.undecided)} not decided (the scenario does not carry their parameters)"
		return f"{len(self.violations)} of {len(self.rules)} rule(s) violated: {head}"


def evaluate_condition(condition: str, values: Mapping[str, float]) -> bool:
	"""Evaluate a cross-validation condition at ``values``.

	``True`` means the condition *holds* -- which for a rule declared as
	``if <condition>: <severity>`` is the bad state, the one the severity
	applies to. The caller fires a finding on ``True``; see
	:func:`run_rules`, where reading it the other way inverted every rule.

	Raises :class:`DslError` for a condition outside the allowed grammar, and
	for one naming a parameter the set does not carry. Both are the caller's
	to turn into a finding: a condition that cannot be run is a fact about the
	rule, not an answer.
	"""
	try:
		tree = ast.parse(condition.strip(), mode="eval")
	except SyntaxError as exc:
		raise DslError(
			f"{condition!r} is not a valid condition: {exc.msg}"
		) from exc
	for node in ast.walk(tree):
		if not isinstance(node, _ALLOWED):
			raise DslError(
				f"{type(node).__name__} is not part of a cross-validation "
				f"condition; a condition compares named parameters with "
				f"< <= > >= == != and joins them with and/or/not"
			)
	result = _eval(tree.body, values)
	if isinstance(result, bool):
		return result
	# A bare parameter or a number is not a condition. `if renewable_target:`
	# reads as "when it is set" and means "when it is non-zero", which is not a
	# rule anybody intends -- so it is refused rather than guessed.
	raise DslError(
		f"{condition!r} is not a condition: it evaluates to {result!r}, and a "
		f"rule must be a comparison, not a value"
	)


def _eval(node: ast.AST, values: Mapping[str, float]) -> Any:
	if isinstance(node, ast.BoolOp):
		operands = [_eval(value, values) for value in node.values]
		if isinstance(node.op, ast.And):
			return all(operands)
		return any(operands)
	if isinstance(node, ast.UnaryOp):
		if isinstance(node.op, ast.Not):
			return not _eval(node.operand, values)
		# A sign on a *constant* only. `-1.5` is USub(Constant(1.5)) and has to
		# be expressible; `-a` is arithmetic on a parameter, which the grammar
		# keeps out so a rule cannot smuggle in an expression the graph should
		# be stating as an equation.
		if isinstance(node.op, (ast.USub, ast.UAdd)):
			if not isinstance(node.operand, ast.Constant):
				raise DslError(
					f"a sign is allowed only on a number, not on "
					f"{type(node.operand).__name__}; arithmetic on a parameter "
					f"belongs in an equation, where the graph checks it"
				)
			magnitude = _eval(node.operand, values)
			return -magnitude if isinstance(node.op, ast.USub) else magnitude
		raise DslError(f"unsupported unary operator {type(node.op).__name__}")
	if isinstance(node, ast.Compare):
		# Chained comparisons evaluate left to right with short-circuiting, the
		# same as Python: `a < b < c` is `a < b and b < c`, and evaluating all
		# pairs would report a comparison Python never makes.
		left = _eval(node.left, values)
		for operator, comparator in zip(node.ops, node.comparators):
			right = _eval(comparator, values)
			if type(operator) not in _COMPARISONS:
				raise DslError(
					f"unsupported comparison {type(operator).__name__}"
				)
			if not _COMPARISONS[type(operator)](left, right):
				return False
			left = right
		return True
	if isinstance(node, ast.Name):
		if node.id not in values:
			raise DslError(
				f"the condition names {node.id!r}, which the parameter set does "
				f"not carry"
			)
		return values[node.id]
	if isinstance(node, ast.Constant):
		if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
			raise DslError(f"{node.value!r} is not a number")
		return node.value
	raise DslError(f"cannot evaluate {type(node).__name__} in a condition")


def parse_rule(
	rule_id: str,
	declaration: str | Mapping[str, Any],
	*,
	message: str = "",
	severity: str | None = None,
	suggestion: str = "",
) -> CrossValidationRule:
	"""Parse one rule, from the spec's one-line form or from a mapping.

	``declaration`` is either ``"if a > 1 and b < 2: warning"`` -- the form
	``alea_prg.md`` §25 writes -- or a mapping with ``condition``, ``severity``,
	``message`` and ``suggestion`` keys. Both are accepted because the spec
	shows the one-liner in its YAML and the message and suggestion are separate
	fields in the same example; a reader should not have to choose.
	"""
	condition = ""
	fields: dict[str, str] = {}
	if isinstance(declaration, Mapping):
		condition = str(declaration.get("condition", "")).strip()
		fields = {
			key: str(declaration[key])
			for key in ("severity", "message", "suggestion")
			if declaration.get(key) is not None
		}
	else:
		match = _RULE.match(str(declaration))
		if match is None:
			raise DslError(
				f"rule {rule_id!r}: {declaration!r} is not "
				f"'<condition>: <severity>' and not a mapping"
			)
		condition = match.group("condition").strip()
		fields = {"severity": match.group("severity")}
	if severity is not None:
		fields["severity"] = severity
	if message:
		fields["message"] = message
	if suggestion:
		fields["suggestion"] = suggestion
	if not condition:
		raise DslError(f"rule {rule_id!r} declares no condition")
	raw_severity = fields.get("severity", "warning").strip().lower()
	try:
		parsed_severity = Severity(raw_severity)
	except ValueError as exc:
		raise DslError(
			f"rule {rule_id!r}: severity {raw_severity!r} is not one of "
			f"{[s.value for s in Severity]}"
		) from exc
	# Parse once here so a malformed condition is a load error rather than a
	# surprise inside a check -- the same rule `graph._validate` applies to
	# every equation.
	parameters = _parameters_of(condition)
	return CrossValidationRule(
		id=rule_id,
		condition=condition,
		severity=parsed_severity,
		message=fields.get("message") or f"if {condition}",
		suggestion=fields.get("suggestion", ""),
		parameters=frozenset(parameters),
	)


def _parameters_of(condition: str) -> set[str]:
	"""Every parameter name a condition names, from its parsed tree."""
	try:
		tree = ast.parse(condition.strip(), mode="eval")
	except SyntaxError as exc:
		raise DslError(f"{condition!r} is not a valid condition: {exc.msg}") from exc
	for node in ast.walk(tree):
		if not isinstance(node, _ALLOWED):
			raise DslError(
				f"{type(node).__name__} is not part of a cross-validation "
				f"condition; a condition compares named parameters with "
				f"< <= > >= == != and joins them with and/or/not"
			)
	# The reserved words a BoolOp carries are not parameters, and neither are
	# the comparison node types; only `Name` nodes are, which is what this
	# walks for rather than filtering a wider set.
	return {
		node.id
		for node in ast.walk(tree)
		if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
	}


def rules_from_document(document: Mapping[str, Any]) -> tuple[CrossValidationRule, ...]:
	"""Every rule a PRG document declares, from either declaration site.

	The spec puts ``cross_validation`` on the *node* (§7) and shows a
	top-level ``cross_validation:`` list (§25). Both are read: a rule declared
	on ``carbon_price`` is about the carbon price, and one declared at the top
	level is about the graph, and refusing either would make the other's rules
	silently absent.
	"""
	rules: list[CrossValidationRule] = []
	seen: set[str] = set()
	for name, body in sorted((document.get("parameters") or {}).items()):
		for index, declaration in enumerate((body or {}).get("cross_validation") or ()):
			rule = parse_rule(f"{name}.cross_validation[{index}]", declaration)
			rules.append(rule)
			seen.add(rule.id)
	for index, declaration in enumerate(document.get("cross_validation") or ()):
		rule_id = f"cross_validation[{index}]"
		if isinstance(declaration, Mapping) and declaration.get("id"):
			rule_id = str(declaration["id"])
		rule = parse_rule(rule_id, declaration)
		if rule.id in seen:
			# Two rules with one id is one rule the report cannot name twice.
			raise DslError(
				f"cross-validation rule id {rule.id!r} is declared twice; the id "
				f"is how a finding is referred to, and a duplicate makes a "
				f"finding ambiguous"
			)
		rules.append(rule)
		seen.add(rule.id)
	return tuple(rules)


def run_rules(
	rules: tuple[CrossValidationRule, ...],
	values: Mapping[str, float],
	graph: ParameterGraph | None = None,
) -> CrossValidationReport:
	"""Evaluate every rule against ``values``.

	``graph`` is optional and used only to check that a rule's parameters exist
	-- a rule naming a parameter the graph does not hold is a finding about the
	rule itself, and is reported as undecided rather than dropped.
	"""
	findings: list[CrossValidationFinding] = []
	for rule in rules:
		if graph is not None:
			unknown = rule.parameters - set(graph.nodes)
			if unknown:
				findings.append(
					CrossValidationFinding(
						rule=rule,
						detail=(
							f"names {sorted(unknown)}, which the graph does not "
							f"hold; the rule was not evaluated"
						),
					)
				)
				continue
		missing = rule.parameters - set(values)
		if missing:
			findings.append(
				CrossValidationFinding(
					rule=rule,
					detail=(
						f"the scenario does not carry {sorted(missing)}, so the "
						f"condition was not evaluated"
					),
				)
			)
			continue
		try:
			fires = evaluate_condition(rule.condition, values)
		except DslError as exc:
			findings.append(CrossValidationFinding(rule=rule, detail=str(exc)))
			continue
		# The condition describes the *bad* state, so a rule fires when it
		# holds -- "if carbon_price > 100 and coal_retirement > 2045: warning"
		# is a warning about the scenario where both are true. Reading it as a
		# requirement ("must hold") inverts every rule into a demand that the
		# scenario be pathological, and a clean graph then reports every rule
		# violated, which is exactly what happened the first time this ran.
		if fires:
			findings.append(CrossValidationFinding(rule=rule))
	return CrossValidationReport(findings=tuple(findings), rules=rules)

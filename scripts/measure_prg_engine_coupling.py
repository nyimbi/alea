# SPDX-License-Identifier: MIT
"""Count how many PRG parameters reach the solver, and by which channel.

Channels: an engine knob (``translate.translated``) and a constraint term
(``constraints.bound_parameter_names``). Everything else the graph holds is
connected to other nodes but moves no solver input. Prints the measured values;
quote those, not a remembered figure.
"""

from collections import Counter

from alea.prg import constraints, load_graph, translate


def main() -> None:
	g = load_graph()
	nodes = set(g.nodes)
	settable = {n for n in nodes if g.is_settable(n)}
	knob = set(translate.translated(g))
	bound = set(constraints.bound_parameter_names(g)) & nodes
	reach = (knob | bound) & settable
	assert settable, "no settable parameters: the graph did not load"
	print(f"nodes={len(nodes)} settable={len(settable)} derived={len(g.computed())} endogenous={len(g.endogenous())}")
	print(f"engine knobs={len(knob)} of {len(translate.coverage(g)['engine_unreached']) + len(translate.translations())} fields")
	print(f"constraint terms={len(bound)} over {len(constraints.bound_routes(g))} bound inequality routes")
	print(f"knob and constraint overlap={len(knob & bound)}")
	print(f"settable reaching the engine={len(reach)} of {len(settable)} ({len(reach) / len(settable):.1%})")
	print(f"settable reaching no solver input={len(settable - reach)}")
	# `bound` means every term is a settable scalar; it does not mean the route
	# reaches the optimiser. Only routes reading a network-sourced symbol can.
	opt_terms = set(constraints.optimiser_parameter_names(g)) & settable
	opt_reach = (knob | opt_terms) & settable
	print(f"optimiser routes={len(constraints.optimiser_routes(g))} of {len(constraints.bound_routes(g))} bound")
	print(f"settable that can move the optimiser={len(opt_reach)} of {len(settable)} ({len(opt_reach) / len(settable):.1%})")
	# `reach` per settable parameter: knob, constraint, both, or none. `none`
	# splits by whether the parameter determines any derived node (a parameter in an inequality only determines nothing). The post-solve
	# audit is not a channel here: it checks the identities of the parameters a
	# result supplies (`audit.parameters_from_result`), which no graph property
	# can enumerate, so claiming "audit" from the graph alone would be invented.
	def reach_of(name: str) -> str:
		if name in knob and name in bound:
			return "knob+constraint"
		if name in knob:
			return "knob"
		if name in bound:
			return "constraint"
		return "none:feeds-derived" if g.affects(name) else "none:no-descendant"

	counts = Counter(reach_of(n) for n in settable)
	for label in ("knob", "constraint", "knob+constraint", "none:feeds-derived", "none:no-descendant"):
		print(f"reach {label}={counts.get(label, 0)}")
	assert sum(counts.values()) == len(settable)
	by_system: Counter[str] = Counter()
	for name in settable - reach:
		by_system[g.nodes[name].category or "uncategorised"] += 1
	for category, count in by_system.most_common(5):
		print(f"none by category: {category}={count}")


if __name__ == "__main__":
	main()

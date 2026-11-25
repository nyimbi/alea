# SPDX-License-Identifier: MIT
"""Count how many PRG parameters reach the solver, and by which channel.

Channels: an engine knob (``translate.translated``) and a constraint term
(``constraints.bound_parameter_names``). Everything else the graph holds is
connected to other nodes but moves no solver input. Prints the measured values;
quote those, not a remembered figure.
"""

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


if __name__ == "__main__":
	main()

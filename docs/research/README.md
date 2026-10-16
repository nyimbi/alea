# Research notes

Working notes on a question that is not yet a decision: an external API, a
schema change, a library's behaviour under our load, a paper whose claim a plan
depends on. One directory per slug, holding a `README.md` with the question, the
sources consulted, the decision, and the options rejected.

The distinction from `sources/` is the point of having both. `sources/` is the
archive of things the code *cites* -- a paper, a vendor document, a dataset
licence -- with an `INDEX.md` recording where each came from, and
`alea.provenance.citations` joins an archived file to the equations that rely on
it. A note here cites nothing yet; it is the reasoning that decides whether
something gets cited at all. When a note settles, the artefact it settles on goes
to `sources/` and the note links to it.

Delete nothing here. A rejected option is the most expensive thing to rediscover,
which is why `00-architecture.md` §6 declares this directory and why
`alea.quality.layout` fails the build if the declaration goes stale.

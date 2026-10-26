# bibliopolis-open — repository card

Public, MIT. The open extraction of Bibliopolis (文獻城邦): turn a literature collection into a city-state. Two modes: a Zotero
library as a city (the collection tree is the street plan) and a city grown from zero (data-driven roads of 10 to 40 houses that
split as they grow).

## Owner and flow

- Canonical development happens in a private repository; changes arrive here as re-extractions that pass the scrub gate. Do not
  develop a feature here that the private engine lacks without saying so in the commit.
- Everything here is public the moment it is pushed. Nothing private enters: no personal data, no host names, paths, service
  names, database names, task or card numbers, credentials, private conversations, or content derived from paywalled full text.
- Journal names appear only descriptively in data or docs, never in a product name, identifier, logo or package name.

## Rules

- Text and code only in Git, no Git LFS. The one exception is `docs/images/`: pictures generated from the sample are SVG (text, made by `examples/make_pictures.py`); screenshots of the viewer are PNG/JPG/WebP in `docs/images/` only, small (under 1 MB each).
- Source-generic: no journal-specific assumption in the engine.
- Fixtures are synthetic (`10.0000/...` DOIs, sample titles and authors).
- Code and agent docs in English; human-facing copy in English and Traditional Chinese (Taiwan terms).
- No GitHub Actions workflows. Run the local tests and the scrub gate before every push.

## Layout and checks

- `bibliopolis/` the package (Python 3.11+, standard library only): `inputs` (read and check the files), `cut` and `plan` (the directions),
  `world` (the growing city), `document` and `layout` and `coast` (the document), `picture` (the SVG), `city` and `cli`. Rules: `docs/engine.md`;
  formats: `docs/format.md` and `schema/`.
- `examples/` the seeded generator of the synthetic sample (`make_example.py`) and its output; a derived city is never committed. `make_pictures.py` makes
  `docs/images/*.svg` from the sample; a test compares them with the committed files byte for byte, so run it after a change to the engine or the sample.
- `tests/`: `python -m pytest` from the repository root. Every test is offline and synthetic.
- The plan, the world of `grow` mode (roads, direct counts, root zone, chronicle, lots, ribs, lines) and the document it makes (places, roads, coast,
  measures) are an extraction of the private engine. A parity test in the private repository compares them with it on random libraries and on the
  sample (the whole document against a private plan without the journal sector). Not compared, because the private engine has nothing to compare
  with: the input checks, the mirror mode (and `complete`), the command line and its summary, the `at` dates of the chronicle, the replay (`first`), the
  chronicle sentences, the picture and the pictures. A change there says so in its commit.
- No third-party code or data is copied in. Two textbook algorithms (largest-remainder apportionment, Douglas-Peucker simplification) are
  implemented here, and the sample is generated from invented word lists.

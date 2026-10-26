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

- Text and code only in Git, no Git LFS. The one exception is PNG images directly under `docs/images/`, at most 1 MiB (1,048,576 bytes) each, pixels only:
  the screenshots of the viewer. Pictures generated from the sample are SVG (text, made by `examples/make_pictures.py`). JPG, WebP and every other binary stay out.
- Source-generic: no journal-specific assumption in the engine.
- Fixtures are synthetic (`10.0000/...` DOIs, sample titles and authors).
- Code and agent docs in English; human-facing copy in English and Traditional Chinese (Taiwan terms).
- No GitHub Actions workflows. Run the local tests and the scrub gate before every push.

## Layout and checks

- `bibliopolis/` the package (Python 3.11+, standard library only): `inputs` (read and check the files), `cut` and `plan` (the directions),
  `world` (the growing city), `document` and `layout` and `coast` (the document), `picture` (the SVG), `city` and `cli`; `canonical` (the one number form of
  every document written). The world built by hand: `events` (the log and its checks), `hand` (the fold), `journal` (append, the world file), `suggest`,
  `store` (SQLite, the home folder). Rules: `docs/engine.md` and `docs/world.md` (with the notes for a port); formats: `docs/format.md` and `schema/` (the library, the tree and, for a world built by hand, `schema/world.schema.json`).
- `examples/` the seeded generator of the synthetic sample (`make_example.py`) and its output; a derived city is never committed. `make_pictures.py` makes
  `docs/images/*.svg` from the sample; a test compares them with the committed files byte for byte, so run it after a change to the engine or the sample.
  `make_worlds.py` makes the three golden world files (`scripted.world.json`, `scripted_nodes.world.json`, `scripted_merge.world.json`) and their index `worlds.json`
  (the sha256 of each file and of the city it folds to), which a port folds; a test compares them byte for byte and with the pins. No city is committed.
- `tests/`: `python3 -m pytest` from the repository root. Every test is offline and synthetic.
- The plan, the world of `grow` mode (roads, direct counts, root zone, chronicle, lots, ribs, lines) and the document it makes (places, roads, coast,
  measures) are an extraction of the private engine. A parity test in the private repository compares them with it on random libraries and on the
  sample (the whole document against a private plan without the journal sector). Not compared, because the private engine has nothing to compare
  with: the input checks (and the checks of a city file), the mirror mode (and `complete`), the command line and its summary, the `at` dates of the
  chronicle, the replay (`first`), the chronicle sentences, and the whole world built by hand (the event log and its fold, the golden-angle sectors,
  undo, the suggestions, the world file and the SQLite store; its tests pin the sha256 of a scripted world and of the sample cities). `picture` is a
  rewrite of the private SVG renderer (the plan view of a layout v4 document), not an extraction, and it is not under parity either; the pictures of the
  README are made here, from the sample. A change to any of these says so in its commit.
- No third-party code or data is copied in. Two textbook algorithms (largest-remainder apportionment, Douglas-Peucker simplification) are
  implemented here, and the sample is generated from invented word lists.

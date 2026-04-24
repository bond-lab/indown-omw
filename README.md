# indown-omw

Convert the [IndoWordNet](https://www.cfilt.iitb.ac.in/indowordnet/) to
[GWA LMF](https://globalwordnet.github.io/schemas/) format so all 18 languages
can be loaded via the Python [`wn`](https://wn.readthedocs.io) library.

## Overview

IndoWordNet (IWN) synsets are linked to the Princeton WordNet 2.1 via a
Hindi–English mapping file.  The build pipeline:

1. Maps each IWN synset through PWN 2.1 → PWN 3.0 → OMW ILI.
2. Assigns each synset one of three link types:
   - **equal** – direct ILI equivalence
   - **hyper** – IWN synset is a hyponym of the English concept
   - **dupe** – multiple IWN synsets map to the same ILI (lexical distinctions
     that English conflates)
3. Writes one LMF XML file per language (`build/iwn-{lang}-1.0.xml`).

Each output file is a self-contained
[WN-LMF 1.1](https://globalwordnet.github.io/schemas/) lexicon, ready for
`wn.add()` or packaging as an OMW collection.

## Prerequisites

- [`uv`](https://docs.astral.sh/uv/) (Python package runner)
- [`pyiwn`](https://github.com/riteshpanjwani/pyiwn) — downloads IndoWordNet
  data to `~/iwn_data` on first use
- `wget` and `git` (for fetching mapping data)
- Internet access on the first run

## Build

```bash
bash build.sh
```

The script is idempotent: external data is only downloaded once.

### What the build does

| Step | Script | Output |
|------|--------|--------|
| Clone IWN-En mapping repo | `git clone` | `etc/IWN-En/` |
| Fix malformed TSV | `scripts/fix_malformed_tsv.py` | `etc/IWN-En/data/english-hindi-linked-fixed.tsv` |
| Download UPC PWN 2.1→3.0 maps | `wget` | `etc/mappings-upc-2007/` |
| Build IWN → ILI mapping | `scripts/map2ili.py` | `build/iwn2ili.yaml` |
| Convert all 18 languages to LMF | `scripts/iwn2omw.py` | `build/iwn-{lang}-1.0.xml` |
| Validate LMF files | `python -m wn validate` | `build/*.xml.report.json` |

### Scripts

| File | Purpose |
|------|---------|
| `scripts/fix_malformed_tsv.py` | Patches split lines and a bad relation tag in the IWN-En TSV |
| `scripts/map2ili.py` | Maps IWN synset IDs to ILIs via PWN 2.1→3.0 offsets; detects duplicates |
| `scripts/validation.py` | Lemma and gloss overlap checks (used by `map2ili.py --validate`) |
| `scripts/iwn2omw.py` | Converts all 18 IWN languages to WN-LMF 1.1 XML |

## Validate mappings

Pass `--validate` to `map2ili.py` to check that ILI assignments agree with
OMW-EN on lemmas and glosses:

```bash
uv run --with-requirements requirements.txt scripts/map2ili.py --validate
# or on a random sample:
uv run --with-requirements requirements.txt scripts/map2ili.py --validate-sample 500
```

## Tests

```bash
uv run tests/test_indown.py
```

`tests/test_indown.py` loads the generated Hindi LMF file and checks specific
synsets for correct ILI assignments, lemma lists, definitions, and examples.
Add new test cases to `TEST_CASES` in that file to cover additional languages
or synset properties.

## Output

After a successful build, `build/` contains:

- `iwn-{lang}-1.0.xml` — LMF XML for each of the 18 languages
- `iwn2ili.yaml` — full IWN → ILI mapping (equal / hyper / dupe)
- `iwn_issues.yaml` — data quality issues found during mapping
- `iwn_data_issues.yaml` — per-language bad POS tags and malformed lemmas
- `*.xml.report.json` — WN-LMF schema validation reports

## Packaging for `wn`

To distribute as a collection loadable by the `wn` module, package each
language into its own directory alongside a LICENSE and citation file:

```
indown-omw/
├── iwn-hi/
│   ├── iwn-hi-1.0.xml
│   ├── LICENSE.md
│   └── citation.bib
├── iwn-bn/
│   └── ...
├── LICENSE
└── README.md
```

Then compress the collection:

```bash
tar cJf indown-omw-1.0.tar.xz indown-omw/
```

See the [`wordnet-release` packaging guide](https://wn.readthedocs.io/en/latest/guides/lexicons.html#wn-lmf-files-packages-and-collections) for details.

## Languages

The 18 IndoWordNet languages covered:

| Language | Code |
|----------|------|
| Assamese | as |
| Bengali | bn |
| Bodo | brx |
| Gujarati | gu |
| Hindi | hi |
| Kannada | kn |
| Kashmiri | ks |
| Konkani | kok |
| Malayalam | ml |
| Marathi | mr |
| Meitei (Manipuri) | mni |
| Nepali | ne |
| Odia | or |
| Punjabi | pa |
| Sanskrit | sa |
| Tamil | ta |
| Telugu | te |
| Urdu | ur |

## License

See [LICENSE](LICENSE).

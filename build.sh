#!/usr/bin/env bash
# build.sh
#
# Build all 18 IndoWordNet LMF files and validate them.
#
# Steps:
#   1. Download external mapping data (IWN-En, UPC PWN 2.1→3.0 mappings)
#   2. Fix malformed lines in the IWN-En TSV
#   3. Build IWN → ILI mapping (scripts/map2ili.py → build/iwn2ili.yaml)
#   4. Convert all 18 languages to LMF XML (scripts/iwn2omw.py → build/*.xml)
#   5. Validate each XML file against the WN-LMF schema

set -euo pipefail

mkdir -p etc    # downloaded external data
mkdir -p build  # generated output

### Step 1–2: Fetch and fix mapping data
pushd etc

if [ ! -d "IWN-En" ]; then
    git clone https://github.com/cfiltnlp/IWN-En.git
    python ../scripts/fix_malformed_tsv.py \
        IWN-En/data/english-hindi-linked.tsv \
        IWN-En/data/english-hindi-linked-fixed.tsv
fi

if [ ! -d "mappings-upc-2007" ]; then
    wget http://nlp.lsi.upc.edu/tools/mapp.tar.gz
    tar xfz mapp.tar.gz
    rm mapp.tar.gz
fi

popd

### Step 3: Build IWN → ILI mapping
uv run --with-requirements requirements.txt scripts/map2ili.py

### Step 4: Convert IndoWordNet to LMF
uv run --with-requirements requirements.txt scripts/iwn2omw.py

### Step 5: Validate output
for f in build/*.xml; do
    echo "Validating ${f}"
    uv run --with-requirements requirements.txt \
        python -m wn validate "${f}" --output "${f}.report.json"
done

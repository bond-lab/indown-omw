#!/bin/bash
set -e  # Exit on error

mkdir -p etc  # for downloaded data
mkdir -p build  # for created data


### get data for mapping to ILI
pushd etc

# Only clone if the repo doesn't exist
if [ ! -d "IWN-En" ]; then
    git clone https://github.com/cfiltnlp/IWN-En.git
    python fix_malformed_tsv.py IWN-En/data/english-hindi-linked.tsv \
                              IWN-En/data/english-hindi-linked-fixed.tsv
b
fi

# Only download and extract if mapp directory doesn't exist
if [ ! -d "mapp" ]; then
    wget http://nlp.lsi.upc.edu/tools/mapp.tar.gz
    tar xfz mapp.tar.gz
    rm mapp.tar.gz  # Clean up the archive after extraction
fi

popd

uv run --with-requirements requirements.txt iwn2omw.py

# Fixed: use double quotes for variable expansion
for f in build/*.xml; do
    echo "Validating ${f}"
    uv run --with-requirements requirements.txt python -m wn validate "${f}"
done

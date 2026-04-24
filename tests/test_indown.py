"""
Tests for generated IndoWordNet LMF files.

Loads the generated Hindi wordnet and checks that specific synsets have
correct ILI assignments, definitions, lemmas, and examples.

Run with: pytest tests/test_indown.py
"""
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "wn>=1.1",
#     "pytest>=8.0",
# ]
# ///

import pytest
import wn

WN_PREFIX = "iwn-hi"
WN_PATH = f"build/{WN_PREFIX}-1.0.xml"

TEST_CASES = [
    {
        'name': 'tree (पेड़) - DIRECT mapping',
        'synset_id': 'iwn-hi-s2349-n',
        'ili_id': 'i105570',
        'lemmas': "पेड़,वृक्ष,पादप,द्रुम,तरु,तरुवर,दरख़्त,दरख्त,विटप,रुक्ष,रूख,विटपी,रूँख,क्षितिज,अघ्रिप,अग,अनोकह,साखी,साखि,अमंद,अमन्द,शिखरी,शिखी,अर्क,स्कंधी,स्कन्धी,बीरो,जर्ण,पुलाकी,भूमिजात,आसना,प्रतिबंधक,प्रतिबन्धक,पल्लवी,रूखड़ा,रूखरा,नख्ल,नख़्ल".split(','),
        'dfn': 'जड़, तने, शाखा तथा पत्तियों से युक्त बहुवर्षीय वनस्पति',
        'exe': ["पेड़ मनुष्य के लिए बहुत ही उपयोगी हैं"],
    },
    {
        'name': 'kumala (कुमाला) - HYPERNYM mapping',
        'synset_id': 'iwn-hi-s23385-n',
        'ili_id': '',
        'lemmas': "कुमाला".split(','),
        'dfn': 'एक छोटा पेड़',
        'exe': ["कुमाला आषाढ़ में फूलता है तथा इसका फल खाया जाता है"],
    },
]


def _safe_remove(lexicon: str) -> None:
    try:
        wn.remove(lexicon, progress_handler=None)
    except wn.Error:
        pass


@pytest.fixture(scope="module")
def iwn_wordnet():
    """Remove any stale cached version and reload from the current build file."""
    _safe_remove(WN_PREFIX)
    wn.add(WN_PATH, progress_handler=None)
    yield wn.Wordnet(lexicon=WN_PREFIX)
    _safe_remove(WN_PREFIX)


@pytest.mark.parametrize("case", TEST_CASES, ids=lambda c: c['name'])
def test_synset(iwn_wordnet, case):
    ss = iwn_wordnet.synset(id=case['synset_id'])

    assert ss.ili == (case['ili_id'] or None), \
        f"Wrong ILI for {case['synset_id']}: got {ss.ili!r}"

    assert set(ss.lemmas()) == set(case['lemmas']), \
        f"Wrong lemmas for {case['synset_id']}: got {ss.lemmas()}"

    assert ss.definition() == case['dfn'], \
        f"Wrong definition for {case['synset_id']}: got {ss.definition()!r}"

    assert ss.examples() == case['exe'], \
        f"Wrong examples for {case['synset_id']}: got {ss.examples()}"

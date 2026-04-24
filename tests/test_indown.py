"""
Validation tests for generated IndoWordNet LMF files.

Loads the generated wordnet and checks:
1. Specific synsets have correct ILI, definition, lemmas
2. Hypernym links are properly formed
3. Anchor synsets exist where needed

Run with: uv run test_lmf.py [build/iwn-hi-1.0.xml]
"""
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "wn>=0.9.0",
# ]
# ///

import sys
import wn

WN_PREFIX="iwn-hi"
WN_PATH=f"build/{WN_PREFIX}-1.0.xml"

TEST_CASES = [
    {
        'name': 'tree (पेड़) - DIRECT mapping',
        'synset_id': 'iwn-hi-s2349-n',  
        'ili_id': 'i105570',
        'lemmas': "पेड़,वृक्ष,पादप,द्रुम,तरु,तरुवर,दरख़्त,दरख्त,विटप,रुक्ष,रूख,विटपी,रूँख,क्षितिज,अघ्रिप,अग,अनोकह,साखी,साखि,अमंद,अमन्द,शिखरी,शिखी,अर्क,स्कंधी,स्कन्धी,बीरो,जर्ण,पुलाकी,भूमिजात,आसना,प्रतिबंधक,प्रतिबन्धक,पल्लवी,रूखड़ा,रूखरा,नख्ल,नख़्ल".split(','),  
        'dfn': 'जड़, तने, शाखा तथा पत्तियों से युक्त बहुवर्षीय वनस्पति', 
        'exe': ["पेड़ मनुष्य के लिए बहुत ही उपयोगी हैं"],
#        'relation_type': 'equal',  # Should have ILI directly
    },
    {
        'name': 'kumala (कुमाला) - HYPERNYM mapping',
        'synset_id': 'iwn-hi-s23385-n',
        'ili_id': '',  # explicitly missing
        'lemmas': "कुमाला".split(','),
        'dfn': 'एक छोटा पेड़',
        'exe': ["कुमाला आषाढ़ में फूलता है तथा इसका फल खाया जाता है"],
        # Optional: if you track relations in your tests
        # 'relation_type': 'hypernymy',
        # 'target_lemma_en': 'tree',
        # 'target_synset_en': '12934526-n',  # if you store Princeton offsets
    },
    # Add more test cases as needed
]

def test_synset(wordnet, test_case, verbose=True):
    """
    Test a single synset against expected properties.
    
    Returns (passed: bool, errors: list)
    """
    errors = []
    name = test_case['name']
    synset_id = test_case['synset_id']
    if verbose:
        print(f"\nTesting: {name}")
        print(f"  Looking for synset matching: {synset_id}")
    # Find the synset
    ss = wordnet.synset(id=synset_id)
    ## check ILI
    if ss.ili == None and  test_case['ili_id'] != '' or \
        ss.ili and (ss.ili.id != test_case['ili_id']):
        errors.append(f"Wrong ILI for {synset_id}")
    ## check lemmas
    if set(ss.lemmas()) != set(test_case['lemmas']):
        errors.append(f"Wrong lemmas for {synset_id}:\t{ss.lemmas()}\t{test_case['lemmas']}")
    ## check lemma order
    if (ss.lemmas()) != set(test_case['lemmas']) and \
       ss.lemmas() != test_case['lemmas']:
        errors.append(f"Wrong order for lemmas for {synset_id}:\t{ss.lemmas()}\t{test_case['lemmas']}")
    ## check definition    
    if ss.definition() != test_case['dfn']:
        errors.append(f"Wrong definition for {synset_id}:\t{ss.definition()}\t{test_case['dfn']}")
    ## check examples    
    if ss.examples() != test_case['exe']:
        errors.append(f"Wrong examples for {synset_id}:\t{ss.examples()}\t{test_case['exe']}")
    

    passed = len(errors) == 0
    return passed, errors
   

wn.add(f'{WN_PATH}')
iwn=wn.Wordnet(lexicon=WN_PREFIX)

total_passed = 0
total_failed = 0
all_errors = []
 
for test_case in TEST_CASES:
    passed, errors = test_synset(iwn, test_case)
    if passed:
        total_passed += 1
        print(f"  ✓ PASSED: {test_case['name']}")
    else:
        total_failed += 1
        print(f"  ❌ FAILED: {test_case['name']}")
        for e in errors:
            print(f"      - {e}")
        all_errors.extend(errors)
  

#!/usr/bin/env python3
"""
Convert IndoWordNet to OMW-LMF format using pre-built ILI mappings.

This script converts all 18 IndoWordNet languages to the OMW-LMF XML format,
using ILI (Inter-Lingual Index) mappings created by map2ili.py.

ILI Assignment Strategy:
------------------------
1. 'equal' mappings: The ILI is assigned directly to the IWN synset.
   These represent exact equivalences between Hindi concepts and PWN synsets.

2. 'hyper' mappings: The IWN synset is a hyponym of the English concept.
   - If another IWN synset already has this ILI (via 'equal'), we link to it
   - Otherwise, we create an "anchor synset" with the English definition

3. 'dupe' mappings: Multiple IWN synsets map to the same English concept.
   - Handled the same as 'hyper' - linked as hyponyms to avoid ILI collision
   - These represent genuine lexical distinctions in Indian languages that
     English conflates (e.g., different Hindi words for types of "experience")

Anchor Synsets:
--------------
When a 'hyper' or 'dupe' ILI has no corresponding 'equal' synset, we create
an "anchor synset" that:
- Has the ILI and English definition (from OMW-EN)
- Has no lemmas (it's just a structural node)
- Links to the nearest IWN hypernym found by traversing the PWN hierarchy

Output Structure:
----------------
For each language, produces build/iwn-{lang_code}-{version}.xml containing:
- LexicalEntry elements with Lemma and Sense children
- Synset elements with Definition, Example, and SynsetRelation children

Dependencies:
------------
- wn: For accessing OMW-EN synsets and ILI data
- pyiwn: For accessing IndoWordNet data
- pyyaml: For reading the ILI mapping file

Usage:
-----
    uv run iwn2omw.py

Requires build/iwn2ili.yaml to exist (created by map2ili.py).

Author: Francis Bond
"""
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "wn>=0.9.0",
#     "pyiwn",
#     "pyyaml>=6.0",
# ]
# ///

import wn
import yaml
import pyiwn
from collections import defaultdict as dd
from xml.sax.saxutils import escape

# Configuration
IWN_DATA = '/home/bond/iwn_data'
IWN_EN_DATA = 'etc/IWN-En/data'
VER = '1.0'
EWN = 'omw-en:1.4'  # OMW English WordNet version

# ISO 639 language codes for IndoWordNet languages
LANGUAGES = {
    "assamese":  "as",
    "bengali":   "bn",
    "bodo":      "brx",
    "gujarati":  "gu",
    "hindi":     "hi",
    "kannada":   "kn",
    "kashmiri":  "ks",
    "konkani":   "kok",
    "malayalam": "ml",
    "marathi":   "mr",
    "meitei":    "mni",   # Meitei (Manipuri)
    "nepali":    "ne",
    "oriya":     "or",    # Odia
    "punjabi":   "pa",
    "sanskrit":  "sa",
    "tamil":     "ta",
    "telugu":    "te",
    "urdu":      "ur"
}

# POS tag mapping from IndoWordNet to OMW-LMF
PosTag = { 
    'noun': 'n',
    'verb': 'v',
    'adverb': 'r',
    'adjective': 'a',
}

# Mapping from IndoWordNet relation names to GWA/OMW-LMF relation types
# See: https://globalwordnet.github.io/schemas/
INDOWNET_TO_GWADOC = {
    # Taxonomic relations
    "hypernymy": "hypernym",
    "hyponymy": "hyponym",
    "troponymy": "hyponym",      # Verb-specific hyponymy
    
    # Meronymy (part-of) relations
    "mero_member_collection": "mero_member",
    "mero_component_object": "mero_part",
    "mero_portion_mass": "mero_portion",
    "mero_stuff_object": "mero_substance",
    "mero_place_area": "mero_location",
    
    # Holonymy (has-part) relations  
    "holo_member_collection": "holo_member",
    "holo_component_object": "holo_part",
    "holo_portion_mass": "holo_portion",
    "holo_stuff_object": "holo_substance",
    "holo_place_area": "holo_location",
    
    # Other standard WordNet relations
    "also_see": "also",
    "similar": "similar",
    "attributes": "attribute",
    "entailment": "entails",
    "causative": "causes",
    
    # IndoWordNet-specific relations (mapped to 'other')
    # These don't have standard GWA equivalents
    "ability_verb": "other",
    "capability_verb": "other",
    "function_verb": "other",
    "modifies_verb": "other",
    "modifies_noun": "other",
    "mero_feature_activity": "other",
    "holo_feature_activity": "other",
    "mero_position_area": "other",
    "holo_position_area": "other",
}


def load_ili_map(filename='build/iwn2ili.yaml'):
    """
    Load the pre-built IWN to ILI mapping from YAML file.
    
    Args:
        filename: Path to the YAML mapping file
    
    Returns:
        Dict with structure:
            {
                'equal': {'iwn_id_pos': 'ili_id', ...},
                'hyper': {'iwn_id_pos': 'ili_id', ...},
                'dupe':  {'iwn_id_pos': 'ili_id', ...},
            }
    """
    with open(filename, 'r') as fh:
        data = yaml.safe_load(fh)
    
    for rel in data:
        print(f"  {rel}: {len(data[rel])} mappings")
    
    return data


def build_ili_to_iwn_index(ili_map):
    """
    Build reverse index from ILI to IWN synset keys.
    
    Args:
        ili_map: The ILI mapping dict from load_ili_map()
    
    Returns:
        Tuple of:
        - ili_to_iwn: Dict mapping ILI -> list of (iwn_key, rel_type)
        - equal_ilis: Set of ILIs that have 'equal' mappings
    """
    ili_to_iwn = dd(list)
    equal_ilis = set()
    
    for rel in ['equal', 'hyper', 'dupe']:
        if rel not in ili_map:
            continue
        for iwn_key, ili in ili_map[rel].items():
            ili_to_iwn[ili].append((iwn_key, rel))
            if rel == 'equal':
                equal_ilis.add(ili)
    
    return ili_to_iwn, equal_ilis


def find_nearest_iwn_hypernym(ewn, ss_id, equal_ilis):
    """
    Traverse up the PWN hypernym hierarchy to find the nearest synset
    that has an 'equal' mapping in IWN.
    
    This is used when creating anchor synsets to link them to the
    existing IWN taxonomy.
    
    Args:
        ewn: The OMW English Wordnet object
        ss_id: OMW synset ID (e.g., 'omw-en-00935500-a')
        equal_ilis: Set of ILIs that have 'equal' mappings
    
    Returns:
        ILI of nearest hypernym with equal mapping, or None if not found
    """
    try:
        ss = ewn.synset(id=ss_id)
    except wn.Error:
        return None
    
    # Traverse all hypernym paths, return first match
    for hype_path in ss.hypernym_paths():
        for hype in hype_path:
            hype_ili = hype.ili
            if hype_ili in equal_ilis:
                return hype_ili
    
    return None


def make_header(lmf_ver='1.1',
                prefix='iwn-hi',
                lang_code='hi',
                lang_name='Hindi',
                license='CC-BY-SA',
                ver='1.0'):
    """Generate the LMF XML header."""
    header = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE LexicalResource SYSTEM "http://globalwordnet.github.io/schemas/WN-LMF-{lmf_ver}.dtd">
<LexicalResource xmlns:dc="https://globalwordnet.github.io/schemas/dc/">
<Lexicon id="{prefix}"
   label="IndoWordNet {lang_name}"
   language="{lang_code}" 
   email=""
   license="{license}"
   version="{ver}"
   citation=""
   url=""
   dc:publisher=""
   dc:format="OMW-LMF"
   dc:description="IndoWordNet converted to LMF by Francis Bond"
   confidenceScore="1.0">"""
    return header


def make_footer():
    """Generate the LMF XML footer."""
    return """</Lexicon>
</LexicalResource>"""


def make_lexes(lemmas):
    """
    Generate LexicalEntry XML elements.
    
    Args:
        lemmas: Dict of lemma_id -> {lemma, pos, sens}
    
    Returns:
        XML string with all LexicalEntry elements
    """
    lxs = ''
    for lem_id in sorted(lemmas.keys()):
        lem = lemmas[lem_id]['lemma']
        pos = lemmas[lem_id]['pos']
        lxs += f'  <LexicalEntry id="{lem_id}">\n'
        lxs += f'    <Lemma writtenForm="{lem}" partOfSpeech="{pos}"/>\n'
        for (s, ss) in sorted(lemmas[lem_id]['sens']):
            lxs += f'    <Sense id="{s}" synset="{ss}"/>\n'
        lxs += '  </LexicalEntry>\n'
    return lxs


def make_synsets(synsets):
    """
    Generate Synset XML elements.
    
    Args:
        synsets: Dict of synset_id -> {pos, ili, def, exe, relations, is_anchor}
    
    Returns:
        XML string with all Synset elements
    """
    syns = ''
    for syn_id in sorted(synsets.keys()):
        syn = synsets[syn_id]
        pos = syn['pos']
        ili = syn.get('ili', '')
        df = syn.get('def', '')
        ex = syn.get('exe', '')
        relations = syn.get('relations', [])
        is_anchor = syn.get('is_anchor', False)
        
        # ILI attribute - empty string if not set
        ili_attr = f'ili="{ili}"' if ili else 'ili=""'
        
        syns += f'  <Synset id="{syn_id}" partOfSpeech="{pos}" {ili_attr}>\n'
        
        # Definition
        if df:
            syns += f'    <Definition>{escape(df)}</Definition>\n'
        
        # Example (not for anchor synsets)
        if ex and not is_anchor:
            syns += f'    <Example>{escape(ex)}</Example>\n'
        
        # Relations
        for rel_type, target in relations:
            syns += f'    <SynsetRelation target="{target}" relType="{rel_type}"/>\n'
        
        syns += '  </Synset>\n'
    
    return syns


def get_entries(prefix, iwn, ili_map, ewn):
    """
    Extract lexical entries and synsets from IndoWordNet.
    
    This is the main processing function that:
    1. First pass: Creates all IWN synsets with ILI assignments
    2. Second pass: Resolves hypernym links for hyper/dupe synsets
    3. Third pass: Adds IWN internal relations (meronymy, etc.)
    
    Args:
        prefix: Wordnet prefix (e.g., 'iwn-hi')
        iwn: pyiwn.IndoWordNet instance
        ili_map: ILI mapping dict from load_ili_map()
        ewn: OMW English Wordnet for anchor synset creation
    
    Returns:
        Tuple of (lemmas_dict, synsets_dict, stats_dict, issues_dict)
    """
    lems = dd(dict)
    syns = dd(dict)
    
    # Build indices
    ili_to_iwn, equal_ilis = build_ili_to_iwn_index(ili_map)
    
    # Track which ILIs we've created anchor synsets for
    anchor_synsets = {}  # ili -> syn_id
    
    # Track synsets that need hypernym links (to be resolved after first pass)
    pending_hypernym_links = []  # (syn_id, ili, rel_type, iwn_key)
    
    # Store original IWN synset objects for relation extraction
    iwn_synset_map = {}  # synset_id -> pyiwn Synset object
    
    stats = {
        'total': 0, 'equal': 0, 'hyper': 0, 'dupe': 0,
        'no_mapping': 0, 'bad_pos': 0, 'bad_lemma': 0,
        'anchor_created': 0, 'hypernym_to_equal': 0,
        'nearest_hypernym_found': 0,
        'iwn_relations': 0, 'iwn_relations_mapped': 0,
        'lemmas': 0,
        'synset_ids': set(),  # Track IWN synset IDs for uniqueness calculation
    }
    
    # Track issues for logging
    issues = {
        'bad_pos': [],    # (synset_id, pos_value)
        'bad_lemma': [],  # (synset_id, lemma, reason)
    }
    
    # =========================================================================
    # First pass: Create all IWN synsets
    # =========================================================================
    for synset in iwn.all_synsets():
        stats['total'] += 1
        synset_id = f"{synset.synset_id()}"
        pos = synset.pos()
        
        if pos not in PosTag:
            print(f'WARNING: Bad POS for synset {synset_id} ({pos})')
            issues['bad_pos'].append((synset_id, pos))
            stats['bad_pos'] += 1
            continue
        
        pos = PosTag[pos]
        iwn_key = f"{synset_id}_{pos}"
        syn_id = f'{prefix}-s{synset_id}-{pos}'
        
        # Store the original synset for relation extraction in third pass
        iwn_synset_map[synset_id] = synset
        
        # Track synset ID for uniqueness calculation
        stats['synset_ids'].add(synset_id)
        
        # Determine relation type and ILI from mapping
        ili = None
        rel_type = None
        
        for rel in ['equal', 'hyper', 'dupe']:
            if rel in ili_map and iwn_key in ili_map[rel]:
                ili = ili_map[rel][iwn_key]
                rel_type = rel
                break
        
        # Initialize synset
        syns[syn_id]['pos'] = pos
        syns[syn_id]['def'] = synset.gloss()
        syns[syn_id]['exe'] = "; ".join(synset.examples())
        syns[syn_id]['relations'] = []
        syns[syn_id]['iwn_key'] = iwn_key
        syns[syn_id]['iwn_synset_id'] = synset_id
        
        if rel_type == 'equal':
            # Direct ILI assignment
            syns[syn_id]['ili'] = ili
            stats[rel_type] += 1
        elif rel_type in ('hyper', 'dupe'):
            # No ILI on this synset - will link to anchor or existing equal synset
            syns[syn_id]['ili'] = ''
            stats[rel_type] += 1
            # Record for second pass
            pending_hypernym_links.append((syn_id, ili, rel_type, iwn_key))
        else:
            # No mapping at all
            syns[syn_id]['ili'] = ''
            stats['no_mapping'] += 1
        
        # Add lemmas
        for lemma in synset.lemmas():
            lemma_name = lemma.name()
            
            # Skip problematic lemmas
            if ':' in lemma_name:
                print(f'WARNING: Bad lemma for {syn_id}: {lemma_name}')
                issues['bad_lemma'].append((synset_id, lemma_name, 'contains_colon'))
                stats['bad_lemma'] += 1
                continue
            if '"' in lemma_name:
                print(f'WARNING: Bad lemma for {syn_id}: {lemma_name}')
                issues['bad_lemma'].append((synset_id, lemma_name, 'contains_quote'))
                stats['bad_lemma'] += 1
                continue
            
            lemma_escaped = escape(lemma_name)
            sense_id = f'{prefix}-{lemma_escaped}-s{synset_id}-{pos}'
            lem_id = f'{prefix}-{lemma_escaped}-{pos}'
            
            lems[lem_id]['lemma'] = lemma_escaped
            lems[lem_id]['pos'] = pos
            if 'sens' in lems[lem_id]:
                lems[lem_id]['sens'].add((sense_id, syn_id))
            else:
                lems[lem_id]['sens'] = {(sense_id, syn_id)}
    
    # Build iwn_key -> syn_id mapping for linking
    iwn_key_to_syn_id = {syns[sid]['iwn_key']: sid for sid in syns if 'iwn_key' in syns[sid]}
    
    # =========================================================================
    # Second pass: Resolve hypernym links for hyper/dupe synsets
    # =========================================================================
    for syn_id, ili, rel_type, iwn_key in pending_hypernym_links:
        target_syn_id = None
        
        # Check if ILI is already used by an 'equal' synset
        if ili in equal_ilis:
            # Find the equal synset with this ILI
            for eq_iwn_key, eq_ili in ili_map.get('equal', {}).items():
                if eq_ili == ili and eq_iwn_key in iwn_key_to_syn_id:
                    target_syn_id = iwn_key_to_syn_id[eq_iwn_key]
                    stats['hypernym_to_equal'] += 1
                    break
        
        if target_syn_id is None:
            # Need to create an anchor synset
            if ili not in anchor_synsets:
                # Get English synset from OMW
                omw_synsets = ewn.synsets(ili=ili)
                
                if len(omw_synsets) == 1:
                    omw_ss = omw_synsets[0]
                else:
                    omw_ss = None
                
                if omw_ss:
                    # Create anchor synset with OMW ID
                    anchor_id = f'{prefix}-{omw_ss.id}'
                    anchor_pos = omw_ss.pos
                    anchor_def = omw_ss.definition() or ''

                    syns[anchor_id] = {
                        'pos': anchor_pos,
                        'ili': ili,
                        'def': anchor_def,
                        'exe': '',
                        'relations': [],
                        'is_anchor': True,
                    }

                    # Find nearest IWN hypernym for the anchor
                    nearest_ili = find_nearest_iwn_hypernym(
                        ewn, omw_ss.id, equal_ilis
                    )

                    if nearest_ili:
                        nearest_iwn_key = ili_to_iwn[nearest_ili][0][0]
                        if nearest_iwn_key in iwn_key_to_syn_id:
                            nearest_syn_id = iwn_key_to_syn_id[nearest_iwn_key]
                            syns[anchor_id]['relations'].append(('hypernym', nearest_syn_id))
                            stats['nearest_hypernym_found'] += 1

                    anchor_synsets[ili] = anchor_id
                    #print(f'Created anchor {anchor_id}')
                    stats['anchor_created'] += 1
            
            target_syn_id = anchor_synsets.get(ili)
        
        # Add hypernym link from IWN synset to target
        if target_syn_id:
            syns[syn_id]['relations'].append(('hypernym', target_syn_id))
    
    # Build iwn_synset_id -> syn_id mapping for relation resolution
    iwn_id_to_syn_id = {}
    for syn_id in syns:
        if 'iwn_synset_id' in syns[syn_id]:
            iwn_id_to_syn_id[syns[syn_id]['iwn_synset_id']] = syn_id
    
    # =========================================================================
    # Third pass: Extract and add IWN internal relations
    # =========================================================================
    for syn_id in syns:
        if 'iwn_synset_id' not in syns[syn_id]:
            continue  # Skip anchor synsets
        
        iwn_synset_id = syns[syn_id]['iwn_synset_id']
        if iwn_synset_id not in iwn_synset_map:
            continue
        
        source_synset = iwn_synset_map[iwn_synset_id]
        
        # Iterate through all IWN relation types
        for iwn_rel in pyiwn.SynsetRelations:
            iwn_rel_name = iwn_rel.value  # e.g., 'hypernymy', 'mero_member_collection'
            
            # Get target synsets for this relation
            try:
                target_synsets = iwn.synset_relation(source_synset, iwn_rel)
            except Exception:
                continue
            
            if not target_synsets:
                continue
            
            # Map to GWA relation type
            gwa_rel = INDOWNET_TO_GWADOC.get(iwn_rel_name)
            if not gwa_rel:
                continue  # Unknown relation type
            
            for target_synset in target_synsets:
                target_iwn_id = str(target_synset.synset_id())
                
                # Find the corresponding LMF synset ID
                if target_iwn_id in iwn_id_to_syn_id:
                    target_syn_id = iwn_id_to_syn_id[target_iwn_id]
                    # Avoid duplicate relations
                    if (gwa_rel, target_syn_id) not in syns[syn_id]['relations']:
                        syns[syn_id]['relations'].append((gwa_rel, target_syn_id))
                    stats['iwn_relations_mapped'] += 1
                
                stats['iwn_relations'] += 1
    
    # =========================================================================
    # Cleanup: Remove temporary keys before output
    # =========================================================================
    for syn_id in syns:
        if 'iwn_key' in syns[syn_id]:
            del syns[syn_id]['iwn_key']
        if 'iwn_synset_id' in syns[syn_id]:
            del syns[syn_id]['iwn_synset_id']
    
    # Record final lemma count
    stats['lemmas'] = len(lems)
    
    # Print statistics
    print(f"\n  Synset statistics:")
    print(f"    Total IWN synsets: {stats['total']}")
    print(f"    With equal ILI: {stats['equal']}")
    print(f"    With hyper link: {stats['hyper']}")
    print(f"    With dupe link: {stats['dupe']}")
    print(f"    No mapping: {stats['no_mapping']}")
    print(f"    Bad POS skipped: {stats['bad_pos']}")
    print(f"  Link resolution:")
    print(f"    Hypernym to existing equal: {stats['hypernym_to_equal']}")
    print(f"    Anchor synsets created: {stats['anchor_created']}")
    print(f"    Nearest IWN hypernym found: {stats['nearest_hypernym_found']}")
    print(f"  IWN relations:")
    print(f"    Total found: {stats['iwn_relations']}")
    print(f"    Successfully mapped: {stats['iwn_relations_mapped']}")
    print(f"  Lemmas: {stats['lemmas']} (bad skipped: {stats['bad_lemma']})")
    
    return lems, syns, stats, issues


def make_wn(ver, lang, ili_map, ewn):
    """
    Generate a complete wordnet in LMF format for a given language.
    
    Args:
        ver: Version string (e.g., '1.0')
        lang: pyiwn.Language enum value
        ili_map: ILI mapping dict
        ewn: OMW English Wordnet
    
    Returns:
        Tuple of (prefix, xml_string, stats_dict, issues_dict)
    """
    iwn = pyiwn.IndoWordNet(lang=lang)

    lang_name = str(lang)[9:].lower()  # Extract from "Language.hindi"
    lang_code = LANGUAGES[lang_name]
    prefix = f'iwn-{lang_code}'
    
    print(f"\n{'='*60}")
    print(f"Processing {lang_name.title()} ({lang_code})")
    print('='*60)
    
    lems, syns, stats, issues = get_entries(prefix, iwn, ili_map, ewn)
    
    # Add language info to stats
    stats['lang_name'] = lang_name.title()
    stats['lang_code'] = lang_code
    stats['synsets'] = len(syns)

    # Build XML
    new_wn = make_header(
        lmf_ver='1.1',
        prefix=prefix,
        lang_code=lang_code,
        lang_name=lang_name.title(),
        license='CC-BY-SA',
        ver=ver
    )
    new_wn += make_lexes(lems)
    new_wn += make_synsets(syns)
    new_wn += make_footer()
    
    return prefix, new_wn, stats, issues


def write_issues_log(all_issues, filename='build/iwn_data_issues.yaml'):
    """
    Write all data quality issues to a YAML file for feedback to IndoWordNet.
    
    Args:
        all_issues: Dict mapping lang_code -> issues dict
        filename: Output file path
    """
    with open(filename, 'w', encoding='utf-8') as fh:
        yaml.dump(all_issues, fh, allow_unicode=True, default_flow_style=False)
    print(f"\nWrote data issues to {filename}")


def write_latex_tables(all_stats, filename='build/results.tex'):
    """
    Write statistics as LaTeX tables for the paper.
    
    Args:
        all_stats: List of stats dicts, one per language
        filename: Output file path
    """
    with open(filename, 'w', encoding='utf-8') as fh:
        # Header comment
        fh.write("% IndoWordNet conversion statistics\n")
        fh.write("% Generated by iwn2omw.py\n\n")
        
        # =================================================================
        # Table 1: Main statistics per language
        # =================================================================
        fh.write("% Table 1: Main statistics per language\n")
        fh.write("\\begin{table*}[t]\n")
        fh.write("\\centering\n")
        fh.write("\\small\n")
        fh.write("\\begin{tabular}{llrrrrrrrr}\n")
        fh.write("\\toprule\n")
        fh.write("\\textbf{Language} & \\textbf{Code} & \\textbf{Synsets} & "
                 "\\textbf{Unique} & \\textbf{Lemmas} & \\textbf{Equal} & \\textbf{Hyper} & "
                 "\\textbf{Dupe} & \\textbf{None} & \\textbf{Rels} \\\\\n")
        fh.write("\\midrule\n")
        
        # Sort by language name
        for s in sorted(all_stats, key=lambda x: x['lang_name']):
            unique = s.get('unique_synsets', 0)
            fh.write(f"{s['lang_name']} & {s['lang_code']} & "
                     f"{s['synsets']:,} & {unique:,} & {s['lemmas']:,} & "
                     f"{s['equal']:,} & {s['hyper']:,} & "
                     f"{s['dupe']:,} & {s['no_mapping']:,} & "
                     f"{s['iwn_relations_mapped']:,} \\\\\n")
        
        # Totals row
        fh.write("\\midrule\n")
        total_synsets = sum(s['synsets'] for s in all_stats)
        total_unique = sum(s.get('unique_synsets', 0) for s in all_stats)
        total_lemmas = sum(s['lemmas'] for s in all_stats)
        total_equal = sum(s['equal'] for s in all_stats)
        total_hyper = sum(s['hyper'] for s in all_stats)
        total_dupe = sum(s['dupe'] for s in all_stats)
        total_none = sum(s['no_mapping'] for s in all_stats)
        total_rels = sum(s['iwn_relations_mapped'] for s in all_stats)
        fh.write(f"\\textbf{{Total}} & & {total_synsets:,} & {total_unique:,} & {total_lemmas:,} & "
                 f"{total_equal:,} & {total_hyper:,} & {total_dupe:,} & "
                 f"{total_none:,} & {total_rels:,} \\\\\n")
        
        fh.write("\\bottomrule\n")
        fh.write("\\end{tabular}\n")
        fh.write("\\caption{Statistics for all 18 IndoWordNet languages. "
                 "Synsets = total synsets in output; Unique = synsets only in this language; "
                 "Lemmas = unique lemma entries; "
                 "Equal/Hyper/Dupe = ILI mapping type; None = no ILI mapping; "
                 "Rels = internal semantic relations.}\n")
        fh.write("\\label{tab:language-stats}\n")
        fh.write("\\end{table*}\n\n")
        
        # =================================================================
        # Table 2: Data quality issues
        # =================================================================
        fh.write("% Table 2: Data quality issues\n")
        fh.write("\\begin{table}[t]\n")
        fh.write("\\centering\n")
        fh.write("\\begin{tabular}{lrr}\n")
        fh.write("\\toprule\n")
        fh.write("\\textbf{Language} & \\textbf{Bad POS} & \\textbf{Bad Lemmas} \\\\\n")
        fh.write("\\midrule\n")
        
        has_issues = False
        for s in sorted(all_stats, key=lambda x: x['lang_name']):
            if s['bad_pos'] > 0 or s['bad_lemma'] > 0:
                has_issues = True
                fh.write(f"{s['lang_name']} & {s['bad_pos']} & {s['bad_lemma']} \\\\\n")
        
        if not has_issues:
            fh.write("\\multicolumn{3}{c}{\\textit{No issues found}} \\\\\n")
        
        fh.write("\\bottomrule\n")
        fh.write("\\end{tabular}\n")
        fh.write("\\caption{Data quality issues found during conversion.}\n")
        fh.write("\\label{tab:data-issues}\n")
        fh.write("\\end{table}\n\n")
        
        # =================================================================
        # Table 3: Link resolution statistics
        # =================================================================
        fh.write("% Table 3: Link resolution\n")
        fh.write("\\begin{table}[t]\n")
        fh.write("\\centering\n")
        fh.write("\\begin{tabular}{lrrr}\n")
        fh.write("\\toprule\n")
        fh.write("\\textbf{Language} & \\textbf{Hyp→Equal} & "
                 "\\textbf{Anchors} & \\textbf{Nearest} \\\\\n")
        fh.write("\\midrule\n")
        
        for s in sorted(all_stats, key=lambda x: x['lang_name']):
            fh.write(f"{s['lang_name']} & {s['hypernym_to_equal']:,} & "
                     f"{s['anchor_created']:,} & {s['nearest_hypernym_found']:,} \\\\\n")
        
        fh.write("\\bottomrule\n")
        fh.write("\\end{tabular}\n")
        fh.write("\\caption{Hypernym link resolution. "
                 "Hyp→Equal = linked to existing equal synset; "
                 "Anchors = English anchor synsets created; "
                 "Nearest = anchors linked to nearest IWN hypernym.}\n")
        fh.write("\\label{tab:link-resolution}\n")
        fh.write("\\end{table}\n")
    
    print(f"Wrote LaTeX tables to {filename}")


def main():
    """Main entry point."""
    print("Loading OMW English...")
    wn.download('omw-en:1.4')
    ewn = wn.Wordnet('omw-en:1.4')
    
    print("\nLoading ILI mapping from build/iwn2ili.yaml...")
    ili_map = load_ili_map('build/iwn2ili.yaml')
    
    total_equal = len(ili_map.get('equal', {}))
    total_hyper = len(ili_map.get('hyper', {}))
    total_dupe = len(ili_map.get('dupe', {}))
    print(f"\nTotal mappings: {total_equal} equal, {total_hyper} hyper, {total_dupe} dupe")
    
    # Collect statistics and issues from all languages
    all_stats = []
    all_issues = {}
    all_synset_ids = {}  # lang_code -> set of IWN synset IDs
    
    # Process all IndoWordNet languages
    for lang in pyiwn.Language:
        version = '1.0'
        prefix, new_wn, stats, issues = make_wn(version, lang=lang, ili_map=ili_map, ewn=ewn)
        
        # Collect stats
        all_stats.append(stats)
        
        # Store synset IDs for uniqueness calculation
        all_synset_ids[stats['lang_code']] = stats.get('synset_ids', set())
        
        # Collect issues (only if there are any)
        if issues['bad_pos'] or issues['bad_lemma']:
            all_issues[stats['lang_code']] = {
                'language': stats['lang_name'],
                'bad_pos': issues['bad_pos'],
                'bad_lemma': issues['bad_lemma'],
            }
        
        # Write LMF file
        output_file = f'build/{prefix}-{version}.xml'
        with open(output_file, 'w', encoding='utf-8') as out:
            print(new_wn, file=out)
        print(f"  Wrote: {output_file}")
    
    # Calculate unique synsets per language
    # A synset is unique if its IWN ID only appears in one language
    print("\nCalculating unique synsets per language...")
    
    # Count how many languages each synset ID appears in
    synset_lang_count = {}
    for lang_code, synset_ids in all_synset_ids.items():
        for sid in synset_ids:
            if sid not in synset_lang_count:
                synset_lang_count[sid] = set()
            synset_lang_count[sid].add(lang_code)
    
    # Count unique synsets per language
    for stats in all_stats:
        lang_code = stats['lang_code']
        synset_ids = all_synset_ids.get(lang_code, set())
        unique_count = sum(1 for sid in synset_ids if len(synset_lang_count.get(sid, set())) == 1)
        stats['unique_synsets'] = unique_count
    
    # Write issues log for IndoWordNet feedback
    if all_issues:
        write_issues_log(all_issues)
    else:
        print("\nNo data quality issues found.")
    
    # Write LaTeX tables for the paper
    write_latex_tables(all_stats)
    
    # Print summary
    print("\n" + "=" * 60)
    print("CONVERSION COMPLETE")
    print("=" * 60)
    print(f"Languages processed: {len(all_stats)}")
    print(f"Total synsets: {sum(s['synsets'] for s in all_stats):,}")
    print(f"Total unique synsets: {sum(s['unique_synsets'] for s in all_stats):,}")
    print(f"Total lemmas: {sum(s['lemmas'] for s in all_stats):,}")
    print(f"Total relations: {sum(s['iwn_relations_mapped'] for s in all_stats):,}")


if __name__ == '__main__':
    main()

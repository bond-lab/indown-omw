import wn
from collections import defaultdict as dd
import yaml
import argparse

IWN_EN_DATA = 'etc/IWN-En/data/english-hindi-linked-fixed.tsv'
PWN_MAP_DIR = 'etc/mappings-upc-2007/mapping-21-30/'
VER = '1.0'

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

PosTag = { 
    'NOUN': 'n',
    'VERB': 'v',
    'ADVERB': 'r',
    'ADJECTIVE': 'a',
}


def load_pwn_map(verbose=False):
    """
    Load PWN 2.1 -> 3.0 mappings from UPC mapping files.
    """
    files = {
        "wn21-30.adj": "a",
        "wn21-30.adv": "r", 
        "wn21-30.noun": "n",
        "wn21-30.verb": "v",
    }
    
    map2130 = {}
    for filename, pos in files.items():
        with open(PWN_MAP_DIR + filename) as fh:
            for line in fh:
                parts = line.strip().split()
                if len(parts) < 3:
                    continue
                    
                offset_21 = parts[0]
                pairs = [(float(parts[i+1]), parts[i]) for i in range(1, len(parts), 2)]
                best_offset_30 = max(pairs)[1]
                
                key = f"{offset_21}-{pos}"
                val = f"{best_offset_30}-{pos}"
                map2130[key] = val
                    
    print(f"Loaded PWN 2.1 to 3.0 map: {len(map2130)} mappings")
    return map2130


def lookup_synset(ewn, pwn30_key):
    """
    Look up a synset in OMW, handling satellite adjectives.
    
    Returns (synset, actual_key) or (None, None) if not found.
    """
    offset, pos = pwn30_key.rsplit('-', 1)
    
    # Try the original POS first
    omw_id = f"omw-en-{pwn30_key}"
    try:
        synset = ewn.synset(id=omw_id)
        return synset, pwn30_key
    except wn.Error:
        pass
    
    # If adjective, try satellite adjective
    if pos == 'a':
        sat_key = f"{offset}-s"
        omw_id = f"omw-en-{sat_key}"
        try:
            synset = ewn.synset(id=omw_id)
            return synset, sat_key
        except wn.Error:
            pass
    
    return None, None


def load_iwn_map(issues):
    """
    Load IWN to PWN 2.1 mappings from the TSV file.
    
    Args:
        issues: dict to collect issues for later reporting
    """
    entries = []
    
    with open(f'{IWN_EN_DATA}') as fh:
        for lineno, line in enumerate(fh, 1):
            row = line.strip().split('\t')
            
            # Skip header
            if row[0] == 'iwn_id':
                continue
            
            # Check we have enough columns
            if len(row) < 9:
                msg = f"only {len(row)} columns"
                print(f"WARN: line {lineno} {msg}, skipping: {row[0] if row else 'empty'}")
                issues['malformed_lines'].append({
                    'line_number': lineno,
                    'error': msg,
                    'original_line': line.rstrip('\n'),
                })
                continue
            
            # Get relation type from last column
            rel_type = row[-1].strip()
            if rel_type == 'Direct':
                rel = 'equal'
            elif rel_type == 'Hypernymy':
                rel = 'hyper'
            else:
                msg = f"unknown rel '{rel_type}'"
                print(f"WARN: line {lineno} {msg}, skipping")
                issues['malformed_lines'].append({
                    'line_number': lineno,
                    'error': msg,
                    'original_line': line.rstrip('\n'),
                })
                continue
            
            # Validate POS
            if row[1] not in PosTag:
                msg = f"unknown IWN POS '{row[1]}'"
                print(f"WARN: line {lineno} {msg}, skipping")
                issues['malformed_lines'].append({
                    'line_number': lineno,
                    'error': msg,
                    'original_line': line.rstrip('\n'),
                })
                continue
            if row[3] not in PosTag:
                msg = f"unknown PWN POS '{row[3]}'"
                print(f"WARN: line {lineno} {msg}, skipping")
                issues['malformed_lines'].append({
                    'line_number': lineno,
                    'error': msg,
                    'original_line': line.rstrip('\n'),
                })
                continue
            
            # Validate offset is numeric
            try:
                pwn_offset = int(row[2])
            except ValueError:
                msg = f"invalid PWN offset '{row[2]}'"
                print(f"WARN: line {lineno} {msg}, skipping")
                issues['malformed_lines'].append({
                    'line_number': lineno,
                    'error': msg,
                    'original_line': line.rstrip('\n'),
                })
                continue
            
            entry = {
                'iwn_id': row[0],
                'iwn_pos': row[1],
                'pwn21_offset': row[2],
                'pwn21_pos': row[3],
                'english_lemmas': row[4],
                'english_gloss': row[5],
                'hindi_lemmas': row[6],
                'hindi_gloss': row[7],
                'original_rel': rel_type,
                'rel': rel,
                'iwn_key': f"{row[0]}_{PosTag[row[1]]}",
                'pwn21_key': f"{pwn_offset:08d}-{PosTag[row[3]]}",
            }
            
            entries.append(entry)
    
    equal_count = sum(1 for e in entries if e['rel'] == 'equal')
    hyper_count = sum(1 for e in entries if e['rel'] == 'hyper')
    print(f"Loaded IWN to PWN map: {equal_count} direct, {hyper_count} hypernym links")
    if issues['malformed_lines']:
        print(f"  Skipped {len(issues['malformed_lines'])} malformed lines")
    
    return entries


def detect_and_mark_dupes(entries, map2130, ewn, issues):
    """
    Detect multiple IWN synsets mapping to the same ILI via Direct links.
    Mark ALL duplicates as 'dupe' and log details for later review.
    """
    # First pass: resolve ILI for all Direct entries
    for entry in entries:
        if entry['rel'] != 'equal':
            continue
            
        pwn21_key = entry['pwn21_key']
        pwn30_key = map2130.get(pwn21_key)
        
        if pwn30_key is None:
            entry['ili'] = None
            entry['pwn30_key'] = None
            issues['missing_pwn30'].append({
                'iwn_id': entry['iwn_id'],
                'pwn21_key': pwn21_key,
                'english_lemmas': entry['english_lemmas'],
                'english_gloss': entry['english_gloss'],
                'hindi_lemmas': entry['hindi_lemmas'],
                'hindi_gloss': entry['hindi_gloss'],
            })
            continue
        
        synset, actual_key = lookup_synset(ewn, pwn30_key)
        entry['pwn30_key'] = actual_key or pwn30_key
        
        if synset:
            ili = synset.ili
            entry['ili'] = ili.id if ili else None
            if not ili:
                issues['missing_ili'].append({
                    'iwn_id': entry['iwn_id'],
                    'pwn21_key': pwn21_key,
                    'pwn30_key': actual_key,
                    'omw_id': f"omw-en-{actual_key}",
                    'english_lemmas': entry['english_lemmas'],
                    'english_gloss': entry['english_gloss'],
                    'hindi_lemmas': entry['hindi_lemmas'],
                    'hindi_gloss': entry['hindi_gloss'],
                })
        else:
            entry['ili'] = None
            issues['missing_omw'].append({
                'iwn_id': entry['iwn_id'],
                'pwn21_key': pwn21_key,
                'pwn30_key': pwn30_key,
                'omw_id_tried': [f"omw-en-{pwn30_key}", f"omw-en-{pwn30_key.replace('-a', '-s')}"] if pwn30_key.endswith('-a') else [f"omw-en-{pwn30_key}"],
                'english_lemmas': entry['english_lemmas'],
                'english_gloss': entry['english_gloss'],
                'hindi_lemmas': entry['hindi_lemmas'],
                'hindi_gloss': entry['hindi_gloss'],
            })
    
    # Second pass: group by ILI and find duplicates
    ili_to_entries = dd(list)
    for entry in entries:
        if entry['rel'] == 'equal' and entry.get('ili'):
            ili_to_entries[entry['ili']].append(entry)
    
    # Third pass: mark ALL entries in duplicate groups as 'dupe'
    dupe_count = 0
    dupe_groups = []
    
    for ili_id, ili_entries in ili_to_entries.items():
        if len(ili_entries) > 1:
            sorted_entries = sorted(ili_entries, key=lambda e: int(e['iwn_id']))
            dupe_groups.append({
                'ili': ili_id,
                'entries': sorted_entries
            })
            
            # Record in issues
            issues['duplicate_ili'].append({
                'ili': ili_id,
                'pwn30_key': sorted_entries[0].get('pwn30_key', ''),
                'english_lemmas': sorted_entries[0]['english_lemmas'],
                'english_gloss': sorted_entries[0]['english_gloss'],
                'iwn_entries': [
                    {
                        'iwn_id': e['iwn_id'],
                        'hindi_lemmas': e['hindi_lemmas'],
                        'hindi_gloss': e['hindi_gloss'],
                    }
                    for e in sorted_entries
                ]
            })
            
            for entry in ili_entries:
                entry['rel'] = 'dupe'
                dupe_count += 1
    
    print(f"Detected {len(dupe_groups)} ILIs with multiple IWN mappings")
    print(f"Marked {dupe_count} entries as 'dupe'")
    
    return entries, dupe_groups


def build_final_mapping(entries, map2130, ewn, issues):
    """
    Build final IWN -> ILI mapping after dupe detection.
    """
    iwn_to_ili = dd(dict)
    stats = dd(int)
    
    for entry in entries:
        rel = entry['rel']
        iwn_key = entry['iwn_key']
        
        # Already have ILI from dupe detection
        if entry.get('ili'):
            iwn_to_ili[rel][iwn_key] = entry['ili']
            stats[rel] += 1
            continue
        
        # Need to compute ILI (for hyper entries)
        pwn21_key = entry['pwn21_key']
        pwn30_key = map2130.get(pwn21_key)
        
        if pwn30_key is None:
            stats['missing_30'] += 1
            if entry['rel'] == 'hyper':
                issues['missing_pwn30'].append({
                    'iwn_id': entry['iwn_id'],
                    'pwn21_key': pwn21_key,
                    'rel': 'hyper',
                    'english_lemmas': entry['english_lemmas'],
                    'english_gloss': entry['english_gloss'],
                    'hindi_lemmas': entry['hindi_lemmas'],
                    'hindi_gloss': entry['hindi_gloss'],
                })
            continue
        
        synset, actual_key = lookup_synset(ewn, pwn30_key)
        
        if synset:
            ili = synset.ili
            if ili:
                iwn_to_ili[rel][iwn_key] = ili.id
                stats[rel] += 1
            else:
                stats['missing_ili'] += 1
                if entry['rel'] == 'hyper':
                    issues['missing_ili'].append({
                        'iwn_id': entry['iwn_id'],
                        'pwn21_key': pwn21_key,
                        'pwn30_key': actual_key,
                        'omw_id': f"omw-en-{actual_key}",
                        'rel': 'hyper',
                        'english_lemmas': entry['english_lemmas'],
                        'english_gloss': entry['english_gloss'],
                        'hindi_lemmas': entry['hindi_lemmas'],
                        'hindi_gloss': entry['hindi_gloss'],
                    })
        else:
            stats['missing_omw'] += 1
            if entry['rel'] == 'hyper':
                issues['missing_omw'].append({
                    'iwn_id': entry['iwn_id'],
                    'pwn21_key': pwn21_key,
                    'pwn30_key': pwn30_key,
                    'omw_id_tried': [f"omw-en-{pwn30_key}", f"omw-en-{pwn30_key.replace('-a', '-s')}"] if pwn30_key.endswith('-a') else [f"omw-en-{pwn30_key}"],
                    'rel': 'hyper',
                    'english_lemmas': entry['english_lemmas'],
                    'english_gloss': entry['english_gloss'],
                    'hindi_lemmas': entry['hindi_lemmas'],
                    'hindi_gloss': entry['hindi_gloss'],
                })
    
    print(f"\nFinal mapping statistics:")
    for key, count in sorted(stats.items()):
        print(f"  {key}: {count}")
    
    return iwn_to_ili


def write_issues(issues, filename='build/iwn_issues.yaml'):
    """
    Write all issues to a YAML file for review.
    """
    # Build summary
    summary = {
        'malformed_lines': len(issues['malformed_lines']),
        'duplicate_ili': len(issues['duplicate_ili']),
        'duplicate_ili_entries': sum(len(d['iwn_entries']) for d in issues['duplicate_ili']),
        'missing_pwn30': len(issues['missing_pwn30']),
        'missing_omw': len(issues['missing_omw']),
        'missing_ili': len(issues['missing_ili']),
    }
    
    output = {
        'summary': summary,
        'issues': dict(issues),
    }
    
    with open(filename, 'w', encoding='utf-8') as fh:
        yaml.dump(output, fh, allow_unicode=True, default_flow_style=False, sort_keys=False)
    
    print(f"\nWrote issues to {filename}")
    print(f"  Summary:")
    for key, count in summary.items():
        print(f"    {key}: {count}")


def validate_mappings(entries, ewn, sample_size=None):
    """
    Validate ILI mappings against OMW-EN by checking lemma and gloss overlap.
    
    Args:
        entries: List of entry dicts from load_iwn_map()
        ewn: wn.Wordnet instance for omw-en:1.4
        sample_size: If set, validate only a random sample
    """
    import random
    
    def normalize_lemma(lemma):
        if '(' in lemma:
            lemma = lemma.split('(')[0]
        return lemma.strip().replace('_', ' ').lower()
    
    def gloss_similarity(g1, g2):
        if not g1 or not g2:
            return 0.0
        w1 = set(g1.lower().split()) - {'a','an','the','of','to','in','for','on','with','as','by','or','and','is','are','be'}
        w2 = set(g2.lower().split()) - {'a','an','the','of','to','in','for','on','with','as','by','or','and','is','are','be'}
        if not w1 or not w2:
            return 0.0
        return len(w1 & w2) / len(w1 | w2)
    
    # Filter entries that have ILI mappings
    mapped = [e for e in entries if e.get('ili')]
    
    if sample_size and len(mapped) > sample_size:
        mapped = random.sample(mapped, sample_size)
    
    stats = {
        'total': len(mapped),
        'validated': 0,
        'lemma_exact': 0, 'lemma_partial': 0, 'lemma_mismatch': 0,
        'gloss_high': 0, 'gloss_medium': 0, 'gloss_low': 0,
        'likely_errors': [],
    }
    
    print(f"\nValidating {len(mapped)} mappings against OMW-EN...")
    
    for entry in mapped:
        try:
            ili = ewn.ili(entry['ili'])
            synsets = ili.synsets()
            if not synsets:
                continue
            
            # Get OMW-EN synset
            omw_ss = next((ss for ss in synsets if ss.lexicon().id() == 'omw-en'), synsets[0])
            
            stats['validated'] += 1
            
            # Compare lemmas
            tsv_lemmas = {normalize_lemma(l) for l in entry['english_lemmas'].split(', ')}
            omw_lemmas = {normalize_lemma(w.lemma()) for w in omw_ss.words()}
            
            if tsv_lemmas == omw_lemmas:
                stats['lemma_exact'] += 1
                lemma_ok = True
            elif tsv_lemmas & omw_lemmas:
                stats['lemma_partial'] += 1
                lemma_ok = True
            else:
                stats['lemma_mismatch'] += 1
                lemma_ok = False
            
            # Compare glosses
            sim = gloss_similarity(entry['english_gloss'], omw_ss.definition() or '')
            
            if sim >= 0.5:
                stats['gloss_high'] += 1
            elif sim >= 0.2:
                stats['gloss_medium'] += 1
            else:
                stats['gloss_low'] += 1
            
            # Flag likely errors
            if not lemma_ok and sim < 0.2:
                stats['likely_errors'].append({
                    'iwn_id': entry['iwn_id'],
                    'ili': entry['ili'],
                    'tsv_lemmas': entry['english_lemmas'],
                    'omw_lemmas': ', '.join(sorted(omw_lemmas)),
                    'tsv_gloss': entry['english_gloss'][:80],
                    'omw_gloss': (omw_ss.definition() or '')[:80],
                    'similarity': round(sim, 3),
                })
                
        except Exception as e:
            continue
    
    # Print summary
    v = max(1, stats['validated'])
    print(f"\n{'='*50}")
    print("VALIDATION RESULTS")
    print(f"{'='*50}")
    print(f"Checked: {stats['validated']} / {stats['total']}")
    print(f"\nLemma overlap:")
    print(f"  Exact match:   {stats['lemma_exact']:5d} ({100*stats['lemma_exact']/v:5.1f}%)")
    print(f"  Partial match: {stats['lemma_partial']:5d} ({100*stats['lemma_partial']/v:5.1f}%)")
    print(f"  No match:      {stats['lemma_mismatch']:5d} ({100*stats['lemma_mismatch']/v:5.1f}%)")
    print(f"\nGloss similarity:")
    print(f"  High (>=50%):  {stats['gloss_high']:5d} ({100*stats['gloss_high']/v:5.1f}%)")
    print(f"  Medium (20-50%): {stats['gloss_medium']:5d} ({100*stats['gloss_medium']/v:5.1f}%)")
    print(f"  Low (<20%):    {stats['gloss_low']:5d} ({100*stats['gloss_low']/v:5.1f}%)")
    
    if stats['likely_errors']:
        print(f"\n⚠️  LIKELY ERRORS: {len(stats['likely_errors'])} (no lemma match + low gloss similarity)")
        print("First 5:")
        for err in stats['likely_errors'][:5]:
            print(f"\n  IWN {err['iwn_id']} -> {err['ili']}")
            print(f"    TSV: {err['tsv_lemmas']}")
            print(f"    OMW: {err['omw_lemmas']}")
            print(f"    Gloss sim: {err['similarity']}")
    
    print(f"{'='*50}")
    
    return stats


     
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Build IWN to ILI mapping')
    parser.add_argument('--validate', action='store_true',
                        help='Validate mappings against OMW-EN')
    parser.add_argument('--validate-sample', type=int, default=None,
                        help='Validate only N random samples (faster)')
    args = parser.parse_args()
    
    # Collect all issues
    issues = {
        'malformed_lines': [],
        'duplicate_ili': [],
        'missing_pwn30': [],
        'missing_omw': [],
        'missing_ili': [],
    }
    
    print("Loading OMW English...")
    ewn = wn.Wordnet(lexicon='omw-en:1.4')
    
    map2130 = load_pwn_map()
    entries = load_iwn_map(issues)
    
    entries, dupe_groups = detect_and_mark_dupes(entries, map2130, ewn, issues)
    
    iwn_to_ili = build_final_mapping(entries, map2130, ewn, issues)
    
    # Write mapping file
    with open('build/iwn2ili.yaml', 'w') as fh:
        yaml.dump({k: dict(v) for k, v in iwn_to_ili.items()}, fh)
    print(f"\nWrote mapping to build/iwn2ili.yaml")
    
    # Write issues file
    write_issues(issues)
    
    # Optional validation
    if args.validate or args.validate_sample:
        val_stats = validate_mappings(entries, ewn, sample_size=args.validate_sample)
        
        # Write validation issues
        if val_stats['likely_errors']:
            with open('build/validation_errors.yaml', 'w') as fh:
                yaml.dump(val_stats['likely_errors'], fh, allow_unicode=True)
            print(f"Wrote {len(val_stats['likely_errors'])} likely errors to build/validation_errors.yaml")
    
    # Print summary
    print(f"\n=== Summary ===")
    print(f"Total entries: {len(entries)}")
    print(f"  equal: {len(iwn_to_ili.get('equal', {}))}")
    print(f"  hyper: {len(iwn_to_ili.get('hyper', {}))}")
    print(f"  dupe:  {len(iwn_to_ili.get('dupe', {}))}")   

import wn
from collections import defaultdict as dd
import yaml

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


if __name__ == '__main__':
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
    with open('build/iwn2ili.jaml', 'w')as fh:
        yaml.dump(iwn_to_ili, fh)
    
    # Write issues file
    write_issues(issues)
    
    print(f"\n=== Summary ===")
    print(f"Total entries: {len(entries)}")
    print(f"  equal: {len(iwn_to_ili.get('equal', {}))}")
    print(f"  hyper: {len(iwn_to_ili.get('hyper', {}))}")
    print(f"  dupe:  {len(iwn_to_ili.get('dupe', {}))}")
    print(f"\nDuplicate groups: {len(dupe_groups)} ILIs involving {sum(len(g['entries']) for g in dupe_groups)} entries")
    
    if dupe_groups:
        print(f"\nFirst 5 duplicate groups:")
        for group in dupe_groups[:5]:
            print(f"\n  ILI: {group['ili']}")
            print(f"  English: {group['entries'][0]['english_lemmas']}")
            for entry in group['entries']:
                print(f"    IWN {entry['iwn_id']}: {entry['hindi_lemmas']}")

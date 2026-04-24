"""
Validation functions for IWN to ILI mappings.

Can be imported into map2ili.py or run standalone via validate_mappings.py
"""

def normalize_lemma(lemma: str) -> str:
    """Normalize lemma for comparison."""
    if '(' in lemma:
        lemma = lemma.split('(')[0]
    return lemma.strip().replace('_', ' ').lower()


def gloss_similarity(gloss1: str, gloss2: str) -> float:
    """
    Compute simple word overlap similarity between two glosses.
    Returns a score from 0.0 to 1.0
    """
    if not gloss1 or not gloss2:
        return 0.0
    
    words1 = set(gloss1.lower().split())
    words2 = set(gloss2.lower().split())
    
    stopwords = {'a', 'an', 'the', 'of', 'to', 'in', 'for', 'on', 'with', 'as', 'by', 'or', 'and', 'is', 'are', 'be'}
    words1 -= stopwords
    words2 -= stopwords
    
    if not words1 or not words2:
        return 0.0
    
    intersection = len(words1 & words2)
    union = len(words1 | words2)
    
    return intersection / union if union > 0 else 0.0


def validate_entry(entry: dict, ewn) -> dict:
    """
    Validate a single entry's ILI mapping against OMW-EN.
    
    Args:
        entry: Dict with keys: ili, english_lemmas, english_gloss, iwn_key
        ewn: wn.Wordnet instance
    
    Returns:
        Dict with validation results
    """
    import wn
    
    result = {
        'iwn_key': entry.get('iwn_key', ''),
        'ili': entry.get('ili'),
        'valid': False,
        'lemma_status': None,
        'gloss_similarity': 0.0,
        'error': None,
    }
    
    ili_id = entry.get('ili')
    if not ili_id:
        result['error'] = 'no_ili'
        return result
    
    try:
        ili = ewn.ili(ili_id)
        synsets = ili.synsets()
        
        if not synsets:
            result['error'] = 'ili_no_synsets'
            return result
        
        # Find OMW-EN synset
        omw_ss = None
        for ss in synsets:
            if ss.lexicon().id() == 'omw-en':
                omw_ss = ss
                break
        if not omw_ss:
            omw_ss = synsets[0]
        
        result['valid'] = True
        
        # Compare lemmas
        tsv_lemmas = {normalize_lemma(l) for l in entry['english_lemmas'].split(', ')}
        omw_lemmas = {normalize_lemma(w.lemma()) for w in omw_ss.words()}
        
        if tsv_lemmas == omw_lemmas:
            result['lemma_status'] = 'exact'
        elif tsv_lemmas & omw_lemmas:
            result['lemma_status'] = 'partial'
        else:
            result['lemma_status'] = 'mismatch'
            result['tsv_lemmas'] = tsv_lemmas
            result['omw_lemmas'] = omw_lemmas
        
        # Compare glosses
        tsv_gloss = entry.get('english_gloss', '')
        omw_gloss = omw_ss.definition() or ''
        result['gloss_similarity'] = gloss_similarity(tsv_gloss, omw_gloss)
        
        if result['lemma_status'] == 'mismatch' and result['gloss_similarity'] < 0.2:
            result['likely_error'] = True
        
    except wn.Error as e:
        result['error'] = str(e)
    
    return result


def validate_all_mappings(entries: list, ewn, sample_size: int = None) -> dict:
    """
    Validate all entries against OMW-EN.
    
    Args:
        entries: List of entry dicts with ili, english_lemmas, english_gloss
        ewn: wn.Wordnet instance
        sample_size: If set, only validate this many entries (for quick checks)
    
    Returns:
        Summary statistics dict
    """
    import random
    
    if sample_size and len(entries) > sample_size:
        entries = random.sample(entries, sample_size)
    
    stats = {
        'total': len(entries),
        'validated': 0,
        'lemma_exact': 0,
        'lemma_partial': 0,
        'lemma_mismatch': 0,
        'gloss_high': 0,
        'gloss_medium': 0,
        'gloss_low': 0,
        'likely_errors': [],
    }
    
    for entry in entries:
        if not entry.get('ili'):
            continue
        
        result = validate_entry(entry, ewn)
        
        if not result['valid']:
            continue
        
        stats['validated'] += 1
        
        if result['lemma_status'] == 'exact':
            stats['lemma_exact'] += 1
        elif result['lemma_status'] == 'partial':
            stats['lemma_partial'] += 1
        else:
            stats['lemma_mismatch'] += 1
        
        if result['gloss_similarity'] >= 0.5:
            stats['gloss_high'] += 1
        elif result['gloss_similarity'] >= 0.2:
            stats['gloss_medium'] += 1
        else:
            stats['gloss_low'] += 1
        
        if result.get('likely_error'):
            stats['likely_errors'].append({
                'iwn_key': entry.get('iwn_key'),
                'ili': entry.get('ili'),
                'tsv_lemmas': entry.get('english_lemmas'),
                'omw_lemmas': ', '.join(sorted(result.get('omw_lemmas', set()))),
                'gloss_similarity': round(result['gloss_similarity'], 3),
            })
    
    return stats


def print_validation_summary(stats: dict):
    """Print validation summary."""
    print("\n" + "=" * 50)
    print("MAPPING VALIDATION SUMMARY")
    print("=" * 50)
    
    v = max(1, stats['validated'])
    
    print(f"Validated: {stats['validated']} / {stats['total']}")
    print(f"\nLemma matches:")
    print(f"  Exact:   {stats['lemma_exact']:5d} ({100*stats['lemma_exact']/v:5.1f}%)")
    print(f"  Partial: {stats['lemma_partial']:5d} ({100*stats['lemma_partial']/v:5.1f}%)")
    print(f"  None:    {stats['lemma_mismatch']:5d} ({100*stats['lemma_mismatch']/v:5.1f}%)")
    
    print(f"\nGloss similarity:")
    print(f"  High:   {stats['gloss_high']:5d} ({100*stats['gloss_high']/v:5.1f}%)")
    print(f"  Medium: {stats['gloss_medium']:5d} ({100*stats['gloss_medium']/v:5.1f}%)")
    print(f"  Low:    {stats['gloss_low']:5d} ({100*stats['gloss_low']/v:5.1f}%)")
    
    if stats['likely_errors']:
        print(f"\nLikely errors (lemma mismatch + low gloss): {len(stats['likely_errors'])}")
        for err in stats['likely_errors'][:5]:
            print(f"  {err['iwn_key']} -> {err['ili']}")
            print(f"    TSV: {err['tsv_lemmas']}")
            print(f"    OMW: {err['omw_lemmas']}")
    
    print("=" * 50)

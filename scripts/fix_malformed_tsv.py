#!/usr/bin/env python3
"""
Fix malformed lines in english-hindi-linked.tsv

Issues to fix:
1. Lines 3784-3785: American entry split across two lines due to embedded quote in Hindi gloss
2. Line 5474: "WordN" relation should be "Hypernymy" (gaming is a hyponym of human_activity)
3. Lines 15835-15836: Tibet entry split across two lines due to embedded quote in Hindi gloss

The split-line issue occurs because the Hindi gloss contains a quote character that wasn't
properly escaped, causing the line to wrap. We detect this by looking for lines with fewer
than 9 columns followed by a line starting with a quote.

Run with: uv run fix_malformed_tsv.py <input.tsv> <output.tsv>
"""
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///

import sys
import re


def fix_tsv(input_path: str, output_path: str) -> dict:
    """
    Fix malformed lines in the TSV file.
    
    Returns statistics about fixes applied.
    """
    stats = {
        'total_lines': 0,
        'merged_lines': 0,
        'fixed_wordn': 0,
        'output_lines': 0,
    }
    
    with open(input_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    stats['total_lines'] = len(lines)
    
    fixed_lines = []
    i = 0
    
    while i < len(lines):
        line = lines[i].rstrip('\n')
        cols = line.split('\t')
        
        # Check if this is a split line (fewer than 9 columns)
        if len(cols) < 9 and len(cols) >= 7:
            # Look ahead - next line should start with " and have the relation
            if i + 1 < len(lines):
                next_line = lines[i + 1].rstrip('\n')
                next_cols = next_line.split('\t')
                
                # Pattern: next line has 2 columns, first is just a quote continuation
                if len(next_cols) == 2 and next_cols[0].startswith('"'):
                    # Merge the lines
                    # The issue is the Hindi gloss started with " but wasn't closed
                    # We need to append the continuation to the gloss
                    merged_gloss = cols[-1] + '\n' + next_cols[0]  # Keep the newline as space
                    merged_gloss = merged_gloss.replace('\n', ' ')  # Or replace with space
                    cols[-1] = merged_gloss
                    cols.append(next_cols[1])  # Add the relation
                    
                    merged_line = '\t'.join(cols)
                    fixed_lines.append(merged_line + '\n')
                    
                    print(f"Merged lines {i+1}-{i+2}: {cols[0]} ({cols[4][:30]}...)")
                    stats['merged_lines'] += 1
                    i += 2  # Skip both lines
                    continue
        
        # Check for WordN relation - should be Hypernymy
        # gaming (गेमिंग) is a hyponym of act/human_action/human_activity
        if len(cols) >= 9 and cols[-1].strip() == 'WordN':
            cols[-1] = 'Hypernymy'
            line = '\t'.join(cols)
            print(f"Fixed WordN→Hypernymy on line {i+1}: IWN {cols[0]} ({cols[6][:20]}...)")
            stats['fixed_wordn'] += 1
        
        fixed_lines.append(line + '\n')
        i += 1
    
    stats['output_lines'] = len(fixed_lines)
    
    # Write output
    with open(output_path, 'w', encoding='utf-8') as f:
        f.writelines(fixed_lines)
    
    return stats


def main():
    if len(sys.argv) < 3:
        print("Usage: python fix_malformed_tsv.py <input.tsv> <output.tsv>")
        print()
        print("Fixes:")
        print("  1. Merges split lines caused by unescaped quotes in Hindi glosses")
        print("  2. Changes 'WordN' relation to 'Hypernymy'")
        print()
        print("Example:")
        print("  python fix_malformed_tsv.py etc/IWN-En/data/english-hindi-linked.tsv \\")
        print("                              etc/IWN-En/data/english-hindi-linked-fixed.tsv")
        sys.exit(1)
    
    input_path = sys.argv[1]
    output_path = sys.argv[2]
    
    print(f"Fixing malformed lines in {input_path}...")
    print()
    
    stats = fix_tsv(input_path, output_path)
    
    print()
    print("Summary:")
    print(f"  Input lines:  {stats['total_lines']}")
    print(f"  Output lines: {stats['output_lines']}")
    print(f"  Merged split lines: {stats['merged_lines']}")
    print(f"  Fixed WordN→Hypernymy: {stats['fixed_wordn']}")
    print()
    print(f"Written to: {output_path}")


if __name__ == '__main__':
    main()

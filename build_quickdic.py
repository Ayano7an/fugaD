#!/opt/anaconda3/bin/python
"""
Convert vocab_db.json → Fuga Vocabs DE-ZH.quickdic
Requires: pip3 install pyglossary
"""
import json
from pathlib import Path
from pyglossary.glossary_v2 import Glossary

DB_PATH  = Path(__file__).parent / 'vocab_db.json'
OUT_PATH = Path(__file__).parent / 'Fuga Vocabs DE-ZH.quickdic'

def build_definition(entry: dict) -> str:
    zh    = entry.get('zh', '')
    en    = entry.get('en', '')
    lemma = entry.get('lemma', '')
    parts = []
    if zh:
        parts.append(zh)
    if en:
        parts.append(en)
    head = ' · '.join(parts)
    lines = [head]
    if lemma:
        lines.append(f'[{lemma}]')
    return '\n'.join(lines)

def main():
    if not DB_PATH.exists():
        print(f'ERROR: {DB_PATH} not found.')
        return

    db = json.loads(DB_PATH.read_text('utf-8'))
    vocab = db.get('vocab', {})
    if not vocab:
        print('Vocab DB is empty — nothing to convert.')
        return

    Glossary.init()
    glos = Glossary()
    glos.setInfo('title',      'Fuga Vocabs DE-ZH')
    glos.setInfo('author',     'Fuga Vocabs')
    glos.setInfo('sourceLang', 'de')
    glos.setInfo('targetLang', 'zh')

    count = 0
    for word, entry in sorted(vocab.items()):
        defi = build_definition(entry)
        if not defi.strip():
            continue
        glos.addEntry(glos.newEntry([word], defi, defiFormat='m'))
        count += 1

    glos.write(str(OUT_PATH), formatName='QuickDic6')
    print(f'Done: {count} entries → {OUT_PATH}')
    print(f'File size: {OUT_PATH.stat().st_size / 1024:.1f} KB')

if __name__ == '__main__':
    main()

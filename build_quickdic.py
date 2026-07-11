#!/opt/anaconda3/bin/python
"""
Convert vocab_db.json → dicthtmlos-de-zht.zip (Kobo/Tolino dicthtml format)
Place the output zip in /Volumes/TOLINOWUTA/.kobo/dict/ to use on device.
Requires: pip install pyglossary marisa-trie
"""
import json
import shutil
import zipfile
from pathlib import Path

from pyglossary.glossary_v2 import Glossary

DB_PATH     = Path(__file__).parent / 'vocab_db.json'
TMP_DIR     = Path('/tmp/fuga_kobo_build')
OUT_PATH    = Path(__file__).parent / 'dicthtmlos-de-zh.zip'


def build_definition(entry: dict) -> str:
    zh    = entry.get('zh', '')
    en    = entry.get('en', '')
    lemma = entry.get('lemma', '')
    parts = []
    if zh:
        parts.append(f'<b>{zh}</b>')
    if en:
        parts.append(en)
    line1 = ' · '.join(parts)
    line2 = f'<br/><small>{lemma}</small>' if lemma else ''
    return line1 + line2


def main():
    if not DB_PATH.exists():
        print(f'ERROR: {DB_PATH} not found.')
        return

    db    = json.loads(DB_PATH.read_text('utf-8'))
    vocab = db.get('vocab', {})
    if not vocab:
        print('Vocab DB is empty.')
        return

    Glossary.init()
    glos = Glossary()
    glos.setInfo('title',      'Fuga Vocabs DE-ZHT')
    glos.setInfo('author',     'Fuga Vocabs')
    glos.setInfo('sourceLang', 'de')
    glos.setInfo('targetLang', 'zht')

    count = 0
    for word in sorted(vocab):
        entry = vocab[word]
        defi  = build_definition(entry)
        if not defi.strip():
            continue
        glos.addEntry(glos.newEntry([word], defi, defiFormat='h'))
        count += 1

    if TMP_DIR.exists():
        shutil.rmtree(TMP_DIR)
    glos.write(str(TMP_DIR), formatName='Kobo')

    with zipfile.ZipFile(OUT_PATH, 'w', compression=zipfile.ZIP_STORED) as zf:
        for f in sorted(TMP_DIR.iterdir()):
            zf.write(f, arcname=f.name)

    shutil.rmtree(TMP_DIR)

    size_kb = OUT_PATH.stat().st_size / 1024
    print(f'Done: {count} entries → {OUT_PATH.name}  ({size_kb:.1f} KB)')


if __name__ == '__main__':
    main()

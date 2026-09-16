import re
INDIAN_PLATE_PATTERN=re.compile(r'^[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{4}$')

def normalize_indian_plate(text:str)->str:
    return re.sub(r'[^A-Z0-9]','',text.upper()) if text else ''

def is_valid_indian_plate(text:str)->bool:
    return bool(INDIAN_PLATE_PATTERN.fullmatch(normalize_indian_plate(text)))

def repair_indian_plate(text:str)->str:
    """Conservative OCR repair: substitutions/deletion only when they produce a valid
    Indian registration grammar. Never changes an already-valid plate."""
    raw=normalize_indian_plate(text)
    if is_valid_indian_plate(raw): return raw
    candidates=[]
    # Common OCR confusions, applied only as global candidates; grammar decides validity.
    variants={raw}
    for a,b in (("O","0"),("I","1"),("L","1"),("Z","2"),("S","5"),("B","8")):
        variants.add(raw.replace(a,b))
    # One-character deletion handles occasional duplicated OCR glyphs.
    variants |= {v[:i]+v[i+1:] for v in list(variants) for i in range(len(v))}
    for v in variants:
        if is_valid_indian_plate(v):
            # Prefer fewer edits, then preserve length closest to original.
            edits=sum(a!=b for a,b in zip(raw,v))+abs(len(raw)-len(v))
            candidates.append((edits,abs(len(raw)-len(v)),v))
    return min(candidates)[2] if candidates else raw

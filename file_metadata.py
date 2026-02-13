"""
Filename metadata parsing utilities.
Extract BPM and scale/key hints embedded in filenames.
"""

import re
from typing import Optional, Tuple

# Patterns to capture BPM and key/scale from filenames
# Examples: "125 BPM D Min", "140bpm C# Maj", "Cymatics - Infinite - 194 BPM D Min.mid"

BPM_REGEX = re.compile(r"(?i)(\d{2,3})\s*BPM")
KEY_REGEXES = [
    # e.g., "C# Maj", "Db Major", "A Min", "F#m"
    re.compile(r"(?i)([A-G](?:#|b)?)\s*[- ]?\s*(maj(?:or)?|dur)"),
    re.compile(r"(?i)([A-G](?:#|b)?)\s*[- ]?\s*(min(?:or)?|m)"),
    # compact forms like "F#m", "C#m"
    re.compile(r"(?i)([A-G](?:#|b)?)(maj|min|m)\b"),
]


def parse_filename_metadata(filename: str) -> Tuple[Optional[int], Optional[str]]:
    """
    Parse BPM and scale/key hints from filename.
    
    Args:
        filename: Filename string (with or without extension)
    
    Returns:
        (bpm, scale_string) where bpm is int or None, scale_string like "D minor" or "C# major" or None.
    """
    name_no_ext = filename.rsplit('.', 1)[0]

    bpm = None
    bpm_match = BPM_REGEX.search(name_no_ext)
    if bpm_match:
        try:
            bpm = int(bpm_match.group(1))
        except ValueError:
            bpm = None

    scale = None
    for rx in KEY_REGEXES:
        m = rx.search(name_no_ext)
        if m:
            tonic_raw = m.group(1)
            # Normalize tonic: capitalize letter, preserve #, use b for flats only
            tonic = tonic_raw[0].upper()
            if len(tonic_raw) > 1:
                accidental = tonic_raw[1]
                if accidental in ['#', '♯']:
                    tonic += '#'
                elif accidental in ['b', '♭', 'B']:
                    tonic += 'b'
            mode_raw = m.group(2).lower() if len(m.groups()) > 1 else ''
            if mode_raw.startswith('maj') or mode_raw == 'dur':
                scale = f"{tonic} major"
            elif mode_raw.startswith('min') or mode_raw == 'm':
                scale = f"{tonic} minor"
            else:
                # If unknown suffix but tonic present
                scale = f"{tonic}"
            break

    return bpm, scale

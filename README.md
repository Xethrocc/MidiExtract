# MIDI Track Extractor

Process local MIDI files: extract single-track MIDIs, detect key/scale, derive mood, and organize by instrument and mood.

## Features

- **Multi-track extraction**: Extracts each instrument track as a separate MIDI file
- **Filename parsing**: Automatically extracts BPM and key hints from filenames (e.g., `125 BPM D Min`, `F#m`)
- **Musical scale detection**: Detects key/scale using filename hints or music21 analysis
- **Smart organization**: Organizes extracted tracks by instrument
- **Intelligent naming**: Files named as `instrument_BPM_duration_scale.mid`
- **Deduplication**: Detects and removes identical extracted tracks to save disk space
- **MIDI trimming**: Automatically trims leading and trailing empty space from extracted tracks using symusic
- **Parallel processing**: Multi-core processing with timeout protection for corrupted files
- **Progress tracking**: Real-time progress bar for processing

## Workflow

### 1. Installation

**Requirements:**
- Python 3.7 or higher
- pip package manager

**Install dependencies:**
```bash
pip install -r requirements.txt
```

> **Note**: It's recommended to use a virtual environment to avoid dependency conflicts:
> ```bash
> python -m venv venv
> source venv/bin/activate  # On Windows: venv\Scripts\activate
> pip install -r requirements.txt
> ```

**Dependencies:**
- `mido` - MIDI file reading/writing
- `tqdm` - Progress bars
- `symusic` - MIDI trimming (removes leading/trailing silence)

### 2. Add MIDI Files

Drop any `.mid` or `.midi` files into the `midi_files/` folder (flat structure, no subdirectories needed).

Files can have metadata hints in their names:
- BPM hint: `125 BPM`, `140bpm`
- Key hint: `D Minor`, `C# Major`, `F#m`, `Bbmaj`

Examples:
- `Cymatics - Inferno - 125 BPM D Min.mid`
- `FL_ST_Kit04_134_Bass_Midi_F#m.mid`
- `track.mid` (no hints - will be analyzed)

### 3. Run Batch Processor

Basic usage:
```bash
python batch_processor.py
```

Advanced options:
```bash
python batch_processor.py --timeout 60 --no-trim --delete-after
```

Command-line arguments:
- `--timeout` - Timeout in seconds for processing each file (default: 30)
- `--no-trim` - Disable MIDI trimming (enabled by default)
- `--min-trim-ticks` - Minimum ticks to trim (default: 480)
- `--no-trim-trailing` - Disable trimming of trailing silence
- `--delete-after` - Delete source MIDI files after successful processing

Processing pipeline:
- Scan all `.mid`/`.midi` files in `midi_files/`
- Extract each non-empty track as a separate MIDI (parallel processing)
- Parse filename for BPM and key hints
- Detect key/scale (uses filename hint if present, falls back to music21)
- Trim leading and trailing empty space (optional)
- Organize into `extracted_tracks/<instrument>/`
- Deduplicate identical tracks
- Generate extraction log

### 4. Output Structure

```
extracted_tracks/
├── piano/
│   ├── piano_120_BPM_180_sec_cmajor.mid
│   ├── piano_96_BPM_224_sec_gmajor.mid
├── violin/
│   └── violin_140_BPM_120_sec_aminor.mid
└── percussion/
    └── percussion_125_BPM_240_sec_unknown.mid
```

## Modules

| Module | Purpose |
|--------|---------|
| `batch_processor.py` | Main processing pipeline with progress bar and parallel processing |
| `midi_extractor.py` | Extracts tracks from multi-track MIDI files using mido |
| `scale_detector.py` | Detects musical key/scale using music21 |
| `file_metadata.py` | Parses BPM and key hints from filenames |

| `midi_deduplicator.py` | Tracks and removes duplicate files |
| `midi_trimmer.py` | Trims leading and trailing empty space from MIDI files using symusic |
| `tag_processor.py` | Processes tags for organizing MIDI files by genre/style |
| `test_extraction.py` | Test script for extraction functionality |



## Output

### Extraction Log: `extracted_tracks/extraction_log.json`

Contains detailed information about each extracted track:
```json
[
  {
    "source_file": "Cool piano melody - 125 BPM D Min.mid",
    "track_index": 0,
    "instrument": "Piano",
    "scale": "D minor",
    "bpm": 125,
    "duration": 240,
    "output_path": "extracted_tracks/piano/piano_125_BPM_240_sec_dminor.mid",
    "is_duplicate": false
  },
  ...
]
```

### Statistics

Processing summary printed to console:
```
BATCH PROCESSING COMPLETE
============================================================
Total MIDI files processed:    53
Skipped (corrupted/missing):   2
Total tracks extracted:        287
Unique extracted tracks:       283
Duplicates found:              4
Disk space saved:              2.34 MB
============================================================
```

## Notes

- **Empty tracks are skipped**: Tracks with no note events are not extracted
- **Filename hints are trusted**: If a filename contains BPM or key info, it's used with high confidence (0.95)
- **Fallback detection**: If no filename hint, music21 analyzes the MIDI file

- **Deduplication**: Uses SHA256 hashing; identical tracks are kept once with canonical path
- **MIDI trimming**: By default, extracts are trimmed to remove leading/trailing silence (uses symusic); can be disabled with `--no-trim`
- **Parallel processing**: Uses ProcessPoolExecutor for multi-core processing to speed up large batches
- **Timeout protection**: Each file has a timeout (default 30s) to prevent hanging on corrupted files
- **Error handling**: Corrupted files are logged and skipped, processing continues

## Example Usage

Extract tracks from MIDI files:
```bash
# 1. Copy MIDI files to midi_files/
cp /path/to/*.mid midi_files/

# 2. Run processor
python batch_processor.py

# 3. Check organized output
ls extracted_tracks/piano/
# Output: piano_125_BPM_240_sec_dminor.mid
```

Use extraction log to find a specific mood/instrument:
import json

with open('extracted_tracks/extraction_log.json') as f:
    log = json.load(f)

# Find all piano tracks
pianos = [t for t in log if 'piano' in t['instrument'].lower()]
for track in pianos:
    print(f"{track['source_file']} -> {track['output_path']}")
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Dependencies & Attribution

This project uses the following open-source libraries:

- **[mido](https://github.com/mido/mido)** - MIDI file I/O (MIT License)
- **[tqdm](https://github.com/tqdm/tqdm)** - Progress bars (MIT/MPL-2.0 License)
- **[symusic](https://github.com/Yikai-Liao/symusic)** - High-performance MIDI processing (MIT License)

We are grateful to the maintainers and contributors of these excellent libraries.

## Contributing

Contributions are welcome! If you'd like to contribute:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

Please ensure your code follows the existing style and includes appropriate documentation.

"""
Main batch processing pipeline for extracting and organizing MIDI tracks.
"""

import os
import json
from pathlib import Path
from tqdm import tqdm
from mido import MidiFile
import multiprocessing
from concurrent.futures import ProcessPoolExecutor, as_completed, TimeoutError

from midi_extractor import MidiExtractor
from scale_detector import ScaleDetector
from midi_deduplicator import MidiDeduplicator
from file_metadata import parse_filename_metadata
from midi_trimmer import MIDITrimmer


def _sanitize_filename(filename: str) -> str:
    """
    Sanitize filename for filesystem.
    
    Args:
        filename: Original filename
        
    Returns:
        Sanitized filename
    """
    # Remove invalid characters
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '-')
    
    # Replace spaces with underscores
    filename = filename.replace(' ', '_')
    
    # Limit length
    return filename[:200]


def _build_filename(instrument: str, bpm: int, duration: int, scale: str) -> str:
    """
    Build extracted track filename.
    
    Args:
        instrument: Instrument name
        bpm: Tempo in BPM
        duration: Duration in seconds
        scale: Musical scale/key name
        
    Returns:
        Filename like "piano_120_BPM_200_sec_cmajor.mid"
    """
    instrument_clean = _sanitize_filename(instrument)
    scale_part = f"_{scale}" if scale else ""
    
    filename = f"{instrument_clean}_{bpm}_BPM_{duration}_sec{scale_part}.mid"
    return filename


def _build_folder_path(instrument: str) -> str:
    """
    Build complete folder path.
    
    Args:
        instrument: Instrument name
        
    Returns:
        Folder path like "piano"
    """
    instrument_clean = _sanitize_filename(instrument)
    return instrument_clean


def _process_single_file_standalone(midi_files_dir: str, filename: str, output_dir: str, timeout: int, 
                                     trim: bool = True, min_trim_ticks: int = 480, trim_trailing: bool = True) -> list:
    """
    Process a single MIDI file - standalone function for multiprocessing.
    
    This function is picklable and can be used with ProcessPoolExecutor.
    Deduplication is handled separately in the main process.
    
    Args:
        midi_files_dir: Directory containing MIDI files
        filename: Name of the MIDI file to process
        output_dir: Output directory for extracted tracks
        timeout: Processing timeout (not used here, handled by executor)
        trim: Whether to trim leading/trailing empty space from extracted tracks
        min_trim_ticks: Minimum number of ticks to trim
        trim_trailing: Whether to trim trailing empty bars
        
    Returns:
        extraction_log: List of extraction log entries for this file
    """
    extraction_log = []
    full_midi_path = os.path.join(midi_files_dir, filename)

    if not os.path.exists(full_midi_path):
        return extraction_log
    
    # Parse filename metadata hints
    filename_bpm, filename_scale = parse_filename_metadata(filename)

    try:
        # OPTIMIZATION: Read MIDI file ONCE
        midi_file = MidiFile(full_midi_path)
        
        # OPTIMIZATION: Pass MidiFile object to detect_scale instead of path
        scale_name, confidence = ScaleDetector.detect_scale(midi_file, filename_hint=filename_scale)
        scale_for_filename = ScaleDetector.format_scale_for_filename(scale_name)
        
        # OPTIMIZATION: Pass MidiFile object to extract_tracks_from_obj instead of path
        tracks, file_bpm, error = MidiExtractor.extract_tracks_from_obj(midi_file)
        
        if error or not tracks:
            return extraction_log
        
        # Use BPM from filename hint, else from file, else default 120
        bpm = filename_bpm or file_bpm or 120
        
        # OPTIMIZATION: Pass MidiFile object to get_duration_seconds instead of path
        duration = MidiExtractor.get_duration_seconds(midi_file)
        
        # OPTIMIZATION: Extract ticks_per_beat once
        ticks_per_beat = midi_file.ticks_per_beat
        
        # Initialize trimmer if needed
        trimmer = MIDITrimmer(min_trim_ticks=min_trim_ticks, trim_trailing=trim_trailing) if trim else None
        
        # Process each track
        for track_data in tracks:
            instrument = track_data['instrument']
            
            # Build folder path (by instrument only)
            folder_path = _build_folder_path(instrument)
            
            # Build filename
            out_filename = _build_filename(instrument, bpm, duration, scale_for_filename)
            
            # Full output path
            output_path = os.path.join(output_dir, folder_path, out_filename)
            
            # Save track
            try:
                # OPTIMIZATION: Pass ticks_per_beat directly instead of file path
                MidiExtractor.save_track(track_data, output_path, ticks_per_beat=ticks_per_beat)
                
                # Apply trimming if enabled
                if trim:
                    temp_path = output_path.replace('.mid', '_temp.mid')
                    os.rename(output_path, temp_path)
                    trim_stats = trimmer.trim_file(Path(temp_path), Path(output_path))
                    os.remove(temp_path)
                    if not trim_stats.success:
                        continue
                
                extraction_log.append({
                    'source_file': filename,
                    'track_index': track_data['track_index'],
                    'instrument': instrument,
                    'output_path': output_path,
                    'scale': scale_name,
                    'is_duplicate': False,  # Will be updated in dedup phase
                    'bpm': bpm,
                    'duration': duration,
                })
            
            except Exception as e:
                # Log error but continue processing other tracks
                pass
    
    except Exception as e:
        # Silently fail for this file
        pass
    
    return extraction_log


class BatchProcessor:
    """Processes all MIDI files in a directory: extracts tracks, detects metadata, organizes files."""

    def __init__(self, midi_files_dir: str, output_dir: str, timeout: int = 30, delete_after_processing: bool = False,
                 trim: bool = True, min_trim_ticks: int = 480, trim_trailing: bool = True):
        """
        Initialize batch processor.

        Args:
            midi_files_dir: Directory containing MIDI files (flat)
            output_dir: Output directory for organized extracted tracks
            timeout: Processing timeout per file in seconds (default: 30)
            delete_after_processing: Whether to delete files after processing or timeout (default: False)
            trim: Whether to trim leading/trailing empty space from extracted tracks (default: True)
            min_trim_ticks: Minimum number of ticks to trim (default: 480)
            trim_trailing: Whether to trim trailing empty bars (default: True)
        """
        self.midi_files_dir = midi_files_dir
        self.output_dir = output_dir
        self.timeout = timeout
        self.delete_after_processing = delete_after_processing
        self.trim = trim
        self.min_trim_ticks = min_trim_ticks
        self.trim_trailing = trim_trailing

        # Gather files
        self.midi_files = self._list_midis()

        # Statistics
        self.stats = {
            'total_files': len(self.midi_files),
            'processed': 0,
            'skipped_corrupted': 0,
            'extracted_tracks': 0,
            'duplicates_skipped': 0,
            'timeouts': 0,
            'errors': [],
        }
    
    def _list_midis(self):
        """List all .mid/.midi files in midi_files_dir (non-recursive)."""
        files = []
        for name in os.listdir(self.midi_files_dir):
            if name.lower().endswith(('.mid', '.midi')):
                files.append(name)
        return files
    
    def process_all(self):
        """
        Process all MIDI files: extract tracks, organize, deduplicate.
        Uses ProcessPoolExecutor for parallel processing with persistent worker pool.
        """
        print(f"Starting batch processing of {len(self.midi_files)} MIDI files...")
        print(f"Output directory: {self.output_dir}")
        print(f"Processing timeout: {self.timeout} seconds per file")
        print(f"Delete after processing: {self.delete_after_processing}\n")
        
        # Create output directory
        os.makedirs(self.output_dir, exist_ok=True)
        
        # OPTIMIZATION: Use persistent ProcessPoolExecutor with multiple workers
        num_workers = min(multiprocessing.cpu_count(), 4)
        print(f"Using {num_workers} worker processes for parallel extraction\n")
        
        # Phase 1: Parallel extraction (no dedup yet)
        all_results = []
        files_to_delete = []  # Track files for deletion
        
        with ProcessPoolExecutor(max_workers=num_workers) as executor:
            # Submit all files for processing
            future_to_file = {
                executor.submit(
                    _process_single_file_standalone,
                    self.midi_files_dir, filename, self.output_dir, self.timeout,
                    self.trim, self.min_trim_ticks, self.trim_trailing
                ): filename
                for filename in self.midi_files
            }
            
            # Process results as they complete
            for future in tqdm(as_completed(future_to_file), total=len(self.midi_files), desc="Processing MIDI files", unit="file"):
                filename = future_to_file[future]
                full_midi_path = os.path.join(self.midi_files_dir, filename)
                
                try:
                    # Get result with timeout
                    file_log = future.result(timeout=self.timeout)
                    
                    if file_log:
                        # File was processed successfully
                        self.stats['processed'] += 1
                        self.stats['extracted_tracks'] += len(file_log)
                        all_results.extend(file_log)
                        files_to_delete.append(full_midi_path)
                    else:
                        # File was skipped (corrupted or no tracks)
                        self.stats['skipped_corrupted'] += 1
                        files_to_delete.append(full_midi_path)
                
                except TimeoutError:
                    # Timeout occurred
                    self.stats['timeouts'] += 1
                    self.stats['errors'].append(f"Timeout processing file: {filename}")
                    files_to_delete.append(full_midi_path)
                
                except Exception as e:
                    # Other error occurred
                    self.stats['errors'].append(f"Error processing {filename}: {str(e)}")
                    self.stats['skipped_corrupted'] += 1
                    files_to_delete.append(full_midi_path)
        
        # Phase 2: Sequential deduplication in main process
        print("\nRunning deduplication...")
        deduplicator = MidiDeduplicator()
        
        for entry in all_results:
            if entry.get('output_path') and os.path.exists(entry['output_path']):
                is_dup, canonical = deduplicator.register_file(entry['output_path'])
                if is_dup:
                    self.stats['duplicates_skipped'] += 1
                    # Remove duplicate file, keep canonical
                    try:
                        os.remove(entry['output_path'])
                        entry['output_path'] = canonical
                    except Exception:
                        pass
                    entry['is_duplicate'] = True
        
        # Delete files after processing if configured
        if self.delete_after_processing:
            print("\nDeleting processed files...")
            for file_path in files_to_delete:
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                except Exception as e:
                    self.stats['errors'].append(f"Failed to delete file {os.path.basename(file_path)}: {str(e)}")
        
        # Print summary
        self._print_summary(all_results)
        
        # Save extraction log
        self._save_extraction_log(all_results)
    
    def _print_summary(self, extraction_log: list):
        """Print processing summary."""
        print("\n" + "="*60)
        print("BATCH PROCESSING COMPLETE")
        print("="*60)
        print(f"Total MIDI files processed:    {self.stats['processed']}")
        print(f"Skipped (corrupted/missing):   {self.stats['skipped_corrupted']}")
        print(f"Processing timeouts:           {self.stats['timeouts']}")
        print(f"Total tracks extracted:        {self.stats['extracted_tracks']}")
        print()
        
        # Dedup stats
        dedup_report = {
            'total_unique_files': self.stats['extracted_tracks'] - self.stats['duplicates_skipped'],
            'duplicates_found': self.stats['duplicates_skipped'],
            'mb_saved': 0  # Approximate
        }
        print(f"Unique extracted tracks:       {dedup_report['total_unique_files']}")
        print(f"Duplicates found:              {dedup_report['duplicates_found']}")
        print()
        
        if self.stats['errors']:
            print(f"Errors encountered:            {len(self.stats['errors'])}")
            for error in self.stats['errors'][:5]:
                print(f"  - {error}")
            if len(self.stats['errors']) > 5:
                print(f"  ... and {len(self.stats['errors']) - 5} more")
        
        print("="*60)
    
    def _save_extraction_log(self, extraction_log: list):
        """Save extraction log to JSON file."""
        log_path = os.path.join(self.output_dir, 'extraction_log.json')
        
        try:
            with open(log_path, 'w', encoding='utf-8') as f:
                json.dump(extraction_log, f, ensure_ascii=False, indent=2)
            print(f"\nExtraction log saved to: {log_path}")
        except Exception as e:
            print(f"Error saving extraction log: {e}")


if __name__ == "__main__":
    import argparse

    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Batch process MIDI files with timeout and deletion options")
    parser.add_argument("--input-dir", default="midi_files", help="Directory containing MIDI files (default: midi_files)")
    parser.add_argument("--output-dir", default="extracted_tracks", help="Output directory for organized tracks (default: extracted_tracks)")
    parser.add_argument("--timeout", type=int, default=30, help="Processing timeout per file in seconds (default: 30)")
    parser.add_argument("--delete-after", action="store_true", help="Delete files after processing or timeout")
    parser.add_argument("--no-trim", action="store_false", dest="trim", help="Disable trimming of leading/trailing empty space")
    parser.add_argument("--min-trim-ticks", type=int, default=480, help="Minimum number of ticks to trim (default: 480)")
    parser.add_argument("--no-trim-trailing", action="store_false", dest="trim_trailing", help="Disable trimming of trailing empty bars")

    args = parser.parse_args()

    # Run batch processor
    processor = BatchProcessor(
        midi_files_dir=args.input_dir,
        output_dir=args.output_dir,
        timeout=args.timeout,
        delete_after_processing=args.delete_after,
        trim=args.trim,
        min_trim_ticks=args.min_trim_ticks,
        trim_trailing=args.trim_trailing
    )
    processor.process_all()

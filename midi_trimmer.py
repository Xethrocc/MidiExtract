"""
Post-processing script to trim leading and trailing empty space from extracted MIDI files.

This script scans the data/processed/by-instrument/ directories for extracted MIDI files,
detects and trims leading empty bars (before first note) and trailing empty bars (after last note),
and saves the trimmed version back to the same location (or optionally to a new location).

Usage:
    python scripts/trim_extracted_tracks.py [options]

Options:
    --input-dir PATH        Input directory to scan (default: data/processed/by-instrument/)
    --output-dir PATH       Output directory (default: same as input, overwrites files)
    --dry-run              Simulate trimming without saving files
    --backup               Create backup of original files before trimming
    --min-trim-ticks N     Minimum ticks to trim (default: 480, ~1 beat at 480 PPQ)
    --trim-trailing        Also trim trailing empty bars (default: True)
    --report-path PATH     Path to save summary report (default: data/processed/trim_report.json)
    --verbose              Enable verbose logging
"""

import os
import sys
import argparse
import logging
import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
import shutil

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import symusic
    SYMUSIC_AVAILABLE = True
except ImportError:
    SYMUSIC_AVAILABLE = False
    print("Error: symusic is required for this script. Install it with: pip install symusic")
    sys.exit(1)


@dataclass
class TrimStatistics:
    """Statistics for a single file trimming operation."""
    file_path: str
    original_duration_ticks: int
    trimmed_start_ticks: int
    trimmed_end_ticks: int
    new_duration_ticks: int
    note_count: int
    first_note_time: int
    last_note_time: int
    tempo_count: int
    time_sig_count: int
    success: bool
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'file_path': self.file_path,
            'original_duration_ticks': self.original_duration_ticks,
            'trimmed_start_ticks': self.trimmed_start_ticks,
            'trimmed_end_ticks': self.trimmed_end_ticks,
            'new_duration_ticks': self.new_duration_ticks,
            'note_count': self.note_count,
            'first_note_time': self.first_note_time,
            'last_note_time': self.last_note_time,
            'tempo_count': self.tempo_count,
            'time_sig_count': self.time_sig_count,
            'success': self.success,
            'error_message': self.error_message
        }


@dataclass
class TrimReport:
    """Summary report of the entire trimming operation."""
    total_files_scanned: int = 0
    files_processed: int = 0
    files_trimmed: int = 0
    files_skipped: int = 0
    files_failed: int = 0
    total_ticks_trimmed_start: int = 0
    total_ticks_trimmed_end: int = 0
    processing_time: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)
    file_statistics: List[TrimStatistics] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'summary': {
                'total_files_scanned': self.total_files_scanned,
                'files_processed': self.files_processed,
                'files_trimmed': self.files_trimmed,
                'files_skipped': self.files_skipped,
                'files_failed': self.files_failed,
                'total_ticks_trimmed_start': self.total_ticks_trimmed_start,
                'total_ticks_trimmed_end': self.total_ticks_trimmed_end,
                'processing_time': self.processing_time,
                'timestamp': self.timestamp.isoformat()
            },
            'file_statistics': [stat.to_dict() for stat in self.file_statistics]
        }


class MIDITrimmer:
    """Handles trimming of MIDI files using symusic."""
    
    def __init__(self, min_trim_ticks: int = 480, trim_trailing: bool = True, verbose: bool = False):
        """
        Initialize the MIDI trimmer.
        
        Args:
            min_trim_ticks: Minimum number of ticks to trim (default: 480, ~1 beat at 480 PPQ)
            trim_trailing: Whether to trim trailing empty bars
            verbose: Enable verbose logging
        """
        self.min_trim_ticks = min_trim_ticks
        self.trim_trailing = trim_trailing
        self.verbose = verbose
        
        # Setup logging
        log_level = logging.DEBUG if verbose else logging.INFO
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)
    
    def find_note_boundaries(self, score: symusic.Score) -> Tuple[Optional[int], Optional[int]]:
        """
        Find the first note start time and last note end time across all tracks.
        
        Args:
            score: symusic Score object
            
        Returns:
            Tuple of (first_note_time, last_note_time) in ticks, or (None, None) if no notes
        """
        first_note_time = None
        last_note_time = None
        
        for track in score.tracks:
            if not track.notes:
                continue
                
            for note in track.notes:
                note_start = note.time
                note_end = note.time + note.duration
                
                if first_note_time is None or note_start < first_note_time:
                    first_note_time = note_start
                
                if last_note_time is None or note_end > last_note_time:
                    last_note_time = note_end
        
        return first_note_time, last_note_time
    
    def count_notes(self, score: symusic.Score) -> int:
        """Count total notes across all tracks."""
        return sum(len(track.notes) for track in score.tracks)
    
    def shift_events(self, score: symusic.Score, shift_ticks: int) -> None:
        """
        Shift all time-based events by the specified number of ticks.
        
        Args:
            score: symusic Score object to modify in-place
            shift_ticks: Number of ticks to shift (negative to shift earlier)
        """
        if shift_ticks == 0:
            return
        
        # Shift notes in all tracks
        for track in score.tracks:
            for note in track.notes:
                note.time = max(0, note.time - shift_ticks)
            
            # Shift control changes
            for cc in track.controls:
                cc.time = max(0, cc.time - shift_ticks)
            
            # Shift pitch bends
            for pb in track.pitch_bends:
                pb.time = max(0, pb.time - shift_ticks)
            
            # Shift pedals
            for pedal in track.pedals:
                pedal.time = max(0, pedal.time - shift_ticks)
        
        # Shift tempo changes
        for tempo in score.tempos:
            tempo.time = max(0, tempo.time - shift_ticks)
        
        # Shift time signatures
        for time_sig in score.time_signatures:
            time_sig.time = max(0, time_sig.time - shift_ticks)
        
        # Shift key signatures
        for key_sig in score.key_signatures:
            key_sig.time = max(0, key_sig.time - shift_ticks)
        
        # Shift lyrics if present
        for track in score.tracks:
            if hasattr(track, 'lyrics'):
                for lyric in track.lyrics:
                    lyric.time = max(0, lyric.time - shift_ticks)
    
    def trim_file(self, input_path: Path, output_path: Optional[Path] = None) -> TrimStatistics:
        """
        Trim a single MIDI file.
        
        Args:
            input_path: Path to input MIDI file
            output_path: Path to save trimmed file (if None, overwrites input)
            
        Returns:
            TrimStatistics object with trimming results
        """
        try:
            # Load MIDI file
            self.logger.debug(f"Loading {input_path}")
            score = symusic.Score(str(input_path))
            
            # Get original duration
            original_duration = score.end()
            
            # Find note boundaries
            first_note_time, last_note_time = self.find_note_boundaries(score)
            
            # Count notes
            note_count = self.count_notes(score)
            
            if first_note_time is None or last_note_time is None:
                self.logger.warning(f"No notes found in {input_path}, skipping")
                return TrimStatistics(
                    file_path=str(input_path),
                    original_duration_ticks=original_duration,
                    trimmed_start_ticks=0,
                    trimmed_end_ticks=0,
                    new_duration_ticks=original_duration,
                    note_count=0,
                    first_note_time=0,
                    last_note_time=0,
                    tempo_count=len(score.tempos),
                    time_sig_count=len(score.time_signatures),
                    success=False,
                    error_message="No notes found in file"
                )
            
            # Calculate trimming amounts
            trim_start = first_note_time if first_note_time >= self.min_trim_ticks else 0
            trim_end = 0
            
            if self.trim_trailing:
                trailing_space = original_duration - last_note_time
                if trailing_space >= self.min_trim_ticks:
                    trim_end = trailing_space
            
            # Apply trimming
            if trim_start > 0:
                self.logger.debug(f"Trimming {trim_start} ticks from start")
                self.shift_events(score, trim_start)
            
            # Calculate new duration
            new_duration = score.end()
            
            # Save file if output path specified
            if output_path:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                score.dump_midi(str(output_path))
                self.logger.debug(f"Saved to {output_path}")
            
            return TrimStatistics(
                file_path=str(input_path),
                original_duration_ticks=original_duration,
                trimmed_start_ticks=trim_start,
                trimmed_end_ticks=trim_end,
                new_duration_ticks=new_duration,
                note_count=note_count,
                first_note_time=first_note_time,
                last_note_time=last_note_time,
                tempo_count=len(score.tempos),
                time_sig_count=len(score.time_signatures),
                success=True
            )
            
        except Exception as e:
            self.logger.error(f"Error processing {input_path}: {e}")
            return TrimStatistics(
                file_path=str(input_path),
                original_duration_ticks=0,
                trimmed_start_ticks=0,
                trimmed_end_ticks=0,
                new_duration_ticks=0,
                note_count=0,
                first_note_time=0,
                last_note_time=0,
                tempo_count=0,
                time_sig_count=0,
                success=False,
                error_message=str(e)
            )


class TrimProcessor:
    """Main processor for batch trimming operations."""
    
    def __init__(
        self,
        input_dir: Path,
        output_dir: Optional[Path] = None,
        dry_run: bool = False,
        backup: bool = False,
        min_trim_ticks: int = 480,
        trim_trailing: bool = True,
        verbose: bool = False
    ):
        """
        Initialize the trim processor.
        
        Args:
            input_dir: Directory to scan for MIDI files
            output_dir: Output directory (if None, overwrites input files)
            dry_run: If True, simulate without saving
            backup: If True, create backups before overwriting
            min_trim_ticks: Minimum ticks to trim
            trim_trailing: Whether to trim trailing empty bars
            verbose: Enable verbose logging
        """
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.dry_run = dry_run
        self.backup = backup
        self.verbose = verbose
        
        self.trimmer = MIDITrimmer(
            min_trim_ticks=min_trim_ticks,
            trim_trailing=trim_trailing,
            verbose=verbose
        )
        
        self.logger = logging.getLogger(__name__)
    
    def find_midi_files(self) -> List[Path]:
        """Find all MIDI files in the input directory."""
        midi_files = []
        
        for root, dirs, files in os.walk(self.input_dir):
            for file in files:
                if file.lower().endswith(('.mid', '.midi')):
                    midi_files.append(Path(root) / file)
        
        return sorted(midi_files)
    
    def create_backup(self, file_path: Path) -> None:
        """Create a backup of the file."""
        backup_path = file_path.with_suffix(file_path.suffix + '.backup')
        shutil.copy2(file_path, backup_path)
        self.logger.debug(f"Created backup: {backup_path}")
    
    def process_all(self) -> TrimReport:
        """
        Process all MIDI files in the input directory.
        
        Returns:
            TrimReport with summary and detailed statistics
        """
        import time
        start_time = time.time()
        
        report = TrimReport()
        
        # Find all MIDI files
        midi_files = self.find_midi_files()
        report.total_files_scanned = len(midi_files)
        
        self.logger.info(f"Found {len(midi_files)} MIDI files to process")
        
        if self.dry_run:
            self.logger.info("DRY RUN MODE - No files will be modified")
        
        # Process each file
        for i, input_path in enumerate(midi_files, 1):
            self.logger.info(f"Processing [{i}/{len(midi_files)}]: {input_path.name}")
            
            # Determine output path
            if self.output_dir:
                # Preserve directory structure relative to input_dir
                rel_path = input_path.relative_to(self.input_dir)
                output_path = self.output_dir / rel_path
            else:
                output_path = input_path
            
            # Create backup if requested and not dry run
            if self.backup and not self.dry_run and output_path == input_path:
                self.create_backup(input_path)
            
            # Trim the file
            stats = self.trimmer.trim_file(
                input_path,
                output_path if not self.dry_run else None
            )
            
            # Update report
            report.file_statistics.append(stats)
            report.files_processed += 1
            
            if stats.success:
                if stats.trimmed_start_ticks > 0 or stats.trimmed_end_ticks > 0:
                    report.files_trimmed += 1
                    report.total_ticks_trimmed_start += stats.trimmed_start_ticks
                    report.total_ticks_trimmed_end += stats.trimmed_end_ticks
                    
                    self.logger.info(
                        f"  Trimmed: {stats.trimmed_start_ticks} ticks from start, "
                        f"{stats.trimmed_end_ticks} ticks from end"
                    )
                else:
                    report.files_skipped += 1
                    self.logger.info("  No trimming needed")
            else:
                report.files_failed += 1
                self.logger.error(f"  Failed: {stats.error_message}")
        
        # Calculate processing time
        report.processing_time = time.time() - start_time
        
        return report
    
    def print_summary(self, report: TrimReport) -> None:
        """Print a summary of the trimming operation."""
        print("\n" + "=" * 80)
        print("TRIMMING SUMMARY")
        print("=" * 80)
        print(f"Total files scanned:     {report.total_files_scanned}")
        print(f"Files processed:         {report.files_processed}")
        print(f"Files trimmed:           {report.files_trimmed}")
        print(f"Files skipped:           {report.files_skipped}")
        print(f"Files failed:            {report.files_failed}")
        print(f"Total ticks trimmed (start): {report.total_ticks_trimmed_start}")
        print(f"Total ticks trimmed (end):   {report.total_ticks_trimmed_end}")
        print(f"Processing time:         {report.processing_time:.2f} seconds")
        print("=" * 80)
        
        if report.files_trimmed > 0:
            avg_trim_start = report.total_ticks_trimmed_start / report.files_trimmed
            avg_trim_end = report.total_ticks_trimmed_end / report.files_trimmed
            print(f"\nAverage trim per file:")
            print(f"  Start: {avg_trim_start:.0f} ticks")
            print(f"  End:   {avg_trim_end:.0f} ticks")
    
    def save_report(self, report: TrimReport, report_path: Path) -> None:
        """Save the report to a JSON file."""
        report_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(report_path, 'w') as f:
            json.dump(report.to_dict(), f, indent=2)
        
        self.logger.info(f"Report saved to: {report_path}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Trim leading and trailing empty space from MIDI files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        '--input-dir',
        type=Path,
        default=Path('data/processed/by-instrument'),
        help='Input directory to scan (default: data/processed/by-instrument/)'
    )
    
    parser.add_argument(
        '--output-dir',
        type=Path,
        default=None,
        help='Output directory (default: same as input, overwrites files)'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Simulate trimming without saving files'
    )
    
    parser.add_argument(
        '--backup',
        action='store_true',
        help='Create backup of original files before trimming'
    )
    
    parser.add_argument(
        '--min-trim-ticks',
        type=int,
        default=480,
        help='Minimum ticks to trim (default: 480, ~1 beat at 480 PPQ)'
    )
    
    parser.add_argument(
        '--no-trim-trailing',
        action='store_true',
        help='Do not trim trailing empty bars'
    )
    
    parser.add_argument(
        '--report-path',
        type=Path,
        default=Path('data/processed/trim_report.json'),
        help='Path to save summary report (default: data/processed/trim_report.json)'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    
    args = parser.parse_args()
    
    # Validate input directory
    if not args.input_dir.exists():
        print(f"Error: Input directory does not exist: {args.input_dir}")
        sys.exit(1)
    
    # Create processor
    processor = TrimProcessor(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        dry_run=args.dry_run,
        backup=args.backup,
        min_trim_ticks=args.min_trim_ticks,
        trim_trailing=not args.no_trim_trailing,
        verbose=args.verbose
    )
    
    # Process all files
    report = processor.process_all()
    
    # Print summary
    processor.print_summary(report)
    
    # Save report
    if not args.dry_run:
        processor.save_report(report, args.report_path)
    
    # Exit with appropriate code
    sys.exit(0 if report.files_failed == 0 else 1)


if __name__ == '__main__':
    main()

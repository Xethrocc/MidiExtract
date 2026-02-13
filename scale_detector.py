"""
Musical scale/key detection module using Krumhansl-Schmuckler algorithm.
"""

from typing import Optional, Tuple, Union
import mido


class ScaleDetector:
    """Detects musical scale/key from MIDI files using pitch-class histogram analysis."""
    
    # Krumhansl-Kessler key profiles (correlation weights for each pitch class)
    MAJOR_PROFILE = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
    MINOR_PROFILE = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]
    
    # Note names for each pitch class (0=C, 1=C#, etc.)
    NOTE_NAMES = ['C', 'C#', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'Ab', 'A', 'Bb', 'B']
    
    @staticmethod
    def detect_scale(midi_input: Union[str, mido.MidiFile], filename_hint: Optional[str] = None) -> Tuple[Optional[str], float]:
        """
        Detect the musical scale/key of a MIDI file using Krumhansl-Schmuckler algorithm.
        
        Args:
            midi_input: Either a file path (str) or a mido.MidiFile object
            filename_hint: Optional pre-detected scale from filename (returned with 0.95 confidence)
            
        Returns:
            Tuple of (scale_name, confidence)
            - scale_name: String like "C Major", "A Minor"; "unknown" if detection fails
            - confidence: Float 0.0-1.0 (0 if detection failed)
        """
        # If user provided hint from filename, trust it first
        if filename_hint:
            return filename_hint, 0.95
        
        try:
            # Load MIDI file if path provided
            if isinstance(midi_input, str):
                midi_file = mido.MidiFile(midi_input)
            else:
                midi_file = midi_input
            
            # Build pitch-class histogram
            pitch_class_histogram = ScaleDetector._build_pitch_class_histogram(midi_file)
            
            # Check if we have any notes
            if sum(pitch_class_histogram) == 0:
                return "unknown", 0.0
            
            # Find best matching key using Krumhansl-Schmuckler
            scale_name, confidence = ScaleDetector._find_best_key(pitch_class_histogram)
            
            return scale_name, confidence
            
        except Exception:
            # Silently fail and return unknown
            return "unknown", 0.0
    
    @staticmethod
    def _build_pitch_class_histogram(midi_file: mido.MidiFile) -> list:
        """
        Build a 12-bin histogram of pitch classes from MIDI file.
        
        Args:
            midi_file: mido.MidiFile object
            
        Returns:
            List of 12 integers representing note counts for each pitch class (C through B)
        """
        histogram = [0] * 12
        
        for track in midi_file.tracks:
            for msg in track:
                # Count note_on events with velocity > 0
                if msg.type == 'note_on' and msg.velocity > 0:
                    pitch_class = msg.note % 12
                    histogram[pitch_class] += 1
        
        return histogram
    
    @staticmethod
    def _find_best_key(histogram: list) -> Tuple[str, float]:
        """
        Find the best matching key using Pearson correlation with Krumhansl-Kessler profiles.
        
        Args:
            histogram: 12-element list of pitch class counts
            
        Returns:
            Tuple of (scale_name, confidence) where confidence is the correlation coefficient
        """
        best_correlation = -1.0
        best_key = "unknown"
        best_mode = "Major"
        
        # Try all 12 possible root notes with both major and minor profiles
        for root in range(12):
            # Rotate histogram to test this root
            rotated_histogram = histogram[root:] + histogram[:root]
            
            # Test major profile
            correlation = ScaleDetector._pearson_correlation(rotated_histogram, ScaleDetector.MAJOR_PROFILE)
            if correlation > best_correlation:
                best_correlation = correlation
                best_key = ScaleDetector.NOTE_NAMES[root]
                best_mode = "Major"
            
            # Test minor profile
            correlation = ScaleDetector._pearson_correlation(rotated_histogram, ScaleDetector.MINOR_PROFILE)
            if correlation > best_correlation:
                best_correlation = correlation
                best_key = ScaleDetector.NOTE_NAMES[root]
                best_mode = "Minor"
        
        # Normalize correlation to 0.0-1.0 range
        # Pearson correlation ranges from -1 to 1, but we expect positive correlations
        confidence = max(0.0, min(1.0, (best_correlation + 1.0) / 2.0))
        
        scale_name = f"{best_key} {best_mode}"
        return scale_name, confidence
    
    @staticmethod
    def _pearson_correlation(x: list, y: list) -> float:
        """
        Calculate Pearson correlation coefficient between two lists.
        
        Args:
            x: First list of values
            y: Second list of values
            
        Returns:
            Correlation coefficient (-1.0 to 1.0)
        """
        n = len(x)
        if n == 0:
            return 0.0
        
        # Calculate means
        mean_x = sum(x) / n
        mean_y = sum(y) / n
        
        # Calculate correlation
        numerator = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
        
        sum_sq_x = sum((x[i] - mean_x) ** 2 for i in range(n))
        sum_sq_y = sum((y[i] - mean_y) ** 2 for i in range(n))
        
        denominator = (sum_sq_x * sum_sq_y) ** 0.5
        
        if denominator == 0:
            return 0.0
        
        return numerator / denominator
    
    @staticmethod
    def format_scale_for_filename(scale_name: Optional[str]) -> str:
        """
        Format scale name for use in filename.
        
        Args:
            scale_name: Scale name like "C Major" or None
            
        Returns:
            Formatted string for filename, empty string if None or "unknown"
        """
        if not scale_name or scale_name.lower() == "unknown":
            return ""
        
        # Convert to abbreviated form if needed
        # "C Major" → "cmajor" or keep as-is
        return scale_name.lower().replace(" ", "")

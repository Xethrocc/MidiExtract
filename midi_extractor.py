"""
MIDI track extraction module.
Extracts individual tracks from multi-track MIDI files.
"""

import mido
from mido import MidiFile
import os
from typing import List, Dict, Tuple, Optional, Union

# General MIDI instrument mapping (Program 0-127)
GM_INSTRUMENTS = {
    0: "Acoustic Piano", 1: "Bright Piano", 2: "Electric Piano 1", 3: "Electric Piano 2",
    4: "Honky Tonk Piano", 5: "Electric Piano", 6: "Harpsichord", 7: "Clavier",
    8: "Celesta", 9: "Glockenspiel", 10: "Music Box", 11: "Vibraphone",
    12: "Marimba", 13: "Xylophone", 14: "Tubular Bells", 15: "Dulcimer",
    16: "Drawbar Organ", 17: "Percussive Organ", 18: "Rock Organ", 19: "Church Organ",
    20: "Reed Organ", 21: "Accordion", 22: "Harmonica", 23: "Tango Accordion",
    24: "Acoustic Nylon Guitar", 25: "Acoustic Steel Guitar", 26: "Electric Jazz Guitar",
    27: "Electric Clean Guitar", 28: "Electric Muted Guitar", 29: "Overdriven Guitar",
    30: "Distortion Guitar", 31: "Guitar Harmonics",
    32: "Acoustic Bass", 33: "Electric Finger Bass", 34: "Electric Pick Bass",
    35: "Fretless Bass", 36: "Slap Bass 1", 37: "Slap Bass 2",
    38: "Synth Bass 1", 39: "Synth Bass 2",
    40: "Violin", 41: "Viola", 42: "Cello", 43: "Contrabass",
    44: "Tremolo Strings", 45: "Pizzicato Strings", 46: "Orchestral Harp", 47: "Timpani",
    48: "String Ensemble 1", 49: "String Ensemble 2", 50: "Synth Strings 1", 51: "Synth Strings 2",
    52: "Choir Aahs", 53: "Choir Oohs", 54: "Synth Voice", 55: "Orchestra Hit",
    56: "Trumpet", 57: "Trombone", 58: "Tuba", 59: "Muted Trumpet",
    60: "French Horn", 61: "Brass Section", 62: "Synth Brass 1", 63: "Synth Brass 2",
    64: "Soprano Sax", 65: "Alto Sax", 66: "Tenor Sax", 67: "Baritone Sax",
    68: "Oboe", 69: "English Horn", 70: "Bassoon", 71: "Clarinet",
    72: "Piccolo", 73: "Flute", 74: "Recorder", 75: "Pan Flute",
    76: "Bottle Blow", 77: "Shakuhachi", 78: "Whistle", 79: "Ocarina",
    80: "Lead Synth Square", 81: "Lead Synth Sawtooth", 82: "Lead Synth Calliope",
    83: "Lead Synth Chiff", 84: "Lead Synth Charang", 85: "Lead Synth Voice",
    86: "Lead Synth Fifths", 87: "Lead Synth Bass + Lead",
    88: "Pad Synth New Age", 89: "Pad Synth Warm", 90: "Pad Synth Polysynth",
    91: "Pad Synth Choir", 92: "Pad Synth Bowed", 93: "Pad Synth Metallic",
    94: "Pad Synth Halo", 95: "Pad Synth Sweep",
    96: "Fx Synth Rain", 97: "Fx Synth Soundtrack", 98: "Fx Synth Crystal",
    99: "Fx Synth Atmosphere", 100: "Fx Synth Brightness",
    101: "Fx Synth Goblins", 102: "Fx Synth Echoes", 103: "Fx Synth Sci Fi",
    104: "Sitar", 105: "Banjo", 106: "Shamisen", 107: "Koto",
    108: "Kalimba", 109: "Bagpipe", 110: "Fiddle", 111: "Shanai",
    112: "Tinkle Bell", 113: "Agogo", 114: "Steel Drums", 115: "Woodblock",
    116: "Taiko Drum", 117: "Melodic Tom", 118: "Synth Drum", 119: "Reverse Cymbal",
    120: "Guitar Fret Noise", 121: "Breath Noise", 122: "Seashore", 123: "Bird Tweet",
    124: "Telephone Ring", 125: "Helicopter", 126: "Applause", 127: "Gunshot",
}

class MidiExtractor:
    """Extracts individual tracks from multi-track MIDI files."""
    
    @staticmethod
    def extract_tracks(midi_path: str) -> Tuple[Optional[List[Dict]], Optional[float], str]:
        """
        Extract tracks from a MIDI file.
        
        Args:
            midi_path: Path to MIDI file
            
        Returns:
            Tuple of (tracks_list, file_bpm, error_message)
            - tracks_list: List of dicts with track data (track_index, name, instrument, midi_data)
            - file_bpm: BPM detected from file (float or None)
            - error_message: Error message if failed, empty string if successful
        """
        try:
            mid = MidiFile(midi_path)
        except Exception as e:
            return None, None, f"Failed to read MIDI file: {str(e)}"
        
        return MidiExtractor.extract_tracks_from_obj(mid)
    
    @staticmethod
    def extract_tracks_from_obj(midi_file: MidiFile) -> Tuple[Optional[List[Dict]], Optional[float], str]:
        """
        Extract tracks from an already-loaded MidiFile object.
        
        Args:
            midi_file: MidiFile object
            
        Returns:
            Tuple of (tracks_list, file_bpm, error_message)
            - tracks_list: List of dicts with track data (track_index, name, instrument, midi_data)
            - file_bpm: BPM detected from file (float or None)
            - error_message: Error message if failed, empty string if successful
        """
        tracks = []
        file_bpm = None
        
        try:
            # Try to extract BPM from first tempo message
            for track in midi_file.tracks:
                for msg in track:
                    if msg.type == 'set_tempo':
                        # Convert microseconds per beat to BPM
                        file_bpm = round(60_000_000 / msg.tempo)
                        break
                if file_bpm:
                    break
        except Exception as e:
            pass  # BPM extraction failed, continue with None
        
        # Extract each track
        for track_idx, track in enumerate(midi_file.tracks):
            track_data = MidiExtractor._extract_track_data(track, track_idx, midi_file)
            
            if track_data:  # Only add non-empty tracks
                tracks.append(track_data)
        
        if not tracks:
            return None, file_bpm, "No non-empty tracks found in MIDI file"
        
        return tracks, file_bpm, ""
    
    @staticmethod
    def _extract_track_data(track, track_idx: int, midi_file: MidiFile) -> Optional[Dict]:
        """
        Extract data from a single track using a single-pass iteration.
        
        Returns:
            Dict with: track_index, name, instrument, midi_data, has_notes
            Returns None if track is empty (no note events)
        """
        # Single-pass extraction of all metadata
        has_notes = False
        track_name = ""
        instrument_name = "Unknown"
        program_change = None
        is_percussion = False
        
        # Flags to track what we've found (for early exit)
        found_track_name = False
        found_program_change = False
        
        for msg in track:
            # Check for note events
            if not has_notes and msg.type in ('note_on', 'note_off'):
                has_notes = True
            
            # Extract track name
            if not found_track_name and msg.type == 'track_name':
                track_name = msg.name
                found_track_name = True
            
            # Extract instrument from program_change
            if not found_program_change and msg.type == 'program_change':
                program_change = msg.program
                instrument_name = GM_INSTRUMENTS.get(msg.program, f"Instrument {msg.program}")
                found_program_change = True
            
            # Check for percussion channel (channel 10 = index 9)
            if not is_percussion and hasattr(msg, 'channel') and msg.channel == 9:
                is_percussion = True
            
            # Early exit if we've found everything we need
            if has_notes and found_track_name and found_program_change:
                break
        
        # Return None if track has no notes
        if not has_notes:
            return None
        
        # If no program change found, check if percussion was detected
        if not program_change and is_percussion:
            instrument_name = "Percussion"
        
        return {
            'track_index': track_idx,
            'track_name': track_name,
            'instrument': instrument_name,
            'program_change': program_change,
            'midi_data': track,  # Keep reference to track
        }
    
    @staticmethod
    def save_track(track_data: Dict, output_path: str, ticks_per_beat: int = 480, original_midi_file: str = None) -> bool:
        """
        Save an extracted track as a new MIDI file.
        
        Args:
            track_data: Track data from extract_track_data
            output_path: Path where to save the MIDI file
            ticks_per_beat: Ticks per beat value (default: 480)
            original_midi_file: (Deprecated) Path to original MIDI file - kept for backward compatibility
            
        Returns:
            True if successful, False if failed
        """
        try:
            # Backward compatibility: if original_midi_file is provided, read ticks_per_beat from it
            if original_midi_file is not None:
                try:
                    original_mid = MidiFile(original_midi_file)
                    ticks_per_beat = original_mid.ticks_per_beat
                except Exception:
                    pass  # Fall back to provided or default ticks_per_beat
            
            # Create new MIDI file with only this track
            new_mid = MidiFile()
            new_mid.ticks_per_beat = ticks_per_beat
            new_mid.tracks.append(track_data['midi_data'])
            
            # Create output directory if needed
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # Save the file
            new_mid.save(output_path)
            return True
        
        except Exception as e:
            print(f"Error saving track {track_data['track_index']} to {output_path}: {str(e)}")
            return False
    
    @staticmethod
    def get_duration_seconds(midi_input: Union[str, MidiFile]) -> int:
        """
        Calculate duration of MIDI file in seconds.
        
        Args:
            midi_input: Either a path to MIDI file (str) or a MidiFile object
            
        Returns:
            Duration in seconds (rounded)
        """
        try:
            # Handle both path and MidiFile object
            if isinstance(midi_input, str):
                midi_file = MidiFile(midi_input)
            else:
                midi_file = midi_input
            
            total_ticks = 0
            for track in midi_file.tracks:
                ticks = 0
                for msg in track:
                    ticks += msg.time
                total_ticks = max(total_ticks, ticks)

            # Convert ticks to seconds using ticks_per_beat
            if midi_file.ticks_per_beat and total_ticks > 0:
                # Assume default tempo 500000 microseconds per beat (120 BPM)
                seconds = (total_ticks / midi_file.ticks_per_beat) * (500000 / 1_000_000)
                return max(1, round(seconds))
        except Exception as e:
            pass
        
        return 0

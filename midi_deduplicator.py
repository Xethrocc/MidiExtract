"""
Deduplication module for extracted MIDI files.
Uses file hashing to detect identical tracks.
"""

import hashlib
import os
from typing import Dict, Tuple, Optional

class MidiDeduplicator:
    """Tracks and deduplicates extracted MIDI files."""
    
    def __init__(self):
        """Initialize deduplicator with empty hash tracking."""
        self.file_hashes = {}  # Dict: hash -> canonical_path
        self.duplicates_found = 0
        self.bytes_saved = 0
    
    def compute_file_hash(self, file_path: str) -> Optional[str]:
        """
        Compute SHA256 hash of a file.
        
        Args:
            file_path: Path to file
            
        Returns:
            Hex string of hash, or None if file doesn't exist
        """
        if not os.path.exists(file_path):
            return None
        
        try:
            hasher = hashlib.sha256()
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except Exception as e:
            print(f"Error computing hash for {file_path}: {str(e)}")
            return None
    
    def register_file(self, file_path: str) -> Tuple[bool, Optional[str]]:
        """
        Register a file and check if it's a duplicate.
        
        Args:
            file_path: Path to extracted MIDI file
            
        Returns:
            Tuple of (is_duplicate, canonical_path)
            - is_duplicate: True if this file is a duplicate of a previously seen file
            - canonical_path: Path to the first occurrence of this file (None if first occurrence)
        """
        file_hash = self.compute_file_hash(file_path)
        
        if not file_hash:
            return False, None
        
        if file_hash in self.file_hashes:
            # This is a duplicate
            self.duplicates_found += 1
            try:
                self.bytes_saved += os.path.getsize(file_path)
            except:
                pass
            
            canonical_path = self.file_hashes[file_hash]
            return True, canonical_path
        else:
            # First occurrence of this file
            self.file_hashes[file_hash] = file_path
            return False, None
    
    def get_dedup_report(self) -> Dict:
        """
        Generate deduplication report.
        
        Returns:
            Dict with statistics
        """
        return {
            'total_unique_files': len(self.file_hashes),
            'duplicates_found': self.duplicates_found,
            'total_duplicates': self.duplicates_found,
            'bytes_saved': self.bytes_saved,
            'mb_saved': round(self.bytes_saved / 1024 / 1024, 2),
        }

"""
Tag processing module for organizing MIDI files by tags.
Implements custom sorting rules for folder hierarchy.
"""

class TagProcessor:
    """Processes tags according to specific rules for folder organization."""
    
    @staticmethod
    def process_tags(tags):
        """
        Process tags according to rules:
        - if tags contain 'medieval', ignore all others
        - if tags contain 'folk music', prioritize it first
        - remove 'fiddle' tag
        - limit to first 3 tags
        - if only 1 tag remains (after filtering), place in 'other' subfolder (except medieval)
        
        Args:
            tags: List of tag strings
            
        Returns:
            Tuple of (folder_path_list, is_other_folder)
            Example: (['folk music', 'country', 'bluegrass'], False)
                     (['jazz'], True) for single remaining tag
        """
        if not tags or not isinstance(tags, list):
            return (['uncategorized'], False)
        
        # Convert to lowercase for comparison, keep originals
        tags_lower = [tag.lower() for tag in tags]
        tags_original = tags.copy()
        
        # Rule 1: If 'medieval' in tags, use only medieval
        if 'medieval' in tags_lower:
            return (['medieval'], False)
        
        # Rule 2: Remove 'fiddle' tag
        filtered_tags = []
        for i, tag_lower in enumerate(tags_lower):
            if tag_lower.strip() != 'fiddle':
                filtered_tags.append(tags_original[i])
        
        if not filtered_tags:
            return (['other'], False)
        
        # Rule 3: Prioritize 'folk music' if present
        folk_index = next((i for i, t in enumerate([t.lower() for t in filtered_tags]) 
                          if t.strip() == 'folk music'), -1)
        
        if folk_index >= 0:
            # Move 'folk music' to the front
            folk_tag = filtered_tags.pop(folk_index)
            filtered_tags.insert(0, folk_tag)
        
        # Rule 4: Limit to first 3 tags
        filtered_tags = filtered_tags[:3]
        
        # Rule 5: If only 1 tag remains, place in 'other' subfolder
        is_other = len(filtered_tags) == 1
        
        return (filtered_tags, is_other)
    
    @staticmethod
    def get_folder_path(tags):
        """
        Generate complete folder path from tags.
        
        Returns:
            Folder path string like 'folk music/country/bluegrass'
                                or 'jazz/other'
                                or 'medieval'
        """
        tag_list, is_other = TagProcessor.process_tags(tags)
        
        if is_other:
            # Single tag → put in 'other' subfolder
            return '/'.join(tag_list) + '/other'
        else:
            return '/'.join(tag_list)

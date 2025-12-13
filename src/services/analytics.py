"""Analytics service for data visualization and statistics."""
from typing import Dict, List
from src.models.link import Link


class AnalyticsService:
    """Service for calculating analytics and statistics."""
    
    @staticmethod
    def calculate_score_histogram(links: List[Link]) -> tuple[List[Dict], int]:
        """
        Calculate histogram data for link scores.
        
        Args:
            links: List of Link objects
            
        Returns:
            Tuple of (histogram_data, max_count)
        """
        score_bins = {i: 0 for i in range(101)}  # 0.00, 0.01, 0.02, ..., 1.00
        
        for link in links:
            if link.score is not None:
                bin_index = round(link.score * 100)
                score_bins[bin_index] += 1
        
        histogram = [{"bin": i/100, "count": score_bins[i]} for i in range(101)]
        max_count = max(score_bins.values()) if score_bins.values() and max(score_bins.values()) > 0 else 1
        
        return histogram, max_count
    
    @staticmethod
    def calculate_tag_frequency_histogram(links: List[Link]) -> tuple[List[Dict], int]:
        """
        Calculate histogram data for tag usage frequency across links.
        
        Args:
            links: List of Link objects
            
        Returns:
            Tuple of (histogram_data, max_count)
        """
        # Count how many times each tag appears across all links
        tag_usage_count = {}
        for link in links:
            for tag in link.selected_tags:
                tag_usage_count[tag] = tag_usage_count.get(tag, 0) + 1
        
        # Bin tags by their frequency of occurrence
        frequency_bins = {
            "1": 0,
            "2-3": 0,
            "4-6": 0,
            "7-10": 0,
            "11-15": 0,
            "16+": 0
        }
        
        for count in tag_usage_count.values():
            if count == 1:
                frequency_bins["1"] += 1
            elif 2 <= count <= 3:
                frequency_bins["2-3"] += 1
            elif 4 <= count <= 6:
                frequency_bins["4-6"] += 1
            elif 7 <= count <= 10:
                frequency_bins["7-10"] += 1
            elif 11 <= count <= 15:
                frequency_bins["11-15"] += 1
            else:
                frequency_bins["16+"] += 1
        
        histogram = [{"bin": k, "count": v} for k, v in frequency_bins.items()]
        max_count = max(frequency_bins.values()) if frequency_bins.values() and max(frequency_bins.values()) > 0 else 1
        
        return histogram, max_count
    
    @staticmethod
    def calculate_tag_collection_histogram(tag_counts: Dict[str, int]) -> tuple[List[Dict], int]:
        """
        Calculate histogram data for tag usage from stored tag counts.
        
        Args:
            tag_counts: Dictionary mapping tag names to their counts
            
        Returns:
            Tuple of (histogram_data, max_count)
        """
        frequency_bins = {
            "1": 0,
            "2": 0,
            "3": 0,
            "4": 0,
            "5": 0,
            "6": 0,
            "7": 0,
            "8": 0,
            "9": 0,
            "10+": 0
        }
        
        for count in tag_counts.values():
            if count == 0:
                continue
            elif 1 <= count <= 9:
                frequency_bins[str(count)] += 1
            else:  # count >= 10
                frequency_bins["10+"] += 1
        
        histogram = [{"bin": k, "count": v} for k, v in frequency_bins.items()]
        max_count = max(frequency_bins.values()) if frequency_bins.values() and max(frequency_bins.values()) > 0 else 1
        
        return histogram, max_count

#!/usr/bin/env python3
"""
Cleanup script for sitemap-gazer data directories.
Keeps only the most recent directory for each site, deletes older ones.
"""

import shutil
from datetime import datetime
from pathlib import Path


def get_timestamp_from_dirname(dirname):
    """Extract timestamp from directory name like '20250723_090156'."""
    try:
        return datetime.strptime(dirname, "%Y%m%d_%H%M%S")
    except ValueError:
        return None


def cleanup_site_directories(data_dir="data"):
    """Clean up old directories for each site, keeping only the most recent."""
    data_path = Path(data_dir)
    
    if not data_path.exists():
        print(f"Data directory {data_dir} does not exist")
        return
    
    cleaned_count = 0
    
    # Process each site directory
    for site_dir in data_path.iterdir():
        if not site_dir.is_dir():
            continue
            
        print(f"Processing site: {site_dir.name}")
        
        # Get all timestamp directories
        timestamp_dirs = []
        for ts_dir in site_dir.iterdir():
            if ts_dir.is_dir():
                timestamp = get_timestamp_from_dirname(ts_dir.name)
                if timestamp:
                    timestamp_dirs.append((timestamp, ts_dir))
        
        if not timestamp_dirs:
            print(f"  No valid timestamp directories found for {site_dir.name}")
            continue
            
        # Sort by timestamp (newest first)
        timestamp_dirs.sort(key=lambda x: x[0], reverse=True)
        
        # Keep the most recent, delete others
        newest_dir = timestamp_dirs[0][1]
        print(f"  Keeping: {newest_dir.name}")
        
        for _, dir_to_remove in timestamp_dirs[1:]:
            print(f"  Removing: {dir_to_remove.name}")
            try:
                shutil.rmtree(dir_to_remove)
                cleaned_count += 1
            except Exception as e:
                print(f"  Error removing {dir_to_remove}: {e}")
    
    print(f"\nCleanup complete. Removed {cleaned_count} old directories.")


if __name__ == "__main__":
    import sys
    
    data_directory = sys.argv[1] if len(sys.argv) > 1 else "data"
    cleanup_site_directories(data_directory)
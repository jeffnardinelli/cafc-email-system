#!/usr/bin/env python3
"""
Debug script to see RSS feed structure
"""

import requests
import xml.etree.ElementTree as ET

RSS_FEED_URL = "https://www.cafc.uscourts.gov/category/opinion-order/feed/"

response = requests.get(RSS_FEED_URL, timeout=30)
root = ET.fromstring(response.content)

# Find all items
items = root.findall('.//item')

print(f"Found {len(items)} items\n")
print("=" * 80)

# Show first 3 items in detail
for i, item in enumerate(items[:3]):
    print(f"\nITEM {i+1}:")
    print("-" * 80)
    
    title = item.find('title')
    print(f"Title: {title.text if title is not None else 'None'}")
    
    desc = item.find('description')
    if desc is not None:
        print(f"\nDescription:")
        print(desc.text)
    
    link = item.find('link')
    print(f"\nLink: {link.text if link is not None else 'None'}")
    
    print("=" * 80)

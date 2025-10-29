#!/usr/bin/env python3
"""
CAFC Daily Decisions Email Generator v2
Scrapes the Court of Appeals for the Federal Circuit RSS feed
"""

import requests
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
import re
from collections import defaultdict
from typing import List, Dict, Optional
import sys

class CAFCDecision:
    """Represents a single CAFC decision"""
    def __init__(self, title: str, appeal_number: str, origin: str, 
                 precedential: bool, date: datetime, doc_type: str = "OPINION", link: str = ""):
        self.title = title
        self.appeal_number = appeal_number
        self.origin = origin
        self.precedential = precedential
        self.date = date
        self.doc_type = doc_type
        self.link = link
        
    def __repr__(self):
        status = "Precedential" if self.precedential else "Nonprecedential"
        return f"{self.title} ({status}) - {self.date.strftime('%Y-%m-%d')}"


class CAFCScraper:
    """Scrapes CAFC RSS feed for decisions"""
    
    RSS_FEED_URL = "https://www.cafc.uscourts.gov/category/opinion-order/feed/"
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def fetch_recent_decisions(self, days_back: int = 30) -> List[CAFCDecision]:
        """Fetch decisions from RSS feed"""
        decisions = []
        cutoff_date = datetime.now() - timedelta(days=days_back)
        
        print(f"Fetching decisions from RSS feed...")
        try:
            response = self.session.get(self.RSS_FEED_URL, timeout=30)
            response.raise_for_status()
            
            # Parse XML
            root = ET.fromstring(response.content)
            
            # Find all items in the feed
            items = root.findall('.//item')
            print(f"Found {len(items)} items in RSS feed")
            
            for item in items:
                try:
                    decision = self._parse_rss_item(item)
                    if decision and decision.date >= cutoff_date:
                        decisions.append(decision)
                except Exception as e:
                    print(f"Error parsing item: {e}")
                    continue
            
        except Exception as e:
            print(f"Error fetching RSS feed: {e}")
            raise
        
        return sorted(decisions, key=lambda x: x.date, reverse=True)
    
    def _parse_rss_item(self, item: ET.Element) -> Optional[CAFCDecision]:
        """Parse a single RSS item into a CAFCDecision"""
        try:
            # Get title
            title_elem = item.find('title')
            if title_elem is None or not title_elem.text:
                return None
            
            full_title = title_elem.text
            
            # Get description
            desc_elem = item.find('description')
            description = desc_elem.text if desc_elem is not None else ""
            
            # Get pub date
            pubdate_elem = item.find('pubDate')
            if pubdate_elem is None or not pubdate_elem.text:
                return None
            
            # Parse date (RSS date format: Mon, 28 Oct 2025 12:00:00 +0000)
            date_str = pubdate_elem.text
            decision_date = self._parse_rss_date(date_str)
            
            # Get link
            link_elem = item.find('link')
            link = link_elem.text if link_elem is not None else ""
            
            # Parse the title to extract components
            # Format examples:
            # "25-1810: WSOU INVESTMENTS LLC v. SALESFORCE, INC. [ORDER]"
            # "23-2027: CENTRIPETAL NETWORKS, LLC v. PALO ALTO NETWORKS, INC. [OPINION]"
            
            # Extract appeal number
            appeal_match = re.match(r'(\d+-\d+):\s*(.+?)\s*\[([^\]]+)\]', full_title)
            if not appeal_match:
                return None
            
            appeal_number = appeal_match.group(1)
            case_title = appeal_match.group(2).strip()
            doc_type = appeal_match.group(3).strip()
            
            # Extract origin and precedential status from description
            origin = "Unknown"
            precedential = False
            
            if description:
                origin_match = re.search(r'Origin:\s*(\w+)', description)
                if origin_match:
                    origin = origin_match.group(1)
                
                precedential = "Precedential" in description and "Nonprecedential" not in description
            
            return CAFCDecision(
                title=case_title,
                appeal_number=appeal_number,
                origin=origin,
                precedential=precedential,
                date=decision_date,
                doc_type=doc_type,
                link=link
            )
            
        except Exception as e:
            print(f"Error parsing RSS item: {e}")
            return None
    
    def _parse_rss_date(self, date_str: str) -> datetime:
        """Parse RSS pubDate format"""
        # Format: Mon, 28 Oct 2025 12:00:00 +0000
        try:
            # Remove timezone info for simplicity
            date_str = re.sub(r'\s*[+-]\d{4}$', '', date_str)
            return datetime.strptime(date_str, '%a, %d %b %Y %H:%M:%S')
        except Exception as e:
            print(f"Error parsing date '{date_str}': {e}")
            return datetime.now()


class EmailGenerator:
    """Generates HTML email from CAFC decisions"""
    
    def __init__(self, decisions: List[CAFCDecision]):
        self.decisions = decisions
        self.today = datetime.now()
    
    def generate_html(self) -> str:
        """Generate complete HTML email"""
        # Group decisions by date
        decisions_by_date = defaultdict(list)
        for decision in self.decisions:
            decisions_by_date[decision.date.date()].append(decision)
        
        # Get today's decisions
        today_decisions = decisions_by_date.get(self.today.date(), [])
        
        # Build HTML
        html = self._html_header()
        html += self._html_body_start()
        
        if today_decisions:
            html += self._format_todays_decisions(today_decisions)
        else:
            html += self._format_no_decisions()
        
        html += self._format_recent_activity(decisions_by_date)
        html += self._format_statistics(decisions_by_date)
        html += self._html_footer()
        html += self._html_body_end()
        
        return html
    
    def _html_header(self) -> str:
        return """<!DOCTYPE html>
<html>
<head>
    <style>
        body { 
            font-family: Arial, sans-serif; 
            line-height: 1.6; 
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .email-container {
            background-color: white;
            padding: 30px;
            border-radius: 5px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }
        h1 { 
            color: #2c3e50; 
            border-bottom: 2px solid #3498db; 
            padding-bottom: 10px; 
            font-size: 24px;
            margin-bottom: 20px;
        }
        h3 { 
            color: #34495e; 
            margin-top: 20px;
            margin-bottom: 12px;
            font-size: 16px;
        }
        .decision-list {
            margin: 15px 0;
        }
        .decision-item {
            background-color: #f8f9fa;
            padding: 15px;
            margin-bottom: 10px;
            border-radius: 5px;
            border-left: 3px solid #3498db;
        }
        .decision-item.precedential {
            border-left-color: #e74c3c;
            background-color: #fff5f5;
        }
        .decision-title {
            font-weight: bold;
            color: #2c3e50;
            font-size: 15px;
            margin-bottom: 5px;
        }
        .decision-meta {
            font-size: 13px;
            color: #7f8c8d;
        }
        .precedential-badge {
            display: inline-block;
            background-color: #e74c3c;
            color: white;
            padding: 2px 8px;
            border-radius: 3px;
            font-size: 11px;
            font-weight: bold;
            margin-left: 5px;
        }
        .no-decisions-box {
            background-color: #f8f9fa;
            padding: 25px;
            border-radius: 5px;
            text-align: center;
            margin: 20px 0;
            border: 1px solid #e9ecef;
        }
        .no-decisions-box p {
            font-size: 16px;
            color: #7f8c8d;
            margin: 0 0 10px 0;
        }
        .recent-decisions {
            background-color: #ecf0f1;
            padding: 20px;
            border-radius: 5px;
            margin-top: 25px;
        }
        .recent-decisions ul {
            margin: 10px 0;
            padding-left: 20px;
        }
        .recent-decisions li {
            margin-bottom: 8px;
            color: #2c3e50;
            font-size: 14px;
        }
        .recent-decisions strong {
            color: #2c3e50;
        }
        .stats-summary {
            background-color: #e8f4fd;
            padding: 15px;
            border-radius: 5px;
            margin-top: 20px;
            text-align: center;
            border-left: 3px solid #3498db;
        }
        .stats-summary h3 {
            margin-top: 0;
            color: #2c3e50;
        }
        .stats-summary p {
            font-size: 14px;
            color: #34495e;
            margin: 5px 0;
        }
        .footer { 
            margin-top: 30px; 
            padding-top: 15px; 
            border-top: 1px solid #bdc3c7; 
            color: #7f8c8d; 
            font-size: 12px;
            text-align: center;
        }
        .footer a {
            color: #3498db;
        }
    </style>
</head>
<body>
    <div class="email-container">
"""
    
    def _html_body_start(self) -> str:
        date_str = self.today.strftime("%B %d, %Y")
        return f"""        <h1>CAFC Daily Decisions - {date_str}</h1>
        
        <p>Good morning,</p>
        <p>Here is today's update from the Court of Appeals for the Federal Circuit:</p>
        
"""
    
    def _format_todays_decisions(self, decisions: List[CAFCDecision]) -> str:
        html = """        <div class="decision-list">
"""
        
        # Separate precedential and nonprecedential
        precedential = [d for d in decisions if d.precedential]
        nonprecedential = [d for d in decisions if not d.precedential]
        
        if precedential:
            html += """            <h3>Precedential Decisions</h3>
"""
            for decision in precedential:
                html += self._format_decision_item(decision, precedential=True)
        
        if nonprecedential:
            count = len(nonprecedential)
            html += f"""            <h3>Nonprecedential Decisions ({count})</h3>
"""
            for decision in nonprecedential[:5]:  # Show first 5
                html += self._format_decision_item(decision, precedential=False)
            
            if count > 5:
                html += f"""            <p style="font-size: 13px; color: #7f8c8d; margin-left: 15px;">
                <em>...and {count - 5} additional nonprecedential decisions</em>
            </p>
"""
        
        html += """        </div>
        
"""
        return html
    
    def _format_decision_item(self, decision: CAFCDecision, precedential: bool) -> str:
        prec_class = " precedential" if precedential else ""
        prec_badge = '<span class="precedential-badge">PRECEDENTIAL</span>' if precedential else ""
        
        return f"""            <div class="decision-item{prec_class}">
                <div class="decision-title">{decision.title}{prec_badge}</div>
                <div class="decision-meta">
                    Appeal No. {decision.appeal_number} | Origin: {decision.origin} | {decision.doc_type}
                </div>
            </div>
"""
    
    def _format_no_decisions(self) -> str:
        date_str = self.today.strftime("%B %d, %Y")
        return f"""        <div class="no-decisions-box">
            <p><em>No decisions were issued on {date_str}.</em></p>
            <p style="font-size: 14px; color: #95a5a6;">The Court did not release any opinions or orders today.</p>
        </div>
        
"""
    
    def _format_recent_activity(self, decisions_by_date: Dict) -> str:
        html = """        <div class="recent-decisions">
            <h3>This Week's Activity</h3>
            <p style="font-size: 14px; color: #7f8c8d;">Recent decisions from the past 7 days:</p>
            
"""
        
        # Get last 7 days
        dates = sorted([d for d in decisions_by_date.keys() 
                       if d >= (self.today - timedelta(days=7)).date()], 
                      reverse=True)
        
        for date in dates[:7]:
            decisions = decisions_by_date[date]
            date_str = date.strftime("%A, %B %d")
            
            html += f"""            <p style="font-size: 14px; margin-top: 15px;"><strong>{date_str}:</strong></p>
            <ul>
"""
            
            # Show precedential decisions
            precedential = [d for d in decisions if d.precedential]
            for decision in precedential:
                html += f"""                <li><strong>{decision.title}</strong> (Precedential) - {decision.doc_type}</li>
"""
            
            # Count nonprecedential
            nonprec_count = len([d for d in decisions if not d.precedential])
            if nonprec_count > 0:
                html += f"""                <li>{nonprec_count} nonprecedential decision{"s" if nonprec_count != 1 else ""}</li>
"""
            
            if not decisions:
                html += """                <li>No decisions issued</li>
"""
            
            html += """            </ul>
"""
        
        html += """        </div>
        
"""
        return html
    
    def _format_statistics(self, decisions_by_date: Dict) -> str:
        # Calculate monthly stats
        month_start = self.today.replace(day=1).date()
        month_decisions = [d for date, decisions in decisions_by_date.items() 
                          if date >= month_start 
                          for d in decisions]
        
        precedential_count = len([d for d in month_decisions if d.precedential])
        nonprecedential_count = len([d for d in month_decisions if not d.precedential])
        
        # Count active days
        active_days = len([date for date in decisions_by_date.keys() if date >= month_start])
        
        # Business days in month so far
        business_days = sum(1 for i in range((self.today.date() - month_start).days + 1)
                           if (month_start + timedelta(days=i)).weekday() < 5)
        
        active_pct = int(active_days / business_days * 100) if business_days > 0 else 0
        
        month_name = self.today.strftime("%B %Y")
        
        return f"""        <div class="stats-summary">
            <h3>{month_name} Statistics</h3>
            <p><strong>Month to Date:</strong> {precedential_count} precedential opinion{"s" if precedential_count != 1 else ""}, {nonprecedential_count} nonprecedential decision{"s" if nonprecedential_count != 1 else ""}</p>
            <p><strong>Active Days:</strong> {active_days} of {business_days} business days ({active_pct}%)</p>
            <p style="font-size: 13px; color: #7f8c8d; margin-top: 10px;">
                <em>The Federal Circuit typically issues decisions 2-3 days per week</em>
            </p>
        </div>
        
"""
    
    def _html_footer(self) -> str:
        return """        <div class="footer">
            <p>This email was automatically generated from the CAFC website. 
            For the most current information, please visit 
            <a href="https://www.cafc.uscourts.gov">www.cafc.uscourts.gov</a>.</p>
            <p><strong>Quinn Emanuel Urquhart & Sullivan, LLP</strong></p>
        </div>
"""
    
    def _html_body_end(self) -> str:
        return """    </div>
</body>
</html>"""


def main():
    """Main execution function"""
    print("CAFC Daily Decisions Email Generator v2")
    print("=" * 50)
    
    try:
        # Scrape decisions
        scraper = CAFCScraper()
        print("\nFetching recent decisions from CAFC RSS feed...")
        decisions = scraper.fetch_recent_decisions(days_back=30)
        
        print(f"\nFound {len(decisions)} decisions from the past 30 days")
        
        # Show summary
        today_count = len([d for d in decisions if d.date.date() == datetime.now().date()])
        precedential_count = len([d for d in decisions if d.precedential])
        
        print(f"  - Today: {today_count} decisions")
        print(f"  - Precedential: {precedential_count}")
        print(f"  - Nonprecedential: {len(decisions) - precedential_count}")
        
        # Show today's decisions
        if today_count > 0:
            print("\n📋 Today's Decisions:")
            for d in [d for d in decisions if d.date.date() == datetime.now().date()]:
                status = "PRECEDENTIAL" if d.precedential else "Nonprec"
                print(f"  • {d.title} ({status} - {d.doc_type})")
        
        # Generate email
        print("\nGenerating HTML email...")
        generator = EmailGenerator(decisions)
        html = generator.generate_html()
        
        # Save to file
        output_file = "cafc_daily_email.html"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html)
        
        print(f"\n✓ Email saved to: {output_file}")
        print("\nYou can open this file in a web browser to preview the email.")
        
    except Exception as e:
        print(f"\n✗ Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
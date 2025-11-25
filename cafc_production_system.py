#!/usr/bin/env python3
"""
CAFC Daily Decisions Email System - PRODUCTION VERSION
Complete integration: scraping + AI summaries + database + Gmail delivery
"""

import os
import sys
import sqlite3
import smtplib
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import requests
import xml.etree.ElementTree as ET
import re
from collections import defaultdict
from typing import List, Dict, Optional
from pypdf import PdfReader
import io
import anthropic
from zoneinfo import ZoneInfo


class CAFCDecision:
    """Represents a single CAFC decision"""
    def __init__(self, title: str, appeal_number: str, origin: str, 
                 precedential: bool, date: datetime, doc_type: str = "OPINION", 
                 link: str = "", summary: str = ""):
        self.title = title
        self.appeal_number = appeal_number
        self.origin = origin
        self.precedential = precedential
        self.date = date
        self.doc_type = doc_type
        self.link = link
        self.summary = summary
        
    def __repr__(self):
        status = "Precedential" if self.precedential else "Nonprecedential"
        return f"{self.title} ({status}) - {self.date.strftime('%Y-%m-%d')}"


def get_eastern_now():
    """Get current datetime in Eastern Time"""
    return datetime.now(ZoneInfo("America/New_York"))


def get_eastern_today():
    """Get today's date in Eastern Time"""
    return get_eastern_now().date()


class DecisionDatabase:
    """Manages SQLite database for tracking sent emails"""
    
    def __init__(self, db_path: str = "cafc_decisions.db"):
        self.db_path = db_path
        self._init_database()
    
    def _init_database(self):
        """Initialize database schema"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sent_decisions (
                appeal_number TEXT PRIMARY KEY,
                case_title TEXT,
                decision_date TEXT,
                sent_date TEXT,
                precedential INTEGER
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def was_sent(self, appeal_number: str) -> bool:
        """Check if decision was already sent"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            'SELECT appeal_number FROM sent_decisions WHERE appeal_number = ?',
            (appeal_number,)
        )
        
        result = cursor.fetchone()
        conn.close()
        
        return result is not None
    
    def mark_as_sent(self, decision: CAFCDecision):
        """Mark decision as sent in database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO sent_decisions 
            (appeal_number, case_title, decision_date, sent_date, precedential)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            decision.appeal_number,
            decision.title,
            decision.date.strftime('%Y-%m-%d'),
            get_eastern_now().strftime('%Y-%m-%d %H:%M:%S'),
            1 if decision.precedential else 0
        ))
        
        conn.commit()
        conn.close()


class DecisionSummarizer:
    """Generates AI summaries of court decisions"""
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize with Claude API key from environment or parameter"""
        self.api_key = api_key or os.environ.get('ANTHROPIC_API_KEY')
        if not self.api_key:
            print("⚠️  Warning: No ANTHROPIC_API_KEY found. Summaries will be skipped.")
            self.client = None
        else:
            self.client = anthropic.Anthropic(api_key=self.api_key)
    
    def fetch_and_summarize(self, decision: CAFCDecision) -> str:
        """Fetch PDF and generate summary"""
        if not self.client:
            return ""
        
        try:
            print(f"  📄 Fetching PDF for {decision.title}...")
            print(f"  🔗 PDF URL: {decision.link}")
            
            # Fetch the PDF
            response = requests.get(decision.link, timeout=30)
            response.raise_for_status()
            
            print(f"  ✓ Got response - Content-Type: {response.headers.get('content-type')}")
            
            # Extract text from PDF
            pdf_text = self._extract_pdf_text(response.content)
            
            if not pdf_text or len(pdf_text) < 100:
                print(f"  ⚠️  Could not extract sufficient text from PDF")
                return ""
            
            # Generate summary
            print(f"  🤖 Generating AI summary...")
            summary = self._generate_summary(decision, pdf_text)
            
            return summary
            
        except Exception as e:
            print(f"  ✗ Error summarizing: {e}")
            return ""
    
    def _extract_pdf_text(self, pdf_content: bytes) -> str:
        """Extract text from PDF bytes"""
        try:
            pdf_file = io.BytesIO(pdf_content)
            reader = PdfReader(pdf_file)
            
            # Extract text from first 5 pages (usually sufficient for summary)
            text = ""
            for page_num in range(min(5, len(reader.pages))):
                text += reader.pages[page_num].extract_text()
            
            return text
        except Exception as e:
            print(f"  ✗ PDF extraction error: {e}")
            return ""
    
    def _generate_summary(self, decision: CAFCDecision, full_text: str) -> str:
        """Generate summary using Claude API"""
        try:
            # Truncate text if too long
            max_chars = 50000
            if len(full_text) > max_chars:
                full_text = full_text[:max_chars] + "\n\n[Text truncated...]"
            
            prompt = f"""You are a legal expert summarizing a Federal Circuit court decision for patent attorneys.

Case: {decision.title}
Appeal Number: {decision.appeal_number}
Type: {decision.doc_type}
Status: {"Precedential" if decision.precedential else "Nonprecedential"}

Please provide a concise 2-3 sentence summary suitable for a daily email digest. Focus on:
1. The main legal issue or question presented
2. The court's holding/decision
3. Key practical implications for patent practitioners

Be specific but concise. Use clear, professional language.

Full decision text:
{full_text}"""

            message = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=300,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            summary = message.content[0].text.strip()
            
            # Strip markdown formatting (bold, italic, etc)
            summary = re.sub(r'\*\*([^*]+)\*\*', r'\1', summary)  # Remove **bold**
            summary = re.sub(r'\*([^*]+)\*', r'\1', summary)      # Remove *italic*
            summary = re.sub(r'__([^_]+)__', r'\1', summary)      # Remove __bold__
            summary = re.sub(r'_([^_]+)_', r'\1', summary)        # Remove _italic_
            
            return summary
            
        except Exception as e:
            print(f"  ✗ API error: {e}")
            return ""
    
    def is_patent_case(self, decision: CAFCDecision, summary: str) -> bool:
        """Determine if a decision is patent-related using AI"""
        if not self.client or not summary:
            return True  # If no AI available, include everything
        
        try:
            prompt = f"""Based on this Federal Circuit case summary, determine if this is a patent law case.

Case: {decision.title}
Origin: {decision.origin}
Summary: {summary}

Answer with ONLY "yes" or "no". 

A patent law case involves:
- Patent infringement, validity, or enforcement
- USPTO appeals (PTAB decisions, examiner rejections)
- Patent claim construction or interpretation
- ITC investigations involving patents
- Any dispute primarily concerning patent rights

Not patent cases:
- Veterans benefits appeals
- Employment/personnel disputes
- Government contracts or procurement
- Tax or customs disputes
- Cases that only tangentially mention patents

Is this a patent law case?"""

            message = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=10,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            answer = message.content[0].text.strip().lower()
            is_patent = "yes" in answer
            
            print(f"  🔍 Patent case? {answer}")
            return is_patent
            
        except Exception as e:
            print(f"  ✗ Patent check error: {e}")
            return True  # On error, include the case to be safe


class CAFCScraper:
    """Scrapes CAFC RSS feed for decisions"""
    
    RSS_FEED_URL = "https://www.cafc.uscourts.gov/category/opinion-order/feed/"
    
    def __init__(self, summarizer: Optional[DecisionSummarizer] = None):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.summarizer = summarizer
    
    def fetch_recent_decisions(self, days_back: int = 30) -> List[CAFCDecision]:
        """Fetch decisions from RSS feed (without summaries)"""
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
            
            # Get description - need raw HTML content with tags to extract PDF links
            desc_elem = item.find('description')
            description = ""
            if desc_elem is not None:
                # Try to get inner HTML content
                # First try: direct text content
                if desc_elem.text:
                    description = desc_elem.text
                # If that's empty, try getting all content including subelements
                elif len(desc_elem):
                    description = ''.join(ET.tostring(child, encoding='unicode') for child in desc_elem)
                # Last resort: serialize the whole element and extract content
                else:
                    full_elem = ET.tostring(desc_elem, encoding='unicode')
                    description = full_elem
            
            # Get pub date
            pubdate_elem = item.find('pubDate')
            if pubdate_elem is None or not pubdate_elem.text:
                return None
            
            # Parse date
            date_str = pubdate_elem.text
            decision_date = self._parse_rss_date(date_str)
            
            # Get webpage link  
            link_elem = item.find('link')
            webpage_link = link_elem.text if link_elem is not None else ""
            
            # DEBUG: See what's in the link field
            if webpage_link:
                print(f"  DEBUG - Webpage link: {webpage_link}")
            
            # Parse the title to extract components
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
            
            # Extract PDF link from description HTML
            # Format: <a href="/opinions-orders/25-1502.OPINION.10-28-2025_2594460.pdf">
            pdf_link = ""
            if description:
                # Debug: print first 200 chars of description
                print(f"  DEBUG - Description preview: {description[:200]}")
                
                pdf_match = re.search(r'href="(/opinions-orders/[^"]+\.pdf)"', description)
                if pdf_match:
                    pdf_link = "https://www.cafc.uscourts.gov" + pdf_match.group(1)
                    print(f"  DEBUG - Extracted PDF link: {pdf_link}")
                else:
                    print(f"  DEBUG - No PDF link found in description, using fallback")
                    # Fallback: construct from webpage link
                    # Webpage: .../10-02-2025-24-1071-...-order-24-1071-order-10-2-2025_2598245/
                    # Note: URL has date TWICE - first with leading zeros, second without
                    # We want the second one (without leading zeros)
                    if webpage_link:
                        # Extract date from end of URL (correct format like 10-2-2025)
                        # Pattern: -order-10-2-2025_ID or -opinion-10-2-2025_ID
                        url_date_match = re.search(r'-(?:order|opinion|errata|rule_36_judgment)-(\d{1,2}-\d{1,2}-\d{4})_', webpage_link)
                        url_id_match = re.search(r'_(\d+)/?$', webpage_link)
                        
                        if url_date_match and url_id_match:
                            date_from_url = url_date_match.group(1)  # Already formatted correctly!
                            doc_id = url_id_match.group(1)
                            pdf_link = f"https://www.cafc.uscourts.gov/opinions-orders/{appeal_number}.{doc_type}.{date_from_url}_{doc_id}.pdf"
                            print(f"  DEBUG - Constructed PDF link: {pdf_link}")
            
            return CAFCDecision(
                title=case_title,
                appeal_number=appeal_number,
                origin=origin,
                precedential=precedential,
                date=decision_date,
                doc_type=doc_type,
                link=pdf_link
            )
            
        except Exception as e:
            print(f"Error parsing RSS item: {e}")
            return None
    
    def _parse_rss_date(self, date_str: str) -> datetime:
        """Parse RSS pubDate format"""
        try:
            # Remove timezone info for simplicity
            date_str = re.sub(r'\s*[+-]\d{4}$', '', date_str)
            return datetime.strptime(date_str, '%a, %d %b %Y %H:%M:%S')
        except Exception as e:
            print(f"Error parsing date '{date_str}': {e}")
            return datetime.now()


class EmailGenerator:
    """Generates HTML email from CAFC decisions"""
    
    def __init__(self, patent_decisions: List[CAFCDecision], non_patent_decisions: List[CAFCDecision] = None):
        self.patent_decisions = patent_decisions
        self.non_patent_decisions = non_patent_decisions or []
        self.today = get_eastern_now()
    
    def generate_html(self) -> str:
        """Generate complete HTML email"""
        # Build HTML with patent decisions first, then non-patent
        html = self._html_header()
        html += self._html_body_start()
        
        if self.patent_decisions:
            html += self._format_decisions_section(self.patent_decisions, "Patent Cases")
        
        if self.non_patent_decisions:
            # Add clear divider before non-patent section
            html += """
        <div style="height: 3px; background: #bdc3c7; margin: 40px 0 30px 0;"></div>
        
"""
            html += self._format_decisions_section(self.non_patent_decisions, "Non-Patent Cases")
        
        if not self.patent_decisions and not self.non_patent_decisions:
            html += self._format_no_decisions()
        
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
        .decision-summary {
            margin-top: 8px;
            font-size: 14px;
            color: #34495e;
            line-height: 1.5;
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
        
        <p>Here is today's update from the Court of Appeals for the Federal Circuit:</p>
        <p style="font-size: 13px; color: #e74c3c; font-weight: bold;"><strong>ALL DECISION SUMMARIES ARE AI-GENERATED AND MAY CONTAIN ERRORS. PLEASE REFER TO THE FULL DECISIONS FOR ACCURATE INFORMATION.</strong></p>
        
"""
    
    def _format_decisions_section(self, decisions: List[CAFCDecision], section_title: str = "Decisions") -> str:
        """Format a section of decisions with a title"""
        html = f"""        <h2 style="color: #2c3e50; font-size: 18px; margin-bottom: 16px;">{section_title}</h2>
        <div class="decision-list">
"""
        
        # Separate precedential and nonprecedential
        precedential = [d for d in decisions if d.precedential]
        nonprecedential = [d for d in decisions if not d.precedential]
        
        if precedential:
            prec_count = len(precedential)
            html += f"""            <h3>Precedential Decisions ({prec_count})</h3>
"""
            for decision in precedential:
                html += self._format_decision_item(decision, precedential=True)
        
        if nonprecedential:
            count = len(nonprecedential)
            # Add divider if we had precedential decisions
            if precedential:
                html += """
            <div class="section-divider"></div>
            
"""
            html += f"""            <h3>Nonprecedential Decisions and Orders ({count})</h3>
"""
            # Show ALL nonprecedential decisions (no limit)
            for decision in nonprecedential:
                html += self._format_decision_item(decision, precedential=False)
        
        html += """        </div>
        
"""
        return html
    
    def _format_decision_item(self, decision: CAFCDecision, precedential: bool) -> str:
        prec_class = " precedential" if precedential else ""
        
        # Add summary with PDF link at the end if available
        summary_html = ""
        if decision.summary:
            pdf_link = f' <a href="{decision.link}" style="color: #3498db;">View Full Decision (PDF)</a>' if decision.link else ""
            summary_html = f"""
                <div class="decision-summary">{decision.summary}{pdf_link}</div>"""
        
        return f"""            <div class="decision-item{prec_class}">
                <div class="decision-title">{decision.title}</div>
                <div class="decision-meta">
                    Appeal No. {decision.appeal_number} | Origin: {decision.origin} | {decision.doc_type}
                </div>{summary_html}
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
            <p><strong>brought to you by quinn emanuel san francisco</strong></p>
        </div>
"""
    
    def _html_body_end(self) -> str:
        return """    </div>
</body>
</html>"""


class EmailSender:
    """Sends emails via Gmail SMTP"""
    
    def __init__(self):
        # Get configuration from environment variables
        self.smtp_server = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = int(os.environ.get('SMTP_PORT', '587'))
        self.from_email = os.environ.get('EMAIL_FROM')
        self.password = os.environ.get('EMAIL_PASSWORD')
        self.recipients_str = os.environ.get('EMAIL_RECIPIENTS', '')
        
        # Validate configuration
        if not self.from_email or not self.password:
            raise ValueError("EMAIL_FROM and EMAIL_PASSWORD environment variables must be set")
        
        if not self.recipients_str:
            raise ValueError("EMAIL_RECIPIENTS environment variable must be set")
        
        self.recipients = [r.strip() for r in self.recipients_str.split(',') if r.strip()]
    
    def send_email(self, html_content: str, subject: str = None) -> bool:
        """Send the HTML email"""
        if subject is None:
            subject = f"CAFC Daily Decisions - {get_eastern_now().strftime('%B %d, %Y')}"
        
        try:
            print(f"\n📧 Sending email to: {', '.join(self.recipients)}")
            
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"CAFC Decisions Bot <{self.from_email}>"
            msg['To'] = ', '.join(self.recipients)
            
            # Attach HTML
            msg.attach(MIMEText(html_content, 'html'))
            
            # Send email
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls()
            server.login(self.from_email, self.password)
            server.send_message(msg)
            server.quit()
            
            print("✓ Email sent successfully!")
            return True
            
        except Exception as e:
            print(f"✗ Failed to send email!")
            print(f"  Error: {e}")
            return False


def main():
    """Main execution function"""
    print("="*60)
    print("CAFC DAILY DECISIONS EMAIL SYSTEM - PRODUCTION")
    print("="*60)
    
    try:
        # Initialize components
        print("\n1. Initializing AI summarizer...")
        summarizer = DecisionSummarizer()
        
        print("2. Initializing scraper...")
        scraper = CAFCScraper(summarizer)
        
        print("3. Initializing email sender...")
        email_sender = EmailSender()
        
        # Fetch decisions
        print("\n4. Fetching recent decisions from CAFC...")
        all_decisions = scraper.fetch_recent_decisions(days_back=30)
        
        # Check for decisions from today only (no database needed - prevents duplicates)
        today = get_eastern_today()
        today_decisions = [d for d in all_decisions if d.date.date() == today]
        
        print(f"\n6. Found {len(today_decisions)} decisions from today (Eastern Time: {today})")
        
        if not today_decisions:
            print("\n✓ No decisions issued today. Nothing to send.")
            return
        
        print(f"7. {len(today_decisions)} decisions to send:")
        for d in today_decisions:
            status = "PRECEDENTIAL" if d.precedential else "Nonprec"
            print(f"   • {d.title} ({status} - {d.doc_type})")
        
        # Generate AI summaries for all today's decisions and classify as patent/non-patent
        if summarizer and summarizer.client:
            print("\n8. Generating AI summaries and classifying decisions...")
            patent_decisions = []
            non_patent_decisions = []
            
            for decision in today_decisions:
                print(f"\n📋 Summarizing: {decision.title}")
                summary = summarizer.fetch_and_summarize(decision)
                if summary:
                    decision.summary = summary
                    print(f"  ✓ Summary generated")
                    
                    # Check if this is a patent case
                    if summarizer.is_patent_case(decision, summary):
                        patent_decisions.append(decision)
                    else:
                        print(f"  ⊗ Non-patent case - will show separately")
                        non_patent_decisions.append(decision)
                else:
                    # If summary fails, treat as patent case to be safe
                    patent_decisions.append(decision)
            
            print(f"\n  {len(patent_decisions)} patent cases, {len(non_patent_decisions)} non-patent cases")
        else:
            # No AI available, treat all as patent cases
            patent_decisions = today_decisions
            non_patent_decisions = []
        
        if not patent_decisions and not non_patent_decisions:
            print("\n✓ No decisions issued today. Nothing to send.")
            return
        
        # Generate email with both sections
        print("\n9. Generating HTML email...")
        generator = EmailGenerator(patent_decisions, non_patent_decisions)
        html_content = generator.generate_html()
        
        # Send email
        print("10. Sending email...")
        email_sender.send_email(html_content)
        
        print("\n" + "="*60)
        print("✓ SUCCESS! Email sent.")
        print("="*60)
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
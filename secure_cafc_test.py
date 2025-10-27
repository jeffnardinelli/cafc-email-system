#!/usr/bin/env python3
"""
CAFC Email System - SECURE VERSION FOR GITHUB/RENDER
No passwords in code - uses environment variables
"""

import os
import sys
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

def test_email_connection():
    """Test if we can connect to the email server"""
    print("\n" + "="*60)
    print("TESTING EMAIL CONNECTION")
    print("="*60)
    
    # Get configuration from environment variables
    smtp_server = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
    smtp_port = int(os.environ.get('SMTP_PORT', '587'))
    from_email = os.environ.get('EMAIL_FROM')
    password = os.environ.get('EMAIL_PASSWORD')
    
    # Check if environment variables are set
    if not from_email or not password:
        print("✗ CONFIGURATION ERROR!")
        print("  EMAIL_FROM and EMAIL_PASSWORD environment variables are not set")
        print("\nFor local testing, set them like this:")
        print("  export EMAIL_FROM='jeff.nardinelli@gmail.com'")
        print("  export EMAIL_PASSWORD='your-app-password'")
        print("  export EMAIL_RECIPIENTS='jeffnardinelli@quinnemanuel.com'")
        print("\nIn Render, set these in the Environment Variables section")
        return False
    
    try:
        print(f"Connecting to {smtp_server}:{smtp_port}...")
        server = smtplib.SMTP(smtp_server, smtp_port)
        
        print("Starting TLS encryption...")
        server.starttls()
        
        print(f"Logging in as {from_email}...")
        server.login(from_email, password)
        
        print("✓ SUCCESS! Email connection works!")
        server.quit()
        return True
        
    except smtplib.SMTPAuthenticationError as e:
        print(f"✗ AUTHENTICATION FAILED!")
        print(f"  Error: {e}")
        return False
        
    except Exception as e:
        print(f"✗ CONNECTION FAILED!")
        print(f"  Error: {e}")
        return False


def get_test_decisions():
    """Return test decisions to verify email formatting"""
    print("\nUsing TEST DATA (not real CAFC data)")
    
    # These are the real decisions from Oct 27, 2025 for testing
    return [
        {
            'date': '10/27/2025',
            'case_number': '24-1145',
            'case_name': 'AORTIC INNOVATIONS LLC v. EDWARDS LIFESCIENCES CORPORATION',
            'origin': 'DCT',
            'precedential': True,
            'url': 'https://www.cafc.uscourts.gov/opinions-orders/24-1145.OPINION.10-27-2025_2593688.pdf'
        },
        {
            'date': '10/27/2025',
            'case_number': '24-1290',
            'case_name': 'PICTOMETRY INTERNATIONAL CORPORATION v. NEARMAP US, INC.',
            'origin': 'PTO',
            'precedential': False,
            'url': 'https://www.cafc.uscourts.gov/opinions-orders/24-1290.OPINION.10-27-2025.pdf'
        },
        {
            'date': '10/27/2025',
            'case_number': '25-2002',
            'case_name': 'PETER J. POLINSKI TRUST v. US',
            'origin': 'CFC',
            'precedential': False,
            'url': 'https://www.cafc.uscourts.gov/opinions-orders/25-2002.ORDER.10-27-2025.pdf'
        }
    ]


def generate_html(decisions):
    """Generate HTML email content"""
    
    # Separate precedential and non-precedential
    precedential = [d for d in decisions if d['precedential']]
    nonprecedential = [d for d in decisions if not d['precedential']]
    
    html = f"""<!DOCTYPE html>
<html>
<body>
<h1>CAFC Test Email</h1>
<p>Hello email world!</p>
<p>This test email contains {len(decisions)} decisions:</p>
<ul>
  <li>{len(precedential)} precedential</li>
  <li>{len(nonprecedential)} non-precedential</li>
</ul>
<p>Sent at: {datetime.now()}</p>
</body>
</html>
"""
    
    return html


def send_test_email(decisions):
    """Send a test email"""
    
    # Get configuration from environment variables
    smtp_server = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
    smtp_port = int(os.environ.get('SMTP_PORT', '587'))
    from_email = os.environ.get('EMAIL_FROM')
    password = os.environ.get('EMAIL_PASSWORD')
    recipients_str = os.environ.get('EMAIL_RECIPIENTS', '')
    
    # Check configuration
    if not from_email or not password:
        print("✗ Cannot send email - EMAIL_FROM and EMAIL_PASSWORD not set")
        return False
    
    if not recipients_str:
        print("✗ Cannot send email - EMAIL_RECIPIENTS not set")
        return False
    
    recipients = [r.strip() for r in recipients_str.split(',') if r.strip()]
    
    try:
        print(f"\nSending test email to: {', '.join(recipients)}")
        
        # Generate HTML
        html_content = generate_html(decisions)
        
        # Create message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"[TEST] CAFC Daily Decisions - {datetime.now().strftime('%B %d, %Y')}"
        msg['From'] = f"CAFC Decisions Bot <{from_email}>"
        msg['To'] = ', '.join(recipients)
        
        # Attach HTML
        msg.attach(MIMEText(html_content, 'html'))
        
        # Send email
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(from_email, password)
        server.send_message(msg)
        server.quit()
        
        print("✓ Test email sent successfully!")
        print(f"  Check the inbox for: {', '.join(recipients)}")
        return True
        
    except Exception as e:
        print(f"✗ Failed to send test email!")
        print(f"  Error: {e}")
        return False


def save_html_preview(decisions):
    """Save HTML to file for preview"""
    html = generate_html(decisions)
    filename = "test_email_preview.html"
    
    with open(filename, 'w') as f:
        f.write(html)
    
    print(f"\n✓ HTML preview saved to: {filename}")
    print("  Open this file in your browser to see how the email will look")


def main():
    """Run the test"""
    print("="*60)
    print("CAFC EMAIL SYSTEM - SECURE VERSION")
    print("="*60)
    
    # Check for environment variables
    from_email = os.environ.get('EMAIL_FROM', 'Not set')
    recipients = os.environ.get('EMAIL_RECIPIENTS', 'Not set')
    password_set = 'Yes' if os.environ.get('EMAIL_PASSWORD') else 'No'
    
    print(f"\nEnvironment Configuration:")
    print(f"  EMAIL_FROM: {from_email}")
    print(f"  EMAIL_RECIPIENTS: {recipients}")
    print(f"  EMAIL_PASSWORD: {password_set}")
    print(f"  SMTP_SERVER: {os.environ.get('SMTP_SERVER', 'smtp.gmail.com')}")
    print(f"  SMTP_PORT: {os.environ.get('SMTP_PORT', '587')}")
    
    # Test connection first
    if not test_email_connection():
        print("\n⚠️  Fix the configuration issues before proceeding")
        print("\nFor local testing, run these commands first:")
        print("  export EMAIL_FROM='jeff.nardinelli@gmail.com'")
        print("  export EMAIL_PASSWORD='lesozjghnnuzshnw'")
        print("  export EMAIL_RECIPIENTS='jeffnardinelli@quinnemanuel.com'")
        print("  python3 secure_cafc_test.py")
        return
    
    # Get test decisions
    decisions = get_test_decisions()
    print(f"  Test decisions: {len(decisions)}")
    
    # Save HTML preview
    save_html_preview(decisions)
    
    # Automatically send email (no prompt in automated mode)
    print("\nAutomatically sending email (running in automated mode)...")
    send_test_email(decisions)
    
    print("\n" + "="*60)
    print("TEST COMPLETE")


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
Startup Outreach Automation Script
==================================

Automated outreach tool for startup incubators and foundries to connect with:
- Tech publications and startup blogs
- AI recommendation engines and platforms
- Startup influencers and thought leaders
- Founder communities and networks
- Investment and accelerator platforms

Features:
- Web scraping for new contact discovery
- Rate-limited outreach (2-4 contacts per target organization)
- Contact tracking and duplicate prevention
- Template-based messaging with personalization
- Integration with email services
- Comprehensive logging and analytics

Usage:
    python startup_outreach.py --mode discover  # Discover new contacts
    python startup_outreach.py --mode outreach  # Send outreach messages
    python startup_outreach.py --mode report    # Generate analytics report
"""

import json
import csv
import time
import random
import logging
import argparse
import requests
import os
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from typing import List, Dict, Set, Optional
from pathlib import Path
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import re
from urllib.parse import urljoin, urlparse, quote
from bs4 import BeautifulSoup
import yagmail
from jinja2 import Template

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("Warning: python-dotenv not installed. Using system environment variables only.")
import schedule
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.syntax import Syntax
from rich.progress import Progress, SpinnerColumn, TextColumn
import textwrap

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('outreach.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class Contact:
    """Data class for contact information"""
    name: str
    email: str
    organization: str
    role: str
    source: str
    category: str  # publication, influencer, platform, community
    social_links: List[str]
    contact_date: Optional[str] = None
    response_received: bool = False
    notes: str = ""
    outreach_count: int = 0
    last_contact: Optional[str] = None

@dataclass
@dataclass
class OutreachTarget:
    """Data class for outreach targets"""
    name: str
    website: str
    category: str
    focus_areas: List[str]
    contact_methods: List[str]
    priority: int  # 1-5, 5 being highest
    contacts_found: int = 0
    last_scraped: Optional[str] = None
    region: str = "US/Global"

@dataclass
class PendingOutreach:
    """Data class for pending outreach messages"""
    contact: Contact
    message: Dict[str, str]
    timestamp: str
    approved: bool = False
    sent: bool = False

class StartupOutreachBot:
    """Main outreach automation class"""
    
    def __init__(self):
        # Set data directory relative to the root project directory
        root_dir = Path(__file__).parent.parent
        self.data_dir = root_dir / "outreach_data"
        self.data_dir.mkdir(exist_ok=True)
        
        # Data files
        self.contacts_file = self.data_dir / "contacts.json"
        self.targets_file = self.data_dir / "targets.json"
        self.outreach_log_file = self.data_dir / "outreach_log.json"
        self.analytics_file = self.data_dir / "analytics.json"
        self.pending_file = self.data_dir / "pending_outreach.json"
        self.opt_outs_file = self.data_dir / "opt_outs.json"
        
        # Load existing data
        self.contacts = self.load_contacts()
        self.targets = self.load_targets()
        self.outreach_log = self.load_outreach_log()
        self.pending_outreach = self.load_pending_outreach()
        self.opt_outs = self.load_opt_outs()
        
        # Configuration
        self.max_outreach_per_target = 4
        self.min_outreach_per_target = 2
        self.rate_limit_delay = (30, 60)  # Random delay between 30-60 seconds
        
        # Rich console for beautiful CLI
        self.console = Console()
        
        # Load configuration
        self.config = self.load_config()
        
        # Initialize with default targets
        if not self.targets:
            self.initialize_default_targets()

    def load_contacts(self) -> List[Contact]:
        """Load contacts from JSON file"""
        if self.contacts_file.exists():
            with open(self.contacts_file, 'r') as f:
                data = json.load(f)
                return [Contact(**contact) for contact in data]
        return []

    def save_contacts(self):
        """Save contacts to JSON file"""
        with open(self.contacts_file, 'w') as f:
            json.dump([asdict(contact) for contact in self.contacts], f, indent=2)

    def load_targets(self) -> List[OutreachTarget]:
        """Load outreach targets from JSON file"""
        if self.targets_file.exists():
            with open(self.targets_file, 'r') as f:
                data = json.load(f)
                return [OutreachTarget(**target) for target in data]
        return []

    def save_targets(self):
        """Save targets to JSON file"""
        with open(self.targets_file, 'w') as f:
            json.dump([asdict(target) for target in self.targets], f, indent=2)

    def load_outreach_log(self) -> List[Dict]:
        """Load outreach log from JSON file"""
        if self.outreach_log_file.exists():
            with open(self.outreach_log_file, 'r') as f:
                return json.load(f)
        return []

    def save_outreach_log(self):
        """Save outreach log to JSON file"""
        with open(self.outreach_log_file, 'w') as f:
            json.dump(self.outreach_log, f, indent=2)

    def load_pending_outreach(self) -> List[PendingOutreach]:
        """Load pending outreach from JSON file"""
        if self.pending_file.exists():
            with open(self.pending_file, 'r') as f:
                data = json.load(f)
                return [PendingOutreach(
                    contact=Contact(**item['contact']),
                    message=item['message'],
                    timestamp=item['timestamp'],
                    approved=item.get('approved', False),
                    sent=item.get('sent', False)
                ) for item in data]
        return []

    def save_pending_outreach(self):
        """Save pending outreach to JSON file"""
        data = []
        for pending in self.pending_outreach:
            data.append({
                'contact': asdict(pending.contact),
                'message': pending.message,
                'timestamp': pending.timestamp,
                'approved': pending.approved,
                'sent': pending.sent
            })
        with open(self.pending_file, 'w') as f:
            json.dump(data, f, indent=2)

    def load_opt_outs(self) -> Dict:
        """Load opt-outs from JSON file"""
        if self.opt_outs_file.exists():
            with open(self.opt_outs_file, 'r') as f:
                return json.load(f)
        return {
            "opt_outs": [],
            "created": datetime.now().strftime("%Y-%m-%d"),
            "last_updated": datetime.now().strftime("%Y-%m-%d"),
            "total_opt_outs": 0
        }

    def save_opt_outs(self):
        """Save opt-outs to JSON file"""
        with open(self.opt_outs_file, 'w') as f:
            json.dump(self.opt_outs, f, indent=2)

    def is_opted_out(self, email: str) -> bool:
        """Check if an email address has opted out"""
        opt_out_emails = [opt_out['email'].lower() for opt_out in self.opt_outs.get('opt_outs', [])]
        return email.lower() in opt_out_emails

    def add_opt_out(self, email: str, reason: str = "", source: str = "manual") -> bool:
        """Add an email to the opt-out list"""
        if self.is_opted_out(email):
            return False  # Already opted out
        
        opt_out_entry = {
            'email': email.lower(),
            'reason': reason,
            'timestamp': datetime.now().isoformat(),
            'source': source  # 'web', 'manual', 'bounce', etc.
        }
        
        self.opt_outs['opt_outs'].append(opt_out_entry)
        self.opt_outs['last_updated'] = datetime.now().strftime("%Y-%m-%d")
        self.opt_outs['total_opt_outs'] = len(self.opt_outs['opt_outs'])
        
        self.save_opt_outs()
        logger.info(f"✅ Added {email} to opt-out list (reason: {reason or 'no reason'})")
        return True

    def generate_opt_out_link(self, email: str) -> str:
        """Generate a personalized opt-out link"""
        base_url = "https://www.firstcityfoundry.com/opt-out.html"
        encoded_email = quote(email)
        return f"{base_url}?email={encoded_email}&auto=true"

    def load_config(self):
        """Load configuration from environment variables and config.py"""
        config_data = {
            'email': {
                'smtp_server': os.getenv('BREVO_SMTP_HOST', 'smtp-relay.brevo.com'),
                'smtp_port': int(os.getenv('BREVO_SMTP_PORT', '587')),
                'username': os.getenv('BREVO_SMTP_USER', ''),
                'password': os.getenv('BREVO_SMTP_PASSWORD', ''),
                'from_email': os.getenv('FROM_EMAIL', 'team@open.build'),
                'from_name': os.getenv('FROM_NAME', 'Open Build Foundry Team'),
                'reply_to': os.getenv('REPLY_TO_EMAIL', 'team@open.build')
            },
            'cli': {'interactive_mode': True},
            'notifications': {
                'daily_summary': True,
                'notification_email': os.getenv('DAILY_NOTIFICATION_EMAIL', 'team@open.build')
            },
            'rate_limits': {
                'max_daily_outreach': int(os.getenv('MAX_DAILY_OUTREACH', '50')),
                'max_per_organization': int(os.getenv('MAX_PER_ORGANIZATION', '4')),
                'min_delay_seconds': int(os.getenv('MIN_DELAY_SECONDS', '30')),
                'max_delay_seconds': int(os.getenv('MAX_DELAY_SECONDS', '60'))
            }
        }
        
        # Try to load additional config from config.py if it exists
        try:
            # Add parent directory to sys.path to find config.py in root
            import sys
            from pathlib import Path
            root_dir = Path(__file__).parent.parent
            if str(root_dir) not in sys.path:
                sys.path.insert(0, str(root_dir))
            
            import config
            config_data['email'].update(getattr(config, 'EMAIL_CONFIG', {}))
            config_data['cli'].update(getattr(config, 'CLI_CONFIG', {}))
            config_data['notifications'].update(getattr(config, 'NOTIFICATION_CONFIG', {}))
            config_data['rate_limits'].update(getattr(config, 'RATE_LIMITS', {}))
        except ImportError:
            logger.info("config.py not found, using environment variables only")
        
        return config_data

    def initialize_default_targets(self):
        """Initialize with default startup-focused targets"""
        default_targets = [
            # Major Tech Publications
            OutreachTarget(
                name="TechCrunch",
                website="https://techcrunch.com",
                category="publication",
                focus_areas=["startups", "funding", "AI", "enterprise"],
                contact_methods=["email", "twitter", "contact_form"],
                priority=5
            ),
            OutreachTarget(
                name="Product Hunt",
                website="https://producthunt.com",
                category="platform",
                focus_areas=["product_launches", "startups", "indie_makers"],
                contact_methods=["platform_message", "email"],
                priority=5
            ),
            OutreachTarget(
                name="Hacker News",
                website="https://news.ycombinator.com",
                category="community",
                focus_areas=["tech", "startups", "programming", "entrepreneurship"],
                contact_methods=["submission", "comments"],
                priority=4
            ),
            OutreachTarget(
                name="AngelList (Wellfound)",
                website="https://wellfound.com",
                category="platform",
                focus_areas=["startups", "jobs", "funding", "accelerators"],
                contact_methods=["platform_message", "email"],
                priority=5
            ),
            OutreachTarget(
                name="Indie Hackers",
                website="https://indiehackers.com",
                category="community",
                focus_areas=["solo_founders", "bootstrapping", "SaaS", "indie_makers"],
                contact_methods=["platform_message", "email"],
                priority=5
            ),
            # AI-Focused Publications
            OutreachTarget(
                name="VentureBeat AI",
                website="https://venturebeat.com/ai/",
                category="publication",
                focus_areas=["AI", "machine_learning", "startups", "enterprise"],
                contact_methods=["email", "twitter"],
                priority=4
            ),
            OutreachTarget(
                name="AI News",
                website="https://artificialintelligence-news.com",
                category="publication",
                focus_areas=["AI", "startups", "technology"],
                contact_methods=["email", "contact_form"],
                priority=4
            ),
            # Startup Influencers & Thought Leaders
            OutreachTarget(
                name="First Round Review",
                website="https://review.firstround.com",
                category="publication",
                focus_areas=["early_stage", "founders", "leadership", "growth"],
                contact_methods=["email", "twitter"],
                priority=5
            ),
            OutreachTarget(
                name="500 Startups Blog",
                website="https://500.co/blog",
                category="publication",
                focus_areas=["global_startups", "accelerator", "funding"],
                contact_methods=["email", "contact_form"],
                priority=4
            ),
            # Developer-Focused Publications
            OutreachTarget(
                name="Dev.to",
                website="https://dev.to",
                category="community",
                focus_areas=["developers", "programming", "startup_tools", "open_source"],
                contact_methods=["platform_message", "email"],
                priority=4
            ),
            OutreachTarget(
                name="GitHub Blog",
                website="https://github.blog",
                category="publication",
                focus_areas=["open_source", "developers", "startups", "enterprise"],
                contact_methods=["email", "github"],
                priority=4
            ),
            # Niche & International Publications
            OutreachTarget(
                name="The Startup Magazine",
                website="https://thestartupmagazine.co.uk",
                category="publication",
                focus_areas=["UK_startups", "entrepreneurship", "small_business"],
                contact_methods=["email", "contact_form"],
                priority=3
            ),
            OutreachTarget(
                name="StartupGrind",
                website="https://startupgrind.com",
                category="community",
                focus_areas=["global_community", "events", "founders"],
                contact_methods=["email", "platform_message"],
                priority=4
            ),
            OutreachTarget(
                name="Entrepreneur.com",
                website="https://entrepreneur.com",
                category="publication",
                focus_areas=["entrepreneurship", "small_business", "startups"],
                contact_methods=["email", "contact_form"],
                priority=4
            ),
            # Solo Founder & Bootstrapper Focused
            OutreachTarget(
                name="Bootstrapped.fm",
                website="https://bootstrapped.fm",
                category="podcast",
                focus_areas=["bootstrapping", "solo_founders", "SaaS"],
                contact_methods=["email", "twitter"],
                priority=4
            ),
            OutreachTarget(
                name="MicroConf",
                website="https://microconf.com",
                category="community",
                focus_areas=["SaaS", "bootstrapping", "solo_founders"],
                contact_methods=["email", "contact_form"],
                priority=4
            )
        ]
        
        self.targets.extend(default_targets)
        self.save_targets()
        logger.info(f"Initialized {len(default_targets)} default targets")

    def discover_new_targets(self):
        """Discover new outreach targets through web scraping"""
        logger.info("Starting target discovery...")
        
        # Search patterns for startup-related sites
        search_queries = [
            "startup blogs 2025",
            "entrepreneur publications",
            "tech startup newsletters",
            "solo founder communities",
            "AI startup platforms",
            "developer startup resources",
            "startup incubator blogs",
            "first time founder resources"
        ]
        
        new_targets = []
        
        for query in search_queries:
            try:
                # Simulate search results discovery (in production, use proper search APIs)
                discovered = self.search_for_targets(query)
                new_targets.extend(discovered)
                time.sleep(random.uniform(5, 10))  # Rate limiting
            except Exception as e:
                logger.error(f"Error discovering targets for query '{query}': {e}")
        
        # Add unique new targets
        existing_websites = {target.website for target in self.targets}
        unique_targets = [t for t in new_targets if t.website not in existing_websites]
        
        self.targets.extend(unique_targets)
        self.save_targets()
        
        logger.info(f"Discovered {len(unique_targets)} new targets")
        return unique_targets

    def search_for_targets(self, query: str) -> List[OutreachTarget]:
        """Search for potential targets.

        Returns an empty list until a real search API (Google Custom Search,
        Bing API, etc.) is integrated.
        """
        # TODO: Integrate with search APIs like Google Custom Search, Bing API, etc.
        logger.info(f"Target search not yet implemented — no results for: {query}")
        return []

    def scrape_contacts_from_target(self, target: OutreachTarget) -> List[Contact]:
        """Enhanced contact scraping with better source discovery"""
        logger.info(f"Scraping contacts from {target.name}")
        
        contacts = []
        
        try:
            # Add headers to appear as a real browser
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            }
            
            # Enhanced contact page URLs to try
            contact_urls = [
                urljoin(target.website, '/contact'),
                urljoin(target.website, '/contact-us'),
                urljoin(target.website, '/about'),
                urljoin(target.website, '/about-us'),
                urljoin(target.website, '/team'),
                urljoin(target.website, '/staff'),
                urljoin(target.website, '/contributors'),
                urljoin(target.website, '/authors'),
                urljoin(target.website, '/press'),
                urljoin(target.website, '/media'),
                urljoin(target.website, '/partnerships'),
                urljoin(target.website, '/advertising'),
                urljoin(target.website, '/submit'),
                urljoin(target.website, '/tips'),
                target.website  # Main page
            ]
            
            # Try to find additional contact methods specific to startup sites
            additional_urls = self.discover_startup_specific_urls(target)
            contact_urls.extend(additional_urls)
            
            for url in contact_urls:
                try:
                    response = requests.get(url, headers=headers, timeout=15)
                    if response.status_code == 200:
                        soup = BeautifulSoup(response.content, 'html.parser')
                        page_contacts = self.extract_contacts_from_page(soup, target, url)
                        
                        # Filter out test emails and duplicates
                        for contact in page_contacts:
                            if (not self.is_test_email(contact.email) and 
                                contact.email not in [c.email for c in contacts]):
                                contacts.append(contact)
                        
                        # Limit contacts per target
                        if len(contacts) >= self.max_outreach_per_target:
                            break
                            
                    time.sleep(random.uniform(3, 7))  # Increased rate limiting
                    
                except requests.RequestException as e:
                    logger.warning(f"Error accessing {url}: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error scraping {target.name}: {e}")
        
        # Update target info
        target.contacts_found = len(contacts)
        target.last_scraped = datetime.now().isoformat()
        
        logger.info(f"Found {len(contacts)} contacts from {target.name}")
        return contacts
    
    def discover_startup_specific_urls(self, target: OutreachTarget) -> List[str]:
        """Discover startup-specific contact URLs based on target type"""
        urls = []
        base_url = target.website
        
        # Publication-specific paths
        if target.category == 'publication':
            urls.extend([
                urljoin(base_url, '/pitch'),
                urljoin(base_url, '/submit-story'),
                urljoin(base_url, '/tip-us'),
                urljoin(base_url, '/editorial'),
                urljoin(base_url, '/newsroom'),
                urljoin(base_url, '/contribute'),
            ])
        
        # Platform-specific paths
        elif target.category == 'platform':
            urls.extend([
                urljoin(base_url, '/partners'),
                urljoin(base_url, '/partnership'),
                urljoin(base_url, '/business'),
                urljoin(base_url, '/enterprise'),
                urljoin(base_url, '/api'),
            ])
        
        # Community-specific paths
        elif target.category == 'community':
            urls.extend([
                urljoin(base_url, '/organizers'),
                urljoin(base_url, '/moderators'),
                urljoin(base_url, '/events'),
                urljoin(base_url, '/speakers'),
            ])
        
        return urls

    def extract_contacts_from_page(self, soup: BeautifulSoup, target: OutreachTarget, url: str) -> List[Contact]:
        """Enhanced contact extraction with better name detection"""
        contacts = []
        
        # Enhanced email regex pattern
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        
        # Find emails in various locations
        emails_found = set()
        
        # 1. Find emails in text
        page_text = soup.get_text()
        text_emails = re.findall(email_pattern, page_text)
        emails_found.update(text_emails)
        
        # 2. Find emails in mailto links
        mailto_links = soup.find_all('a', href=re.compile(r'^mailto:', re.I))
        for link in mailto_links:
            email = link['href'].replace('mailto:', '').split('?')[0]
            if re.match(email_pattern, email):
                emails_found.add(email)
        
        # 3. Find emails in data attributes and form actions
        for element in soup.find_all(attrs={'data-email': True}):
            if element.get('data-email'):
                emails_found.add(element['data-email'])
        
        # 4. Look for obfuscated emails (simple cases)
        obfuscated_patterns = [
            r'\b[A-Za-z0-9._%+-]+\s*\[at\]\s*[A-Za-z0-9.-]+\s*\[dot\]\s*[A-Z|a-z]{2,}\b',
            r'\b[A-Za-z0-9._%+-]+\s*@\s*[A-Za-z0-9.-]+\s*\.\s*[A-Z|a-z]{2,}\b'
        ]
        
        for pattern in obfuscated_patterns:
            obfuscated_emails = re.findall(pattern, page_text, re.I)
            for email in obfuscated_emails:
                clean_email = email.replace('[at]', '@').replace('[dot]', '.').replace(' ', '')
                if re.match(email_pattern, clean_email):
                    emails_found.add(clean_email)
        
        # Process unique emails
        for email in emails_found:
            email = email.lower().strip()
            
            # Enhanced filtering
            skip_patterns = [
                'noreply', 'no-reply', 'donotreply', 'mailer-daemon',
                'postmaster', 'abuse', 'security', 'legal',
                'privacy', 'gdpr', 'unsubscribe', 'bounces'
            ]
            
            if any(skip in email for skip in skip_patterns):
                continue
            
            # Skip if it's a test email
            if self.is_test_email(email):
                continue
                
            # Try to extract name and role context with improved methods
            name, role = self.extract_enhanced_name_and_role(soup, email, target)
            
            contact = Contact(
                name=name or "Unknown",
                email=email,
                organization=target.name,
                role=role or "Contact",
                source=url,
                category=target.category,
                social_links=[]
            )
            
            contacts.append(contact)
            
            # Limit per page
            if len(contacts) >= 5:
                break
        
        return contacts

    def extract_enhanced_name_and_role(self, soup: BeautifulSoup, email: str, target: OutreachTarget) -> tuple:
        """Enhanced name and role extraction with better pattern matching"""
        name = None
        role = None
        
        # Look for the email in the page and extract nearby context
        email_elements = soup.find_all(text=re.compile(re.escape(email)))
        
        for element in email_elements:
            parent = element.parent
            if parent:
                # Get surrounding context
                context_text = parent.get_text()
                
                # Look for structured data (JSON-LD, microdata)
                structured_data = self.extract_structured_contact_data(soup, email)
                if structured_data:
                    name = structured_data.get('name', name)
                    role = structured_data.get('role', role)
                
                # Extract name using multiple patterns
                if not name:
                    name = self.extract_name_patterns(context_text, email)
                
                # Extract role using enhanced patterns
                if not role:
                    role = self.extract_role_patterns(context_text, target)
        
        # Fallback: try to extract generic contact info
        if not name and not role:
            name, role = self.extract_generic_contact_info(soup, email, target)
        
        return name, role
    
    def extract_structured_contact_data(self, soup: BeautifulSoup, email: str) -> dict:
        """Extract contact data from structured markup"""
        data = {}
        
        # Look for JSON-LD
        scripts = soup.find_all('script', type='application/ld+json')
        for script in scripts:
            try:
                json_data = json.loads(script.string)
                if isinstance(json_data, dict):
                    # Look for Person or Organization schema
                    if json_data.get('@type') in ['Person', 'Organization']:
                        if email in str(json_data):
                            data['name'] = json_data.get('name')
                            data['role'] = json_data.get('jobTitle')
            except json.JSONDecodeError:
                continue
        
        return data
    
    def extract_name_patterns(self, text: str, email: str) -> str:
        """Extract names using various patterns"""
        # Common name patterns
        patterns = [
            # "Name <email>"
            r'([A-Z][a-z]+ [A-Z][a-z]+)\s*<[^>]*' + re.escape(email) + r'[^>]*>',
            # "Name - email"
            r'([A-Z][a-z]+ [A-Z][a-z]+)\s*[-–—]\s*[^@]*' + re.escape(email),
            # "Contact: Name"
            r'Contact:\s*([A-Z][a-z]+ [A-Z][a-z]+)',
            # "Name (title)"
            r'([A-Z][a-z]+ [A-Z][a-z]+)\s*\([^)]*\)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.I)
            if match:
                return match.group(1).strip()
        
        return None
    
    def extract_role_patterns(self, text: str, target: OutreachTarget) -> str:
        """Extract roles using enhanced patterns"""
        role_patterns = {
            'publication': ['editor', 'writer', 'journalist', 'reporter', 'contributor', 'author', 'correspondent'],
            'platform': ['founder', 'ceo', 'cto', 'product', 'marketing', 'business development', 'partnerships'],
            'community': ['organizer', 'moderator', 'community manager', 'event coordinator', 'ambassador'],
            'influencer': ['founder', 'consultant', 'advisor', 'speaker', 'thought leader']
        }
        
        patterns = role_patterns.get(target.category, role_patterns['publication'])
        text_lower = text.lower()
        
        for pattern in patterns:
            if pattern in text_lower:
                return pattern.title()
        
        return None
    
    def extract_generic_contact_info(self, soup: BeautifulSoup, email: str, target: OutreachTarget) -> tuple:
        """Extract generic contact information when specific patterns fail"""
        # Look for common contact section headers
        contact_headers = soup.find_all(['h1', 'h2', 'h3', 'h4'], text=re.compile(r'contact|team|about|staff', re.I))
        
        for header in contact_headers:
            # Look in the section following this header
            section = header.find_next_sibling()
            if section and email in section.get_text():
                # Extract any capitalized words that might be names
                words = section.get_text().split()
                names = [word for word in words if word.istitle() and len(word) > 2 and word.isalpha()]
                if names:
                    if len(names) >= 2:
                        return f"{names[0]} {names[1]}", None
                    else:
                        return names[0], None
        
        return None, None
        
        return name, role

    def generate_outreach_message(self, contact: Contact) -> Dict[str, str]:
        """Generate personalized outreach message with improved name handling"""
        
        # Get improved contact name
        contact_name = self.improve_contact_name(contact)
        
        # Message templates based on contact category
        templates = {
            'publication': """
Subject: Partnership Opportunity: Global Startup Foundry Launch + Bootstrapped Founders Podcast

{{ contact_name }},

I hope this email finds you well. I'm reaching out from Buildly Labs Foundry, a new global startup incubator that just launched in partnership with OpenBuild and Buildly Labs.

Given {{ organization }}'s focus on {{ focus_area }}, I thought you might be interested in covering our unique approach to supporting software developers and entrepreneurs worldwide.

What makes us different:
• 100% equity-free support (unprecedented in the industry)
• AI-powered startup analysis and recommendations  
• Free cloud hosting credits through partnerships
• Global developer community access via OpenBuild
• Focus on solo founders and first-time entrepreneurs
• FirstCityFoundry Bootstrapped Founders Podcast featuring real founder stories

Our platform at https://www.firstcityfoundry.com showcases how we're democratizing startup support globally, and our podcast (https://www.firstcityfoundry.com/podcast.html) highlights authentic bootstrapping journeys from Portland StartupGrind community.

Would you be interested in:
- Learning more about our story and partnerships
- Interviewing some of our founders
- Having our founders as podcast guests to share their bootstrapping stories
- Featuring our podcast content or cross-promoting with your audience

I'd be happy to provide additional information, press materials, or arrange interviews.

Please feel free to reach out with any questions or inquiries to team@open.build.

Best regards,
Buildly Labs Foundry Team

P.S. We're also happy to provide exclusive early access to our platform for {{ organization }}'s readers if that would be of interest.

---
If you no longer wish to receive these communications, you can unsubscribe here: {{ opt_out_link }}
            """,
            
            'influencer': """
Subject: New Global Startup Foundry + Bootstrapped Founders Podcast - Partnership with OpenBuild

{{ contact_name }},

I've been following your work at {{ organization }} and your insights on {{ focus_area }} - really appreciate your perspective on the startup ecosystem.

I wanted to introduce you to Buildly Labs Foundry, a new global startup incubator we've just launched. What caught my attention is how our approach aligns with many of the challenges you've highlighted about traditional accelerators.

Key differentiators:
• Zero equity required (keeping founders in full control)
• AI-powered startup evaluation and recommendations 
• Partnership with OpenBuild for global developer community access
• Free cloud infrastructure support
• Specific focus on solo founders and developers transitioning to entrepreneurship
• FirstCityFoundry Bootstrapped Founders Podcast showcasing real founder journeys

You can check out our platform at https://www.firstcityfoundry.com and our podcast at https://www.firstcityfoundry.com/podcast.html

Given your influence in the startup community, I'd love to get your thoughts on our approach. Would you be open to:
- A brief conversation about what we're building
- Being a guest on our Bootstrapped Founders Podcast to share your insights
- Cross-promoting our podcast content with your audience

If this resonates with your community, we'd also be happy to discuss other collaboration opportunities or provide exclusive insights.

Feel free to reach out with questions to team@open.build.

Best,
Buildly Labs Foundry Team

---
If you no longer wish to receive these communications, you can unsubscribe here: {{ opt_out_link }}
            """,
            
            'platform': """
Subject: Partnership Opportunity: Buildly Labs Foundry Launch + Podcast Content

{{ contact_name }},

I'm reaching out from Buildly Labs Foundry, a new global startup incubator that recently launched in partnership with OpenBuild and Buildly Labs.

Given {{ organization }}'s platform and community, I believe there could be great synergy between our missions to support entrepreneurs and developers.

Our unique approach:
• 100% equity-free incubator model
• AI-powered startup analysis and strategic recommendations
• Global reach through OpenBuild partnership  
• Free cloud hosting and technical infrastructure
• Focus on underserved founders (solo, first-time, international)
• FirstCityFoundry Bootstrapped Founders Podcast with authentic founder stories

Our platform: https://www.firstcityfoundry.com
Our podcast: https://www.firstcityfoundry.com/podcast.html

I'd love to explore potential partnership opportunities, whether that's:
- Cross-promotion to relevant communities
- Integration opportunities
- Content collaboration (including podcast content sharing)
- Joint events or initiatives
- Podcast guest exchanges

Would you be interested in a conversation about how we might work together to better serve the startup community?

Please reach out to team@open.build with any questions or to discuss further.

Best regards,
Buildly Labs Foundry Partnership Team

---
If you no longer wish to receive these communications, you can unsubscribe here: {{ opt_out_link }}
            """,
            
            'community': """
Subject: Introducing Buildly Labs Foundry + Bootstrapped Founders Podcast

{{ contact_name }},

I hope you're doing well! I wanted to share something new that I think the {{ organization }} community would find interesting.

We've just launched Buildly Labs Foundry, a global startup incubator with a fundamentally different approach to supporting entrepreneurs and developers.

What makes us unique:
• Completely equity-free (founders keep 100% ownership)
• AI-powered analysis and personalized recommendations
• Partnership with OpenBuild for global developer community access
• Free cloud hosting and infrastructure support  
• Designed specifically for solo founders, developers, and first-time entrepreneurs
• FirstCityFoundry Bootstrapped Founders Podcast featuring real founder stories from Portland StartupGrind

Check it out: https://www.firstcityfoundry.com
Our podcast: https://www.firstcityfoundry.com/podcast.html

I thought this might resonate with {{ organization }}'s community, especially those looking to transition from development to entrepreneurship or seeking startup support without giving up equity.

Would you be open to:
- Me sharing this with the community
- Discussing collaboration opportunities
- Having community members as podcast guests to share their bootstrapping journeys
- Cross-promoting our podcast content

Happy to answer any questions at team@open.build.

Cheers,
Buildly Labs Foundry Team

---
If you no longer wish to receive these communications, you can unsubscribe here: {{ opt_out_link }}
            """
        }
        
        # Select appropriate template
        template_key = contact.category if contact.category in templates else 'publication'
        template_text = templates[template_key]
        
        # Personalize the message
        template = Template(template_text.strip())
        
        # Determine focus area based on organization
        focus_area = self.get_focus_area_for_organization(contact.organization)
        
        message = template.render(
            contact_name=contact_name,
            contact=contact,
            organization=contact.organization,
            focus_area=focus_area,
            site_url="https://www.firstcityfoundry.com",
            opt_out_link=self.generate_opt_out_link(contact.email)
        )
        
        # Extract subject line
        lines = message.split('\n')
        subject = lines[0].replace('Subject: ', '') if lines[0].startswith('Subject: ') else "Partnership Opportunity: Buildly Labs Foundry"
        body = '\n'.join(lines[2:])  # Skip subject and empty line
        
        return {
            'subject': subject,
            'body': body,
            'template_used': template_key
        }

    def get_focus_area_for_organization(self, organization: str) -> str:
        """Get relevant focus area for an organization"""
        focus_mapping = {
            'techcrunch': 'startup funding and innovation',
            'product hunt': 'product launches and startup discovery',
            'hacker news': 'developer community and tech discussions',
            'indie hackers': 'solo founders and bootstrapping',
            'angellist': 'startup funding and talent',
            'dev.to': 'developer community and technical content',
            'github': 'open source and developer tools',
            'venturebeat': 'AI and enterprise technology',
            'entrepreneur': 'small business and entrepreneurship'
        }
        
        org_lower = organization.lower()
        for key, value in focus_mapping.items():
            if key in org_lower:
                return value
        
        return "entrepreneurship and startup development"

    def preview_message_cli(self, contact: Contact, message: Dict[str, str]) -> str:
        """Preview message in CLI and get user decision"""
        
        # Create contact info panel
        contact_info = f"""
[bold cyan]Name:[/bold cyan] {contact.name}
[bold cyan]Email:[/bold cyan] {contact.email}
[bold cyan]Organization:[/bold cyan] {contact.organization}
[bold cyan]Role:[/bold cyan] {contact.role}
[bold cyan]Category:[/bold cyan] {contact.category}
[bold cyan]Source:[/bold cyan] {contact.source}
        """
        
        self.console.print(Panel(contact_info.strip(), title="📧 Contact Information", border_style="blue"))
        
        # Show subject
        self.console.print(f"\n[bold yellow]Subject:[/bold yellow] {message['subject']}")
        
        # Show message body with syntax highlighting
        wrapped_body = textwrap.fill(message['body'], width=80)
        self.console.print(Panel(wrapped_body, title="📝 Message Body", border_style="green"))
        
        # Show options
        self.console.print("\n[bold]Options:[/bold]")
        self.console.print("  [green]s[/green] - Send message")
        self.console.print("  [yellow]e[/yellow] - Edit message")
        self.console.print("  [red]k[/red] - Skip this contact")
        self.console.print("  [blue]q[/blue] - Quit and save progress")
        
        while True:
            choice = Prompt.ask("\nWhat would you like to do?", choices=["s", "e", "k", "q"], default="s")
            
            if choice == "s":
                return "send"
            elif choice == "e":
                return "edit" 
            elif choice == "k":
                return "skip"
            elif choice == "q":
                return "quit"

    def edit_message_cli(self, message: Dict[str, str]) -> Dict[str, str]:
        """Allow user to edit message in CLI"""
        
        self.console.print("\n[bold]Edit Message[/bold]")
        
        # Edit subject
        new_subject = Prompt.ask("Subject", default=message['subject'])
        
        # Edit body (simplified - in production, could use external editor)
        self.console.print("\nCurrent message body:")
        self.console.print(Panel(message['body'], border_style="dim"))
        
        if Confirm.ask("Would you like to edit the message body?"):
            self.console.print("Enter your new message (type 'END' on a new line to finish):")
            lines = []
            while True:
                line = input()
                if line.strip() == 'END':
                    break
                lines.append(line)
            new_body = '\n'.join(lines)
        else:
            new_body = message['body']
        
        return {
            'subject': new_subject,
            'body': new_body,
            'template_used': message['template_used']
        }

    def interactive_outreach_session(self, pending_outreach: List[PendingOutreach]) -> None:
        """Run interactive outreach session with option for batch approval"""
        
        if not pending_outreach:
            self.console.print("[yellow]No pending outreach messages to review.[/yellow]")
            return
        
        self.console.print(f"\n[bold green]📧 Interactive Outreach Session[/bold green]")
        self.console.print(f"Found {len(pending_outreach)} messages to review\n")
        
        # Ask for review mode
        self.console.print("[bold]Choose review mode:[/bold]")
        self.console.print("1. [green]Individual review[/green] - Review each message separately")
        self.console.print("2. [blue]Batch approval[/blue] - Review all recipients and approve in bulk")
        self.console.print("3. [red]Auto-send all[/red] - Send all messages without review")
        
        mode_choice = Prompt.ask("Select mode", choices=["1", "2", "3"], default="1")
        
        if mode_choice == "2":
            return self.batch_approval_session(pending_outreach)
        elif mode_choice == "3":
            return self.auto_send_all_session(pending_outreach)
        else:
            return self.individual_review_session(pending_outreach)
    
    def batch_approval_session(self, pending_outreach: List[PendingOutreach]) -> None:
        """Batch approval mode - show all recipients and approve in bulk"""
        
        self.console.print(f"\n[bold blue]📋 Batch Approval Mode[/bold blue]")
        self.console.print(f"Reviewing {len(pending_outreach)} pending messages\n")
        
        # Create summary table
        table = Table(title="Pending Outreach Messages")
        table.add_column("No.", style="cyan", no_wrap=True)
        table.add_column("Name", style="green")
        table.add_column("Email", style="blue")
        table.add_column("Organization", style="yellow")
        table.add_column("Category", style="magenta")
        table.add_column("Subject Preview", style="white")
        
        for i, pending in enumerate(pending_outreach):
            if not pending.sent:
                subject_preview = pending.message['subject'][:50] + "..." if len(pending.message['subject']) > 50 else pending.message['subject']
                table.add_row(
                    str(i+1),
                    pending.contact.name,
                    pending.contact.email,
                    pending.contact.organization,
                    pending.contact.category,
                    subject_preview
                )
        
        self.console.print(table)
        
        # Show a sample message
        if pending_outreach:
            self.console.print(f"\n[bold]Sample Message (to {pending_outreach[0].contact.name}):[/bold]")
            self.console.print(Panel(
                pending_outreach[0].message['body'][:500] + "..." if len(pending_outreach[0].message['body']) > 500 else pending_outreach[0].message['body'],
                title=pending_outreach[0].message['subject'],
                border_style="blue"
            ))
        
        # Approval options
        self.console.print("\n[bold]Batch Actions:[/bold]")
        self.console.print("1. [green]Send all messages[/green]")
        self.console.print("2. [yellow]Review individual messages first[/yellow]") 
        self.console.print("3. [blue]Select specific messages to send[/blue]")
        self.console.print("4. [red]Cancel and return[/red]")
        
        action = Prompt.ask("Choose action", choices=["1", "2", "3", "4"], default="1")
        
        if action == "1":
            if Confirm.ask(f"[bold red]Send all {len(pending_outreach)} messages?[/bold red]"):
                self.send_batch_messages(pending_outreach)
        elif action == "2":
            self.individual_review_session(pending_outreach)
        elif action == "3":
            self.selective_send_session(pending_outreach)
        else:
            self.console.print("[blue]Cancelled batch approval[/blue]")
    
    def auto_send_all_session(self, pending_outreach: List[PendingOutreach]) -> None:
        """Auto-send all mode - send everything without individual review"""
        
        self.console.print(f"\n[bold red]🚀 Auto-Send All Mode[/bold red]")
        self.console.print(f"This will send ALL {len(pending_outreach)} messages without further review!")
        
        if Confirm.ask("[bold red]Are you absolutely sure you want to send all messages?[/bold red]"):
            self.console.print("[yellow]Sending all messages...[/yellow]")
            self.send_batch_messages(pending_outreach)
        else:
            self.console.print("[blue]Auto-send cancelled[/blue]")
    
    def selective_send_session(self, pending_outreach: List[PendingOutreach]) -> None:
        """Allow user to select specific messages to send"""
        
        self.console.print(f"\n[bold yellow]🎯 Selective Send Mode[/bold yellow]")
        
        # Show numbered list
        for i, pending in enumerate(pending_outreach):
            if not pending.sent:
                self.console.print(f"{i+1}. {pending.contact.name} ({pending.contact.email}) - {pending.contact.organization}")
        
        selection = Prompt.ask(
            "\nEnter message numbers to send (comma-separated, e.g., '1,3,5' or 'all')",
            default="all"
        )
        
        if selection.lower() == "all":
            selected_messages = pending_outreach
        else:
            try:
                indices = [int(x.strip()) - 1 for x in selection.split(",")]
                selected_messages = [pending_outreach[i] for i in indices if 0 <= i < len(pending_outreach)]
            except (ValueError, IndexError):
                self.console.print("[red]Invalid selection. Cancelling.[/red]")
                return
        
        if selected_messages and Confirm.ask(f"Send {len(selected_messages)} selected messages?"):
            self.send_batch_messages(selected_messages)
    
    def send_batch_messages(self, messages: List[PendingOutreach]) -> None:
        """Send multiple messages with progress tracking"""
        
        sent_count = 0
        failed_count = 0
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
        ) as progress:
            
            task = progress.add_task("Sending messages...", total=len(messages))
            
            for pending in messages:
                if pending.sent:
                    continue
                
                progress.update(task, description=f"Sending to {pending.contact.name}...")
                
                try:
                    if self.send_outreach_message(pending.contact, pending.message):
                        pending.sent = True
                        pending.approved = True
                        sent_count += 1
                        self.console.print(f"[green]✅ Sent to {pending.contact.name}[/green]")
                    else:
                        failed_count += 1
                        self.console.print(f"[red]❌ Failed to send to {pending.contact.name}[/red]")
                
                except Exception as e:
                    failed_count += 1
                    self.console.print(f"[red]❌ Error sending to {pending.contact.name}: {e}[/red]")
                
                # Rate limiting between sends
                delay = random.uniform(*self.rate_limit_delay)
                progress.update(task, description=f"Waiting {delay:.1f}s before next message...")
                time.sleep(delay)
                
                progress.advance(task)
        
        # Save progress
        self.save_pending_outreach()
        self.save_contacts()
        self.save_outreach_log()
        
        # Summary
        self.console.print(f"\n[bold green]📊 Batch Send Summary[/bold green]")
        self.console.print(f"✅ Sent: {sent_count}")
        self.console.print(f"❌ Failed: {failed_count}")
        self.console.print(f"⏳ Remaining: {len([p for p in self.pending_outreach if not p.sent and not p.approved])}")
        
        # Send notification email about outreach results
        try:
            from analytics_reporter import send_outreach_notification
            
            outreach_summary = {
                'sent_count': sent_count,
                'failed_count': failed_count,
                'total_messages': len(messages),
                'timestamp': datetime.now().isoformat(),
                'recipients': [
                    {
                        'name': pending.contact.name,
                        'email': pending.contact.email,
                        'organization': pending.contact.organization,
                        'status': 'sent' if pending.sent else 'failed'
                    }
                    for pending in messages
                ]
            }
            
            notification_email = os.getenv('DAILY_NOTIFICATION_EMAIL', 'greg@open.build')
            send_outreach_notification(outreach_summary, notification_email)
            
        except Exception as e:
            logger.warning(f"Failed to send outreach notification: {e}")
    
    def individual_review_session(self, pending_outreach: List[PendingOutreach]) -> None:
        """Original individual review mode"""
        
        sent_count = 0
        skipped_count = 0
        
        for i, pending in enumerate(pending_outreach):
            if pending.sent or pending.approved:
                continue
                
            self.console.print(f"\n[bold]Message {i+1} of {len(pending_outreach)}[/bold]")
            self.console.rule()
            
            decision = self.preview_message_cli(pending.contact, pending.message)
            
            if decision == "send":
                if self.send_outreach_message(pending.contact, pending.message):
                    pending.sent = True
                    pending.approved = True
                    sent_count += 1
                    self.console.print("[green]✅ Message sent successfully![/green]")
                else:
                    self.console.print("[red]❌ Failed to send message[/red]")
                
            elif decision == "edit":
                edited_message = self.edit_message_cli(pending.message)
                pending.message = edited_message
                
                # Ask again after editing
                decision = self.preview_message_cli(pending.contact, edited_message)
                if decision == "send":
                    if self.send_outreach_message(pending.contact, edited_message):
                        pending.sent = True
                        pending.approved = True
                        sent_count += 1
                        self.console.print("[green]✅ Edited message sent successfully![/green]")
                
            elif decision == "skip":
                skipped_count += 1
                self.console.print("[yellow]⏭️  Skipped this contact[/yellow]")
                
            elif decision == "quit":
                self.console.print("[blue]💾 Saving progress and exiting...[/blue]")
                break
            
            # Add delay between sends
            if decision == "send" and sent_count > 0:
                delay = random.uniform(10, 30)
                self.console.print(f"[dim]Waiting {delay:.1f} seconds before next message...[/dim]")
                time.sleep(delay)
        
        # Save progress
        self.save_pending_outreach()
        self.save_contacts()
        self.save_outreach_log()
        
        # Summary
        self.console.print(f"\n[bold green]📊 Session Summary[/bold green]")
        self.console.print(f"✅ Sent: {sent_count}")
        self.console.print(f"⏭️  Skipped: {skipped_count}")
        self.console.print(f"⏳ Remaining: {len([p for p in pending_outreach if not p.sent and not p.approved])}")

    def send_daily_analytics_report(self):
        """Send comprehensive daily analytics report"""
        try:
            # Import analytics module
            from analytics_reporter import AnalyticsCollector, format_daily_report_email
            
            # Generate analytics report
            collector = AnalyticsCollector()
            analytics = collector.generate_daily_report()
            report = format_daily_report_email(analytics)
            
            # Send report email
            email_config = self.config.get('email', {})
            notification_email = os.getenv('DAILY_NOTIFICATION_EMAIL', email_config.get('from_email'))
            
            if notification_email and email_config:
                # Create SMTP connection
                server = smtplib.SMTP(email_config['smtp_server'], email_config['smtp_port'])
                server.starttls()
                server.login(email_config['username'], email_config['password'])
                
                # Create HTML message
                msg = MIMEMultipart('alternative')
                msg['From'] = f"{email_config['from_name']} <{email_config['from_email']}>"
                msg['To'] = notification_email
                msg['Subject'] = report['subject']
                msg['Reply-To'] = email_config['from_email']
                
                # Add CC for greg@buildly.io
                cc_email = os.getenv('DAILY_CC_EMAIL', 'greg@buildly.io')
                msg['Cc'] = cc_email
                
                # Add BCC if configured  
                bcc_email = os.getenv('BCC_EMAIL')
                if bcc_email:
                    msg['Bcc'] = bcc_email
                
                # Add both plain text and HTML versions
                text_part = MIMEText(report['text_body'], 'plain')
                html_part = MIMEText(report['html_body'], 'html')
                
                msg.attach(text_part)
                msg.attach(html_part)
                
                # Send message (include CC and BCC in recipient list)
                recipients = [notification_email, cc_email]
                if bcc_email:
                    recipients.append(bcc_email)
                
                server.send_message(msg, to_addrs=recipients)
                server.quit()
                
                logger.info(f"✅ Daily analytics report sent to {notification_email} (CC: {cc_email})")
            
        except Exception as e:
            logger.error(f"Failed to send daily analytics report: {e}")
    
    def send_daily_notification(self):
        """Send daily summary notification (legacy method)"""
        # Call the new analytics report method
        self.send_daily_analytics_report()

    def send_outreach_message(self, contact: Contact, message: Dict[str, str], dry_run: bool = False) -> bool:
        """Send outreach message via Brevo SMTP"""
        
        # Check if contact has opted out
        if self.is_opted_out(contact.email):
            logger.warning(f"❌ Skipping {contact.email} - opted out")
            return False
        
        if dry_run:
            logger.info(f"[DRY RUN] Would send to {contact.name} at {contact.email}")
            logger.info(f"[DRY RUN] Subject: {message['subject']}")
            return True
        
        logger.info(f"Sending outreach to {contact.name} at {contact.email}")
        logger.info(f"Subject: {message['subject']}")
        
        try:
            # Brevo SMTP configuration
            email_config = self.config.get('email', {})
            
            if not email_config:
                logger.error("No email configuration found")
                return False
            
            # Create SMTP connection
            server = smtplib.SMTP(email_config['smtp_server'], email_config['smtp_port'])
            server.starttls()
            server.login(email_config['username'], email_config['password'])
            
            # Create message
            msg = MIMEMultipart()
            msg['From'] = f"{email_config['from_name']} <{email_config['from_email']}>"
            msg['To'] = contact.email
            msg['Subject'] = message['subject']
            msg['Reply-To'] = email_config['from_email']
            
            # Add BCC if configured
            bcc_email = os.getenv('BCC_EMAIL')
            if bcc_email:
                msg['Bcc'] = bcc_email
            
            # Add body
            msg.attach(MIMEText(message['body'], 'plain'))
            
            # Send message (include BCC in recipient list)
            recipients = [contact.email]
            if bcc_email:
                recipients.append(bcc_email)
            
            server.send_message(msg, to_addrs=recipients)
            server.quit()
            
            logger.info(f"✅ Message sent successfully to {contact.email}")
            
            # Update contact record
            contact.contact_date = datetime.now().isoformat()
            contact.outreach_count += 1
            contact.last_contact = datetime.now().isoformat()
            
            # Log the outreach
            self.outreach_log.append({
                'timestamp': datetime.now().isoformat(),
                'contact_name': contact.name,
                'contact_email': contact.email,
                'organization': contact.organization,
                'subject': message['subject'],
                'template_used': message['template_used'],
                'status': 'sent'
            })
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to send message to {contact.email}: {e}")
            
            self.outreach_log.append({
                'timestamp': datetime.now().isoformat(),
                'contact_name': contact.name,
                'contact_email': contact.email,
                'organization': contact.organization,
                'subject': message['subject'],
                'template_used': message['template_used'],
                'status': 'failed',
                'error': str(e)
            })
            
            return False

    def run_discovery_phase(self):
        """Run the contact discovery phase"""
        logger.info("🔍 Starting discovery phase...")
        
        # Discover new targets
        new_targets = self.discover_new_targets()
        
        # Scrape contacts from existing and new targets
        for target in self.targets:
            # Skip if recently scraped (within 7 days)
            if target.last_scraped:
                last_scraped = datetime.fromisoformat(target.last_scraped)
                if datetime.now() - last_scraped < timedelta(days=7):
                    logger.info(f"Skipping {target.name} - recently scraped")
                    continue
            
            # Scrape contacts
            new_contacts = self.scrape_contacts_from_target(target)
            
            # Add new contacts (avoid duplicates)
            existing_emails = {contact.email for contact in self.contacts}
            unique_contacts = [c for c in new_contacts if c.email not in existing_emails]
            
            self.contacts.extend(unique_contacts)
            logger.info(f"Added {len(unique_contacts)} new contacts from {target.name}")
            
            # Rate limiting
            time.sleep(random.uniform(*self.rate_limit_delay))
        
        # Save updated data
        self.save_contacts()
        self.save_targets()
        
        logger.info(f"✅ Discovery complete. Total contacts: {len(self.contacts)}")

    def is_test_email(self, email: str) -> bool:
        """Check if email is a test/honeypot/invalid email"""
        test_domains = {
            'example.com', 'example.org', 'example.net',
            'test.com', 'test.org', 'test.net',
            'localhost', '127.0.0.1',
            'noreply.com', 'no-reply.com',
            'fake.com', 'dummy.com',
            'spam.com', 'honeypot.com',
            'mailinator.com', '10minutemail.com',
            'tempmail.org', 'guerrillamail.com'
        }
        
        if not email or '@' not in email:
            return True
            
        domain = email.split('@')[1].lower()
        return domain in test_domains
    
    def get_domain_from_email(self, email: str) -> str:
        """Extract domain from email address"""
        if '@' not in email:
            return ''
        return email.split('@')[1].lower()
    
    def improve_contact_name(self, contact: Contact) -> str:
        """Improve contact name handling for better personalization"""
        if not contact.name or contact.name.lower() in ['unknown', '', 'null', 'none']:
            # Try to determine if it's a generic email
            email_local = contact.email.split('@')[0].lower()
            
            generic_prefixes = {
                'info', 'contact', 'support', 'help', 'admin',
                'hello', 'hi', 'team', 'mail', 'office',
                'press', 'media', 'news', 'editor', 'tips',
                'marketing', 'sales', 'business', 'partnerships',
                'events', 'community', 'careers'
            }
            
            if any(prefix in email_local for prefix in generic_prefixes):
                return "Hello team"
            else:
                return "Hello"
        
        # Clean up the name
        name = contact.name.strip()
        if name.lower() == 'unknown':
            return "Hello"
        
        return name
    
    def has_recent_outreach_to_domain(self, domain: str, days: int = 7) -> bool:
        """Check if we've contacted this domain recently"""
        cutoff_date = datetime.now() - timedelta(days=days)
        
        for log_entry in self.outreach_log:
            if (log_entry.get('status') == 'sent' and 
                log_entry.get('timestamp')):
                try:
                    log_date = datetime.fromisoformat(log_entry['timestamp'])
                    if log_date > cutoff_date:
                        email = log_entry.get('email', '')
                        if domain == self.get_domain_from_email(email):
                            return True
                except (ValueError, TypeError):
                    continue
        
        return False
    
    def run_outreach_phase(self, interactive: bool = True):
        """Run the outreach phase - generate pending messages with improved filtering"""
        logger.info("📧 Starting outreach phase...")
        
        # Filter contacts for outreach
        eligible_contacts = []
        seen_emails = set()
        seen_domains = set()
        
        for contact in self.contacts:
            # Skip test/honeypot emails
            if self.is_test_email(contact.email):
                logger.info(f"Skipping {contact.email} - test/honeypot email")
                continue
            
            # Skip if opted out
            if self.is_opted_out(contact.email):
                logger.info(f"Skipping {contact.name} ({contact.email}) - opted out")
                continue
            
            # Skip duplicate emails in this batch
            if contact.email.lower() in seen_emails:
                logger.info(f"Skipping {contact.email} - duplicate in batch")
                continue
            
            # Skip if already contacted recently (within 30 days)
            if contact.last_contact:
                last_contact = datetime.fromisoformat(contact.last_contact)
                if datetime.now() - last_contact < timedelta(days=30):
                    logger.info(f"Skipping {contact.email} - contacted recently")
                    continue
            
            # Skip if exceeded max outreach attempts
            if contact.outreach_count >= self.max_outreach_per_target:
                logger.info(f"Skipping {contact.email} - max attempts reached")
                continue
            
            # Check domain limits
            domain = self.get_domain_from_email(contact.email)
            
            # Skip if we've already selected a contact from this domain in this batch
            if domain in seen_domains:
                logger.info(f"Skipping {contact.email} - domain {domain} already selected for batch")
                continue
            
            # Skip if we've contacted this domain recently (within 7 days)
            if self.has_recent_outreach_to_domain(domain, days=7):
                logger.info(f"Skipping {contact.email} - domain {domain} contacted recently")
                continue
            
            eligible_contacts.append(contact)
            seen_emails.add(contact.email.lower())
            seen_domains.add(domain)
        
        logger.info(f"🔍 Filtered to {len(eligible_contacts)} eligible contacts from {len(self.contacts)} total")
        
        # Group by organization to limit outreach per target
        org_contacts = {}
        for contact in eligible_contacts:
            if contact.organization not in org_contacts:
                org_contacts[contact.organization] = []
            org_contacts[contact.organization].append(contact)
        
        # Generate pending outreach messages
        new_pending = []
        batch_emails = set()
        batch_domains = set()
        
        for org, contacts in org_contacts.items():
            # Limit contacts per organization (but respect domain limits)
            available_contacts = []
            for contact in contacts:
                domain = self.get_domain_from_email(contact.email)
                if (contact.email.lower() not in batch_emails and 
                    domain not in batch_domains):
                    available_contacts.append(contact)
            
            if not available_contacts:
                continue
                
            max_contacts = min(len(available_contacts), random.randint(self.min_outreach_per_target, self.max_outreach_per_target))
            selected_contacts = random.sample(available_contacts, max_contacts)
            
            logger.info(f"Preparing outreach to {len(selected_contacts)} contacts from {org}")
            
            for contact in selected_contacts:
                try:
                    # Double-check we haven't added this email or domain already
                    domain = self.get_domain_from_email(contact.email)
                    if (contact.email.lower() in batch_emails or 
                        domain in batch_domains):
                        continue
                    
                    # Generate personalized message
                    message = self.generate_outreach_message(contact)
                    
                    # Create pending outreach
                    pending = PendingOutreach(
                        contact=contact,
                        message=message,
                        timestamp=datetime.now().isoformat()
                    )
                    
                    new_pending.append(pending)
                    batch_emails.add(contact.email.lower())
                    batch_domains.add(domain)
                    
                except Exception as e:
                    logger.error(f"Error generating message for {contact.email}: {e}")
        
        # Add to pending outreach
        self.pending_outreach.extend(new_pending)
        self.save_pending_outreach()
        
        logger.info(f"✅ Generated {len(new_pending)} pending outreach messages.")
        logger.info(f"📊 Unique emails: {len(batch_emails)}, Unique domains: {len(batch_domains)}")
        
        # Run interactive session if enabled
        if interactive and self.config.get('cli', {}).get('interactive_mode', True):
            self.interactive_outreach_session(self.pending_outreach)
        
        return len(new_pending)
    
    def send_all_pending(self):
        """Send all pending outreach messages (for non-interactive mode)"""
        if not self.pending_outreach:
            logger.info("No pending messages to send")
            return 0
        
        sent_count = 0
        failed_count = 0
        
        for pending in self.pending_outreach[:]:  # Copy list to avoid modification issues
            try:
                if self.send_outreach_message(pending.contact, pending.message):
                    sent_count += 1
                    self.pending_outreach.remove(pending)
                else:
                    failed_count += 1
                
                # Rate limiting between sends
                time.sleep(random.uniform(*self.rate_limit_delay))
                
            except Exception as e:
                logger.error(f"Error sending to {pending.contact.email}: {e}")
                failed_count += 1
        
        # Save updated pending list
        self.save_pending_outreach()
        
        logger.info(f"✅ Sent {sent_count} messages, {failed_count} failed")
        return sent_count

    def generate_analytics_report(self):
        """Generate analytics and performance report"""
        logger.info("📊 Generating analytics report...")
        
        analytics = {
            'timestamp': datetime.now().isoformat(),
            'total_targets': len(self.targets),
            'total_contacts': len(self.contacts),
            'total_outreach_sent': len([log for log in self.outreach_log if log['status'] == 'sent']),
            'total_outreach_failed': len([log for log in self.outreach_log if log['status'] == 'failed']),
            'total_opt_outs': len(self.opt_outs.get('opt_outs', [])),
            'contacts_by_category': {},
            'outreach_by_organization': {},
            'opt_outs_by_reason': {},
            'response_rate': 0,
            'top_performing_templates': {},
            'recent_activity': []
        }
        
        # Contacts by category
        for contact in self.contacts:
            category = contact.category
            if category not in analytics['contacts_by_category']:
                analytics['contacts_by_category'][category] = 0
            analytics['contacts_by_category'][category] += 1
        
        # Outreach by organization
        for log in self.outreach_log:
            org = log['organization']
            if org not in analytics['outreach_by_organization']:
                analytics['outreach_by_organization'][org] = {'sent': 0, 'failed': 0}
            analytics['outreach_by_organization'][org][log['status']] += 1
        
        # Opt-outs by reason
        for opt_out in self.opt_outs.get('opt_outs', []):
            reason = opt_out.get('reason', 'no_reason')
            if not reason:
                reason = 'no_reason'
            if reason not in analytics['opt_outs_by_reason']:
                analytics['opt_outs_by_reason'][reason] = 0
            analytics['opt_outs_by_reason'][reason] += 1
        
        # Template performance
        template_stats = {}
        for log in self.outreach_log:
            template = log.get('template_used', 'unknown')
            if template not in template_stats:
                template_stats[template] = {'sent': 0, 'responses': 0}
            template_stats[template]['sent'] += 1
        
        analytics['top_performing_templates'] = template_stats
        
        # Response rate calculation
        total_sent = analytics['total_outreach_sent']
        total_responses = len([c for c in self.contacts if c.response_received])
        analytics['response_rate'] = (total_responses / total_sent * 100) if total_sent > 0 else 0
        
        # Recent activity (last 7 days)
        recent_cutoff = datetime.now() - timedelta(days=7)
        analytics['recent_activity'] = [
            log for log in self.outreach_log 
            if datetime.fromisoformat(log['timestamp']) > recent_cutoff
        ]
        
        # Save analytics
        with open(self.analytics_file, 'w') as f:
            json.dump(analytics, f, indent=2)
        
        # Print summary
        print("\n" + "="*60)
        print("📊 STARTUP OUTREACH ANALYTICS REPORT")
        print("="*60)
        print(f"📋 Total Targets: {analytics['total_targets']}")
        print(f"👥 Total Contacts: {analytics['total_contacts']}")
        print(f"✅ Messages Sent: {analytics['total_outreach_sent']}")
        print(f"❌ Failed Messages: {analytics['total_outreach_failed']}")
        print(f"� Opt-outs: {analytics['total_opt_outs']}")
        print(f"�📈 Response Rate: {analytics['response_rate']:.1f}%")
        print(f"🕒 Recent Activity (7 days): {len(analytics['recent_activity'])} actions")
        
        print("\n📊 Contacts by Category:")
        for category, count in analytics['contacts_by_category'].items():
            print(f"  • {category.title()}: {count}")
        
        print("\n🏢 Top Organizations by Outreach:")
        org_totals = [(org, data['sent']) for org, data in analytics['outreach_by_organization'].items()]
        org_totals.sort(key=lambda x: x[1], reverse=True)
        for org, count in org_totals[:10]:
            print(f"  • {org}: {count} messages")
        
        if analytics['total_opt_outs'] > 0:
            print("\n🚫 Opt-outs by Reason:")
            for reason, count in analytics['opt_outs_by_reason'].items():
                print(f"  • {reason.replace('_', ' ').title()}: {count}")
        
        print("="*60)
        
        logger.info("✅ Analytics report generated")

def main():
    """Main function to handle command line arguments"""
    parser = argparse.ArgumentParser(description='Startup Outreach Automation')
    parser.add_argument('--mode', choices=['discover', 'outreach', 'review', 'send', 'notify', 'report', 'analytics', 'opt-out', 'full'], 
                       default='full', help='Operation mode')
    parser.add_argument('--dry-run', action='store_true', 
                       help='Run without actually sending emails')
    parser.add_argument('--non-interactive', action='store_true',
                       help='Run in non-interactive mode (auto-send all messages)')
    parser.add_argument('--auto-send', action='store_true',
                       help='Auto-send all generated messages without any review (combines outreach + send)')
    parser.add_argument('--batch-mode', action='store_true',
                       help='Use batch approval mode for reviewing messages')
    parser.add_argument('--email', type=str,
                       help='Email address for opt-out mode')
    parser.add_argument('--reason', type=str, default='',
                       help='Reason for opt-out')
    
    args = parser.parse_args()
    
    # Initialize the bot
    bot = StartupOutreachBot()
    
    try:
        if args.mode == 'opt-out':
            if not args.email:
                print("❌ Email address required for opt-out mode")
                print("Usage: python startup_outreach.py --mode opt-out --email user@example.com --reason 'reason'")
                return
            
            success = bot.add_opt_out(args.email, args.reason, source='manual')
            if success:
                print(f"✅ Successfully opted out {args.email}")
            else:
                print(f"ℹ️  {args.email} was already opted out")
            return
        
        if args.mode in ['discover', 'full']:
            bot.run_discovery_phase()
        
        if args.mode in ['outreach', 'full']:
            # Determine interaction mode
            if args.auto_send:
                # Generate messages and auto-send without review
                bot.run_outreach_phase(interactive=False)
                bot.send_all_pending()
                print("✅ Auto-send mode: Generated and sent all messages")
            elif args.non_interactive:
                # Generate messages but don't start interactive session
                bot.run_outreach_phase(interactive=False)
            elif args.batch_mode:
                # Force batch mode by temporarily modifying behavior
                bot.run_outreach_phase(interactive=True)
            else:
                # Normal interactive mode (default)
                interactive = not args.dry_run
                bot.run_outreach_phase(interactive=interactive)
        
        if args.mode == 'review':
            # Load pending outreach and start interactive session
            bot.load_pending_outreach()
            if bot.pending_outreach:
                bot.interactive_outreach_session(bot.pending_outreach)
            else:
                print("No pending outreach messages to review")
        
        if args.mode == 'send':
            # Send all pending messages without review
            bot.load_pending_outreach()
            bot.send_all_pending()
        
        if args.mode == 'notify':
            # Send daily notification (legacy)
            bot.send_daily_notification()
        
        if args.mode == 'analytics':
            # Send comprehensive daily analytics report
            bot.send_daily_analytics_report()
        
        if args.mode in ['report', 'full']:
            bot.generate_analytics_report()
            
    except KeyboardInterrupt:
        logger.info("Operation cancelled by user")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise

if __name__ == "__main__":
    main()

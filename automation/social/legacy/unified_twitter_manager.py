# Unified Twitter/Social Media Management System
# Consolidates automation from Ads/, marketing/, and radical/ folders

import os
import sys
import time
import random
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from pathlib import Path

# Twitter API imports (OAuth1Session from existing scripts)
try:
    from requests_oauthlib import OAuth1Session
    import requests
except ImportError:
    print("Missing required packages. Install with: pip install requests requests-oauthlib")
    sys.exit(1)

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

class UnifiedTwitterManager:
    """
    Unified Twitter automation system for all Buildly brands
    Consolidates functionality from:
    - Ads/tweet_scheduler.py (Buildly ads)
    - marketing/the_real_tweet.py (General marketing)  
    - radical/joke_tweet.py (Radical Therapy humor)
    """
    
    def __init__(self, config_path: Optional[str] = None):
        self.project_root = PROJECT_ROOT
        self.config_dir = self.project_root / 'config'
        
        # Set up logging
        self.setup_logging()
        
        # Load configuration
        self.config = self.load_config()
        
        # Load credentials
        self.credentials = self.load_credentials()
        
        # Initialize Twitter session
        self.twitter_session = self.initialize_twitter()
        
        # Load content for all brands
        self.content_library = self.load_content_library()
        
    def setup_logging(self):
        """Set up logging for social media automation"""
        log_dir = self.project_root / 'logs'
        log_dir.mkdir(exist_ok=True)
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_dir / 'social_automation.log'),
                logging.StreamHandler()
            ]
        )
        
        self.logger = logging.getLogger('UnifiedTwitterManager')
        
    def load_credentials(self) -> Dict[str, str]:
        """Load Twitter API credentials"""
        # Load from environment variables
        return {
            'consumer_key': os.environ.get('TWITTER_CONSUMER_KEY', ''),
            'consumer_secret': os.environ.get('TWITTER_CONSUMER_SECRET', ''),
            'bearer_token': os.environ.get('TWITTER_BEARER_TOKEN', ''),
            'access_token': os.environ.get('TWITTER_ACCESS_TOKEN', ''),
            'access_token_secret': os.environ.get('TWITTER_ACCESS_TOKEN_SECRET', '')
        }
        
    def initialize_twitter(self) -> OAuth1Session:
        """Initialize Twitter OAuth session"""
        try:
            oauth = OAuth1Session(
                self.credentials['consumer_key'],
                client_secret=self.credentials['consumer_secret'],
                resource_owner_key=self.credentials['access_token'],
                resource_owner_secret=self.credentials['access_token_secret']
            )
            
            self.logger.info("Twitter OAuth session initialized")
            return oauth
            
        except Exception as e:
            self.logger.error(f"Failed to initialize Twitter session: {e}")
            return None
    
    def load_content_library(self) -> Dict[str, List[str]]:
        """Load content for all brands"""
        content = {
            'buildly': [
                "Elevate Your Software Development with #Buildly Insights & Our Partner Marketplace 🚀 Join our private beta today! https://insights.buildly.io",
                "Transform your development journey with #Buildly - AI-driven project management & expert development community. Discover more https://insights.buildly.io",
                "#BuildlyMarketplace connects you to expert agencies for efficient software solutions. Explore our Bounty Hunter feature! https://insights.buildly.io",
                "Streamline your software projects with #Buildly Insights and access quick fixes through our Partner Marketplace. Join now! https://insights.buildly.io",
                "Innovate with #Buildly's AI-Based Idea Translation & Product Roadmaps. Connect with experts on our marketplace. https://insights.buildly.io",
                "Discover how #Buildly's cloud-based solutions can accelerate your startup's growth. Explore our features today! https://insights.buildly.io",
                "Maximize productivity with #Buildly Insights. AI-powered project management for modern teams. Learn more https://insights.buildly.io",
                "Join the #Buildly revolution! Seamless project management and a vibrant expert community await. https://insights.buildly.io",
                "Revolutionize your software development with #Buildly. Cutting-edge tools for startups and enterprises. https://insights.buildly.io",
                "Efficiency meets innovation with #Buildly. Dive into our AI-driven platform and marketplace today! https://insights.buildly.io"
            ],
            
            'foundry': [
                "🚀 The Foundry is transforming startup support with our equity-free incubator model. Join the global startup community! #StartupLife #Entrepreneurship",
                "Breaking barriers in the startup world. The Foundry provides mentorship, resources, and connections without taking equity. #StartupSupport",
                "From idea to launch: The Foundry accelerates your startup journey. Connect with global mentors and investors. https://www.firstcityfoundry.com",
                "🌟 Equity-free startup acceleration. The Foundry believes in keeping your ownership while providing world-class support. #StartupFounder"
            ],
            
            'open_build': [
                "Building the future together 🔧 Open Build connects developers, creators, and innovators in the open source community. #OpenSource #BuildTogether",
                "Community-driven development at its finest. Join Open Build and contribute to projects that matter. #OpenSource #DevCommunity",
                "🌟 Open Build: Where collaboration meets innovation. Discover projects, contribute code, and grow with the community.",
                "The power of open source lies in community. Open Build amplifies that power. Join us! #OpenSource #Community"
            ],
            
            'radical_therapy': [
                "Why do programmers prefer dark mode? Because light attracts bugs! 🐛💡 #ProgrammingHumor #RadicalTherapy",
                "A SQL query walks into a bar, walks up to two tables and asks... 'Can I join you?' 📊😄 #TechHumor #DatabaseJokes",
                "How many programmers does it take to change a light bulb? None. It's a hardware problem. 💡⚡ #ProgrammingJokes",
                "Why do Java developers wear glasses? Because they don't see sharp! 👓☕ #JavaJokes #TechHumor",
                "There are only 10 types of people in the world: those who understand binary and those who don't. 01001000 01101001! #BinaryJokes"
            ]
        }
        
        self.logger.info(f"Loaded content for {len(content)} brands")
        return content
    
    def post_scheduled_content(self, brand: str, content_type: str = 'random') -> bool:
        """Post scheduled content for a specific brand"""
        try:
            if brand not in self.content_library:
                self.logger.error(f"No content library found for brand: {brand}")
                return False
            
            # Select content
            content = random.choice(self.content_library[brand])
            
            # Post to Twitter
            success = self.post_tweet(content, brand)
            
            if success:
                self.logger.info(f"Successfully posted {brand} content: {content[:50]}...")
                return True
            else:
                self.logger.error(f"Failed to post {brand} content")
                return False
                
        except Exception as e:
            self.logger.error(f"Error posting content for {brand}: {e}")
            return False
    
    def post_tweet(self, content: str, brand: str) -> bool:
        """Post a tweet using Twitter API"""
        try:
            if not self.twitter_session:
                self.logger.error("Twitter session not initialized")
                return False
            
            # Twitter API v2 endpoint for posting tweets
            url = "https://api.twitter.com/2/tweets"
            
            payload = {
                "text": content
            }
            
            response = self.twitter_session.post(url, json=payload)
            
            if response.status_code == 201:
                tweet_data = response.json()
                tweet_id = tweet_data.get('data', {}).get('id', 'unknown')
                self.logger.info(f"Tweet posted successfully for {brand}. ID: {tweet_id}")
                return True
            else:
                self.logger.error(f"Twitter API error: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error posting tweet: {e}")
            return False
    
    def run_daily_social_automation(self):
        """Run daily social media automation for all brands"""
        self.logger.info("🚀 Starting daily social media automation")
        
        brands_to_post = ['buildly', 'foundry', 'open_build', 'radical_therapy']
        
        for brand in brands_to_post:
            try:
                # Add delay between posts to respect rate limits
                if brand != brands_to_post[0]:  # Skip delay for first brand
                    delay = random.randint(300, 600)  # 5-10 minutes between brands
                    self.logger.info(f"Waiting {delay} seconds before posting for {brand}")
                    time.sleep(delay)
                
                success = self.post_scheduled_content(brand)
                
                if success:
                    self.logger.info(f"✅ {brand} social media automation completed")
                else:
                    self.logger.error(f"❌ {brand} social media automation failed")
                    
            except Exception as e:
                self.logger.error(f"Error in social automation for {brand}: {e}")
        
        self.logger.info("📱 Daily social media automation completed")
    
    def get_engagement_stats(self) -> Dict[str, Any]:
        """Get engagement statistics for recent posts"""
        # TODO: Implement engagement tracking
        # - Fetch recent tweet metrics
        # - Track likes, retweets, replies
        # - Return performance data
        return {
            'last_updated': datetime.now().isoformat(),
            'total_posts_today': 0,
            'engagement_rate': 0.0,
            'top_performing_content': []
        }
    
    def load_config(self) -> Dict[str, Any]:
        """Load configuration (placeholder)"""
        # TODO: Load from config files
        return {
            'rate_limits': {
                'posts_per_hour': 12,
                'posts_per_day': 100
            }
        }

def main():
    """Main entry point for social media automation"""
    manager = UnifiedTwitterManager()
    
    print("🎛️ Unified Twitter Manager")
    print("Choose an option:")
    print("1. Run daily automation for all brands")
    print("2. Post content for specific brand")
    print("3. Check engagement stats")
    print("4. Test Twitter connection")
    
    choice = input("Enter your choice (1-4): ")
    
    if choice == '1':
        manager.run_daily_social_automation()
    elif choice == '2':
        brand = input("Enter brand (buildly/foundry/open_build/radical_therapy): ")
        manager.post_scheduled_content(brand)
    elif choice == '3':
        stats = manager.get_engagement_stats()
        print(f"Engagement Stats: {stats}")
    elif choice == '4':
        if manager.twitter_session:
            print("✅ Twitter connection successful")
        else:
            print("❌ Twitter connection failed")
    else:
        print("Invalid choice")

if __name__ == "__main__":
    main()
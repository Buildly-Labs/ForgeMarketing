# ForgeMarketing - Main Controller
# Central orchestration for multi-brand marketing operations

import os
import sys
import logging
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List
import yaml
import json

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

class MarketingController:
    """
    Central controller for ForgeMarketing operations.
    Coordinates content planning, scheduling, and tracking across brands.
    """
    
    def __init__(self):
        self.project_root = PROJECT_ROOT
        self.config_dir = self.project_root / 'config'
        self.data_dir = self.project_root / 'data'
        self.logs_dir = self.project_root / 'logs'
        
        # Ensure directories exist
        self.logs_dir.mkdir(exist_ok=True)
        
        # Set up logging
        self.setup_logging()
        
        # Load configuration
        self.config = self.load_configuration()
        
        # Initialize modules (will be implemented)
        self.modules = {}
        
    def setup_logging(self):
        """Set up comprehensive logging system"""
        log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        
        # Main log file
        logging.basicConfig(
            level=logging.INFO,
            format=log_format,
            handlers=[
                logging.FileHandler(self.logs_dir / 'dashboard.log'),
                logging.StreamHandler(sys.stdout)
            ]
        )
        
        self.logger = logging.getLogger('MarketingController')
        self.logger.info("Marketing Controller initialized")
        
    def load_configuration(self) -> Dict[str, Any]:
        """Load all configuration files"""
        try:
            config = {}
            
            # Load brand configuration
            brands_file = self.config_dir / 'brands.yaml'
            if brands_file.exists():
                with open(brands_file, 'r') as f:
                    config['brands'] = yaml.safe_load(f)
            
            # Load schedules
            schedules_file = self.config_dir / 'schedules.yaml'
            if schedules_file.exists():
                with open(schedules_file, 'r') as f:
                    config['schedules'] = yaml.safe_load(f)
            
            # Load credentials (encrypted)
            credentials_file = self.config_dir / 'credentials.yaml'
            if credentials_file.exists():
                with open(credentials_file, 'r') as f:
                    config['credentials'] = yaml.safe_load(f)
            
            self.logger.info("Configuration loaded successfully")
            return config
            
        except Exception as e:
            self.logger.error(f"Error loading configuration: {e}")
            return {}
    
    async def run_daily_automation(self):
        """Run complete daily automation workflow"""
        self.logger.info("🚀 Starting daily automation workflow")
        
        try:
            # Phase 1: Social Media Automation
            await self.run_social_automation()
            
            # Phase 2: Outreach Campaigns  
            await self.run_outreach_automation()
            
            # Phase 3: Content Generation
            await self.run_content_automation()
            
            # Phase 4: Analytics Collection
            await self.run_analytics_collection()
            
            # Phase 5: Generate Reports
            await self.generate_daily_reports()
            
            self.logger.info("✅ Daily automation workflow completed successfully")
            
        except Exception as e:
            self.logger.error(f"❌ Daily automation failed: {e}")
            await self.send_error_notification(e)
    
    async def run_social_automation(self):
        """Social automation is handled by social_media_manager.py/Ads/*
        This controller currently provides scheduling status only.
        """
        self.logger.info("Social automation integration not yet wired in MarketingController")

    async def run_outreach_automation(self):
        """Outreach automation is handled by multi_brand_outreach.py/run_unified_outreach.py"""
        self.logger.info("Outreach automation integration not yet wired in MarketingController")

    async def run_content_automation(self):
        """Content automation is handled by article_publisher.py and Ads/ modules"""
        self.logger.info("Content automation integration not yet wired in MarketingController")

    async def run_analytics_collection(self):
        """Analytics collection is handled by automation/analytics/* and unified_analytics.py"""
        self.logger.info("Analytics collection integration not yet wired in MarketingController")

    async def generate_daily_reports(self):
        """Report generation is not yet implemented in MarketingController"""
        self.logger.info("Daily report generation integration not yet wired in MarketingController")

    async def send_error_notification(self, error: Exception):
        """Error notification is not yet implemented"""
        self.logger.info(f"send_error_notification not implemented; original error: {error}")
    
    def get_system_status(self) -> Dict[str, Any]:
        """Get current system status"""
        return {
            'timestamp': datetime.now().isoformat(),
            'project_root': str(self.project_root),
            'config_loaded': bool(self.config),
            'brands_configured': list(self.config.get('brands', {}).keys()),
            'logs_directory': str(self.logs_dir),
            'data_directory': str(self.data_dir)
        }

def main():
    """Main entry point for marketing automation"""
    controller = MarketingController()
    
    # Print system status
    status = controller.get_system_status()
    print("🎛️ Marketing Automation System Status:")
    print(f"   Project Root: {status['project_root']}")
    print(f"   Config Loaded: {status['config_loaded']}")
    print(f"   Brands: {status['brands_configured']}")
    print(f"   Timestamp: {status['timestamp']}")
    
    # Run daily automation
    asyncio.run(controller.run_daily_automation())

if __name__ == "__main__":
    main()
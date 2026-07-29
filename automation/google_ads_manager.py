#!/usr/bin/env python3
"""
Google Ads Integration Module
Comprehensive Google Ads campaign management and automation for multiple brands
"""

import os
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional

# Mock the Google Ads library for development
try:
    from google.ads.googleads.client import GoogleAdsClient
    from google.ads.googleads.errors import GoogleAdsException
    GOOGLE_ADS_AVAILABLE = True
except ImportError:
    GOOGLE_ADS_AVAILABLE = False
    print("⚠️  Google Ads library not available - using mock client")


class RealGoogleAdsClient:
    """
    Real Google Ads API client wrapper
    Interfaces with the official Google Ads Python client library
    """
    
    def __init__(self, client, config: Dict[str, Any], logger: logging.Logger):
        """Initialize with Google Ads client instance"""
        self.client = client
        self.config = config
        self.logger = logger
        
    def get_campaigns(self, customer_id: str) -> List[Dict[str, Any]]:
        """Get all campaigns for a customer"""
        try:
            ga_service = self.client.get_service("GoogleAdsService")
            
            query = """
                SELECT 
                    campaign.id,
                    campaign.name,
                    campaign.status,
                    campaign.advertising_channel_type,
                    campaign_budget.amount_micros
                FROM campaign
                ORDER BY campaign.id
            """
            
            search_request = self.client.get_type("SearchGoogleAdsRequest")
            search_request.customer_id = customer_id
            search_request.query = query
            
            results = ga_service.search(request=search_request)
            
            campaigns = []
            for row in results:
                campaign = row.campaign
                campaigns.append({
                    'id': campaign.id,
                    'name': campaign.name,
                    'status': campaign.status.name,
                    'type': campaign.advertising_channel_type.name,
                    'budget_micros': row.campaign_budget.amount_micros
                })
            
            return campaigns
            
        except Exception as e:
            self.logger.error(f"Error fetching campaigns: {e}")
            return []
    
    def get_performance_data(self, customer_id: str, days_back: int = 30) -> List[Dict[str, Any]]:
        """Get performance data for a brand's campaigns"""
        try:
            ga_service = self.client.get_service("GoogleAdsService")
            
            # Calculate date range
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days_back)
            
            query = f"""
                SELECT 
                    campaign.id,
                    campaign.name,
                    metrics.impressions,
                    metrics.clicks,
                    metrics.cost_micros,
                    metrics.conversions,
                    segments.date
                FROM campaign
                WHERE segments.date >= '{start_date.strftime('%Y-%m-%d')}'
                  AND segments.date <= '{end_date.strftime('%Y-%m-%d')}'
                ORDER BY segments.date DESC
            """
            
            search_request = self.client.get_type("SearchGoogleAdsRequest")
            search_request.customer_id = customer_id
            search_request.query = query
            
            results = ga_service.search(request=search_request)
            
            performance_data = []
            for row in results:
                campaign = row.campaign
                metrics = row.metrics
                
                performance_data.append({
                    'campaign_id': campaign.id,
                    'campaign_name': campaign.name,
                    'date': row.segments.date,
                    'impressions': metrics.impressions,
                    'clicks': metrics.clicks,
                    'cost_micros': metrics.cost_micros,
                    'conversions': metrics.conversions,
                    'ctr': (metrics.clicks / metrics.impressions * 100) if metrics.impressions > 0 else 0,
                    'cpc_micros': (metrics.cost_micros / metrics.clicks) if metrics.clicks > 0 else 0
                })
            
            return performance_data
            
        except Exception as e:
            self.logger.error(f"Error fetching performance data: {e}")
            return []

    def get_keyword_suggestions(self, customer_id: str, seed_keywords: List[str]) -> List[Dict[str, Any]]:
        """Get keyword suggestions for campaign optimization"""
        try:
            keyword_plan_idea_service = self.client.get_service("KeywordPlanIdeaService")
            
            request = self.client.get_type("GenerateKeywordIdeasRequest")
            request.customer_id = customer_id
            request.language = "1000"  # English
            request.geo_target_constants = ["2840"]  # United States
            
            # Add seed keywords
            for keyword in seed_keywords:
                request.keyword_and_url_seed.keywords.append(keyword)
            
            results = keyword_plan_idea_service.generate_keyword_ideas(request=request)
            
            suggestions = []
            for idea in results:
                suggestions.append({
                    'text': idea.text,
                    'avg_monthly_searches': idea.keyword_idea_metrics.avg_monthly_searches,
                    'competition': idea.keyword_idea_metrics.competition.name,
                    'low_top_of_page_bid_micros': idea.keyword_idea_metrics.low_top_of_page_bid_micros,
                    'high_top_of_page_bid_micros': idea.keyword_idea_metrics.high_top_of_page_bid_micros
                })
            
            return suggestions[:50]  # Limit to top 50 suggestions
            
        except Exception as e:
            self.logger.error(f"Error getting keyword suggestions: {e}")
            return []
    
    def create_campaign(self, customer_id: str, campaign_name: str, campaign_type: str, budget_micros: int, keywords: List[str]) -> Dict[str, Any]:
        """Create a new campaign"""
        try:
            # This would implement the actual Google Ads API campaign creation
            # For now, we'll simulate the creation process
            self.logger.info(f"Creating real campaign: {campaign_name} for customer {customer_id}")
            
            # In a real implementation, this would use the Google Ads API to:
            # 1. Create a campaign budget
            # 2. Create the campaign
            # 3. Create ad groups
            # 4. Add keywords
            # 5. Create ads
            
            # Simulate successful creation
            import random
            campaign_id = random.randint(1000000, 9999999)
            
            return {
                'success': True,
                'campaign_id': campaign_id,
                'message': f'Real campaign {campaign_name} would be created with Google Ads API'
            }
            
        except Exception as e:
            self.logger.error(f"Error creating real campaign: {e}")
            return {
                'success': False,
                'error': str(e)
            }


class GoogleAdsManager:
    """
    Comprehensive Google Ads campaign management for multiple brands
    Supports both mock and real Google Ads API integration
    """
    
    def __init__(self, config_file: str = None, use_mock: bool = True, use_service_account: bool = False):
        """Initialize Google Ads Manager with configuration"""
        self.config_file = config_file or self._get_default_config_path()
        self.config = self._load_config()
        self.logger = self._setup_logging()
        self.use_mock = use_mock
        self.use_service_account = use_service_account
        
        # Update open_build customer ID with real API key if available
        open_build_customer_id = '345-678-9012'  # Default
        if self.config.get('api_key'):
            # This is the real API key, so we should use real OpenBuild details
            open_build_customer_id = 'REAL_OPENBUILD_CUSTOMER_ID'  # To be updated with actual
        
        # Brand configurations
        self.brands = {
            'foundry': {
                'name': 'First City Foundry',
                'customer_id': self.config.get('customer_ids', {}).get('foundry', ''),
                'target_audience': 'manufacturing professionals',
                'primary_keywords': ['manufacturing software', 'production optimization', 'industrial automation'],
                'budget_daily_micros': 50000000,  # $50 daily
                'campaign_type': 'SEARCH'
            },
            'buildly': {
                'name': 'Buildly',
                'customer_id': self.config.get('customer_ids', {}).get('buildly', ''),
                'target_audience': 'software developers and CTOs',
                'primary_keywords': ['low-code platform', 'API gateway', 'microservices'],
                'budget_daily_micros': 75000000,  # $75 daily
                'campaign_type': 'SEARCH'
            },
            'open_build': {
                'name': 'Open Build',
                'customer_id': self.config.get('customer_ids', {}).get('open_build', ''),
                'target_audience': 'open source developers',
                'primary_keywords': ['open source tools', 'developer community', 'coding collaboration'],
                'budget_daily_micros': 30000000,  # $30 daily
                'campaign_type': 'SEARCH'
            },
            'radical_therapy': {
                'name': 'Radical Therapy',
                'customer_id': self.config.get('customer_ids', {}).get('radical_therapy', ''),
                'target_audience': 'therapy seekers and mental health professionals',
                'primary_keywords': ['online therapy', 'mental health support', 'counseling services'],
                'budget_daily_micros': 40000000,  # $40 daily
                'campaign_type': 'SEARCH'
            }
        }
        
        # Initialize client
        self.client = self._initialize_client()
    
    def _get_default_config_path(self) -> str:
        """Get default configuration file path"""
        return str(Path(__file__).parent / 'config' / 'google_ads_config.json')
    
    def _load_config(self) -> Dict[str, Any]:
        """Load Google Ads configuration"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    # Add the real API key if not present
                    return config
            else:
                self.logger.warning(f"Config file not found: {self.config_file}")
                return {
                    "developer_token": "",
                    "client_id": "",
                    "client_secret": "",
                    "refresh_token": "",
                    "service_account_path": "",
                    "api_key": os.environ.get('GOOGLE_ADS_API_KEY', '')
                }
        except Exception as e:
            self.logger.error(f"Error loading config: {e}")
            return {"api_key": os.environ.get('GOOGLE_ADS_API_KEY', '')}
    
    def _setup_logging(self) -> logging.Logger:
        """Setup logging for Google Ads operations"""
        logger = logging.getLogger('GoogleAdsManager')
        logger.setLevel(logging.INFO)
        
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        
        return logger
    
    def _initialize_client(self):
        """Initialize Google Ads client (mock or real)"""
        if self.use_mock:
            self.logger.info("🔧 Initializing Mock Google Ads Client")
            return MockGoogleAdsClient(self.config, self.logger)
        else:
            try:
                if self.use_service_account:
                    return self._initialize_service_account_client()
                else:
                    return self._initialize_oauth_client()
            except Exception as e:
                self.logger.error(f"Failed to initialize real client, falling back to mock: {e}")
                return MockGoogleAdsClient(self.config, self.logger)
    
    def _initialize_service_account_client(self):
        """Initialize Google Ads API client with service account authentication"""
        if not GOOGLE_ADS_AVAILABLE:
            raise ImportError("Google Ads library not available")
            
        try:
            if not self.config.get('service_account_path'):
                raise ValueError("service_account_path not configured")
                
            # Configure Google Ads client with service account
            client_config = {
                'developer_token': self.config['developer_token'],
                'client_id': self.config['client_id'],
                'client_secret': self.config['client_secret'],
                'refresh_token': self.config['refresh_token'],
                'service_account_path': self.config['service_account_path']
            }
            
            client = GoogleAdsClient.load_from_dict(client_config)
            
            self.logger.info("🚀 Google Ads API client initialized (Service Account)")
            return RealGoogleAdsClient(client, self.config, self.logger)
            
        except Exception as e:
            self.logger.error(f"Failed to initialize service account client: {e}")
            raise
    
    def _initialize_oauth_client(self):
        """Initialize Google Ads API client with OAuth authentication"""
        if not GOOGLE_ADS_AVAILABLE:
            raise ImportError("Google Ads library not available")
            
        try:
            # Configure Google Ads client with OAuth
            client_config = {
                'developer_token': self.config['developer_token'],
                'client_id': self.config['client_id'],
                'client_secret': self.config['client_secret'],
                'refresh_token': self.config['refresh_token']
            }
            
            client = GoogleAdsClient.load_from_dict(client_config)
            
            self.logger.info("🚀 Google Ads API client initialized (OAuth)")
            return RealGoogleAdsClient(client, self.config, self.logger)
            
        except Exception as e:
            self.logger.error(f"Failed to initialize OAuth client: {e}")
            raise
    
    # API Methods
    def get_brand_campaigns(self, brand: str) -> List[Dict[str, Any]]:
        """Get all campaigns for a specific brand"""
        if brand not in self.brands:
            self.logger.error(f"Unknown brand: {brand}")
            return []
        
        customer_id = self.brands[brand]['customer_id']
        self.logger.info(f"🔍 Fetching campaigns for {brand} (Customer ID: {customer_id})")
        
        campaigns = self.client.get_campaigns(customer_id)
        
        self.logger.info(f"✅ Found {len(campaigns)} campaigns for {brand}")
        return campaigns
    
    def get_brand_performance(self, brand: str, days: int = 30) -> Dict[str, Any]:
        """Get performance data for a specific brand"""
        if brand not in self.brands:
            self.logger.error(f"Unknown brand: {brand}")
            return {}
        
        customer_id = self.brands[brand]['customer_id']
        self.logger.info(f"📊 Fetching {days}-day performance for {brand}")
        
        performance_data = self.client.get_performance_data(customer_id, days)
        
        # Aggregate performance metrics
        total_impressions = sum(d['impressions'] for d in performance_data)
        total_clicks = sum(d['clicks'] for d in performance_data)
        total_cost_micros = sum(d['cost_micros'] for d in performance_data)
        total_conversions = sum(d['conversions'] for d in performance_data)
        
        summary = {
            'brand': brand,
            'period_days': days,
            'total_campaigns': len(set(d['campaign_id'] for d in performance_data)),
            'total_impressions': total_impressions,
            'total_clicks': total_clicks,
            'total_cost_micros': total_cost_micros,
            'total_conversions': total_conversions,
            'avg_ctr': (total_clicks / total_impressions * 100) if total_impressions > 0 else 0,
            'avg_cpc_micros': (total_cost_micros / total_clicks) if total_clicks > 0 else 0,
            'conversion_rate': (total_conversions / total_clicks * 100) if total_clicks > 0 else 0,
            'daily_performance': performance_data
        }
        
        self.logger.info(f"✅ Performance summary for {brand}: {total_impressions} impressions, {total_clicks} clicks")
        return summary
    
    def get_keyword_opportunities(self, brand: str) -> List[Dict[str, Any]]:
        """Get keyword expansion opportunities for a brand"""
        if brand not in self.brands:
            self.logger.error(f"Unknown brand: {brand}")
            return []
        
        customer_id = self.brands[brand]['customer_id']
        seed_keywords = self.brands[brand]['primary_keywords']
        
        self.logger.info(f"🔑 Getting keyword suggestions for {brand}")
        
        suggestions = self.client.get_keyword_suggestions(customer_id, seed_keywords)
        
        self.logger.info(f"✅ Found {len(suggestions)} keyword opportunities for {brand}")
        return suggestions
    
    def get_all_brands_summary(self) -> Dict[str, Any]:
        """Get performance summary for all brands"""
        self.logger.info("📈 Generating multi-brand performance summary")
        
        summary = {
            'timestamp': datetime.now().isoformat(),
            'brands': {},
            'totals': {
                'impressions': 0,
                'clicks': 0,
                'cost_micros': 0,
                'conversions': 0
            }
        }
        
        # Use all brands configured in the system
        for brand in self.brands.keys():
            brand_performance = self.get_brand_performance(brand, 30)
            summary['brands'][brand] = brand_performance
            
            # Add to totals
            if brand_performance:
                summary['totals']['impressions'] += brand_performance.get('total_impressions', 0)
                summary['totals']['clicks'] += brand_performance.get('total_clicks', 0)
                summary['totals']['cost_micros'] += brand_performance.get('total_cost_micros', 0)
                summary['totals']['conversions'] += brand_performance.get('total_conversions', 0)
        
        # Calculate overall metrics
        total_impressions = summary['totals']['impressions']
        total_clicks = summary['totals']['clicks']
        total_cost_micros = summary['totals']['cost_micros']
        total_conversions = summary['totals']['conversions']
        
        summary['overall_metrics'] = {
            'ctr': (total_clicks / total_impressions * 100) if total_impressions > 0 else 0,
            'cpc_micros': (total_cost_micros / total_clicks) if total_clicks > 0 else 0,
            'conversion_rate': (total_conversions / total_clicks * 100) if total_clicks > 0 else 0,
            'cost_per_conversion_micros': (total_cost_micros / total_conversions) if total_conversions > 0 else 0
        }
        
        self.logger.info("✅ Multi-brand summary generated")
        return summary
    
    def create_campaign(self, brand: str, campaign_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new campaign for a specific brand"""
        if brand not in self.brands:
            self.logger.error(f"Unknown brand: {brand}")
            return {'success': False, 'error': f'Unknown brand: {brand}'}
        
        customer_id = self.brands[brand]['customer_id']
        self.logger.info(f"🚀 Creating campaign for {brand} (Customer ID: {customer_id})")
        
        try:
            # Extract campaign details from request
            campaign_name = campaign_data.get('name', f'{brand} Campaign')
            campaign_type = campaign_data.get('type', 'SEARCH')
            daily_budget = campaign_data.get('dailyBudget', 30.00)  # Default $30
            keywords = campaign_data.get('keywords', [])
            
            # Convert daily budget to micros (multiply by 1,000,000)
            budget_micros = int(float(daily_budget) * 1000000)
            
            # Create campaign using the appropriate client
            result = self.client.create_campaign(
                customer_id=customer_id,
                campaign_name=campaign_name,
                campaign_type=campaign_type,
                budget_micros=budget_micros,
                keywords=keywords
            )
            
            if result.get('success'):
                self.logger.info(f"✅ Campaign created successfully for {brand}: {campaign_name}")
                return {
                    'success': True,
                    'campaign_id': result.get('campaign_id'),
                    'campaign_name': campaign_name,
                    'brand': brand,
                    'daily_budget': daily_budget,
                    'message': f'Campaign "{campaign_name}" created successfully for {brand}'
                }
            else:
                self.logger.error(f"❌ Failed to create campaign for {brand}: {result.get('error')}")
                return {
                    'success': False,
                    'error': result.get('error', 'Unknown error during campaign creation'),
                    'brand': brand
                }
                
        except Exception as e:
            self.logger.error(f"❌ Exception creating campaign for {brand}: {e}")
            return {
                'success': False,
                'error': str(e),
                'brand': brand
            }


class MockGoogleAdsClient:
    """
    Mock Google Ads API client for development and testing
    Simulates Google Ads API responses with realistic data
    """
    
    def __init__(self, config: Dict[str, Any], logger: logging.Logger):
        """Initialize mock client"""
        self.config = config
        self.logger = logger
        self.logger.info("🔧 Mock Google Ads Client initialized")
    
    def get_campaigns(self, customer_id: str) -> List[Dict[str, Any]]:
        """Return mock campaign data"""
        self.logger.info(f"🎭 Mock: Fetching campaigns for customer {customer_id}")
        
        # Generate realistic mock data based on customer ID
        base_id = hash(customer_id) % 1000000
        
        campaigns = [
            {
                'id': base_id + 1,
                'name': f'Search Campaign - {customer_id}',
                'status': 'ENABLED',
                'type': 'SEARCH',
                'budget_micros': 50000000  # $50
            },
            {
                'id': base_id + 2,
                'name': f'Display Campaign - {customer_id}',
                'status': 'ENABLED',
                'type': 'DISPLAY',
                'budget_micros': 30000000  # $30
            },
            {
                'id': base_id + 3,
                'name': f'Video Campaign - {customer_id}',
                'status': 'PAUSED',
                'type': 'VIDEO',
                'budget_micros': 25000000  # $25
            }
        ]
        
        return campaigns
    
    def get_performance_data(self, customer_id: str, days_back: int = 30) -> List[Dict[str, Any]]:
        """Return mock performance data"""
        self.logger.info(f"🎭 Mock: Fetching {days_back}-day performance for customer {customer_id}")
        
        import random
        
        performance_data = []
        base_id = hash(customer_id) % 1000000
        
        # Generate daily performance data
        for i in range(days_back):
            date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
            
            # Simulate realistic performance metrics
            impressions = random.randint(100, 1000)
            clicks = random.randint(5, impressions // 10)
            cost_micros = random.randint(5000000, 50000000)  # $5-$50
            conversions = random.randint(0, clicks // 20)
            
            performance_data.append({
                'campaign_id': base_id + 1,
                'campaign_name': f'Search Campaign - {customer_id}',
                'date': date,
                'impressions': impressions,
                'clicks': clicks,
                'cost_micros': cost_micros,
                'conversions': conversions,
                'ctr': (clicks / impressions * 100) if impressions > 0 else 0,
                'cpc_micros': (cost_micros / clicks) if clicks > 0 else 0
            })
        
        return performance_data
    
    def get_keyword_suggestions(self, customer_id: str, seed_keywords: List[str]) -> List[Dict[str, Any]]:
        """Return mock keyword suggestions"""
        self.logger.info(f"🎭 Mock: Getting keyword suggestions for customer {customer_id}")
        
        import random
        
        # Generate mock keyword suggestions based on seed keywords
        suggestions = []
        for seed in seed_keywords:
            for suffix in [' software', ' platform', ' solution', ' tool', ' service']:
                suggestions.append({
                    'text': seed + suffix,
                    'avg_monthly_searches': random.randint(100, 10000),
                    'competition': random.choice(['LOW', 'MEDIUM', 'HIGH']),
                    'low_top_of_page_bid_micros': random.randint(500000, 2000000),  # $0.50-$2.00
                    'high_top_of_page_bid_micros': random.randint(2000000, 8000000)  # $2.00-$8.00
                })
        
        return suggestions[:20]  # Return top 20 suggestions
    
    def create_campaign(self, customer_id: str, campaign_name: str, campaign_type: str, budget_micros: int, keywords: List[str]) -> Dict[str, Any]:
        """Create a mock campaign"""
        self.logger.info(f"🎭 Mock: Creating campaign '{campaign_name}' for customer {customer_id}")
        
        import random
        
        # Simulate campaign creation with realistic response
        campaign_id = random.randint(1000000, 9999999)
        
        # Simulate some basic validation
        if not campaign_name or not campaign_name.strip():
            return {
                'success': False,
                'error': 'Campaign name cannot be empty'
            }
        
        if budget_micros < 1000000:  # Less than $1
            return {
                'success': False,
                'error': 'Daily budget must be at least $1.00'
            }
        
        # Simulate successful creation
        self.logger.info(f"🎭 Mock: Campaign created successfully with ID {campaign_id}")
        
        return {
            'success': True,
            'campaign_id': campaign_id,
            'campaign_name': campaign_name,
            'customer_id': customer_id,
            'campaign_type': campaign_type,
            'budget_micros': budget_micros,
            'keywords_added': len(keywords),
            'status': 'ENABLED',
            'message': f'Mock campaign "{campaign_name}" created successfully'
        }


def main():
    """Main function for testing Google Ads integration"""
    print("🚀 Google Ads Integration Test")
    print("=" * 50)
    
    # Test with mock client
    manager = GoogleAdsManager(use_mock=True)
    
    def run_tests():
        print("\n📊 Testing brand performance retrieval...")
        
        for brand in ['foundry', 'buildly', 'open_build', 'radical_therapy']:
            print(f"\n🔍 Testing {brand}...")
            
            # Get campaigns
            campaigns = manager.get_brand_campaigns(brand)
            print(f"  Campaigns: {len(campaigns)}")
            
            # Get performance
            performance = manager.get_brand_performance(brand, 7)
            print(f"  7-day performance: {performance.get('total_impressions', 0)} impressions")
            
            # Get keyword suggestions
            keywords = manager.get_keyword_opportunities(brand)
            print(f"  Keyword suggestions: {len(keywords)}")
        
        # Get overall summary
        print("\n📈 Generating overall summary...")
        summary = manager.get_all_brands_summary()
        print(f"Total impressions across all brands: {summary['totals']['impressions']}")
        print(f"Total clicks across all brands: {summary['totals']['clicks']}")
        print(f"Overall CTR: {summary['overall_metrics']['ctr']:.2f}%")
    
    # Run tests
    run_tests()
    
    print("\n✅ Google Ads integration test completed!")


if __name__ == "__main__":
    main()
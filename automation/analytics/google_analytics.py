# Google Analytics Integration for Brand Analytics
# Pulls data from Google Analytics 4 for each brand's website

import os
import sys
import json
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from pathlib import Path
import logging

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from config.brand_loader import get_all_brands, get_brand_details

try:
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    from google.analytics.data_v1beta.types import (
        RunReportRequest,
        Dimension,
        Metric,
        DateRange
    )
    from google.oauth2.service_account import Credentials
    GA_AVAILABLE = True
except ImportError:
    GA_AVAILABLE = False
    print("⚠️  Google Analytics Data API not available. Run: pip install google-analytics-data")

class GoogleAnalyticsIntegration:
    """Collects Google Analytics data for each brand"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent.parent
        self.credentials_path = self.project_root / 'config' / 'ga_credentials.json'
        self.logger = logging.getLogger('GoogleAnalytics')
        
        # Load brand-specific GA property mappings from database
        self.brand_properties = self._load_brand_properties()
    
    def _load_brand_properties(self) -> Dict[str, Dict[str, Any]]:
        """Load brand GA configurations from database with fallback"""
        properties = {}
        brands = get_all_brands(active_only=True)
        
        for brand in brands:
            brand_data = get_brand_details(brand)
            if brand_data:
                properties[brand] = {
                    'property_id': os.getenv(f'{brand.upper()}_GA_PROPERTY_ID', ''),
                    'website': brand_data.get('website_url', f'https://{brand}.io'),
                    'main_pages': ['/', '/about', '/contact', '/blog']  # Default pages
                }
        
        return properties
        
        self.client = None
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize Google Analytics client with service account credentials"""
        if not GA_AVAILABLE:
            self.logger.warning("Google Analytics Data API not available")
            return
            
        try:
            # Check for service account JSON file
            if self.credentials_path.exists():
                credentials = Credentials.from_service_account_file(str(self.credentials_path))
                self.client = BetaAnalyticsDataClient(credentials=credentials)
                self.logger.info("✅ Google Analytics client initialized with service account")
            else:
                # Try application default credentials (for development)
                self.client = BetaAnalyticsDataClient()
                self.logger.info("✅ Google Analytics client initialized with default credentials")
                
        except Exception as e:
            self.logger.error(f"❌ Failed to initialize Google Analytics client: {e}")
            self.client = None
    
    async def get_brand_analytics(self, brand: str, days: int = 30) -> Dict[str, Any]:
        """Get comprehensive analytics data for a specific brand"""
        if not self.client or brand not in self.brand_properties:
            return self._get_mock_analytics(brand, days)
        
        property_id = self.brand_properties[brand]['property_id']
        if not property_id:
            self.logger.warning(f"No GA property ID configured for brand: {brand}")
            return self._get_mock_analytics(brand, days)
        
        try:
            # Define date range
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            # Get overview metrics
            overview = await self._get_overview_metrics(property_id, start_date, end_date)
            
            # Get page views by page
            page_views = await self._get_page_analytics(property_id, start_date, end_date)
            
            # Get traffic sources
            traffic_sources = await self._get_traffic_sources(property_id, start_date, end_date)
            
            # Get device and browser data
            device_data = await self._get_device_analytics(property_id, start_date, end_date)
            
            # Get geographic data
            geographic_data = await self._get_geographic_analytics(property_id, start_date, end_date)
            
            return {
                'brand': brand,
                'website': self.brand_properties[brand]['website'],
                'period': f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}",
                'overview': overview,
                'pages': page_views,
                'traffic_sources': traffic_sources,
                'devices': device_data,
                'geographic': geographic_data,
                'last_updated': datetime.now().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Error fetching analytics for {brand}: {e}")
            return self._get_mock_analytics(brand, days)
    
    async def _get_overview_metrics(self, property_id: str, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Get basic overview metrics"""
        request = RunReportRequest(
            property=f"properties/{property_id}",
            dimensions=[
                Dimension(name="date")
            ],
            metrics=[
                Metric(name="sessions"),
                Metric(name="activeUsers"),
                Metric(name="screenPageViews"),
                Metric(name="averageSessionDuration"),
                Metric(name="bounceRate")
            ],
            date_ranges=[DateRange(
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d")
            )]
        )
        
        response = self.client.run_report(request=request)
        
        # Aggregate totals
        total_sessions = 0
        total_users = 0
        total_pageviews = 0
        total_duration = 0
        bounce_rates = []
        
        for row in response.rows:
            total_sessions += int(row.metric_values[0].value or 0)
            total_users += int(row.metric_values[1].value or 0)
            total_pageviews += int(row.metric_values[2].value or 0)
            total_duration += float(row.metric_values[3].value or 0)
            if row.metric_values[4].value:
                bounce_rates.append(float(row.metric_values[4].value))
        
        return {
            'sessions': total_sessions,
            'users': total_users,
            'pageviews': total_pageviews,
            'avg_session_duration': total_duration / len(response.rows) if response.rows else 0,
            'bounce_rate': sum(bounce_rates) / len(bounce_rates) if bounce_rates else 0
        }
    
    async def _get_page_analytics(self, property_id: str, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
        """Get page-specific analytics"""
        request = RunReportRequest(
            property=f"properties/{property_id}",
            dimensions=[
                Dimension(name="pagePath"),
                Dimension(name="pageTitle")
            ],
            metrics=[
                Metric(name="screenPageViews"),
                Metric(name="sessions"),
                Metric(name="averageSessionDuration")
            ],
            date_ranges=[DateRange(
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d")
            )]
        )
        
        response = self.client.run_report(request=request)
        
        pages = []
        for row in response.rows:
            pages.append({
                'path': row.dimension_values[0].value,
                'title': row.dimension_values[1].value,
                'pageviews': int(row.metric_values[0].value or 0),
                'sessions': int(row.metric_values[1].value or 0),
                'avg_duration': float(row.metric_values[2].value or 0)
            })
        
        # Sort by pageviews
        return sorted(pages, key=lambda x: x['pageviews'], reverse=True)[:20]
    
    async def _get_traffic_sources(self, property_id: str, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
        """Get traffic source analytics"""
        request = RunReportRequest(
            property=f"properties/{property_id}",
            dimensions=[
                Dimension(name="sessionDefaultChannelGroup"),
                Dimension(name="sessionSource")
            ],
            metrics=[
                Metric(name="sessions"),
                Metric(name="activeUsers")
            ],
            date_ranges=[DateRange(
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d")
            )]
        )
        
        response = self.client.run_report(request=request)
        
        sources = []
        for row in response.rows:
            sources.append({
                'channel': row.dimension_values[0].value,
                'source': row.dimension_values[1].value,
                'sessions': int(row.metric_values[0].value or 0),
                'users': int(row.metric_values[1].value or 0)
            })
        
        return sorted(sources, key=lambda x: x['sessions'], reverse=True)[:15]
    
    async def _get_device_analytics(self, property_id: str, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Get device and browser analytics"""
        request = RunReportRequest(
            property=f"properties/{property_id}",
            dimensions=[
                Dimension(name="deviceCategory"),
                Dimension(name="browser")
            ],
            metrics=[
                Metric(name="sessions"),
                Metric(name="activeUsers")
            ],
            date_ranges=[DateRange(
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d")
            )]
        )
        
        response = self.client.run_report(request=request)
        
        devices = {}
        browsers = {}
        
        for row in response.rows:
            device = row.dimension_values[0].value
            browser = row.dimension_values[1].value
            sessions = int(row.metric_values[0].value or 0)
            
            devices[device] = devices.get(device, 0) + sessions
            browsers[browser] = browsers.get(browser, 0) + sessions
        
        return {
            'devices': dict(sorted(devices.items(), key=lambda x: x[1], reverse=True)[:10]),
            'browsers': dict(sorted(browsers.items(), key=lambda x: x[1], reverse=True)[:10])
        }
    
    async def _get_geographic_analytics(self, property_id: str, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
        """Get geographic analytics"""
        request = RunReportRequest(
            property=f"properties/{property_id}",
            dimensions=[
                Dimension(name="country"),
                Dimension(name="city")
            ],
            metrics=[
                Metric(name="sessions"),
                Metric(name="activeUsers")
            ],
            date_ranges=[DateRange(
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d")
            )]
        )
        
        response = self.client.run_report(request=request)
        
        locations = []
        for row in response.rows:
            locations.append({
                'country': row.dimension_values[0].value,
                'city': row.dimension_values[1].value,
                'sessions': int(row.metric_values[0].value or 0),
                'users': int(row.metric_values[1].value or 0)
            })
        
        return sorted(locations, key=lambda x: x['sessions'], reverse=True)[:20]
    
    def _get_mock_analytics(self, brand: str, days: int) -> Dict[str, Any]:
        """Return empty analytics data when GA is not configured"""
        return {
            'brand': brand,
            'website': self.brand_properties.get(brand, {}).get('website', ''),
            'period': f"Last {days} days",
            'overview': {
                'sessions': 0,
                'users': 0,
                'pageviews': 0,
                'avg_session_duration': 0,
                'bounce_rate': 0
            },
            'pages': [],
            'traffic_sources': [],
            'devices': {'devices': {}, 'browsers': {}},
            'geographic': [],
            'last_updated': datetime.now().isoformat(),
            'note': 'Google Analytics not configured — add GA credentials in Settings'
        }

    async def get_all_brands_analytics(self, days: int = 30) -> Dict[str, Any]:
        """Get analytics for all brands"""
        results = {}
        for brand in self.brand_properties.keys():
            results[brand] = await self.get_brand_analytics(brand, days)
        
        return results

# Create global instance
ga_integration = GoogleAnalyticsIntegration() if GA_AVAILABLE else None
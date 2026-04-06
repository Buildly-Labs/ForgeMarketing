# Consolidated Analytics Manager
# Integrates Google Analytics, Email Campaign Analytics, and Social Media Analytics for all brands

import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from pathlib import Path
import logging
import sys

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Import brand loader
from config.brand_loader import get_all_brands

# Import our analytics modules
try:
    from .google_analytics import ga_integration
except ImportError:
    ga_integration = None

try:
    from .email_analytics import email_analytics
except ImportError:
    email_analytics = None

class AnalyticsManager:
    """Central manager for all brand analytics data"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent.parent
        self.data_dir = self.project_root / 'data' / 'analytics'
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger('AnalyticsManager')
        
        # Load brands from database
        self.brands = get_all_brands(active_only=True)
        
        # Cache settings
        self.cache_duration = timedelta(hours=6)  # Cache for 6 hours
        self.cache_files = {}
    
    async def get_comprehensive_analytics(self, brand: str = None, days: int = 30) -> Dict[str, Any]:
        """Get comprehensive analytics for one or all brands"""
        if brand:
            return await self._get_brand_comprehensive_analytics(brand, days)
        else:
            # Get analytics for all brands
            results = {}
            for brand_name in self.brands:
                results[brand_name] = await self._get_brand_comprehensive_analytics(brand_name, days)
            
            # Add summary across all brands
            results['summary'] = self._calculate_cross_brand_summary(results)
            return results
    
    async def _get_brand_comprehensive_analytics(self, brand: str, days: int) -> Dict[str, Any]:
        """Get comprehensive analytics for a specific brand"""
        cache_key = f"{brand}_{days}days"
        
        # Check cache first
        cached_data = self._get_cached_data(cache_key)
        if cached_data:
            return cached_data
        
        # Gather analytics from all sources
        analytics_data = {
            'brand': brand,
            'period': f"Last {days} days",
            'collected_at': datetime.now().isoformat(),
            'website_analytics': {},
            'email_analytics': {},
            'social_analytics': {},
            'summary': {}
        }
        
        # Get Google Analytics data
        if ga_integration:
            try:
                analytics_data['website_analytics'] = await ga_integration.get_brand_analytics(brand, days)
                self.logger.info(f"✅ Collected Google Analytics for {brand}")
            except Exception as e:
                self.logger.error(f"❌ Error collecting Google Analytics for {brand}: {e}")
                analytics_data['website_analytics'] = {'error': str(e), 'note': 'Using mock data'}
        
        # Get Email Analytics data
        if email_analytics:
            try:
                analytics_data['email_analytics'] = await email_analytics.get_brand_email_analytics(brand, days)
                self.logger.info(f"✅ Collected Email Analytics for {brand}")
            except Exception as e:
                self.logger.error(f"❌ Error collecting Email Analytics for {brand}: {e}")
                analytics_data['email_analytics'] = {'error': str(e), 'note': 'Using mock data'}
        
        # Get Social Media Analytics (placeholder for now)
        analytics_data['social_analytics'] = await self._get_social_analytics(brand, days)
        
        # Calculate brand summary
        analytics_data['summary'] = self._calculate_brand_summary(analytics_data)
        
        # Cache the results
        self._cache_data(cache_key, analytics_data)
        
        return analytics_data
    
    async def _get_social_analytics(self, brand: str, days: int) -> Dict[str, Any]:
        """Get social media analytics — returns empty data until social APIs are integrated"""
        # TODO: Integrate with existing social_media_manager.py
        return {
            'platforms': {
                'twitter': {
                    'followers': 0,
                    'posts': 0,
                    'engagement': 0,
                    'impressions': 0,
                    'engagement_rate': 0
                },
                'linkedin': {
                    'followers': 0,
                    'posts': 0,
                    'engagement': 0,
                    'impressions': 0,
                    'engagement_rate': 0
                }
            },
            'summary': {
                'total_followers': 0,
                'total_posts': 0,
                'total_engagement': 0,
                'avg_engagement_rate': 0
            },
            'note': 'Social analytics not configured — integrate social media APIs in Settings'
        }
    
    def _calculate_brand_summary(self, analytics_data: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate comprehensive summary for a brand"""
        summary = {
            'website': {},
            'email': {},
            'social': {},
            'overall_performance': {}
        }
        
        # Website summary
        website = analytics_data.get('website_analytics', {}).get('overview', {})
        if website:
            summary['website'] = {
                'total_sessions': website.get('sessions', 0),
                'total_users': website.get('users', 0),
                'total_pageviews': website.get('pageviews', 0),
                'bounce_rate': website.get('bounce_rate', 0),
                'performance': 'good' if website.get('bounce_rate', 1) < 0.5 else 'needs_improvement'
            }
        
        # Email summary
        email = analytics_data.get('email_analytics', {}).get('statistics', {})
        if email:
            summary['email'] = {
                'total_sent': email.get('total_sent', 0),
                'total_delivered': email.get('total_delivered', 0),
                'avg_open_rate': email.get('avg_open_rate', 0),
                'avg_click_rate': email.get('avg_click_rate', 0),
                'performance': 'excellent' if email.get('avg_open_rate', 0) > 25 else 'good' if email.get('avg_open_rate', 0) > 20 else 'needs_improvement'
            }
        
        # Social summary
        social = analytics_data.get('social_analytics', {}).get('summary', {})
        if social:
            summary['social'] = {
                'total_followers': social.get('total_followers', 0),
                'total_posts': social.get('total_posts', 0),
                'avg_engagement_rate': social.get('avg_engagement_rate', 0),
                'performance': 'excellent' if social.get('avg_engagement_rate', 0) > 5 else 'good' if social.get('avg_engagement_rate', 0) > 2 else 'needs_improvement'
            }
        
        # Overall performance score
        scores = []
        if summary['website'].get('performance') == 'excellent': scores.append(10)
        elif summary['website'].get('performance') == 'good': scores.append(7)
        elif summary['website'].get('performance') == 'needs_improvement': scores.append(4)
        
        if summary['email'].get('performance') == 'excellent': scores.append(10)
        elif summary['email'].get('performance') == 'good': scores.append(7)
        elif summary['email'].get('performance') == 'needs_improvement': scores.append(4)
        
        if summary['social'].get('performance') == 'excellent': scores.append(10)
        elif summary['social'].get('performance') == 'good': scores.append(7)
        elif summary['social'].get('performance') == 'needs_improvement': scores.append(4)
        
        avg_score = sum(scores) / len(scores) if scores else 5
        summary['overall_performance'] = {
            'score': avg_score,
            'rating': 'excellent' if avg_score >= 8.5 else 'good' if avg_score >= 6.5 else 'needs_improvement',
            'trend': 'stable'  # TODO: Calculate based on historical data
        }
        
        return summary
    
    def _calculate_cross_brand_summary(self, all_brands_data: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate summary across all brands"""
        total_sessions = 0
        total_users = 0
        total_emails_sent = 0
        total_followers = 0
        
        brand_performances = []
        
        for brand, data in all_brands_data.items():
            if brand == 'summary':
                continue
                
            # Aggregate website data
            website = data.get('website_analytics', {}).get('overview', {})
            total_sessions += website.get('sessions', 0)
            total_users += website.get('users', 0)
            
            # Aggregate email data
            email = data.get('email_analytics', {}).get('statistics', {})
            total_emails_sent += email.get('total_sent', 0)
            
            # Aggregate social data
            social = data.get('social_analytics', {}).get('summary', {})
            total_followers += social.get('total_followers', 0)
            
            # Collect performance scores
            summary = data.get('summary', {})
            overall = summary.get('overall_performance', {})
            if overall.get('score'):
                brand_performances.append(overall['score'])
        
        avg_performance = sum(brand_performances) / len(brand_performances) if brand_performances else 5
        
        return {
            'total_website_sessions': total_sessions,
            'total_website_users': total_users,
            'total_emails_sent': total_emails_sent,
            'total_social_followers': total_followers,
            'number_of_brands': len([b for b in all_brands_data.keys() if b != 'summary']),
            'average_performance_score': avg_performance,
            'overall_rating': 'excellent' if avg_performance >= 8.5 else 'good' if avg_performance >= 6.5 else 'needs_improvement',
            'top_performing_brand': max(all_brands_data.keys(), 
                                      key=lambda b: all_brands_data[b].get('summary', {}).get('overall_performance', {}).get('score', 0)
                                      ) if all_brands_data else None
        }
    
    def _get_cached_data(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get data from cache if still valid"""
        cache_file = self.data_dir / f"{cache_key}.json"
        
        if cache_file.exists():
            try:
                with open(cache_file, 'r') as f:
                    cached = json.load(f)
                
                cached_time = datetime.fromisoformat(cached['collected_at'])
                if datetime.now() - cached_time < self.cache_duration:
                    self.logger.info(f"📚 Using cached analytics data for {cache_key}")
                    return cached
                else:
                    self.logger.info(f"⏰ Cache expired for {cache_key}, fetching fresh data")
            except Exception as e:
                self.logger.error(f"Error reading cache for {cache_key}: {e}")
        
        return None
    
    def _cache_data(self, cache_key: str, data: Dict[str, Any]) -> None:
        """Cache analytics data"""
        cache_file = self.data_dir / f"{cache_key}.json"
        
        try:
            with open(cache_file, 'w') as f:
                json.dump(data, f, indent=2, default=str)
            self.logger.info(f"💾 Cached analytics data for {cache_key}")
        except Exception as e:
            self.logger.error(f"Error caching data for {cache_key}: {e}")
    
    async def get_analytics_summary(self) -> Dict[str, Any]:
        """Get a quick summary of all brands analytics"""
        summary_data = {}
        
        for brand in self.brands:
            # Try to get from cache first, then minimal fresh data
            cache_key = f"{brand}_30days"
            cached = self._get_cached_data(cache_key)
            
            if cached:
                summary_data[brand] = cached.get('summary', {})
            else:
                # Get minimal data for summary
                brand_data = await self._get_brand_comprehensive_analytics(brand, 30)
                summary_data[brand] = brand_data.get('summary', {})
        
        return summary_data
    
    def clear_cache(self) -> None:
        """Clear all cached analytics data"""
        try:
            for cache_file in self.data_dir.glob("*.json"):
                cache_file.unlink()
            self.logger.info("🗑️ Cleared all analytics cache")
        except Exception as e:
            self.logger.error(f"Error clearing cache: {e}")

# Create global instance
analytics_manager = AnalyticsManager()
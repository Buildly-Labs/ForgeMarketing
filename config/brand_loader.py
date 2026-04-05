"""
Brand Loader Utility
Replaces hardcoded brand lists with database queries.
Works both inside Flask app context and standalone (for cron jobs etc).
"""

import os
import sys
from pathlib import Path
from typing import List, Dict, Optional, Any
from functools import lru_cache

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Default brands used as fallback when database is unavailable
DEFAULT_BRANDS = [
    {'name': 'buildly', 'display_name': 'Buildly', 'description': 'Low-code automation platform', 'website_url': 'https://buildly.io'},
    {'name': 'foundry', 'display_name': 'First City Foundry', 'description': 'Startup accelerator platform', 'website_url': 'https://firstcityfoundry.com'},
    {'name': 'openbuild', 'display_name': 'OpenBuild', 'description': 'Community-driven development platform', 'website_url': 'https://open.build'},
    {'name': 'radical', 'display_name': 'Radical Therapy', 'description': 'Digital therapy platform', 'website_url': 'https://radicaltherapy.com'},
    {'name': 'oregonsoftware', 'display_name': 'Oregon Software', 'description': 'Software development services', 'website_url': 'https://oregonsoftware.com'},
]


class BrandLoader:
    """Load brand data from database instead of hardcoded values"""
    
    def __init__(self, app=None):
        """Initialize brand loader with optional Flask app context"""
        self.app = app
        self._brands_cache = None
        self._cache_timestamp = None
        
    def _get_app(self):
        """Get Flask app if available"""
        if self.app:
            return self.app
        # Don't try to import dashboard.app — it causes circular imports
        # when called from automation scripts during module load
        return None
    
    def _query_db_direct(self, active_only=True):
        """Query the database directly with SQLAlchemy (no Flask context needed)"""
        try:
            from sqlalchemy import create_engine, text
            
            db_url = os.getenv('DATABASE_URL')
            if db_url:
                if db_url.startswith('postgres://'):
                    db_url = db_url.replace('postgres://', 'postgresql://', 1)
                if db_url.startswith('mysql://'):
                    db_url = db_url.replace('mysql://', 'mysql+mysqldb://', 1)
                if '?' in db_url:
                    db_url = db_url.split('?')[0]
            else:
                db_path = os.path.join(project_root, 'data', 'marketing_dashboard.db')
                if not os.path.exists(db_path):
                    return None
                db_url = f'sqlite:///{db_path}'
            
            engine = create_engine(db_url)
            with engine.connect() as conn:
                query = "SELECT name, display_name, description, website_url, is_active FROM brands"
                if active_only:
                    query += " WHERE is_active = 1"
                query += " ORDER BY name"
                result = conn.execute(text(query))
                rows = result.fetchall()
                return [
                    {'name': r[0], 'display_name': r[1], 'description': r[2], 'website_url': r[3], 'is_active': bool(r[4])}
                    for r in rows
                ]
        except Exception:
            return None
    
    def get_all_brands(self, active_only: bool = True, include_details: bool = False) -> list:
        """
        Get all brands from database.
        Falls back to DEFAULT_BRANDS if database unavailable.
        """
        # Try direct DB query first (works without Flask)
        rows = self._query_db_direct(active_only=active_only)
        if rows:
            if include_details:
                return rows
            return [r['name'] for r in rows]
        
        # Try Flask app context if available
        app = self._get_app()
        if app:
            try:
                with app.app_context():
                    from dashboard.models import Brand
                    query = Brand.query
                    if active_only:
                        query = query.filter_by(is_active=True)
                    brands = query.order_by(Brand.name).all()
                    if include_details:
                        return [brand.to_dict() for brand in brands]
                    return [brand.name for brand in brands]
            except Exception:
                pass
        
        # Fallback to defaults
        if include_details:
            return list(DEFAULT_BRANDS)
        return [b['name'] for b in DEFAULT_BRANDS]
    
    def get_brand_by_name(self, brand_name: str) -> Optional[Dict[str, Any]]:
        """Get brand details by name"""
        all_brands = self.get_all_brands(include_details=True)
        for b in all_brands:
            if b.get('name') == brand_name:
                return b
        return None
    
    def get_brand_config(self, brand_name: str, config_type: str = 'all') -> Dict[str, Any]:
        """Get brand configuration including credentials and settings"""
        brand = self.get_brand_by_name(brand_name)
        if not brand:
            return {}
        
        config = {'brand': brand}
        
        # Try Flask app context for detailed config
        app = self._get_app()
        if app:
            try:
                with app.app_context():
                    from dashboard.models import Brand, BrandEmailConfig, BrandSettings, BrandAPICredential
                    db_brand = Brand.query.filter_by(name=brand_name).first()
                    if db_brand:
                        if config_type in ['email', 'all']:
                            email_configs = BrandEmailConfig.query.filter_by(brand_id=db_brand.id).all()
                            config['email'] = [
                                {'provider': ec.provider, 'from_email': ec.from_email, 'from_name': ec.from_name, 'is_primary': ec.is_primary}
                                for ec in email_configs
                            ]
                        if config_type in ['settings', 'all']:
                            config['settings'] = {'website_url': db_brand.website_url, 'description': db_brand.description}
                        if config_type in ['api', 'all']:
                            api_creds = BrandAPICredential.query.filter_by(brand_id=db_brand.id).all()
                            config['services'] = [cred.service for cred in api_creds]
            except Exception:
                pass
        
        return config
    
    def is_brand_active(self, brand_name: str) -> bool:
        """Check if a brand is active"""
        brand = self.get_brand_by_name(brand_name)
        if brand:
            return brand.get('is_active', True)
        return False
    
    def get_brand_mapping(self) -> Dict[str, str]:
        """Get mapping of brand names to display names"""
        brands = self.get_all_brands(include_details=True)
        if isinstance(brands, list) and len(brands) > 0 and isinstance(brands[0], dict):
            return {b['name']: b.get('display_name', b['name']) for b in brands}
        return {}


# Global singleton instance
_brand_loader = None


def get_brand_loader(app=None) -> BrandLoader:
    """Get or create the global brand loader instance"""
    global _brand_loader
    if _brand_loader is None:
        _brand_loader = BrandLoader(app)
    elif app is not None and _brand_loader.app is None:
        _brand_loader.app = app
    return _brand_loader


def get_all_brands(active_only: bool = True) -> List[str]:
    """
    Convenience function to get all brand names
    
    Usage:
        from config.brand_loader import get_all_brands
        brands = get_all_brands()  # Returns ['buildly', 'foundry', ...]
    """
    loader = get_brand_loader()
    return loader.get_all_brands(active_only=active_only)


def get_brand_details(brand_name: str) -> Optional[Dict[str, Any]]:
    """
    Convenience function to get brand details
    
    Usage:
        from config.brand_loader import get_brand_details
        brand = get_brand_details('buildly')
    """
    loader = get_brand_loader()
    return loader.get_brand_by_name(brand_name)


# Export key functions
__all__ = ['BrandLoader', 'get_brand_loader', 'get_all_brands', 'get_brand_details']

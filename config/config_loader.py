"""
Secure Configuration Loader
Loads configuration from database instead of hardcoded values or environment variables
"""

import os
from typing import Dict, Any, Optional
from dashboard.models import db, Brand, BrandEmailConfig, BrandAPICredential, SystemConfig


class ConfigLoader:
    """Load configuration from database with fallback to environment variables"""
    
    _instance = None
    _cache = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigLoader, cls).__new__(cls)
        return cls._instance
    
    def get_system_config(self, key: str, default: Any = None, category: str = 'general') -> Any:
        """Get system-wide configuration value"""
        cache_key = f"system:{key}"
        
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        try:
            config = SystemConfig.query.filter_by(key=key).first()
            if config:
                value = config.value
                self._cache[cache_key] = value
                return value
        except Exception:
            pass  # Expected outside Flask app context (e.g. module-level init)
        
        # Fallback to environment variable
        env_value = os.getenv(key.upper(), default)
        return env_value
    
    def set_system_config(self, key: str, value: str, description: str = '', 
                         is_secret: bool = False, category: str = 'general',
                         updated_by: str = 'system') -> bool:
        """Set or update system configuration value"""
        try:
            config = SystemConfig.query.filter_by(key=key).first()
            if config:
                config.value = value
                config.description = description
                config.is_secret = is_secret
                config.category = category
                config.updated_by = updated_by
            else:
                config = SystemConfig(
                    key=key,
                    value=value,
                    description=description,
                    is_secret=is_secret,
                    category=category,
                    updated_by=updated_by
                )
                db.session.add(config)
            
            db.session.commit()
            
            # Update cache
            self._cache[f"system:{key}"] = value
            return True
        except Exception as e:
            print(f"Error setting system config {key}: {e}")
            db.session.rollback()
            return False
    
    def get_brand_email_config(self, brand_name: str, provider: str = None) -> Optional[BrandEmailConfig]:
        """Get email configuration for a brand"""
        try:
            brand = Brand.query.filter_by(name=brand_name).first()
            if not brand:
                return None
            
            if provider:
                return BrandEmailConfig.query.filter_by(
                    brand_id=brand.id, 
                    provider=provider
                ).first()
            else:
                # Get primary config
                return BrandEmailConfig.query.filter_by(
                    brand_id=brand.id,
                    is_primary=True
                ).first()
        except Exception as e:
            print(f"Error loading email config for {brand_name}: {e}")
            return None
    
    def get_brand_api_credential(self, brand_name: str, service: str) -> Optional[Dict[str, Any]]:
        """Get API credentials for a brand and service"""
        cache_key = f"api:{brand_name}:{service}"
        
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        try:
            brand = Brand.query.filter_by(name=brand_name).first()
            if not brand:
                return None
            
            credential = BrandAPICredential.query.filter_by(
                brand_id=brand.id,
                service=service,
                is_active=True
            ).first()
            
            if credential:
                creds = credential.get_credentials()
                self._cache[cache_key] = creds
                return creds
        except Exception as e:
            print(f"Error loading API credential for {brand_name}/{service}: {e}")
        
        return None
    
    def set_brand_api_credential(self, brand_name: str, service: str, 
                                credential_type: str, credentials: Dict[str, Any],
                                service_settings: Dict[str, Any] = None) -> bool:
        """Set or update API credentials for a brand and service"""
        try:
            brand = Brand.query.filter_by(name=brand_name).first()
            if not brand:
                print(f"Brand {brand_name} not found")
                return False
            
            credential = BrandAPICredential.query.filter_by(
                brand_id=brand.id,
                service=service
            ).first()
            
            if credential:
                credential.set_credentials(credentials)
                credential.credential_type = credential_type
                if service_settings:
                    credential.set_service_settings(service_settings)
            else:
                credential = BrandAPICredential(
                    brand_id=brand.id,
                    service=service,
                    credential_type=credential_type
                )
                credential.set_credentials(credentials)
                if service_settings:
                    credential.set_service_settings(service_settings)
                db.session.add(credential)
            
            db.session.commit()
            
            # Clear cache
            cache_key = f"api:{brand_name}:{service}"
            if cache_key in self._cache:
                del self._cache[cache_key]
            
            return True
        except Exception as e:
            print(f"Error setting API credential for {brand_name}/{service}: {e}")
            db.session.rollback()
            return False
    
    def get_twitter_credentials(self, brand_name: str) -> Optional[Dict[str, str]]:
        """Get Twitter/X API credentials for a brand"""
        creds = self.get_brand_api_credential(brand_name, 'twitter')
        if creds:
            return creds
        
        # Fallback to environment variables
        prefix = brand_name.upper()
        return {
            'api_key': os.getenv(f'{prefix}_TWITTER_API_KEY', os.getenv('TWITTER_API_KEY', '')),
            'api_secret': os.getenv(f'{prefix}_TWITTER_API_SECRET', os.getenv('TWITTER_API_SECRET', '')),
            'access_token': os.getenv(f'{prefix}_TWITTER_ACCESS_TOKEN', os.getenv('TWITTER_ACCESS_TOKEN', '')),
            'access_token_secret': os.getenv(f'{prefix}_TWITTER_ACCESS_TOKEN_SECRET', os.getenv('TWITTER_ACCESS_TOKEN_SECRET', '')),
            'bearer_token': os.getenv(f'{prefix}_TWITTER_BEARER_TOKEN', os.getenv('TWITTER_BEARER_TOKEN', ''))
        }
    
    def get_google_analytics_credentials(self, brand_name: str) -> Optional[Dict[str, str]]:
        """Get Google Analytics credentials for a brand"""
        creds = self.get_brand_api_credential(brand_name, 'google_analytics')
        if creds:
            return creds
        
        # Fallback to environment variables
        prefix = brand_name.upper()
        return {
            'property_id': os.getenv(f'{prefix}_GA_PROPERTY_ID', ''),
            'api_key': os.getenv('GOOGLE_ANALYTICS_API_KEY', ''),
            'credentials_file': os.getenv('GOOGLE_ANALYTICS_CREDENTIALS_FILE', '')
        }
    
    def clear_cache(self):
        """Clear configuration cache"""
        self._cache = {}


# Global instance
config_loader = ConfigLoader()

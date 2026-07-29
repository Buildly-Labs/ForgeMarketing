#!/usr/bin/env python3
"""
Configuration Management System
Centralized configuration loading and management for productized deployment
"""

import os
import yaml
import json
from pathlib import Path
from typing import Dict, Any, Optional
import logging
from datetime import datetime

class ConfigurationError(Exception):
    """Configuration-related errors"""
    pass

class ConfigManager:
    """Centralized configuration management"""
    
    def __init__(self, config_dir: Optional[Path] = None, environment: Optional[str] = None):
        self.config_dir = config_dir or Path(__file__).parent
        self.environment = environment or os.getenv('ENVIRONMENT', 'development')
        self.config_cache = {}
        self.logger = logging.getLogger('ConfigManager')
        
        # Load system configuration
        self._load_system_config()
    
    def _load_system_config(self):
        """Load system configuration with environment overrides."""
        system_config_path = self.config_dir / 'system_config.yaml'
        fallback_path = self.config_dir / 'ai_config.yaml'

        config_path = system_config_path if system_config_path.exists() else fallback_path

        if not config_path.exists():
            # Last-resort empty config so startup never hard-fails.
            self.logger.warning(
                'No system config found at %s or %s; using empty defaults',
                system_config_path,
                fallback_path,
            )
            self.system_config = {}
            return

        try:
            with open(config_path, 'r') as f:
                self.system_config = yaml.safe_load(f) or {}

            # Apply environment-specific overrides when using system_config.yaml.
            if config_path == system_config_path:
                if 'deployment' in self.system_config and 'environments' in self.system_config['deployment']:
                    env_overrides = self.system_config['deployment']['environments'].get(self.environment, {})
                    self._apply_overrides(self.system_config, env_overrides)

            self._substitute_env_vars(self.system_config)
            self.logger.info('System configuration loaded from %s for environment: %s', config_path, self.environment)

        except Exception as exc:
            raise ConfigurationError(f'Failed to load system configuration from {config_path}: {exc}') from exc
    
    def _apply_overrides(self, config: Dict[str, Any], overrides: Dict[str, Any]):
        """Apply environment-specific configuration overrides"""
        for key, value in overrides.items():
            if '.' in key:
                # Handle nested keys like 'dashboard.debug'
                keys = key.split('.')
                current = config
                for k in keys[:-1]:
                    if k not in current:
                        current[k] = {}
                    current = current[k]
                current[keys[-1]] = value
            else:
                config[key] = value
    
    def _substitute_env_vars(self, config: Any) -> Any:
        """Recursively substitute environment variables in configuration"""
        if isinstance(config, dict):
            for key, value in config.items():
                config[key] = self._substitute_env_vars(value)
        elif isinstance(config, list):
            for i, item in enumerate(config):
                config[i] = self._substitute_env_vars(item)
        elif isinstance(config, str) and config.startswith('${') and config.endswith('}'):
            env_var = config[2:-1]
            default_value = None
            
            # Handle default values like ${VAR:default}
            if ':' in env_var:
                env_var, default_value = env_var.split(':', 1)
            
            return os.getenv(env_var, default_value)
        
        return config
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value using dot notation"""
        keys = key.split('.')
        current = self.system_config
        
        try:
            for k in keys:
                current = current[k]
            return current
        except (KeyError, TypeError):
            return default
    
    def get_ai_config(self) -> Dict[str, Any]:
        """Get AI configuration"""
        return self.get('ai', {})
    
    def get_dashboard_config(self) -> Dict[str, Any]:
        """Get dashboard configuration"""
        return self.get('dashboard', {})
    
    def get_brand_config(self, brand_name: str) -> Dict[str, Any]:
        """Get brand-specific configuration"""
        # Load from brand-specific file
        brand_config_path = self.config_dir.parent / 'templates' / 'brands' / brand_name / 'brand_config.yaml'
        
        if brand_config_path.exists():
            try:
                with open(brand_config_path, 'r') as f:
                    brand_config = yaml.safe_load(f)
                
                # Apply system-level brand defaults
                defaults = self.get('brands.default_settings', {})
                brand_config.setdefault('system', defaults)
                
                return brand_config
            except Exception as e:
                self.logger.error(f"Failed to load brand config for {brand_name}: {e}")
        
        return {}
    
    def get_enabled_brands(self) -> list:
        """Get list of enabled brands"""
        return self.get('brands.enabled_brands', [])
    
    def is_feature_enabled(self, feature: str) -> bool:
        """Check if a feature is enabled"""
        return self.get(f'dashboard.features.{feature}', False)
    
    def get_api_config(self) -> Dict[str, Any]:
        """Get API configuration"""
        return self.get('api', {})
    
    def get_security_config(self) -> Dict[str, Any]:
        """Get security configuration"""
        return self.get('security', {})
    
    def validate_configuration(self) -> Dict[str, Any]:
        """Validate system configuration and return status"""
        validation_results = {
            'valid': True,
            'errors': [],
            'warnings': [],
            'checks_performed': []
        }
        
        # Check required configurations
        required_configs = [
            'ai.provider',
            'dashboard.host',
            'dashboard.port'
        ]
        
        for config_key in required_configs:
            validation_results['checks_performed'].append(f"Checking {config_key}")
            if self.get(config_key) is None:
                validation_results['errors'].append(f"Missing required configuration: {config_key}")
                validation_results['valid'] = False
        
        # Check AI configuration
        if self.get('ai.provider') == 'ollama':
            ollama_url = self.get('ai.ollama.base_url')
            if not ollama_url:
                validation_results['errors'].append("Ollama base_url not configured")
                validation_results['valid'] = False
        
        # Check brand configurations
        enabled_brands = self.get_enabled_brands()
        for brand in enabled_brands:
            brand_config = self.get_brand_config(brand)
            if not brand_config:
                validation_results['warnings'].append(f"Brand configuration missing for: {brand}")
        
        # Check environment variables
        env_vars = ['SECRET_KEY']  # Add more as needed
        for env_var in env_vars:
            if not os.getenv(env_var):
                validation_results['warnings'].append(f"Environment variable not set: {env_var}")
        
        return validation_results
    
    def export_config(self, format: str = 'yaml') -> str:
        """Export current configuration"""
        if format.lower() == 'json':
            return json.dumps(self.system_config, indent=2)
        else:
            return yaml.dump(self.system_config, default_flow_style=False)
    
    def reload_config(self):
        """Reload configuration from files"""
        self.config_cache.clear()
        self._load_system_config()
        self.logger.info("Configuration reloaded")
    
    def get_deployment_info(self) -> Dict[str, Any]:
        """Get deployment information"""
        return {
            'environment': self.environment,
            'version': self.get('system.version', 'unknown'),
            'config_loaded_at': datetime.now().isoformat(),
            'enabled_brands': self.get_enabled_brands(),
            'features_enabled': {
                feature: self.is_feature_enabled(feature)
                for feature in ['content_generation', 'brand_management', 'analytics_reporting', 'api_access']
            }
        }

# Global configuration manager instance
_config_manager = None

def get_config() -> ConfigManager:
    """Get global configuration manager instance"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager

def reload_config():
    """Reload global configuration"""
    global _config_manager
    if _config_manager:
        _config_manager.reload_config()

# Configuration validation CLI
if __name__ == "__main__":
    import sys
    
    print("🔧 Marketing Automation Configuration Validator")
    print("=" * 55)
    
    try:
        config = ConfigManager()
        
        # Validate configuration
        validation = config.validate_configuration()
        
        print(f"🔍 Configuration validation for environment: {config.environment}")
        print(f"📋 Checks performed: {len(validation['checks_performed'])}")
        
        if validation['valid']:
            print("✅ Configuration is valid!")
        else:
            print("❌ Configuration has errors:")
            for error in validation['errors']:
                print(f"   • {error}")
        
        if validation['warnings']:
            print("⚠️  Warnings:")
            for warning in validation['warnings']:
                print(f"   • {warning}")
        
        # Display deployment info
        deployment_info = config.get_deployment_info()
        print(f"\n📊 Deployment Information:")
        print(f"   Environment: {deployment_info['environment']}")
        print(f"   Version: {deployment_info['version']}")
        print(f"   Brands: {', '.join(deployment_info['enabled_brands'])}")
        
        # Export configuration if requested
        if len(sys.argv) > 1 and sys.argv[1] == '--export':
            format_type = sys.argv[2] if len(sys.argv) > 2 else 'yaml'
            print(f"\n📤 Configuration Export ({format_type}):")
            print("-" * 40)
            print(config.export_config(format_type))
        
        sys.exit(0 if validation['valid'] else 1)
        
    except Exception as e:
        print(f"❌ Configuration error: {e}")
        sys.exit(1)
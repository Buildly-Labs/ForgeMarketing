# Ollama AI Integration for Marketing Automation
# Integrates with Ollama instance (configured via admin panel or OLLAMA_HOST env var)

import aiohttp
import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
import yaml


def _get_ai_config(key, default=None):
    """Get AI config from DB (if Flask context available) or fall back to env var."""
    try:
        from config.config_loader import ConfigLoader
        return ConfigLoader().get_system_config(key, default)
    except Exception:
        return os.getenv(key, default)


class OllamaClient:
    """Client for interacting with Ollama AI instance"""
    
    def __init__(self, base_url: str = None):
        if base_url is None:
            base_url = _get_ai_config('OLLAMA_HOST', 'http://localhost:11434')
        self.base_url = base_url.rstrip('/')
        self.models_cache = {}
        self.logger = logging.getLogger('OllamaClient')
        
    async def test_connection(self) -> bool:
        """Test connection to Ollama instance"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/api/tags") as response:
                    if response.status == 200:
                        models = await response.json()
                        self.logger.info(f"✅ Connected to Ollama. Available models: {len(models.get('models', []))}")
                        return True
                    else:
                        self.logger.error(f"❌ Ollama connection failed: HTTP {response.status}")
                        return False
        except Exception as e:
            self.logger.error(f"❌ Failed to connect to Ollama at {self.base_url}: {e}")
            return False
    
    async def list_models(self) -> List[Dict[str, Any]]:
        """List available models"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/api/tags") as response:
                    if response.status == 200:
                        data = await response.json()
                        models = data.get('models', [])
                        self.logger.info(f"Found {len(models)} available models")
                        return models
                    else:
                        self.logger.error(f"Failed to list models: HTTP {response.status}")
                        return []
        except Exception as e:
            self.logger.error(f"Error listing models: {e}")
            return []
    
    async def generate(self, 
                      model: str = "llama3.1", 
                      prompt: str = "", 
                      temperature: float = 0.7,
                      max_tokens: int = 2000,
                      system_prompt: str = None) -> str:
        """Generate content using Ollama"""
        try:
            payload = {
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                    "top_p": 0.9,
                    "repeat_penalty": 1.1
                }
            }
            
            if system_prompt:
                payload["system"] = system_prompt
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=300)  # 5 minute timeout
                ) as response:
                    
                    if response.status == 200:
                        result = await response.json()
                        content = result.get('response', '').strip()
                        
                        self.logger.info(f"✅ Generated {len(content)} characters with {model}")
                        return content
                    else:
                        error_text = await response.text()
                        self.logger.error(f"Generation failed: HTTP {response.status} - {error_text}")
                        return ""
                        
        except asyncio.TimeoutError:
            self.logger.error("Generation timed out after 5 minutes")
            return ""
        except Exception as e:
            self.logger.error(f"Error generating content: {e}")
            return ""
    
    async def chat(self, 
                   model: str = "llama3.1",
                   messages: List[Dict[str, str]] = None,
                   temperature: float = 0.7) -> str:
        """Chat-style interaction with Ollama"""
        try:
            payload = {
                "model": model,
                "messages": messages or [],
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": 2000
                }
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/api/chat",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=300)
                ) as response:
                    
                    if response.status == 200:
                        result = await response.json()
                        content = result.get('message', {}).get('content', '').strip()
                        return content
                    else:
                        self.logger.error(f"Chat failed: HTTP {response.status}")
                        return ""
                        
        except Exception as e:
            self.logger.error(f"Error in chat: {e}")
            return ""

class AIContentGenerator:
    """AI-powered content generator using Ollama with brand templates"""
    
    def __init__(self, ollama_url: str = None):
        if ollama_url is None:
            ollama_url = _get_ai_config('OLLAMA_HOST', 'http://localhost:11434')
        self.ollama = OllamaClient(ollama_url)
        self.config_dir = Path(__file__).parent.parent.parent / 'config'
        self.templates_dir = Path(__file__).parent.parent.parent / 'templates'
        self.logger = logging.getLogger('AIContentGenerator')
        
        # Load configurations
        self.ai_config = self.load_ai_config()
        self.brand_configs = self.load_brand_configs()
    
    def load_ai_config(self) -> Dict[str, Any]:
        """Load AI configuration"""
        config_file = self.config_dir / 'ai_config.yaml'
        if config_file.exists():
            with open(config_file, 'r') as f:
                return yaml.safe_load(f)
        
        # Default configuration
        return {
            'ollama': {
                'models': {
                    'content_generation': 'llama3.2:1b',
                    'social_media': 'llama3.2:1b',
                    'outreach': 'llama3.2:1b'
                },
                'generation_settings': {
                    'temperature': 0.7,
                    'max_tokens': 2000
                }
            }
        }
    
    def load_brand_configs(self) -> Dict[str, Dict[str, Any]]:
        """Load all brand configurations from individual brand directories"""
        brand_configs = {}
        brands_dir = self.templates_dir / 'brands'
        
        if brands_dir.exists():
            for brand_dir in brands_dir.iterdir():
                if brand_dir.is_dir():
                    config_file = brand_dir / 'brand_config.yaml'
                    if config_file.exists():
                        try:
                            with open(config_file, 'r') as f:
                                config = yaml.safe_load(f)
                                brand_configs[brand_dir.name] = config
                        except Exception as e:
                            self.logger.warning(f"Failed to load brand config for {brand_dir.name}: {e}")
        
        return brand_configs
    
    async def generate_blog_post(self, brand: str, topic: str, target_audience: str = None) -> Dict[str, Any]:
        """Generate AI blog post for specific brand"""
        
        if brand not in self.brand_configs:
            raise ValueError(f"Unknown brand: {brand}")
        
        brand_config = self.brand_configs[brand]
        brand_info = brand_config.get('brand', {})
        voice_info = brand_config.get('voice', {})
        messaging = brand_config.get('key_messages', {})
        audiences = brand_config.get('target_audience', {})
        
        system_prompt = f"""You are a professional content writer for {brand_info.get('name', brand)}.
        
Brand Voice: {', '.join(voice_info.get('tone', ['professional']))}
Target Audience: {target_audience or ', '.join(audiences.get('primary', ['developers']))}
Key Messages: {messaging.get('primary', 'Innovation in technology')}
Brand Description: {brand_info.get('description', 'Technology solutions')}
"""
        
        user_prompt = f"""Write a comprehensive blog post about: {topic}

Requirements:
- 800-1200 words
- Include practical examples or code snippets if technical
- Maintain {brand_info.get('name', brand)} voice and expertise
- Structure with clear headings and subheadings
- Include a compelling introduction and conclusion
- Add a call-to-action related to {brand_info.get('description', 'our solutions')}
- Make it SEO-friendly with relevant keywords

Focus on providing value to {target_audience or 'developers and product managers'} while showcasing {brand_info.get('name', brand)}'s expertise."""
        
        content = await self.ollama.generate(
            model=self.ai_config['ollama']['default_model'],
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.7,
            max_tokens=2500
        )
        
        # Extract title (first line typically)
        lines = content.split('\n')
        title = lines[0].replace('#', '').strip() if lines else f"{topic} - {brand_info.get('name', brand)}"
        
        return {
            'title': title,
            'content': content,
            'brand': brand,
            'topic': topic,
            'target_audience': target_audience,
            'generated_at': datetime.now().isoformat(),
            'word_count': len(content.split()),
            'model_used': self.ai_config['ollama']['default_model']
        }
    
    async def generate_social_post(self, brand: str, content_type: str, platform: str = "twitter") -> Dict[str, Any]:
        """Generate social media post for specific brand and platform"""
        
        if brand not in self.brand_configs:
            raise ValueError(f"Unknown brand: {brand}")
        
        brand_config = self.brand_configs[brand]
        brand_info = brand_config.get('brand', {})
        voice_info = brand_config.get('voice', {})
        social_media = brand_config.get('social_media', {})
        
        char_limits = {
            'twitter': 280,
            'linkedin': 3000,
            'facebook': 500
        }
        
        char_limit = char_limits.get(platform, 280)
        
        system_prompt = f"""You are the social media manager for {brand_info.get('name', brand)}.

Brand Personality: {', '.join(voice_info.get('tone', ['professional']))}
Platform: {platform}
Content Type: {content_type}
Character Limit: {char_limit}"""

        # Get brand-specific hashtags
        hashtags = social_media.get('hashtags', [])
        hashtag_str = ' '.join(hashtags[:3]) if hashtags else ''
        
        content_types = {
            'educational': f"Share a quick tip or insight about {brand_info.get('description', 'technology solutions')}",
            'promotional': f"Promote {brand_info.get('name', brand)} and its benefits",
            'community': "Engage with the developer community",
            'news': f"Share industry news relevant to {brand_info.get('name', brand)} audience",
            'humor': "Share appropriate developer/tech humor",
            'behind_the_scenes': f"Share behind-the-scenes content from {brand_info.get('name', brand)}"
        }
        
        content_instruction = content_types.get(content_type, content_types['educational'])
        
        user_prompt = f"""{content_instruction}

Requirements:
- Keep under {char_limit} characters
- Engaging and {brand_config.get('voice', {}).get('style', ['professional'])[0]} tone
- Include relevant hashtags: {hashtag_str}
- Include a subtle call-to-action if appropriate
- Make it platform-appropriate for {platform}
- Focus on value for the audience"""
        
        content = await self.ollama.generate(
            model=self.ai_config['ollama']['default_model'],
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.8,  # Higher temperature for creativity
            max_tokens=150
        )
        
        return {
            'content': content.strip(),
            'brand': brand,
            'platform': platform,
            'content_type': content_type,
            'character_count': len(content),
            'generated_at': datetime.now().isoformat(),
            'hashtags': self.extract_hashtags(content),
            'model_used': self.ai_config['ollama']['default_model']
        }
    
    async def generate_outreach_email(self, brand: str, recipient_info: Dict[str, Any], campaign_type: str = "general") -> Dict[str, Any]:
        """Generate personalized outreach email"""
        
        if brand not in self.brand_configs:
            raise ValueError(f"Unknown brand: {brand}")
        
        brand_config = self.brand_configs[brand]
        brand_info = brand_config.get('brand', {})
        voice_info = brand_config.get('voice', {})
        messaging = brand_config.get('key_messages', {})
        
        system_prompt = f"""You are writing a professional outreach email for {brand_info.get('name', brand)}.

Brand: {brand_info.get('name', brand)} - {brand_info.get('description', 'Technology solutions')}
Tone: Professional, helpful, and {voice_info.get('tone', ['professional'])[0]}
Value Proposition: {messaging.get('primary', 'Innovation in technology')}"""
        
        # Extract recipient information
        recipient_name = recipient_info.get('name', 'there')
        company = recipient_info.get('company', 'your organization')
        industry = recipient_info.get('industry', 'your industry')
        pain_points = recipient_info.get('pain_points', ['development challenges'])
        
        user_prompt = f"""Write a personalized outreach email with the following details:

Recipient: {recipient_name}
Company: {company}
Industry/Focus: {industry}
Likely Pain Points: {', '.join(pain_points) if isinstance(pain_points, list) else pain_points}
Campaign Type: {campaign_type}

Email Requirements:
- Professional but friendly tone
- Personalize with recipient and company information
- Address their likely pain points
- Clearly explain how {brand_info.get('name', brand)} can help
- Include specific value proposition
- Keep to 150-250 words
- Include clear call-to-action
- Professional email structure with subject line

Make it feel personal and valuable, not like a mass email."""
        
        content = await self.ollama.generate(
            model=self.ai_config['ollama']['default_model'],
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.6,  # Lower temperature for professional communication
            max_tokens=400
        )
        
        # Extract subject line (usually first line)
        lines = content.split('\n')
        subject_line = ""
        email_body = content
        
        for i, line in enumerate(lines):
            if line.lower().startswith('subject:'):
                subject_line = line.replace('Subject:', '').strip()
                email_body = '\n'.join(lines[i+1:]).strip()
                break
        
        if not subject_line:
            # Generate a subject line if not found
            subject_line = f"Partnership opportunity - {brand_config['name']} & {company}"
        
        return {
            'subject': subject_line,
            'body': email_body,
            'brand': brand,
            'recipient_name': recipient_name,
            'recipient_company': company,
            'campaign_type': campaign_type,
            'generated_at': datetime.now().isoformat(),
            'word_count': len(email_body.split()),
            'model_used': self.ai_config['ollama']['default_model']
        }
    
    def extract_hashtags(self, content: str) -> List[str]:
        """Extract hashtags from content"""
        import re
        hashtags = re.findall(r'#\w+', content)
        return hashtags

# Test and example usage
async def test_ollama_integration():
    """Test the Ollama integration"""
    print("🧠 Testing Ollama AI Integration")
    print("=" * 50)
    
    # Test connection
    client = OllamaClient()
    connected = await client.test_connection()
    
    if not connected:
        print(f"❌ Cannot connect to Ollama. Make sure it's running at {_get_ai_config('OLLAMA_HOST', 'http://localhost:11434')}")
        return
    
    # List available models
    models = await client.list_models()
    print(f"\n📋 Available Models:")
    for model in models:
        print(f"  • {model.get('name', 'Unknown')}")
    
    # Test content generation
    generator = AIContentGenerator()
    
    print(f"\n📝 Testing Blog Post Generation...")
    blog_post = await generator.generate_blog_post(
        brand="buildly",
        topic="AI-Powered Development Workflows",
        target_audience="developers and product managers"
    )
    
    print(f"Title: {blog_post['title']}")
    print(f"Word Count: {blog_post['word_count']}")
    print(f"First 200 chars: {blog_post['content'][:200]}...")
    
    print(f"\n📱 Testing Social Media Generation...")
    social_post = await generator.generate_social_post(
        brand="foundry",
        content_type="educational",
        platform="twitter"
    )
    
    print(f"Platform: {social_post['platform']}")
    print(f"Content: {social_post['content']}")
    print(f"Character Count: {social_post['character_count']}")
    
    print(f"\n📧 Testing Outreach Email Generation...")
    outreach_email = await generator.generate_outreach_email(
        brand="open_build",
        recipient_info={
            'name': 'Sarah Johnson',
            'company': 'DevTools Inc',
            'industry': 'Developer Tools',
            'pain_points': ['scaling development teams', 'open source management']
        },
        campaign_type="partnership"
    )
    
    print(f"Subject: {outreach_email['subject']}")
    print(f"Body (first 200 chars): {outreach_email['body'][:200]}...")
    print(f"Word Count: {outreach_email['word_count']}")
    
    print("\n✅ Ollama integration test complete!")

if __name__ == "__main__":
    asyncio.run(test_ollama_integration())
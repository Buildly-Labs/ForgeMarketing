#!/usr/bin/env python3
"""
Daily Marketing Automation
Centralized daily automation for all marketing brands
Replaces individual website automation scripts
"""

import sys
import logging
from datetime import datetime, timezone
from pathlib import Path
import asyncio

# Setup paths and logging
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from config.brand_loader import get_all_brands

logs_dir = project_root / 'logs'
logs_dir.mkdir(exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(logs_dir / 'marketing_automation.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('DailyAutomation')


def _get_active_brands():
    """Load active brands from database, with a conservative fallback set."""
    brands = get_all_brands(active_only=True)
    if brands:
        return brands
    return ['open_build', 'radical_therapy']

async def run_daily_automation():
    """Run daily marketing automation for all brands"""
    logger.info("🚀 Starting daily marketing automation")
    
    try:
        # Import AI generator
        from automation.ai.ollama_integration import AIContentGenerator
        ai_generator = AIContentGenerator()
        
        brands = _get_active_brands()
        if not brands:
            logger.warning("No active brands configured; skipping daily automation run")
            return {}
        results = {}
        
        for brand in brands:
            logger.info(f"📊 Processing brand: {brand}")
            
            try:
                # Generate daily social media content
                social_result = await ai_generator.generate_social_post(
                    brand=brand,
                    content_type='daily_tip',
                    platform='linkedin'
                )
                
                # Generate weekly blog idea (only on Mondays)
                if datetime.now().weekday() == 0:  # Monday
                    blog_result = await ai_generator.generate_blog_post(
                        brand=brand,
                        topic='Weekly Industry Insights',
                        target_audience='professionals'
                    )
                    results[f'{brand}_blog'] = blog_result
                
                results[f'{brand}_social'] = social_result
                logger.info(f"✅ Completed content generation for {brand}")
                
            except Exception as e:
                logger.error(f"❌ Error processing {brand}: {e}")
                results[f'{brand}_error'] = str(e)
        
        # Log summary
        successful_brands = len([k for k in results.keys() if not k.endswith('_error')])
        logger.info(f"📈 Daily automation complete: {successful_brands} successful operations")
        
        return results
        
    except Exception as e:
        logger.error(f"❌ Critical error in daily automation: {e}")
        return {'critical_error': str(e)}

async def main():
    """Main execution function"""
    start_time = datetime.now(timezone.utc)
    logger.info(f"⏰ Daily automation started at {start_time}")
    
    results = await run_daily_automation()
    
    end_time = datetime.now(timezone.utc)
    duration = (end_time - start_time).total_seconds()
    
    logger.info(f"✨ Daily automation completed in {duration:.2f} seconds")
    logger.info(f"📋 Results summary: {len(results)} operations completed")
    
    return results

if __name__ == '__main__':
    try:
        results = asyncio.run(main())
        # Exit with error code if there were critical errors
        if 'critical_error' in results:
            sys.exit(1)
    except KeyboardInterrupt:
        logger.info("🛑 Daily automation interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"💥 Unexpected error: {e}")
        sys.exit(1)
#!/usr/bin/env python3
"""
Unified Outreach Automation Runner
Runs unified discovery and outreach campaigns across configured active brands.
"""

import sys
import subprocess
import logging
import asyncio
from datetime import datetime
from pathlib import Path

# Get project root directory
project_root = Path(__file__).parent.parent

# Add project root to Python path for imports
sys.path.insert(0, str(project_root))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(project_root / 'logs' / 'unified_outreach.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('UnifiedOutreach')

from config.brand_loader import get_all_brands
from automation.multi_brand_outreach import MultiBrandOutreachCampaign, BRAND_DISCOVERY_STRATEGIES


def _supported_active_brands():
    """Return active brands that have discovery/outreach strategies."""
    active_brands = get_all_brands(active_only=True)
    supported = [b for b in active_brands if b in BRAND_DISCOVERY_STRATEGIES]
    return supported or list(BRAND_DISCOVERY_STRATEGIES.keys())


def run_daily_marketing_automation() -> bool:
    """Run centralized daily content automation."""
    try:
        script_path = project_root / 'automation' / 'websites' / 'daily_automation.py'
        if not script_path.exists():
            logger.warning(f"⚠️ Daily automation script not found: {script_path}")
            return False

        logger.info("🚀 Running centralized daily marketing automation...")
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            cwd=str(project_root)
        )

        if result.returncode == 0:
            logger.info("✅ Daily marketing automation completed successfully")
            return True

        logger.error(f"❌ Daily marketing automation failed: {result.stderr}")
        return False
    except Exception as e:
        logger.error(f"❌ Error running daily marketing automation: {e}")
        return False


def run_discovery() -> bool:
    """Run discovery across all supported brands."""
    try:
        logger.info("🔍 Running discovery across all supported brands...")
        campaign = MultiBrandOutreachCampaign()
        results = asyncio.run(campaign.run_discovery_for_all_brands())
        total = sum(results.values())
        logger.info(f"✅ Discovery complete: {total} targets discovered")
        return True
    except Exception as e:
        logger.error(f"❌ Error running discovery: {e}")
        return False


def run_unified_outreach() -> bool:
    """Run outreach campaigns for all supported active brands."""
    try:
        brands = _supported_active_brands()
        if not brands:
            logger.warning("⚠️ No supported active brands found for outreach")
            return False

        logger.info(f"🚀 Running unified outreach campaigns for {len(brands)} brand(s)...")
        outreach = MultiBrandOutreachCampaign()

        success_count = 0
        for brand in brands:
            result = outreach.execute_brand_campaign(brand_key=brand, target_count=3, campaign_type='general')
            if result.get('success'):
                success_count += 1

        logger.info(f"✅ Unified outreach completed: {success_count}/{len(brands)} brands successful")
        return success_count > 0
    except Exception as e:
        logger.error(f"❌ Error running unified outreach: {e}")
        return False


def send_execution_report(success_results: dict):
    """Send execution report using configured daily analytics emailer."""
    try:
        from automation.daily_analytics_emailer import DailyAnalyticsEmailer

        emailer = DailyAnalyticsEmailer()

        # Reuse existing summary path rather than maintaining a custom mail implementation.
        sent = emailer.send_multi_brand_summary(dry_run=False)
        if sent:
            logger.info("📧 Execution report sent successfully")
        else:
            logger.warning("⚠️ Execution report was not sent (emailer returned False)")
    except Exception as e:
        logger.error(f"❌ Error sending execution report: {e}")


def main():
    """Main unified outreach automation runner"""
    logger.info("🎯 Starting unified marketing automation pipeline")

    # Track execution results
    execution_results = {}

    # Run centralized workflows
    execution_results['Daily Automation'] = run_daily_marketing_automation()
    execution_results['Discovery'] = run_discovery()
    # Run unified outreach campaign
    execution_results['Unified Outreach'] = run_unified_outreach()

    # Calculate overall success
    successful_count = sum(execution_results.values())
    total_count = len(execution_results)

    # Send execution report
    send_execution_report(execution_results)

    # Log final results
    if successful_count == total_count:
        logger.info(f"🎉 All automations completed successfully ({successful_count}/{total_count})")
        sys.exit(0)
    elif successful_count > 0:
        logger.warning(f"⚠️ Partial success: {successful_count}/{total_count} automations completed")
        sys.exit(1)
    else:
        logger.error(f"❌ All automations failed ({successful_count}/{total_count})")
        sys.exit(2)

if __name__ == "__main__":
    main()
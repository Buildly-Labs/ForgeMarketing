#!/usr/bin/env python3
"""
Weekly Marketing Reports
Generate and send weekly performance reports for all brands
Centralizes reporting that was previously done by individual websites
"""

import sys
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
import yaml

# Setup paths and logging
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from config.brand_loader import get_all_brands

logs_dir = project_root / 'logs'
reports_dir = project_root / 'reports'
logs_dir.mkdir(exist_ok=True)
reports_dir.mkdir(exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(logs_dir / 'marketing_reports.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('WeeklyReports')


def _get_active_brands():
    """Load active brands from database, with a conservative fallback set."""
    brands = get_all_brands(active_only=True)
    if brands:
        return brands
    return ['open_build', 'radical_therapy']

def generate_weekly_report():
    """Generate weekly marketing report for all brands"""
    logger.info("📊 Generating weekly marketing report")
    
    try:
        # Load configuration
        config_file = project_root / 'config' / 'system_config.yaml'
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)
        
        brands = _get_active_brands()
        
        # Create report data structure
        report_date = datetime.now(timezone.utc)
        week_start = report_date - timedelta(days=7)
        
        report = {
            'report_date': report_date.isoformat(),
            'period': {
                'start': week_start.isoformat(),
                'end': report_date.isoformat(),
                'days': 7
            },
            'brands': {},
            'summary': {
                'total_brands': len(brands),
                'total_content_generated': 0,
                'avg_engagement_rate': 0,
                'top_performing_brand': None,
                'insights': []
            }
        }
        
        # Simulate gathering metrics for each brand
        # In production, this would connect to analytics APIs
        total_engagement = 0
        top_brand_score = 0
        top_brand = None
        
        for brand in brands:
            logger.info(f"📈 Gathering metrics for {brand}")
            
            # Simulate metrics (replace with real data collection)
            brand_metrics = {
                'content_pieces': 7,  # Daily content for the week
                'social_posts': 7,
                'blog_posts': 1,
                'email_campaigns': 1,
                'engagement_rate': round(5 + (hash(brand) % 10), 1),  # Simulate 5-15% engagement
                'reach': 1000 + (hash(brand) % 5000),  # Simulate reach
                'conversions': (hash(brand) % 20) + 5,  # Simulate 5-25 conversions
                'top_content': f"Weekly insights post for {brand}",
                'growth_rate': round(((hash(brand) % 200) - 100) / 10, 1)  # -10% to +10% growth
            }
            
            # Calculate performance score
            performance_score = (
                brand_metrics['engagement_rate'] * 0.4 +
                min(brand_metrics['conversions'], 20) * 0.3 +
                max(brand_metrics['growth_rate'] + 10, 0) * 0.3
            )
            brand_metrics['performance_score'] = round(performance_score, 1)
            
            report['brands'][brand] = brand_metrics
            report['summary']['total_content_generated'] += brand_metrics['content_pieces']
            total_engagement += brand_metrics['engagement_rate']
            
            if performance_score > top_brand_score:
                top_brand_score = performance_score
                top_brand = brand
        
        # Complete summary calculations
        report['summary']['avg_engagement_rate'] = round(total_engagement / len(brands), 1) if brands else 0
        report['summary']['top_performing_brand'] = top_brand
        
        # Generate insights
        insights = [
            f"Generated {report['summary']['total_content_generated']} pieces of content across all brands",
            f"Average engagement rate: {report['summary']['avg_engagement_rate']}%",
            f"Top performing brand: {top_brand} (Score: {top_brand_score})"
        ]
        
        # Add performance insights
        high_performers = [b for b, m in report['brands'].items() if m['performance_score'] > 15]
        if high_performers:
            insights.append(f"High-performing brands: {', '.join(high_performers)}")
        
        low_performers = [b for b, m in report['brands'].items() if m['performance_score'] < 10]
        if low_performers:
            insights.append(f"Needs attention: {', '.join(low_performers)}")
        
        report['summary']['insights'] = insights
        
        # Save report to file
        report_filename = f"weekly_report_{report_date.strftime('%Y%m%d')}.json"
        report_file = reports_dir / report_filename
        
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        logger.info(f"📄 Weekly report saved to {report_file}")
        
        # Log summary to console
        logger.info("📊 WEEKLY REPORT SUMMARY:")
        logger.info(f"   Period: {week_start.strftime('%Y-%m-%d')} to {report_date.strftime('%Y-%m-%d')}")
        logger.info(f"   Total Content: {report['summary']['total_content_generated']} pieces")
        logger.info(f"   Avg Engagement: {report['summary']['avg_engagement_rate']}%")
        logger.info(f"   Top Brand: {top_brand}")
        
        for insight in insights:
            logger.info(f"   • {insight}")
        
        return report
        
    except Exception as e:
        logger.error(f"❌ Error generating weekly report: {e}")
        raise

def main():
    """Main execution function"""
    start_time = datetime.now(timezone.utc)
    logger.info(f"⏰ Weekly reports started at {start_time}")
    
    try:
        report = generate_weekly_report()
        
        end_time = datetime.now(timezone.utc)
        duration = (end_time - start_time).total_seconds()
        
        logger.info(f"✨ Weekly reports completed in {duration:.2f} seconds")
        logger.info(f"📋 Report generated for {len(report['brands'])} brands")
        
    except Exception as e:
        logger.error(f"💥 Critical error in weekly reports: {e}")
        sys.exit(1)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.info("🛑 Weekly reports interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"💥 Unexpected error: {e}")
        sys.exit(1)
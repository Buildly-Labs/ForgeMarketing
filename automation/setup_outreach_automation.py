#!/usr/bin/env python3
"""
Automated Outreach & Discovery Scheduler
========================================

Manages automated discovery and outreach campaigns for all brands.
Sets up intelligent scheduling to discover new targets and run
outreach campaigns based on optimal timing and rate limits.
"""

import asyncio
import subprocess
import tempfile
import os
from pathlib import Path
from datetime import datetime, time
import sys

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from automation.multi_brand_outreach import MultiBrandOutreachCampaign, BrandTargetDiscovery, BRAND_DISCOVERY_STRATEGIES
from config.brand_loader import get_all_brands

class OutreachAutomationScheduler:
    """Manages automated outreach and discovery scheduling"""
    
    def __init__(self):
        self.project_root = project_root
        self.outreach_script = self.project_root / 'automation' / 'multi_brand_outreach.py'

    def _scheduled_brands(self):
        """Return brands supported by outreach strategies, preferring configured active brands."""
        strategy_brands = list(BRAND_DISCOVERY_STRATEGIES.keys())
        configured = get_all_brands(active_only=True)
        configured_supported = [b for b in configured if b in strategy_brands]
        return configured_supported or strategy_brands

    def _build_brand_outreach_jobs(self):
        """Create outreach cron entries distributed across weekday time slots."""
        slots = [
            ('30 9', '1-5'),   # Mon-Fri 9:30 AM
            ('0 10', '2,4'),   # Tue/Thu 10:00 AM
            ('30 14', '3,5'),  # Wed/Fri 2:30 PM
        ]
        jobs = []
        for idx, brand in enumerate(self._scheduled_brands()):
            slot_time, day_restriction = slots[idx % len(slots)]
            jobs.append({
                'time': slot_time,
                'day_restriction': day_restriction,
                'command': f'cd "{self.project_root}" && python3 automation/run_brand_outreach.py --brand {brand} --limit 3',
                'description': f'{brand} outreach campaign'
            })
        return jobs
        
    def setup_outreach_crons(self):
        """Set up cron jobs for automated outreach and discovery"""
        
        print("🚀 Setting up automated outreach & discovery schedules...")
        
        # Outreach automation schedules
        cron_jobs = [
            # Discovery phases (find new targets)
            {
                'time': '0 8',  # 8:00 AM daily
                'command': f'cd "{self.project_root}" && python3 -c "import asyncio; from automation.multi_brand_outreach import MultiBrandOutreachCampaign; asyncio.run(MultiBrandOutreachCampaign().run_discovery_for_all_brands())"',
                'description': 'Daily target discovery for all brands'
            },
            # Weekly discovery deep dive (Sundays)
            {
                'time': '0 10',  # 10:00 AM Sundays
                'day_restriction': '0',
                'command': f'cd "{self.project_root}" && python3 -c "import asyncio; from automation.multi_brand_outreach import MultiBrandOutreachCampaign; asyncio.run(MultiBrandOutreachCampaign().run_discovery_for_all_brands())" --extended',
                'description': 'Weekly extended target discovery'
            },
            # Weekly outreach analytics (Sundays)
            {
                'time': '0 17',  # 5:00 PM Sundays
                'day_restriction': '0',
                'command': f'cd "{self.project_root}" && python3 automation/outreach_analytics.py',
                'description': 'Weekly outreach performance report'
            },
            # Influencer discovery (Wednesdays)
            {
                'time': '0 14',  # 2:00 PM Wednesdays
                'day_restriction': '3',
                'command': f'cd "{self.project_root}" && python3 automation/run_influencer_discovery.py --all-brands',
                'description': 'Weekly influencer discovery for all brands'
            },
            # Influencer reports generation (Sundays)
            {
                'time': '30 17',  # 5:30 PM Sundays
                'day_restriction': '0',
                'command': f'cd "{self.project_root}" && python3 automation/influencer_report_generator.py',
                'description': 'Weekly influencer reports generation'
            }
        ]
        cron_jobs[1:1] = self._build_brand_outreach_jobs()
        
        # Get current crontab
        try:
            current_crontab = subprocess.check_output(['crontab', '-l'], text=True)
        except subprocess.CalledProcessError:
            current_crontab = ""
        
        # Create new crontab content
        new_crontab = current_crontab
        
        # Add header if not exists
        if "# Multi-Brand Outreach Automation" not in current_crontab:
            new_crontab += "\n# Multi-Brand Outreach Automation\n"
        
        # Add each cron job
        for job in cron_jobs:
            # Build cron expression (minute hour day_of_month month day_of_week)
            day_of_week = job.get('day_restriction', '*')
            cron_line = f"{job['time']} * * {day_of_week} {job['command']} # {job['description']}"
            
            if cron_line not in current_crontab:
                new_crontab += cron_line + "\n"
                print(f"✅ Added: {job['description']}")
            else:
                print(f"📋 Already exists: {job['description']}")
        
        # Write new crontab
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.cron') as f:
            f.write(new_crontab)
            temp_file = f.name
        
        try:
            subprocess.run(['crontab', temp_file], check=True)
            print("✅ Crontab updated successfully")
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to update crontab: {e}")
        finally:
            os.unlink(temp_file)
    
    def show_current_schedule(self):
        """Display current outreach automation schedule"""
        print("📅 Current Outreach & Discovery Schedule")
        print("=" * 50)

        schedule_info = [("Daily 8:00 AM", "🔍 Target Discovery", "All brands")]
        slots = [
            ("Mon-Fri 9:30 AM", "📨 Brand Outreach", "3 contacts"),
            ("Tue/Thu 10:00 AM", "📨 Brand Outreach", "3 contacts"),
            ("Wed/Fri 2:30 PM", "📨 Brand Outreach", "3 contacts"),
        ]
        for idx, brand in enumerate(self._scheduled_brands()):
            time_str, task, details = slots[idx % len(slots)]
            schedule_info.append((time_str, f"{task} ({brand})", details))
        schedule_info.extend([
            ("Sunday 10:00 AM", "🔍 Extended Discovery", "All brands"),
            ("Sunday 5:00 PM", "📊 Weekly Analytics", "Performance reports")
        ])
        
        for time_str, task, details in schedule_info:
            print(f"{time_str:<20} {task:<25} {details}")
        
        print("\n📋 Rate Limits & Best Practices:")
        print("   • Maximum 15 emails per brand per day")
        print("   • 7-day minimum between contacts to same target")
        print("   • Discovery runs before outreach for fresh targets")
        print("   • Weekday focus for B2B, mixed timing for developers")
    
    async def test_outreach_system(self):
        """Test the outreach and discovery system"""
        print("🧪 Testing Outreach & Discovery System")
        print("=" * 40)
        
        # Test discovery
        print("\n🔍 Testing Target Discovery...")
        campaign = MultiBrandOutreachCampaign()
        
        try:
            test_brand = self._scheduled_brands()[0]
            # Test discovery for one brand
            discovery = BrandTargetDiscovery(test_brand)
            targets = await discovery.discover_targets(max_targets=3)
            print(f"✅ Discovery test passed: {len(targets)} targets found")
            
            # Test campaign target retrieval
            campaign_targets = campaign.get_campaign_targets(test_brand, limit=2)
            print(f"✅ Campaign targets: {len(campaign_targets)} ready for outreach")
            
            print("\n📊 System Status:")
            print(f"   • Database: ✅ Connected")
            print(f"   • Discovery: ✅ Working")
            print(f"   • Target Storage: ✅ Working")
            print(f"   • Campaign Management: ✅ Working")
            
        except Exception as e:
            print(f"❌ Test failed: {e}")
            return False
        
        return True

def main():
    """Main scheduler interface"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Outreach & Discovery Automation Scheduler')
    parser.add_argument('--setup-crons', action='store_true', help='Setup cron jobs')
    parser.add_argument('--show-schedule', action='store_true', help='Show current schedule')
    parser.add_argument('--test', action='store_true', help='Test outreach system')
    parser.add_argument('--run-discovery', action='store_true', help='Run discovery now')
    
    args = parser.parse_args()
    
    scheduler = OutreachAutomationScheduler()
    
    if args.setup_crons:
        scheduler.setup_outreach_crons()
    elif args.show_schedule:
        scheduler.show_current_schedule()
    elif args.test:
        asyncio.run(scheduler.test_outreach_system())
    elif args.run_discovery:
        # Run discovery now
        async def run_now():
            campaign = MultiBrandOutreachCampaign()
            results = await campaign.run_discovery_for_all_brands()
            print(f"✅ Discovery completed: {sum(results.values())} total targets")
        
        asyncio.run(run_now())
    else:
        # Show default information
        print("🚀 Multi-Brand Outreach & Discovery Automation")
        print("=" * 50)
        print("📅 Intelligent Scheduling:")
        print("   • Daily target discovery at 8:00 AM")
        print("   • Brand-specific outreach timing")
        print("   • Rate-limited and ethical automation")
        print("   • Weekly performance analytics")
        print("")
        print("Available commands:")
        print("  --setup-crons    Setup automated schedules")
        print("  --show-schedule  Display current schedule") 
        print("  --test          Test the system")
        print("  --run-discovery Run discovery now")

if __name__ == '__main__':
    main()
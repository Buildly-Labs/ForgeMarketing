#!/usr/bin/env python3
"""
Daily Email Automation Setup
============================

Sets up automated daily analytics emails for all brands.
Configures cron jobs to send reports at optimal times.
"""

import os
import subprocess
from pathlib import Path
import tempfile

from config.brand_loader import get_all_brands

def setup_daily_email_crons():
    """Set up cron jobs for daily analytics emails"""
    
    project_root = Path(__file__).parent.parent
    script_path = project_root / 'automation' / 'daily_analytics_emailer.py'
    
    # Daily email schedules (all times in 24-hour format)
    cron_jobs = [
        {
            'time': '0 9',  # 9:00 AM daily
            'command': f'cd "{project_root}" && python3 "{script_path}"',
            'description': 'Daily analytics reports for all brands'
        },
        {
            'time': '0 17',  # 5:00 PM daily  
            'command': f'cd "{project_root}" && python3 "{script_path}" --summary-only',
            'description': 'Daily multi-brand summary report'
        }
    ]
    
    print("📧 Setting up daily analytics email automation...")
    
    # Get current crontab
    try:
        current_crontab = subprocess.check_output(['crontab', '-l'], text=True)
    except subprocess.CalledProcessError:
        current_crontab = ""
    
    # Create new crontab content
    new_crontab = current_crontab
    
    # Add header if not exists
    if "# Marketing Analytics Daily Emails" not in current_crontab:
        new_crontab += "\n# Marketing Analytics Daily Emails\n"
    
    # Add each cron job
    for job in cron_jobs:
        cron_line = f"{job['time']} * * * {job['command']} # {job['description']}"
        
        if cron_line not in current_crontab:
            new_crontab += cron_line + "\n"
            print(f"✅ Added: {job['description']} at {job['time']}")
        else:
            print(f"📋 Already exists: {job['description']}")
    
    # Write new crontab
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.cron') as f:
        f.write(new_crontab)
        temp_file = f.name
    
    try:
        subprocess.run(['crontab', temp_file], check=True)
        print("✅ Crontab updated successfully")
        
        # Show current crontab
        print("\n📋 Current crontab:")
        subprocess.run(['crontab', '-l'])
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to update crontab: {e}")
    finally:
        os.unlink(temp_file)

def test_email_setup():
    """Test the email setup with dry run"""
    print("\n🧪 Testing daily email setup...")
    
    project_root = Path(__file__).parent.parent
    script_path = project_root / 'automation' / 'daily_analytics_emailer.py'
    
    # Test dry run
    try:
        active_brands = get_all_brands(active_only=True)
        test_cmd = ['python3', str(script_path), '--dry-run']
        if active_brands:
            test_cmd.extend(['--brand', active_brands[0]])
        else:
            test_cmd.append('--summary-only')

        result = subprocess.run(test_cmd, cwd=project_root, capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ Email system test passed")
            print(result.stdout)
        else:
            print("❌ Email system test failed")
            print(result.stderr)
            
    except Exception as e:
        print(f"❌ Test failed: {e}")

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Setup daily analytics email automation')
    parser.add_argument('--setup-crons', action='store_true', help='Setup cron jobs')
    parser.add_argument('--test', action='store_true', help='Test email system')
    parser.add_argument('--show-schedule', action='store_true', help='Show current schedule')
    
    args = parser.parse_args()
    
    if args.setup_crons:
        setup_daily_email_crons()
    elif args.test:
        test_email_setup()  
    elif args.show_schedule:
        print("📋 Current crontab schedule:")
        subprocess.run(['crontab', '-l'])
    else:
        # Default: show what would be set up
        print("📧 Daily Analytics Email Schedule")
        print("=" * 40)
        print("🌅 9:00 AM  - Brand analytics reports")
        print("🌆 5:00 PM  - Multi-brand summary")
        print("")
        print("To setup: python3 setup_daily_emails.py --setup-crons")
        print("To test:  python3 setup_daily_emails.py --test")
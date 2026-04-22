#!/usr/bin/env python3
"""
Centralized Cron Job Management System
Integrates existing website automation scripts into unified dashboard control
"""

import os
import subprocess
import sys
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional
import sqlite3
import logging
from dataclasses import dataclass

# Get project root directory
project_root = Path(__file__).parent.parent

# Add project root to Python path for imports
sys.path.insert(0, str(project_root))

@dataclass
class CronJob:
    """Represents a managed cron job"""
    id: str
    name: str
    brand: str
    script_path: str
    schedule: str
    description: str
    status: str = 'active'
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    success_count: int = 0
    failure_count: int = 0
    last_output: str = ''
    created_at: datetime = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()

class CentralizedCronManager:
    """Manages all marketing automation cron jobs from a central location"""
    
    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = str(project_root / 'data' / 'cron_management.db')
        
        self.db_path = db_path
        self.logger = self._setup_logger()
        self.init_database()
        
        # Define known automation scripts
        self.automation_scripts = {
            'foundry_daily': {
                'name': 'Foundry Daily Automation',
                'brand': 'Foundry',
                'script_path': str(project_root / 'automation' / 'websites' / 'foundry' / 'daily_automation.py'),
                'schedule': '0 8 * * *',  # Daily at 8 AM
                'description': 'Daily outreach pipeline automation for Foundry brand'
            },
            'open_build_daily': {
                'name': 'Open Build Daily Automation',
                'brand': 'Open Build',
                'script_path': str(project_root / 'open-build-new-website' / 'scripts' / 'run_daily_automation.sh'),
                'schedule': '0 9 * * *',  # Daily at 9 AM
                'description': 'Daily automation for Open Build website and outreach'
            },
            'unified_outreach': {
                'name': 'Multi-Brand Outreach Campaign',
                'brand': 'All Brands',
                'script_path': str(project_root / 'automation' / 'run_unified_outreach.py'),
                'schedule': '0 10 * * *',  # Daily at 10 AM
                'description': 'Unified outreach campaign across all brands'
            },
            'weekly_analytics': {
                'name': 'Weekly Analytics Report',
                'brand': 'All Brands',
                'script_path': str(project_root / 'automation' / 'weekly_analytics_report.py'),
                'schedule': '0 9 * * 1',  # Mondays at 9 AM
                'description': 'Weekly analytics and performance report generation'
            },
            'influencer_discovery': {
                'name': 'Influencer Discovery (All Brands)',
                'brand': 'All Brands',
                'script_path': str(project_root / 'automation' / 'run_influencer_discovery.py'),
                'schedule': '0 6 * * 3',  # Wednesdays at 6 AM
                'description': 'Automated influencer discovery across all platforms for all brands',
                'args': ['--all-brands', '--max-per-platform', '10']
            },
            'influencer_enrichment': {
                'name': 'Influencer Enrichment (All Brands)',
                'brand': 'All Brands',
                'script_path': str(project_root / 'automation' / 'influencer_enrichment.py'),
                'schedule': '0 7 * * 1,4',  # Mondays & Thursdays at 7 AM
                'description': 'Enrich influencer profiles with content, contacts, and updated metrics',
                'args': ['--all', '--max', '50']
            }
        }
    
    def _setup_logger(self):
        """Setup logging for cron manager"""
        logger = logging.getLogger('CronManager')
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        return logger
    
    def init_database(self):
        """Initialize the cron management database"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS cron_jobs (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    brand TEXT NOT NULL,
                    script_path TEXT NOT NULL,
                    schedule TEXT NOT NULL,
                    description TEXT,
                    status TEXT DEFAULT 'active',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS cron_executions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cron_job_id TEXT NOT NULL,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    status TEXT,
                    output TEXT,
                    error_message TEXT,
                    FOREIGN KEY (cron_job_id) REFERENCES cron_jobs (id)
                )
            ''')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS cron_status (
                    cron_job_id TEXT PRIMARY KEY,
                    last_run TIMESTAMP,
                    next_run TIMESTAMP,
                    success_count INTEGER DEFAULT 0,
                    failure_count INTEGER DEFAULT 0,
                    last_output TEXT,
                    FOREIGN KEY (cron_job_id) REFERENCES cron_jobs (id)
                )
            ''')
            
            conn.commit()
        
        self.logger.info("✅ Cron management database initialized")
    
    def register_automation_scripts(self):
        """Register all known automation scripts in the database"""
        with sqlite3.connect(self.db_path) as conn:
            for script_id, script_info in self.automation_scripts.items():
                # Check if script exists
                existing = conn.execute(
                    'SELECT id FROM cron_jobs WHERE id = ?',
                    (script_id,)
                ).fetchone()
                
                if not existing:
                    # Insert new script
                    conn.execute('''
                        INSERT INTO cron_jobs (id, name, brand, script_path, schedule, description)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (
                        script_id,
                        script_info['name'],
                        script_info['brand'],
                        script_info['script_path'],
                        script_info['schedule'],
                        script_info['description']
                    ))
                    
                    # Initialize status record
                    conn.execute('''
                        INSERT INTO cron_status (cron_job_id, success_count, failure_count)
                        VALUES (?, 0, 0)
                    ''', (script_id,))
                    
                    self.logger.info(f"✅ Registered automation script: {script_info['name']}")
                else:
                    # Update existing script info
                    conn.execute('''
                        UPDATE cron_jobs 
                        SET name = ?, brand = ?, script_path = ?, schedule = ?, description = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    ''', (
                        script_info['name'],
                        script_info['brand'],
                        script_info['script_path'],
                        script_info['schedule'],
                        script_info['description'],
                        script_id
                    ))
            
            conn.commit()
    
    def get_all_cron_jobs(self) -> List[Dict[str, Any]]:
        """Get all registered cron jobs with their current status"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            jobs = conn.execute('''
                SELECT 
                    j.*,
                    s.last_run,
                    s.next_run,
                    s.success_count,
                    s.failure_count,
                    s.last_output
                FROM cron_jobs j
                LEFT JOIN cron_status s ON j.id = s.cron_job_id
                ORDER BY j.name
            ''').fetchall()
            
            return [dict(job) for job in jobs]
    
    def get_system_cron_jobs(self) -> List[Dict[str, Any]]:
        """Get current system cron jobs from crontab"""
        try:
            result = subprocess.run(['crontab', '-l'], capture_output=True, text=True)
            if result.returncode != 0:
                return []
            
            cron_jobs = []
            lines = result.stdout.strip().split('\n')
            
            for line_num, line in enumerate(lines):
                line = line.strip()
                if line and not line.startswith('#'):
                    parts = line.split(None, 5)
                    if len(parts) >= 6:
                        schedule = ' '.join(parts[:5])
                        command = parts[5]
                        
                        cron_jobs.append({
                            'id': f'system_cron_{line_num}',
                            'name': self._extract_job_name(command),
                            'brand': self._extract_brand_from_command(command),
                            'script_path': command,
                            'schedule': schedule,
                            'description': f'System cron: {command[:100]}...',
                            'status': 'active',
                            'source': 'system_cron',
                            'last_run': 'Unknown',
                            'next_run': self._calculate_next_run(parts[:5])
                        })
            
            return cron_jobs
            
        except Exception as e:
            self.logger.error(f"Error getting system cron jobs: {e}")
            return []
    
    def get_combined_cron_status(self) -> Dict[str, Any]:
        """Get combined status of all cron jobs (managed + system)"""
        managed_jobs = self.get_all_cron_jobs()
        system_jobs = self.get_system_cron_jobs()
        
        # Combine and categorize
        all_jobs = []
        
        # Add managed jobs
        for job in managed_jobs:
            job['source'] = 'managed'
            all_jobs.append(job)
        
        # Add system jobs (filter out duplicates with managed jobs)
        managed_paths = {job['script_path'] for job in managed_jobs}
        for job in system_jobs:
            if job['script_path'] not in managed_paths:
                all_jobs.append(job)
        
        # Calculate statistics
        stats = {
            'total_jobs': len(all_jobs),
            'managed_jobs': len(managed_jobs),
            'system_jobs': len(system_jobs),
            'active_jobs': len([j for j in all_jobs if j.get('status') == 'active']),
            'failed_jobs': len([j for j in all_jobs if j.get('status') == 'failed']),
            'success_rate': self._calculate_success_rate(all_jobs)
        }
        
        return {
            'stats': stats,
            'jobs': all_jobs,
            'managed_jobs': managed_jobs,
            'system_jobs': system_jobs
        }
    
    def execute_job(self, job_id: str) -> Dict[str, Any]:
        """Execute a specific cron job manually"""
        job = self.get_job_by_id(job_id)
        if not job:
            return {'success': False, 'error': 'Job not found'}
        
        execution_id = self._start_execution_tracking(job_id)
        
        try:
            script_path = job['script_path']
            
            # Determine how to execute the script
            if script_path.endswith('.py'):
                cmd = ['python3', script_path]
            elif script_path.endswith('.sh'):
                cmd = ['bash', script_path]
            else:
                # Assume it's a direct command
                cmd = script_path.split()
            
            self.logger.info(f"🚀 Executing job {job['name']}: {' '.join(cmd)}")
            
            # Execute with timeout and capture output
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=3600,  # 1 hour timeout
                cwd=str(project_root)
            )
            
            success = result.returncode == 0
            output = result.stdout + result.stderr
            
            # Update execution tracking
            self._complete_execution_tracking(
                execution_id,
                'success' if success else 'failed',
                output,
                None if success else f"Exit code: {result.returncode}"
            )
            
            # Update job status
            self._update_job_status(job_id, success, output)
            
            return {
                'success': success,
                'output': output,
                'exit_code': result.returncode
            }
            
        except subprocess.TimeoutExpired:
            self._complete_execution_tracking(execution_id, 'timeout', '', 'Job timed out after 1 hour')
            return {'success': False, 'error': 'Job timed out after 1 hour'}
        
        except Exception as e:
            self._complete_execution_tracking(execution_id, 'error', '', str(e))
            return {'success': False, 'error': str(e)}
    
    def get_job_by_id(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific job by ID"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            job = conn.execute('''
                SELECT 
                    j.*,
                    s.last_run,
                    s.next_run,
                    s.success_count,
                    s.failure_count,
                    s.last_output
                FROM cron_jobs j
                LEFT JOIN cron_status s ON j.id = s.cron_job_id
                WHERE j.id = ?
            ''', (job_id,)).fetchone()
            
            return dict(job) if job else None
    
    def get_execution_history(self, job_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get execution history for a specific job"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            executions = conn.execute('''
                SELECT * FROM cron_executions
                WHERE cron_job_id = ?
                ORDER BY started_at DESC
                LIMIT ?
            ''', (job_id, limit)).fetchall()
            
            return [dict(exec) for exec in executions]
    
    def _start_execution_tracking(self, job_id: str) -> int:
        """Start tracking a job execution"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                INSERT INTO cron_executions (cron_job_id, started_at, status)
                VALUES (?, ?, 'running')
            ''', (job_id, datetime.now()))
            conn.commit()
            return cursor.lastrowid
    
    def _complete_execution_tracking(self, execution_id: int, status: str, output: str, error_message: str = None):
        """Complete tracking a job execution"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                UPDATE cron_executions
                SET completed_at = ?, status = ?, output = ?, error_message = ?
                WHERE id = ?
            ''', (datetime.now(), status, output, error_message, execution_id))
            conn.commit()
    
    def _update_job_status(self, job_id: str, success: bool, output: str):
        """Update job status after execution"""
        with sqlite3.connect(self.db_path) as conn:
            # Update or insert status record
            conn.execute('''
                INSERT INTO cron_status (cron_job_id, last_run, success_count, failure_count, last_output)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(cron_job_id) DO UPDATE SET
                    last_run = excluded.last_run,
                    success_count = success_count + ?,
                    failure_count = failure_count + ?,
                    last_output = excluded.last_output
            ''', (
                job_id,
                datetime.now(),
                1 if success else 0,
                0 if success else 1,
                output[:1000],  # Limit output length
                1 if success else 0,
                0 if success else 1
            ))
            conn.commit()
    
    def _extract_job_name(self, command: str) -> str:
        """Extract a human-readable job name from a command"""
        # Handle common patterns first
        if 'daily_automation' in command:
            return 'Daily Automation'
        elif 'music_outreach' in command:
            return 'Music Outreach Campaign'
        elif 'news_system.sh collect' in command:
            return 'News Collection System'
        elif 'news_system.sh releases' in command:
            return 'Music Releases Update'
        elif 'news_system.sh generate' in command:
            return 'News Content Generation'
        elif 'news_system.sh update' in command:
            return 'News System Update'
        elif 'outreach' in command:
            return 'Outreach Campaign'
        elif 'analytics' in command:
            return 'Analytics Report'
        elif 'social' in command:
            return 'Social Media Automation'
        else:
            # Extract script name from path, avoiding redirection operators
            parts = command.split()
            # Find the actual script/executable, not redirection parts
            script_part = None
            for part in parts:
                if part.endswith('.py') or part.endswith('.sh'):
                    script_part = part
                    break
            
            if script_part:
                script_name = Path(script_part).stem
                return script_name.replace('_', ' ').title()
            
            # If no script found, look for recognizable command patterns
            for part in parts:
                if not part.startswith('-') and not part.startswith('>') and not part.startswith('2>&1') and '/' in part:
                    script_name = Path(part).stem
                    if script_name and script_name not in ['cd', 'python3', 'python', 'bash', 'sh']:
                        return script_name.replace('_', ' ').title()
            
            return 'System Task'
    
    def _extract_brand_from_command(self, command: str) -> str:
        """Extract brand name from command path"""
        if 'foundry' in command.lower():
            return 'Foundry'
        elif 'open-build' in command.lower() or 'open_build' in command.lower():
            return 'Open Build'
        elif 'buildly' in command.lower():
            return 'Buildly'
        elif 'radical' in command.lower():
            return 'Radical Therapy'
        elif 'oregon' in command.lower():
            return 'Oregon Software'
        else:
            return 'System'
    
    def _calculate_next_run(self, cron_parts: List[str]) -> str:
        """Calculate next run time from cron schedule (simplified)"""
        try:
            # This is a simplified calculation
            # In production, you'd want to use a proper cron parsing library
            minute, hour, day, month, weekday = cron_parts
            
            if minute == '*' and hour == '*':
                return 'Every minute'
            elif hour == '*':
                return f'Every hour at :{minute}'
            elif day == '*' and month == '*' and weekday == '*':
                return f'Daily at {hour}:{minute:0>2}'
            else:
                return f'Scheduled: {" ".join(cron_parts)}'
                
        except Exception:
            return 'Unknown schedule'
    
    def _calculate_success_rate(self, jobs: List[Dict[str, Any]]) -> float:
        """Calculate overall success rate across all jobs"""
        total_successes = sum(job.get('success_count', 0) for job in jobs)
        total_failures = sum(job.get('failure_count', 0) for job in jobs)
        total_executions = total_successes + total_failures
        
        if total_executions == 0:
            return 0.0
        
        return round((total_successes / total_executions) * 100, 1)

if __name__ == "__main__":
    # Command-line interface for cron management
    import argparse
    
    parser = argparse.ArgumentParser(description='Centralized Marketing Automation Cron Manager')
    parser.add_argument('action', choices=['register', 'list', 'execute', 'status'], help='Action to perform')
    parser.add_argument('--job-id', help='Job ID for execute action')
    parser.add_argument('--format', choices=['json', 'table'], default='table', help='Output format')
    
    args = parser.parse_args()
    
    manager = CentralizedCronManager()
    
    if args.action == 'register':
        manager.register_automation_scripts()
        print("✅ All automation scripts registered")
    
    elif args.action == 'list':
        jobs = manager.get_all_cron_jobs()
        if args.format == 'json':
            print(json.dumps(jobs, indent=2, default=str))
        else:
            print(f"{'ID':<20} {'Name':<30} {'Brand':<15} {'Status':<10} {'Last Run':<20}")
            print("-" * 95)
            for job in jobs:
                job_id = str(job.get('id', 'N/A'))
                job_name = str(job.get('name', 'N/A'))
                job_brand = str(job.get('brand', 'N/A'))
                job_status = str(job.get('status', 'N/A'))
                job_last_run = str(job.get('last_run') or 'Never')
                print(f"{job_id:<20} {job_name:<30} {job_brand:<15} {job_status:<10} {job_last_run:<20}")
    
    elif args.action == 'execute':
        if not args.job_id:
            print("Error: --job-id required for execute action")
            sys.exit(1)
        
        result = manager.execute_job(args.job_id)
        if result['success']:
            print(f"✅ Job {args.job_id} executed successfully")
            if result.get('output'):
                print("Output:")
                print(result['output'])
        else:
            print(f"❌ Job {args.job_id} failed: {result.get('error', 'Unknown error')}")
    
    elif args.action == 'status':
        status = manager.get_combined_cron_status()
        if args.format == 'json':
            print(json.dumps(status, indent=2, default=str))
        else:
            stats = status['stats']
            print(f"📊 Cron Job Status Summary")
            print(f"Total Jobs: {stats['total_jobs']}")
            print(f"Managed Jobs: {stats['managed_jobs']}")
            print(f"System Jobs: {stats['system_jobs']}")
            print(f"Active Jobs: {stats['active_jobs']}")
            print(f"Failed Jobs: {stats['failed_jobs']}")
            print(f"Success Rate: {stats['success_rate']}%")
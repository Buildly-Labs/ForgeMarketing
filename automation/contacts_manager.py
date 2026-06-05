#!/usr/bin/env python3
"""
Unified Contacts Management System
==================================

A lightweight CRM system that combines all outreach contacts:
- Email outreach targets
- Social media connections  
- Influencer relationships
- Touch tracking across all channels
- Brand-specific filtering and management

Provides CRUD operations and comprehensive contact analytics.
"""

import sqlite3
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import json
import re
import sys

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

class UnifiedContactsManager:
    """Manages all contacts across email, social media, and influencer channels"""

    @staticmethod
    def _normalize_optional_text(value: Any) -> Optional[str]:
        """Convert blank strings to None so unique indexes don't collide on empty values."""
        if value is None:
            return None
        if isinstance(value, str):
            cleaned = value.strip()
            return cleaned or None
        return value
    
    def __init__(self):
        self.db_path = project_root / 'data' / 'unified_contacts.db'
        self.ensure_database()
    
    def ensure_database(self):
        """Create unified contacts database and tables"""
        self.db_path.parent.mkdir(exist_ok=True)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                -- Main contacts table
                CREATE TABLE IF NOT EXISTS contacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    email TEXT,
                    company TEXT,
                    title TEXT,
                    brand TEXT NOT NULL,
                    contact_type TEXT NOT NULL, -- 'email', 'social', 'influencer'
                    status TEXT DEFAULT 'active', -- 'active', 'inactive', 'bounced', 'unsubscribed'
                    source TEXT, -- 'discovery', 'manual', 'import', 'referral'
                    
                    -- Social media profiles
                    linkedin_url TEXT,
                    twitter_handle TEXT,
                    instagram_handle TEXT,
                    youtube_channel TEXT,
                    website_url TEXT,
                    
                    -- Influencer specific data
                    followers_count INTEGER DEFAULT 0,
                    engagement_rate REAL DEFAULT 0.0,
                    alignment_score REAL DEFAULT 0.0,
                    platform TEXT, -- primary platform for influencers
                    
                    -- Contact metadata
                    tags TEXT, -- JSON array of tags
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_contact_at TIMESTAMP,
                    
                    UNIQUE(email, brand) ON CONFLICT IGNORE
                );
                
                -- Touch history table (all interactions)
                CREATE TABLE IF NOT EXISTS contact_touches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    contact_id INTEGER NOT NULL,
                    touch_type TEXT NOT NULL, -- 'email', 'social_post', 'social_dm', 'call', 'meeting', 'manual'
                    touch_direction TEXT NOT NULL, -- 'outbound', 'inbound'
                    subject TEXT,
                    message TEXT,
                    platform TEXT, -- email, linkedin, twitter, etc.
                    status TEXT, -- 'sent', 'delivered', 'opened', 'clicked', 'replied', 'failed'
                    response_text TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    
                    FOREIGN KEY (contact_id) REFERENCES contacts (id) ON DELETE CASCADE
                );
                
                -- Contact segments/lists
                CREATE TABLE IF NOT EXISTS contact_segments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    brand TEXT NOT NULL,
                    description TEXT,
                    filter_criteria TEXT, -- JSON filter criteria
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    
                    UNIQUE(name, brand)
                );
                
                -- Indexes for performance
                CREATE INDEX IF NOT EXISTS idx_contacts_brand ON contacts(brand);
                CREATE INDEX IF NOT EXISTS idx_contacts_type ON contacts(contact_type);
                CREATE INDEX IF NOT EXISTS idx_contacts_status ON contacts(status);
                CREATE INDEX IF NOT EXISTS idx_contacts_email ON contacts(email);
                CREATE INDEX IF NOT EXISTS idx_touches_contact ON contact_touches(contact_id);
                CREATE INDEX IF NOT EXISTS idx_touches_created ON contact_touches(created_at);
                
                -- Update trigger for contacts
                CREATE TRIGGER IF NOT EXISTS update_contact_timestamp 
                    AFTER UPDATE ON contacts
                    BEGIN
                        UPDATE contacts SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
                    END;
            """)
            # Idempotently add columns introduced after the initial schema
            for col, defn in [
                ('phone',          'TEXT DEFAULT ""'),
                ('bluesky_handle', 'TEXT DEFAULT ""'),
                ('tiktok_handle',  'TEXT DEFAULT ""'),
            ]:
                try:
                    conn.execute(f'ALTER TABLE contacts ADD COLUMN {col} {defn}')
                except Exception:
                    pass  # Column already exists

    def import_existing_data(self):
        """Import existing outreach and influencer data"""
        print("🔄 Importing existing contact data...")
        
        # Import from unified outreach database
        outreach_db = project_root / 'data' / 'unified_outreach.db'
        if outreach_db.exists():
            self._import_outreach_data(outreach_db)
        
        # Import from influencer database
        influencer_db = project_root / 'data' / 'influencer_discovery.db'
        if influencer_db.exists():
            self._import_influencer_data(influencer_db)
        
        print("✅ Contact data import complete")
    
    def _import_outreach_data(self, outreach_db_path: Path):
        """Import email outreach targets and logs"""
        with sqlite3.connect(outreach_db_path) as outreach_conn:
            # Get targets
            targets = outreach_conn.execute("""
                SELECT COALESCE(contact_name, name) as name, email, company_name, contact_role, brand, created_at 
                FROM unified_targets
                WHERE email IS NOT NULL
            """).fetchall()
            
            # Get outreach logs
            logs = outreach_conn.execute("""
                SELECT ol.email_address, ol.brand, ol.subject, ol.message_template, 
                       ol.status, ol.delivery_time, ol.response_received, ol.response_content,
                       t.contact_name, t.name
                FROM unified_outreach_log ol
                LEFT JOIN unified_targets t ON ol.target_id = t.id
                WHERE ol.email_address IS NOT NULL
            """).fetchall()
        
        with sqlite3.connect(self.db_path) as conn:
            # Import targets as contacts
            for name, email, company, title, brand, created_at in targets:
                if name and email:  # Only import if we have both name and email
                    conn.execute("""
                        INSERT OR REPLACE INTO contacts 
                        (name, email, company, title, brand, contact_type, source, created_at)
                        VALUES (?, ?, ?, ?, ?, 'email', 'discovery', ?)
                    """, (name, email, company, title, brand, created_at))
            
            # Import outreach logs as touches
            for (target_email, brand, subject, message_template, 
                 status, delivery_time, response_received, response_content,
                 contact_name, target_name) in logs:
                
                if not target_email:
                    continue
                
                # Find contact ID
                contact = conn.execute("""
                    SELECT id FROM contacts WHERE email = ? AND brand = ?
                """, (target_email, brand)).fetchone()
                
                if contact:
                    contact_id = contact[0]
                    
                    # Add outbound touch
                    conn.execute("""
                        INSERT INTO contact_touches 
                        (contact_id, touch_type, touch_direction, subject, message, 
                         platform, status, created_at)
                        VALUES (?, 'email', 'outbound', ?, ?, 'email', ?, ?)
                    """, (contact_id, subject, message_template, status, delivery_time))
                    
                    # Add inbound response if exists
                    if response_received and response_content:
                        conn.execute("""
                            INSERT INTO contact_touches 
                            (contact_id, touch_type, touch_direction, message, 
                             platform, status, created_at)
                            VALUES (?, 'email', 'inbound', ?, 'email', 'received', ?)
                        """, (contact_id, response_content, response_received))
    
    def _import_influencer_data(self, influencer_db_path: Path):
        """Import influencer profiles"""
        with sqlite3.connect(influencer_db_path) as inf_conn:
            influencers = inf_conn.execute("""
                SELECT name, primary_platform, brand, brand_alignment_score, 
                       total_reach, avg_engagement_rate, contact_email, 
                       website, bio_summary, discovery_date
                FROM influencers
            """).fetchall()
        
        with sqlite3.connect(self.db_path) as conn:
            for (name, platform, brand, alignment_score, total_reach,
                 engagement_rate, contact_email, website, bio_summary, created_at) in influencers:
                
                # Map platform to appropriate social media fields
                linkedin_url = website if platform == 'linkedin' else None
                twitter_handle = name if platform == 'twitter' else None
                instagram_handle = name if platform == 'instagram' else None
                youtube_channel = website if platform == 'youtube' else None
                
                conn.execute("""
                    INSERT OR REPLACE INTO contacts 
                    (name, email, brand, contact_type, source, platform, followers_count,
                     engagement_rate, alignment_score, linkedin_url, twitter_handle,
                     instagram_handle, youtube_channel, website_url, notes, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (name, contact_email, brand, 'influencer', 'discovery', platform, total_reach, 
                      engagement_rate, alignment_score, linkedin_url, twitter_handle, 
                      instagram_handle, youtube_channel, website, bio_summary, created_at))
    
    def get_contacts(self, brand: str = None, contact_type: str = None, 
                    status: str = None, search: str = None, 
                    limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Get filtered list of contacts"""
        
        query = """
            SELECT c.*, 
                   COUNT(ct.id) as total_touches,
                   MAX(ct.created_at) as last_touch_at,
                   COUNT(CASE WHEN ct.touch_direction = 'inbound' THEN 1 END) as response_count
            FROM contacts c
            LEFT JOIN contact_touches ct ON c.id = ct.contact_id
            WHERE 1=1
        """
        params = []
        
        if brand:
            query += " AND c.brand = ?"
            params.append(brand)
        
        if contact_type:
            query += " AND c.contact_type = ?"
            params.append(contact_type)
        
        if status:
            query += " AND c.status = ?"
            params.append(status)
        
        if search:
            query += " AND (c.name LIKE ? OR c.email LIKE ? OR c.company LIKE ?)"
            search_term = f"%{search}%"
            params.extend([search_term, search_term, search_term])
        
        query += " GROUP BY c.id ORDER BY c.updated_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()
            
            contacts = []
            for row in rows:
                contact = dict(row)
                # Parse JSON fields
                if contact['tags']:
                    try:
                        contact['tags'] = json.loads(contact['tags'])
                    except:
                        contact['tags'] = []
                else:
                    contact['tags'] = []
                
                contacts.append(contact)
            
            return contacts
    
    def get_contact(self, contact_id: int) -> Optional[Dict[str, Any]]:
        """Get single contact with full details"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            contact = conn.execute("""
                SELECT * FROM contacts WHERE id = ?
            """, (contact_id,)).fetchone()
            
            if not contact:
                return None
            
            contact = dict(contact)
            
            # Get touch history
            touches = conn.execute("""
                SELECT * FROM contact_touches 
                WHERE contact_id = ? 
                ORDER BY created_at DESC
            """, (contact_id,)).fetchall()
            
            contact['touches'] = [dict(touch) for touch in touches]
            
            # Parse JSON fields
            if contact['tags']:
                try:
                    contact['tags'] = json.loads(contact['tags'])
                except:
                    contact['tags'] = []
            else:
                contact['tags'] = []
            
            return contact
    
    def create_contact(self, contact_data: Dict[str, Any]) -> int:
        """Create new contact"""
        with sqlite3.connect(self.db_path) as conn:
            normalized_email = self._normalize_optional_text(contact_data.get('email'))
            # Prepare tags as JSON
            tags_value = contact_data.get('tags', [])
            tags = tags_value if isinstance(tags_value, str) else json.dumps(tags_value)
            
            cursor = conn.execute("""
                INSERT INTO contacts 
                (name, email, company, title, brand, contact_type, source, status,
                 linkedin_url, twitter_handle, instagram_handle, youtube_channel,
                 website_url, followers_count, engagement_rate, alignment_score,
                 platform, tags, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                contact_data.get('name'),
                normalized_email,
                contact_data.get('company'),
                contact_data.get('title'),
                contact_data.get('brand'),
                contact_data.get('contact_type', 'email'),
                contact_data.get('source', 'manual'),
                contact_data.get('status', 'active'),
                contact_data.get('linkedin_url'),
                contact_data.get('twitter_handle'),
                contact_data.get('instagram_handle'),
                contact_data.get('youtube_channel'),
                contact_data.get('website_url'),
                contact_data.get('followers_count', 0),
                contact_data.get('engagement_rate', 0.0),
                contact_data.get('alignment_score', 0.0),
                contact_data.get('platform'),
                tags,
                contact_data.get('notes')
            ))
            
            return cursor.lastrowid

    def upsert_contact(self, contact_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create or update a contact using the best available identity fields."""
        contact = dict(contact_data)
        contact['email'] = self._normalize_optional_text(contact.get('email'))

        if contact.get('linkedin_url'):
            contact['linkedin_url'] = self.normalize_linkedin_url(contact['linkedin_url'])

        for optional_key in [
            'website_url',
            'twitter_handle',
            'instagram_handle',
            'youtube_channel',
            'bluesky_handle',
            'tiktok_handle',
            'linkedin_url',
        ]:
            contact[optional_key] = self._normalize_optional_text(contact.get(optional_key))

        if 'tags' in contact and not isinstance(contact['tags'], str):
            contact['tags'] = json.dumps(contact['tags'] or [])

        brand = (contact.get('brand') or '').strip()
        contact_type = contact.get('contact_type') or 'influencer'
        search_fields = [
            ('email', contact.get('email')),
            ('linkedin_url', contact.get('linkedin_url')),
            ('website_url', contact.get('website_url')),
            ('twitter_handle', contact.get('twitter_handle')),
            ('instagram_handle', contact.get('instagram_handle')),
            ('youtube_channel', contact.get('youtube_channel')),
            ('bluesky_handle', contact.get('bluesky_handle')),
            ('tiktok_handle', contact.get('tiktok_handle')),
        ]

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            contact_id = None
            allowed_keys = {
                'name', 'email', 'company', 'title', 'brand', 'contact_type', 'status', 'source',
                'linkedin_url', 'twitter_handle', 'instagram_handle', 'youtube_channel', 'website_url',
                'followers_count', 'engagement_rate', 'alignment_score', 'platform', 'tags', 'notes',
                'phone', 'bluesky_handle', 'tiktok_handle'
            }

            for field, value in search_fields:
                if not value:
                    continue
                row = conn.execute(
                    f"SELECT id FROM contacts WHERE {field} = ? AND brand = ? LIMIT 1",
                    (value, brand),
                ).fetchone()
                if row:
                    contact_id = row['id']
                    break

            if not contact_id and contact.get('name'):
                row = conn.execute(
                    "SELECT id FROM contacts WHERE name = ? AND brand = ? AND contact_type = ? LIMIT 1",
                    (contact['name'], brand, contact_type),
                ).fetchone()
                if row:
                    contact_id = row['id']

            if contact_id:
                update_payload = {
                    key: value for key, value in contact.items()
                    if key in allowed_keys and value is not None
                }
                self.update_contact(contact_id, update_payload)
                return {'id': contact_id, 'created': False}

            payload = {key: value for key, value in contact.items() if key in allowed_keys and value is not None}
            payload.setdefault('brand', brand)
            payload.setdefault('contact_type', contact_type)
            payload.setdefault('status', 'active')
            payload.setdefault('source', 'discovery')
            return {'id': self.create_contact(payload), 'created': True}
    
    def update_contact(self, contact_id: int, update_data: Dict[str, Any]) -> bool:
        """Update existing contact"""
        with sqlite3.connect(self.db_path) as conn:
            # Prepare tags as JSON if provided
            if 'tags' in update_data:
                update_data['tags'] = json.dumps(update_data['tags'])
            
            # Build dynamic update query
            fields = []
            values = []
            for field, value in update_data.items():
                if field != 'id':  # Don't update ID
                    fields.append(f"{field} = ?")
                    values.append(value)
            
            if not fields:
                return False
            
            values.append(contact_id)
            query = f"UPDATE contacts SET {', '.join(fields)} WHERE id = ?"
            
            cursor = conn.execute(query, values)
            return cursor.rowcount > 0
    
    def delete_contact(self, contact_id: int) -> bool:
        """Delete contact and all associated touches"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))
            return cursor.rowcount > 0
    
    def add_touch(self, contact_id: int, touch_data: Dict[str, Any]) -> int:
        """Add interaction/touch to contact"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                INSERT INTO contact_touches 
                (contact_id, touch_type, touch_direction, subject, message,
                 platform, status, response_text)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                contact_id,
                touch_data.get('touch_type'),
                touch_data.get('touch_direction'),
                touch_data.get('subject'),
                touch_data.get('message'),
                touch_data.get('platform'),
                touch_data.get('status'),
                touch_data.get('response_text')
            ))
            
            # Update last contact time
            conn.execute("""
                UPDATE contacts SET last_contact_at = CURRENT_TIMESTAMP WHERE id = ?
            """, (contact_id,))
            
            return cursor.lastrowid
    
    def get_contact_stats(self, brand: str = None) -> Dict[str, Any]:
        """Get contact statistics"""
        with sqlite3.connect(self.db_path) as conn:
            base_query = "SELECT {} FROM contacts"
            where_clause = " WHERE brand = ?" if brand else ""
            params = [brand] if brand else []
            
            # Total contacts
            total = conn.execute(
                base_query.format("COUNT(*)") + where_clause, params
            ).fetchone()[0]
            
            # By type
            by_type = {}
            for row in conn.execute(
                base_query.format("contact_type, COUNT(*)") + where_clause + " GROUP BY contact_type", 
                params
            ):
                by_type[row[0]] = row[1]
            
            # By status
            by_status = {}
            for row in conn.execute(
                base_query.format("status, COUNT(*)") + where_clause + " GROUP BY status", 
                params
            ):
                by_status[row[0]] = row[1]
            
            # Touch statistics
            touch_query = """
                SELECT COUNT(*) as total_touches,
                       COUNT(DISTINCT ct.contact_id) as contacts_with_touches,
                       COUNT(CASE WHEN ct.touch_direction = 'inbound' THEN 1 END) as responses
                FROM contact_touches ct
                JOIN contacts c ON ct.contact_id = c.id
            """
            
            if brand:
                touch_query += " WHERE c.brand = ?"
            
            touch_stats = conn.execute(touch_query, params).fetchone()
            
            return {
                'total_contacts': total,
                'by_type': by_type,
                'by_status': by_status,
                'total_touches': touch_stats[0],
                'contacts_with_touches': touch_stats[1],
                'total_responses': touch_stats[2],
                'response_rate': (touch_stats[2] / touch_stats[0] * 100) if touch_stats[0] > 0 else 0
            }

    # ── CSV Import ─────────────────────────────────────────────────────────────

    FIELD_SYNONYMS: dict = {
        'name':             ['name', 'full name', 'fullname', 'contact name', 'contact_name', 'full_name', 'person'],
        'email':            ['email', 'email address', 'email_address', 'e-mail', 'work email', 'personal email', 'mail'],
        'company':          ['company', 'company name', 'company_name', 'organization', 'org', 'employer', 'firm'],
        'title':            ['title', 'job title', 'job_title', 'position', 'role', 'job role', 'occupation'],
        'linkedin_url':     ['linkedin', 'linkedin url', 'linkedin_url', 'linkedin profile', 'li url', 'li profile', 'linkedin link'],
        'twitter_handle':   ['twitter', 'twitter handle', 'twitter_handle', 'x handle', 'x url', 'twitter url'],
        'instagram_handle': ['instagram', 'instagram handle', 'instagram_handle', 'ig', 'ig handle'],
        'youtube_channel':  ['youtube', 'youtube channel', 'youtube_channel', 'yt'],
        'website_url':      ['website', 'website url', 'website_url', 'url', 'homepage', 'web', 'site'],
        'followers_count':  ['followers', 'followers count', 'followers_count', 'subscriber count', 'subscribers'],
        'phone':            ['phone', 'phone number', 'phone_number', 'mobile', 'telephone', 'cell'],
        'notes':            ['notes', 'note', 'comments', 'description', 'bio', 'about'],
        'tags':             ['tags', 'tag', 'labels', 'categories', 'category', 'industry'],
        'bluesky_handle':   ['bluesky', 'bsky', 'bluesky handle', 'bluesky_handle'],
        'tiktok_handle':    ['tiktok', 'tik tok', 'tiktok handle', 'tiktok_handle'],
    }

    @staticmethod
    def auto_detect_mapping(headers: list) -> dict:
        """Return best-guess {csv_header: db_field} mapping from CSV column names."""
        synonyms = UnifiedContactsManager.FIELD_SYNONYMS
        mapping: dict = {}
        used_fields: set = set()
        for header in headers:
            h = header.lower().strip()
            matched = False
            for db_field, patterns in synonyms.items():
                if db_field in used_fields:
                    continue
                if any(p == h or p in h or h in p for p in patterns):
                    mapping[header] = db_field
                    used_fields.add(db_field)
                    matched = True
                    break
            if not matched:
                mapping[header] = ''
        return mapping

    @staticmethod
    def extract_social_from_text(text: str) -> dict:
        """Scan any text value for social media URLs and handles."""
        social: dict = {}
        if not text:
            return social
        li = re.search(
            r'https?://(?:www\.)?linkedin\.com/(?:in|company)/([^\s,;|"\' <>)\]]+)', text
        )
        if li:
            slug = li.group(1).rstrip('/')
            social['linkedin_url'] = f'https://www.linkedin.com/in/{slug}'
        tw = re.search(r'https?://(?:www\.)?(?:twitter|x)\.com/([A-Za-z0-9_]{1,50})', text)
        if tw:
            social['twitter_handle'] = '@' + tw.group(1)
        ig = re.search(r'https?://(?:www\.)?instagram\.com/([A-Za-z0-9._]{1,50})', text)
        if ig:
            social['instagram_handle'] = '@' + ig.group(1)
        yt = re.search(
            r'https?://(?:www\.)?youtube\.com/(?:channel/|@|c/|user/)?([^\s,;|"\' <>)\]]+)', text
        )
        if yt:
            social['youtube_channel'] = 'https://www.youtube.com/' + yt.group(1).rstrip('/')
        bsky = re.search(r'https?://bsky\.app/profile/([^\s,;|"\' <>)\]]+)', text)
        if bsky:
            social['bluesky_handle'] = bsky.group(1)
        else:
            bsky2 = re.search(r'([A-Za-z0-9._-]+\.bsky\.social)', text)
            if bsky2:
                social['bluesky_handle'] = bsky2.group(1)
        tt = re.search(r'https?://(?:www\.)?tiktok\.com/@([A-Za-z0-9._]{1,50})', text)
        if tt:
            social['tiktok_handle'] = '@' + tt.group(1)
        return social

    @staticmethod
    def normalize_linkedin_url(url: str) -> str:
        """Normalise to https://www.linkedin.com/in/<slug> form."""
        if not url:
            return url
        url = url.strip().rstrip('/')
        if not url.startswith('http'):
            url = 'https://' + url.lstrip('/')
        if 'linkedin.com/' in url and '/in/' not in url and '/company/' not in url:
            url = url.replace('linkedin.com/', 'linkedin.com/in/', 1)
        return url

    def import_from_csv(self, rows: list, mapping: dict,
                        source_label: str = 'csv_import',
                        contact_type: str = 'email',
                        brand: str = '') -> dict:
        """Import contact rows from CSV using a field mapping.

        Args:
            rows:         List of {csv_header: value} dicts.
            mapping:      {csv_header: db_field | ''} — '' ignores the column.
            source_label: Free-text label stored as ``source`` on every row
                          (e.g. "LinkedIn Export June 2024").
            contact_type: Default type applied to every imported row.
            brand:        Brand slug to assign.

        Returns:
            {'imported': int, 'skipped': int, 'errors': list[str]}
        """
        imported = skipped = 0
        errors: list = []
        for i, row in enumerate(rows):
            try:
                contact: dict = {
                    'contact_type': contact_type,
                    'source':       source_label,
                    'status':       'active',
                    'brand':        brand,
                }
                # Apply explicit column mapping
                for csv_col, db_field in mapping.items():
                    if not db_field:
                        continue
                    val = (row.get(csv_col) or '').strip()
                    if not val:
                        continue
                    if db_field == 'followers_count':
                        try:
                            contact[db_field] = int(val.replace(',', '').split('.')[0])
                        except ValueError:
                            pass
                    elif db_field == 'engagement_rate':
                        try:
                            contact[db_field] = float(val.replace('%', '').strip())
                        except ValueError:
                            pass
                    else:
                        contact[db_field] = val

                if not contact.get('name'):
                    skipped += 1
                    continue

                # Auto-enrich: scan every cell for social media URLs
                for cell_val in row.values():
                    if not cell_val:
                        continue
                    extracted = UnifiedContactsManager.extract_social_from_text(str(cell_val))
                    for k, v in extracted.items():
                        if not contact.get(k):
                            contact[k] = v

                if contact.get('linkedin_url'):
                    contact['linkedin_url'] = UnifiedContactsManager.normalize_linkedin_url(
                        contact['linkedin_url']
                    )

                self.create_contact(contact)
                imported += 1
            except Exception as exc:
                errors.append(f"Row {i + 2}: {exc}")

        return {'imported': imported, 'skipped': skipped, 'errors': errors[:20]}


def main():
    """CLI interface for contacts management"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Unified Contacts Management')
    parser.add_argument('--import-data', action='store_true', help='Import existing data')
    parser.add_argument('--stats', help='Show stats for brand (or all)')
    parser.add_argument('--list', help='List contacts for brand')
    
    args = parser.parse_args()
    
    manager = UnifiedContactsManager()
    
    if args.import_data:
        manager.import_existing_data()
    elif args.stats is not None:
        stats = manager.get_contact_stats(args.stats if args.stats != 'all' else None)
        print(f"📊 Contact Statistics:")
        print(f"   Total Contacts: {stats['total_contacts']}")
        print(f"   By Type: {stats['by_type']}")
        print(f"   By Status: {stats['by_status']}")
        print(f"   Total Touches: {stats['total_touches']}")
        print(f"   Response Rate: {stats['response_rate']:.1f}%")
    elif args.list:
        contacts = manager.get_contacts(brand=args.list if args.list != 'all' else None)
        print(f"👥 Contacts ({len(contacts)}):")
        for contact in contacts[:10]:  # Show first 10
            print(f"   {contact['name']} - {contact['email']} ({contact['contact_type']})")
    else:
        print("🏢 Unified Contacts Management System")
        print("   --import-data    Import existing outreach and influencer data")
        print("   --stats [brand]  Show contact statistics") 
        print("   --list [brand]   List contacts")

if __name__ == '__main__':
    main()
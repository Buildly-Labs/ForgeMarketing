"""
Marketing Calendar API endpoints for campaign and task management.
"""

from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
from dashboard.marketing_calendar_models import (
    MarketingCalendar, MarketingTask, ContentTemplate, MarketingWeekly,
    ContentPillar, ContentIdea, SocialPostDraft, ManualTask, Asset, PerformanceSnapshot,
    TaskStatus, TaskPriority, TaskType, PlatformType
)
from dashboard.models import Brand, SystemConfig, db
import json
import os

import requests as ext_requests

marketing_calendar_bp = Blueprint('marketing_calendar', __name__, url_prefix='/api/marketing')


DEFAULT_DO_AGENT_URL = 'https://upssgpoiscmhlp3uuvm65hyn.agents.do-ai.run'


def _resolve_ai_runtime_config():
    """Resolve AI runtime config with DB settings overriding defaults/env."""
    cfg = {
        'provider': 'do_agent',
        'url': os.getenv('DO_AGENT_URL', DEFAULT_DO_AGENT_URL),
        'model': os.getenv('DO_AGENT_MODEL', ''),
        'token': os.getenv('DO_AGENT_TOKEN', ''),
    }

    try:
        stored = {c.key: c.value for c in SystemConfig.query.filter(SystemConfig.key.like('ai_%')).all()}
        provider = (stored.get('ai_provider') or '').strip().lower()
        if provider:
            cfg['provider'] = provider

        cfg['url'] = (stored.get('ai_do_agent_url') or stored.get('ai_ollama_url') or cfg['url']).strip()
        cfg['model'] = (stored.get('ai_model') or cfg['model']).strip()
        # Support both DigitalOcean agent token and OpenAI key under the generic 'token' field
        cfg['token'] = (
            stored.get('ai_do_agent_token')
            or stored.get('ai_openai_key')
            or os.getenv('OPENAI_API_KEY', '')
            or cfg['token']
        ).strip()

        # When provider is openai, point url at the standard OpenAI chat completions endpoint
        if provider == 'openai' and not stored.get('ai_do_agent_url'):
            cfg['url'] = 'https://api.openai.com/v1/chat/completions'
        if not cfg['model'] and provider == 'openai':
            cfg['model'] = 'gpt-4o'
    except Exception:
        pass

    if not cfg['url']:
        cfg['url'] = DEFAULT_DO_AGENT_URL
    return cfg


def _extract_ai_text(payload):
    """Normalize common response shapes from OpenAI-compatible and custom agent APIs."""
    if not isinstance(payload, dict):
        return ''

    choices = payload.get('choices')
    if isinstance(choices, list) and choices:
        first = choices[0] or {}
        message = first.get('message') or {}
        content = message.get('content')
        if isinstance(content, str) and content.strip():
            return content.strip()

    for key in ('response', 'output_text', 'text', 'content'):
        val = payload.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()

    return ''


def _call_do_agent_chat(agent_url, prompt, model='', token=''):
    """Call a DO-hosted agent endpoint with OpenAI-compatible payload fallbacks."""
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'

    payload = {
        'model': model or 'gpt-4o-mini',
        'messages': [
            {
                'role': 'system',
                'content': (
                    'You are a senior marketing strategist. Return strict JSON only, '
                    'with no markdown fences and no explanatory prose.'
                ),
            },
            {'role': 'user', 'content': prompt},
        ],
        'temperature': 0.4,
    }

    endpoint_candidates = [
        agent_url.rstrip('/'),
        f"{agent_url.rstrip('/')}/v1/chat/completions",
        f"{agent_url.rstrip('/')}/chat/completions",
        f"{agent_url.rstrip('/')}/api/v1/chat/completions",
    ]

    last_error = None
    for endpoint in endpoint_candidates:
        try:
            resp = ext_requests.post(endpoint, headers=headers, json=payload, timeout=120)
            if resp.status_code >= 400:
                last_error = f'HTTP {resp.status_code}: {resp.text[:280]}'
                continue

            data = resp.json()
            text = _extract_ai_text(data)
            if text:
                return text, endpoint
            last_error = 'AI response did not include any content text.'
        except Exception as exc:
            last_error = str(exc)

    raise RuntimeError(last_error or 'Failed to reach agent endpoint')


DEFAULT_DO_MARKETING_AGENT_URL = "https://upssgpoiscmhlp3uuvm65hyn.agents.do-ai.run"


def _serialize_datetime(value):
    return value.isoformat() if value else None


def _serialize_pillar(pillar):
    return {
        'id': pillar.id,
        'name': pillar.name,
        'description': pillar.description,
        'examples': pillar.examples,
        'brand_name': pillar.brand_name,
        'is_active': pillar.is_active,
        'created_at': _serialize_datetime(pillar.created_at),
        'updated_at': _serialize_datetime(pillar.updated_at),
    }


def _serialize_idea(idea):
    return {
        'id': idea.id,
        'campaign_id': idea.campaign_id,
        'title': idea.title,
        'pillar_id': idea.pillar_id,
        'audience': idea.audience,
        'message': idea.message,
        'cta': idea.cta,
        'source_notes': idea.source_notes,
        'status': idea.status,
        'owner': idea.owner,
        'due_date': _serialize_datetime(idea.due_date),
        'created_at': _serialize_datetime(idea.created_at),
        'updated_at': _serialize_datetime(idea.updated_at),
    }


def _serialize_draft(draft):
    return {
        'id': draft.id,
        'content_idea_id': draft.content_idea_id,
        'platform': draft.platform,
        'post_format': draft.post_format,
        'caption_body': draft.caption_body,
        'hashtags': draft.hashtags,
        'cta': draft.cta,
        'link': draft.link,
        'media_asset': draft.media_asset,
        'status': draft.status,
        'scheduled_datetime': _serialize_datetime(draft.scheduled_datetime),
        'external_scheduler_name': draft.external_scheduler_name,
        'external_scheduler_url': draft.external_scheduler_url,
        'posted_url': draft.posted_url,
        'notes': draft.notes,
        'draft_origin': draft.draft_origin,
        'created_at': _serialize_datetime(draft.created_at),
        'updated_at': _serialize_datetime(draft.updated_at),
    }


def _serialize_manual_task(task):
    return {
        'id': task.id,
        'title': task.title,
        'description': task.description,
        'related_brand_name': task.related_brand_name,
        'related_campaign_id': task.related_campaign_id,
        'related_content_idea_id': task.related_content_idea_id,
        'related_social_post_id': task.related_social_post_id,
        'platform': task.platform,
        'task_type': task.task_type,
        'checklist_steps': task.checklist_steps,
        'owner': task.owner,
        'status': task.status,
        'due_date': _serialize_datetime(task.due_date),
        'completed_date': _serialize_datetime(task.completed_date),
        'notes': task.notes,
        'reference_url': task.reference_url,
        'created_at': _serialize_datetime(task.created_at),
        'updated_at': _serialize_datetime(task.updated_at),
    }


def _serialize_asset(asset):
    return {
        'id': asset.id,
        'name': asset.name,
        'asset_type': asset.asset_type,
        'file_or_url': asset.file_or_url,
        'brand_name': asset.brand_name,
        'usage_notes': asset.usage_notes,
        'alt_text': asset.alt_text,
        'platform_suitability': asset.platform_suitability,
        'status': asset.status,
        'created_at': _serialize_datetime(asset.created_at),
        'updated_at': _serialize_datetime(asset.updated_at),
    }


def _serialize_snapshot(snapshot):
    return {
        'id': snapshot.id,
        'platform': snapshot.platform,
        'related_social_post_id': snapshot.related_social_post_id,
        'post_url': snapshot.post_url,
        'date_checked': _serialize_datetime(snapshot.date_checked),
        'impressions_views': snapshot.impressions_views,
        'likes': snapshot.likes,
        'comments': snapshot.comments,
        'shares_reposts': snapshot.shares_reposts,
        'saves': snapshot.saves,
        'clicks': snapshot.clicks,
        'follows_subscribers': snapshot.follows_subscribers,
        'notes': snapshot.notes,
        'created_at': _serialize_datetime(snapshot.created_at),
        'updated_at': _serialize_datetime(snapshot.updated_at),
    }


def _get_marketing_agent_config():
    """Resolve agent URL/token/model from env + SystemConfig with safe defaults."""
    cfg = {}
    try:
        cfg = {c.key: c.value for c in SystemConfig.query.filter(SystemConfig.key.like('ai_%')).all()}
    except Exception:
        cfg = {}

    agent_url = (
        os.getenv('DO_MARKETING_AGENT_URL')
        or cfg.get('ai_do_agent_url')
        or DEFAULT_DO_MARKETING_AGENT_URL
    ).strip().rstrip('/')

    bearer_token = (
        os.getenv('DO_MARKETING_AGENT_TOKEN')
        or cfg.get('ai_do_agent_token')
        or ''
    ).strip()

    model_name = (
        os.getenv('DO_MARKETING_AGENT_MODEL')
        or cfg.get('ai_model')
        or 'gpt-4.1-mini'
    ).strip()

    return agent_url, bearer_token, model_name


def _build_marketing_plan_prompt(brand, payload):
    goal = (payload.get('goal') or 'Build a 30-day growth marketing plan').strip()
    timeframe = (payload.get('timeframe') or '30 days').strip()
    budget = (payload.get('budget') or 'Not specified').strip()
    constraints = payload.get('constraints') or []
    channels = payload.get('channels') or []
    additional_context = (payload.get('context') or '').strip()

    active_campaigns = MarketingCalendar.query.filter_by(brand_name=brand.name).count()
    active_tasks = MarketingTask.query.filter_by(brand_name=brand.name).count()

    channels_text = ', '.join(channels) if channels else 'email, social, content, partnerships'
    constraints_text = '; '.join(constraints) if constraints else 'No additional constraints provided.'

    return f"""You are an expert marketing strategy assistant.

Create a practical marketing agent plan for this brand.

Brand slug: {brand.name}
Brand display name: {brand.display_name}
Brand description: {brand.description or 'Not provided'}
Brand website: {brand.website_url or 'Not provided'}
Goal: {goal}
Timeframe: {timeframe}
Budget: {budget}
Preferred channels: {channels_text}
Constraints: {constraints_text}
Current campaign count in app: {active_campaigns}
Current task count in app: {active_tasks}
Additional context: {additional_context or 'None'}

Return ONLY valid JSON with this shape:
{{
  "summary": "short executive summary",
  "objectives": ["..."],
  "phases": [
    {{
      "name": "Phase name",
      "duration": "e.g. Week 1",
      "actions": [
        {{
          "title": "Action title",
          "channel": "EMAIL|SOCIAL|CONTENT|ADS|SEO|PARTNERSHIPS|OTHER",
          "owner": "Marketing|Sales|Founder|Other",
          "priority": "HIGH|MEDIUM|LOW",
          "kpi": "measurable KPI",
          "due_in_days": 0
        }}
      ]
    }}
  ],
  "content_ideas": ["..."],
  "risks": ["..."],
  "next_7_days": ["..."]
}}"""


def _extract_plan_json(text):
    """Parse JSON from direct output or fenced code block response."""
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    fence_start = text.find('```json')
    if fence_start != -1:
        fence_start = text.find('\n', fence_start)
        fence_end = text.find('```', fence_start + 1)
        if fence_start != -1 and fence_end != -1:
            snippet = text[fence_start + 1:fence_end].strip()
            try:
                parsed = json.loads(snippet)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass

    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1 and end > start:
        snippet = text[start:end + 1]
        try:
            parsed = json.loads(snippet)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

    return None


@marketing_calendar_bp.route('/agent/marketing-plan', methods=['POST'])
def generate_marketing_agent_plan():
    """Generate a marketing plan via DigitalOcean agent endpoint."""
    data = request.get_json() or {}
    brand_name = (data.get('brand_name') or '').strip()
    if not brand_name:
        return jsonify({'success': False, 'error': 'brand_name is required'}), 400

    brand = Brand.query.filter_by(name=brand_name).first()
    if not brand:
        return jsonify({'success': False, 'error': 'Brand not found'}), 404

    agent_url, bearer_token, model_name = _get_marketing_agent_config()
    prompt = _build_marketing_plan_prompt(brand, data)

    import requests as ext_requests
    headers = {'Content-Type': 'application/json'}
    if bearer_token:
        headers['Authorization'] = f'Bearer {bearer_token}'

    # Prefer chat-style payload; fall back to simple input payload for agent runtimes
    chat_payload = {
        'model': model_name,
        'messages': [
            {'role': 'system', 'content': 'You produce strict JSON output only.'},
            {'role': 'user', 'content': prompt},
        ],
        'stream': False,
        'temperature': 0.4,
    }

    response = None
    last_error = None
    for payload in (chat_payload, {'input': prompt, 'stream': False}):
        try:
            response = ext_requests.post(agent_url, json=payload, headers=headers, timeout=180)
            if response.status_code < 400:
                break
            last_error = f'Agent returned {response.status_code}: {response.text[:300]}'
        except Exception as exc:
            last_error = str(exc)

    if response is None or response.status_code >= 400:
        return jsonify({'success': False, 'error': last_error or 'Agent request failed'}), 502

    raw_text = ''
    try:
        body = response.json()
        raw_text = (
            body.get('output_text')
            or body.get('response')
            or body.get('content')
            or (body.get('choices', [{}])[0].get('message', {}).get('content') if isinstance(body.get('choices'), list) else '')
            or json.dumps(body)
        )
    except Exception:
        raw_text = response.text or ''

    structured = _extract_plan_json(raw_text)
    return jsonify({
        'success': True,
        'brand_name': brand.name,
        'agent_url': agent_url,
        'plan': structured,
        'raw_plan_text': raw_text[:20000],
    })


# ============ CAMPAIGNS ============

@marketing_calendar_bp.route('/campaigns', methods=['GET'])
def get_campaigns():
    """Get all marketing campaigns, optionally filtered by brand"""
    brand = request.args.get('brand')
    
    query = MarketingCalendar.query
    if brand:
        query = query.filter_by(brand_name=brand)
    
    campaigns = query.all()
    
    return jsonify({
        'success': True,
        'data': [{
            'id': c.id,
            'brand_name': c.brand_name,
            'campaign_name': c.campaign_name,
            'campaign_slug': c.campaign_slug,
            'description': c.description,
            'goal': c.goal,
            'target_metric': c.target_metric,
            'start_date': c.start_date.isoformat(),
            'end_date': c.end_date.isoformat(),
            'budget': c.budget,
            'status': c.status,
            'owner': c.owner,
            'task_count': len(c.tasks),
            'completed_tasks': sum(1 for t in c.tasks if t.status == TaskStatus.COMPLETED),
            'created_at': c.created_at.isoformat()
        } for c in campaigns]
    })


@marketing_calendar_bp.route('/campaigns', methods=['POST'])
def create_campaign():
    """Create a new marketing campaign"""
    data = request.get_json()
    
    # Validate required fields
    required = ['brand_name', 'campaign_name', 'start_date', 'end_date']
    if not all(field in data for field in required):
        return jsonify({'success': False, 'error': 'Missing required fields'}), 400
    
    # Verify brand exists
    brand = Brand.query.filter_by(name=data['brand_name']).first()
    if not brand:
        return jsonify({'success': False, 'error': 'Brand not found'}), 404
    
    try:
        campaign = MarketingCalendar(
            brand_name=data['brand_name'],
            campaign_name=data['campaign_name'],
            campaign_slug=data.get('campaign_slug', data['campaign_name'].lower().replace(' ', '-')),
            description=data.get('description'),
            goal=data.get('goal'),
            target_metric=data.get('target_metric'),
            start_date=datetime.fromisoformat(data['start_date']),
            end_date=datetime.fromisoformat(data['end_date']),
            budget=data.get('budget', 0),
            currency=data.get('currency', 'USD'),
            status=data.get('status', 'draft'),
            owner=data.get('owner'),
            notes=data.get('notes'),
            meta_data=data.get('metadata', {})
        )
        
        db.session.add(campaign)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Campaign "{campaign.campaign_name}" created successfully',
            'data': {'id': campaign.id, 'campaign_name': campaign.campaign_name}
        }), 201
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@marketing_calendar_bp.route('/campaigns/<int:campaign_id>', methods=['GET'])
def get_campaign(campaign_id):
    """Get campaign details with all tasks"""
    campaign = MarketingCalendar.query.get(campaign_id)
    if not campaign:
        return jsonify({'success': False, 'error': 'Campaign not found'}), 404
    
    return jsonify({
        'success': True,
        'data': {
            'id': campaign.id,
            'brand_name': campaign.brand_name,
            'campaign_name': campaign.campaign_name,
            'description': campaign.description,
            'goal': campaign.goal,
            'start_date': campaign.start_date.isoformat(),
            'end_date': campaign.end_date.isoformat(),
            'budget': campaign.budget,
            'status': campaign.status,
            'owner': campaign.owner,
            'tasks': [{
                'id': t.id,
                'task_name': t.task_name,
                'platform': t.platform.value,
                'status': t.status.value,
                'scheduled_date': t.scheduled_date.isoformat(),
                'priority': t.priority.value,
                'assigned_to': t.assigned_to,
                'is_automated': t.is_automated
            } for t in campaign.tasks],
            'created_at': campaign.created_at.isoformat()
        }
    })


@marketing_calendar_bp.route('/campaigns/<int:campaign_id>', methods=['PUT'])
def update_campaign(campaign_id):
    """Update a campaign"""
    campaign = MarketingCalendar.query.get(campaign_id)
    if not campaign:
        return jsonify({'success': False, 'error': 'Campaign not found'}), 404

    data = request.get_json()
    for field in ['campaign_name', 'description', 'goal', 'target_metric', 'status', 'owner', 'notes']:
        if field in data:
            setattr(campaign, field, data[field])
    if 'start_date' in data:
        campaign.start_date = datetime.fromisoformat(data['start_date'])
    if 'end_date' in data:
        campaign.end_date = datetime.fromisoformat(data['end_date'])
    if 'budget' in data:
        campaign.budget = data['budget']
    campaign.updated_at = datetime.utcnow()

    try:
        db.session.commit()
        return jsonify({'success': True, 'message': f'Campaign "{campaign.campaign_name}" updated'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@marketing_calendar_bp.route('/campaigns/<int:campaign_id>', methods=['DELETE'])
def delete_campaign(campaign_id):
    """Delete a campaign and all its tasks"""
    campaign = MarketingCalendar.query.get(campaign_id)
    if not campaign:
        return jsonify({'success': False, 'error': 'Campaign not found'}), 404

    try:
        name = campaign.campaign_name
        db.session.delete(campaign)
        db.session.commit()
        return jsonify({'success': True, 'message': f'Campaign "{name}" deleted'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ============ TASKS ============

@marketing_calendar_bp.route('/tasks', methods=['GET'])
def get_tasks():
    """Get marketing tasks with filtering"""
    brand = request.args.get('brand')
    status = request.args.get('status')
    platform = request.args.get('platform')
    assigned_to = request.args.get('assigned_to')
    calendar_id = request.args.get('calendar_id')
    
    query = MarketingTask.query
    
    if brand:
        query = query.filter_by(brand_name=brand)
    if status:
        query = query.filter_by(status=TaskStatus[status.upper()])
    if platform:
        query = query.filter_by(platform=PlatformType[platform.upper()])
    if assigned_to:
        query = query.filter_by(assigned_to=assigned_to)
    if calendar_id:
        query = query.filter_by(calendar_id=int(calendar_id))
    
    tasks = query.order_by(MarketingTask.scheduled_date).all()
    
    return jsonify({
        'success': True,
        'data': [{
            'id': t.id,
            'task_name': t.task_name,
            'platform': t.platform.value,
            'status': t.status.value,
            'priority': t.priority.value,
            'scheduled_date': t.scheduled_date.isoformat(),
            'title': t.title,
            'assigned_to': t.assigned_to,
            'is_automated': t.is_automated,
            'calendar_id': t.calendar_id
        } for t in tasks]
    })


@marketing_calendar_bp.route('/tasks', methods=['POST'])
def create_task():
    """Create a new marketing task"""
    data = request.get_json()
    
    required = ['brand_name', 'calendar_id', 'task_name', 'platform', 'scheduled_date']
    if not all(field in data for field in required):
        return jsonify({'success': False, 'error': 'Missing required fields'}), 400
    
    try:
        task = MarketingTask(
            calendar_id=data['calendar_id'],
            brand_name=data['brand_name'],
            task_name=data['task_name'],
            task_slug=data.get('task_slug', data['task_name'].lower().replace(' ', '-')),
            description=data.get('description'),
            task_type=TaskType[data.get('task_type', 'SOCIAL_POST').upper()],
            platform=PlatformType[data['platform'].upper()],
            scheduled_date=datetime.fromisoformat(data['scheduled_date']),
            scheduled_time=data.get('scheduled_time'),
            duration_minutes=data.get('duration_minutes'),
            assigned_to=data.get('assigned_to'),
            status=TaskStatus[data.get('status', 'DRAFT').upper()],
            priority=TaskPriority[data.get('priority', 'MEDIUM').upper()],
            is_automated=data.get('is_automated', False),
            title=data.get('title'),
            body=data.get('body'),
            meta_data=data.get('metadata', {})
        )
        
        db.session.add(task)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Task "{task.task_name}" created successfully',
            'data': {'id': task.id, 'task_name': task.task_name}
        }), 201
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@marketing_calendar_bp.route('/tasks/<int:task_id>', methods=['GET'])
def get_task(task_id):
    """Get task details"""
    task = MarketingTask.query.get(task_id)
    if not task:
        return jsonify({'success': False, 'error': 'Task not found'}), 404
    
    return jsonify({
        'success': True,
        'data': {
            'id': task.id,
            'task_name': task.task_name,
            'description': task.description,
            'platform': task.platform.value,
            'task_type': task.task_type.value,
            'status': task.status.value,
            'priority': task.priority.value,
            'scheduled_date': task.scheduled_date.isoformat(),
            'title': task.title,
            'body': task.body,
            'assigned_to': task.assigned_to,
            'is_automated': task.is_automated,
            'metrics': task.performance_metrics,
            'created_at': task.created_at.isoformat()
        }
    })


@marketing_calendar_bp.route('/tasks/<int:task_id>', methods=['PUT'])
def update_task(task_id):
    """Update a task"""
    task = MarketingTask.query.get(task_id)
    if not task:
        return jsonify({'success': False, 'error': 'Task not found'}), 404
    
    data = request.get_json()
    
    # Update fields
    if 'status' in data:
        task.status = TaskStatus[data['status'].upper()]
    if 'priority' in data:
        task.priority = TaskPriority[data['priority'].upper()]
    if 'assigned_to' in data:
        task.assigned_to = data['assigned_to']
    if 'title' in data:
        task.title = data['title']
    if 'body' in data:
        task.body = data['body']
    if 'scheduled_date' in data:
        task.scheduled_date = datetime.fromisoformat(data['scheduled_date'])
    if 'metrics' in data:
        task.performance_metrics = data['metrics']
    
    task.updated_at = datetime.utcnow()
    
    try:
        db.session.commit()
        return jsonify({
            'success': True,
            'message': f'Task "{task.task_name}" updated successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@marketing_calendar_bp.route('/tasks/<int:task_id>/complete', methods=['POST'])
def complete_task(task_id):
    """Mark a task as completed"""
    task = MarketingTask.query.get(task_id)
    if not task:
        return jsonify({'success': False, 'error': 'Task not found'}), 404
    
    data = request.get_json() or {}
    
    task.status = TaskStatus.COMPLETED
    task.completed_at = datetime.utcnow()
    task.executed_by = data.get('executed_by', 'system')
    task.execution_log = data.get('execution_log')
    task.performance_metrics = data.get('metrics', {})
    
    try:
        db.session.commit()
        return jsonify({
            'success': True,
            'message': f'Task "{task.task_name}" marked as completed'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ============ CONTENT TEMPLATES ============

@marketing_calendar_bp.route('/templates', methods=['GET'])
def get_templates():
    """Get content templates"""
    brand = request.args.get('brand')
    platform = request.args.get('platform')
    category = request.args.get('category')
    
    query = ContentTemplate.query
    
    if brand:
        query = query.filter_by(brand_name=brand)
    if platform:
        query = query.filter_by(platform=PlatformType[platform.upper()])
    if category:
        query = query.filter_by(category=category)
    
    templates = query.all()
    
    return jsonify({
        'success': True,
        'data': [{
            'id': t.id,
            'template_name': t.template_name,
            'platform': t.platform.value,
            'task_type': t.task_type.value,
            'category': t.category,
            'title_template': t.title_template,
            'body_template': t.body_template,
            'prompt_instructions': t.prompt_instructions,
            'example_output': t.example_output,
            'required_assets': t.required_assets,
            'usage_count': t.usage_count,
            'description': t.description,
            'suggested_cta': t.suggested_cta,
            'suggested_hashtags': t.suggested_hashtags
        } for t in templates]
    })


@marketing_calendar_bp.route('/templates', methods=['POST'])
def create_template():
    """Create a content template"""
    data = request.get_json()
    
    required = ['brand_name', 'template_name', 'platform', 'task_type']
    if not all(field in data for field in required):
        return jsonify({'success': False, 'error': 'Missing required fields'}), 400
    
    try:
        template = ContentTemplate(
            brand_name=data['brand_name'],
            template_name=data['template_name'],
            template_slug=data.get('template_slug', data['template_name'].lower().replace(' ', '-')),
            category=data.get('category'),
            platform=PlatformType[data['platform'].upper()],
            task_type=TaskType[data['task_type'].upper()],
            title_template=data.get('title_template'),
            body_template=data.get('body_template'),
            prompt_instructions=data.get('prompt_instructions'),
            example_output=data.get('example_output'),
            required_assets=data.get('required_assets', []),
            cta=data.get('cta'),
            hashtags=data.get('hashtags'),
            suggested_cta=data.get('suggested_cta'),
            suggested_hashtags=data.get('suggested_hashtags'),
            variables=data.get('variables', {}),
            description=data.get('description')
        )
        
        db.session.add(template)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Template "{template.template_name}" created',
            'data': {'id': template.id}
        }), 201
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ============ WEEKLY REPORTS ============

@marketing_calendar_bp.route('/weekly-reports', methods=['GET'])
def get_weekly_reports():
    """Get weekly marketing reports"""
    brand = request.args.get('brand')
    calendar_id = request.args.get('calendar_id')
    
    query = MarketingWeekly.query
    
    if brand:
        query = query.filter_by(brand_name=brand)
    if calendar_id:
        query = query.filter_by(calendar_id=int(calendar_id))
    
    reports = query.order_by(MarketingWeekly.week_start.desc()).all()
    
    return jsonify({
        'success': True,
        'data': [{
            'id': r.id,
            'brand_name': r.brand_name,
            'week_start': r.week_start.isoformat(),
            'week_end': r.week_end.isoformat(),
            'posts_published': r.posts_published,
            'total_reach': r.total_reach,
            'total_engagement': r.total_engagement,
            'total_conversions': r.total_conversions,
            'signups': r.signups,
            'insights': r.insights
        } for r in reports]
    })


@marketing_calendar_bp.route('/weekly-reports', methods=['POST'])
def create_weekly_report():
    """Create a weekly marketing report"""
    data = request.get_json()
    
    required = ['brand_name', 'week_start', 'week_end']
    if not all(field in data for field in required):
        return jsonify({'success': False, 'error': 'Missing required fields'}), 400
    
    try:
        report = MarketingWeekly(
            brand_name=data['brand_name'],
            calendar_id=data.get('calendar_id'),
            week_start=datetime.fromisoformat(data['week_start']),
            week_end=datetime.fromisoformat(data['week_end']),
            posts_published=data.get('posts_published', 0),
            total_reach=data.get('total_reach', 0),
            total_engagement=data.get('total_engagement', 0),
            total_clicks=data.get('total_clicks', 0),
            total_conversions=data.get('total_conversions', 0),
            signups=data.get('signups', 0),
            platform_metrics=data.get('platform_metrics', {}),
            notes=data.get('notes'),
            insights=data.get('insights')
        )
        
        db.session.add(report)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Weekly report created',
            'data': {'id': report.id}
        }), 201
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ============ CALENDAR VIEW ============

@marketing_calendar_bp.route('/calendar-view', methods=['GET'])
def get_calendar_view():
    """Get tasks for calendar view (grouped by date)"""
    brand = request.args.get('brand')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    query = MarketingTask.query
    
    if brand:
        query = query.filter_by(brand_name=brand)
    
    if start_date:
        start = datetime.fromisoformat(start_date)
        query = query.filter(MarketingTask.scheduled_date >= start)
    
    if end_date:
        end = datetime.fromisoformat(end_date)
        query = query.filter(MarketingTask.scheduled_date <= end)
    
    tasks = query.order_by(MarketingTask.scheduled_date).all()
    
    # Group by date
    calendar_data = {}
    for task in tasks:
        date_key = task.scheduled_date.date().isoformat()
        if date_key not in calendar_data:
            calendar_data[date_key] = []
        
        calendar_data[date_key].append({
            'id': task.id,
            'task_name': task.task_name,
            'platform': task.platform.value,
            'status': task.status.value,
            'priority': task.priority.value,
            'assigned_to': task.assigned_to,
            'is_automated': task.is_automated
        })
    
    return jsonify({
        'success': True,
        'data': calendar_data
    })


@marketing_calendar_bp.route('/tasks/<int:task_id>', methods=['DELETE'])
def delete_task(task_id):
    """Delete a task"""
    task = MarketingTask.query.get(task_id)
    if not task:
        return jsonify({'success': False, 'error': 'Task not found'}), 404
    try:
        name = task.task_name
        db.session.delete(task)
        db.session.commit()
        return jsonify({'success': True, 'message': f'Task "{name}" deleted'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ============ CONTENT PILLARS ============

@marketing_calendar_bp.route('/pillars', methods=['GET'])
def get_content_pillars():
    brand = request.args.get('brand')
    active_only = request.args.get('active_only', 'true').lower() != 'false'

    query = ContentPillar.query
    if brand:
        query = query.filter_by(brand_name=brand)
    if active_only:
        query = query.filter_by(is_active=True)

    pillars = query.order_by(ContentPillar.name).all()
    return jsonify({'success': True, 'data': [_serialize_pillar(p) for p in pillars]})


@marketing_calendar_bp.route('/pillars', methods=['POST'])
def create_content_pillar():
    data = request.get_json() or {}
    if not data.get('name'):
        return jsonify({'success': False, 'error': 'name is required'}), 400

    brand_name = data.get('brand_name')
    if brand_name:
        brand = Brand.query.filter_by(name=brand_name).first()
        if not brand:
            return jsonify({'success': False, 'error': 'Brand not found'}), 404

    pillar = ContentPillar(
        name=data['name'],
        description=data.get('description'),
        examples=data.get('examples'),
        brand_name=brand_name,
        is_active=data.get('is_active', True),
    )
    try:
        db.session.add(pillar)
        db.session.commit()
        return jsonify({'success': True, 'data': _serialize_pillar(pillar)}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@marketing_calendar_bp.route('/pillars/<int:pillar_id>', methods=['GET'])
def get_content_pillar(pillar_id):
    pillar = ContentPillar.query.get(pillar_id)
    if not pillar:
        return jsonify({'success': False, 'error': 'Content pillar not found'}), 404
    return jsonify({'success': True, 'data': _serialize_pillar(pillar)})


@marketing_calendar_bp.route('/pillars/<int:pillar_id>', methods=['PUT'])
def update_content_pillar(pillar_id):
    pillar = ContentPillar.query.get(pillar_id)
    if not pillar:
        return jsonify({'success': False, 'error': 'Content pillar not found'}), 404

    data = request.get_json() or {}
    for field in ['name', 'description', 'examples', 'brand_name', 'is_active']:
        if field in data:
            setattr(pillar, field, data[field])

    try:
        db.session.commit()
        return jsonify({'success': True, 'data': _serialize_pillar(pillar)})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@marketing_calendar_bp.route('/pillars/<int:pillar_id>', methods=['DELETE'])
def delete_content_pillar(pillar_id):
    pillar = ContentPillar.query.get(pillar_id)
    if not pillar:
        return jsonify({'success': False, 'error': 'Content pillar not found'}), 404
    try:
        db.session.delete(pillar)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Content pillar deleted'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ============ CONTENT IDEAS ============

@marketing_calendar_bp.route('/ideas', methods=['GET'])
def get_content_ideas():
    campaign_id = request.args.get('campaign_id')
    status = request.args.get('status')
    owner = request.args.get('owner')

    query = ContentIdea.query
    if campaign_id:
        query = query.filter_by(campaign_id=int(campaign_id))
    if status:
        query = query.filter_by(status=status)
    if owner:
        query = query.filter_by(owner=owner)

    ideas = query.order_by(ContentIdea.due_date.nullslast(), ContentIdea.created_at.desc()).all()
    return jsonify({'success': True, 'data': [_serialize_idea(i) for i in ideas]})


@marketing_calendar_bp.route('/ideas', methods=['POST'])
def create_content_idea():
    data = request.get_json() or {}
    required = ['campaign_id', 'title']
    if not all(data.get(field) for field in required):
        return jsonify({'success': False, 'error': 'campaign_id and title are required'}), 400

    campaign = MarketingCalendar.query.get(int(data['campaign_id']))
    if not campaign:
        return jsonify({'success': False, 'error': 'Campaign not found'}), 404

    pillar_id = data.get('pillar_id')
    if pillar_id:
        pillar = ContentPillar.query.get(int(pillar_id))
        if not pillar:
            return jsonify({'success': False, 'error': 'Content pillar not found'}), 404

    idea = ContentIdea(
        campaign_id=int(data['campaign_id']),
        title=data['title'],
        pillar_id=int(pillar_id) if pillar_id else None,
        audience=data.get('audience'),
        message=data.get('message'),
        cta=data.get('cta'),
        source_notes=data.get('source_notes'),
        status=data.get('status', 'idea'),
        owner=data.get('owner'),
        due_date=datetime.fromisoformat(data['due_date']) if data.get('due_date') else None,
    )

    try:
        db.session.add(idea)
        db.session.commit()
        return jsonify({'success': True, 'data': _serialize_idea(idea)}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@marketing_calendar_bp.route('/ideas/<int:idea_id>', methods=['GET'])
def get_content_idea(idea_id):
    idea = ContentIdea.query.get(idea_id)
    if not idea:
        return jsonify({'success': False, 'error': 'Content idea not found'}), 404
    return jsonify({'success': True, 'data': _serialize_idea(idea)})


@marketing_calendar_bp.route('/ideas/<int:idea_id>', methods=['PUT'])
def update_content_idea(idea_id):
    idea = ContentIdea.query.get(idea_id)
    if not idea:
        return jsonify({'success': False, 'error': 'Content idea not found'}), 404

    data = request.get_json() or {}
    for field in ['title', 'pillar_id', 'audience', 'message', 'cta', 'source_notes', 'status', 'owner']:
        if field in data:
            setattr(idea, field, data[field])
    if 'due_date' in data:
        idea.due_date = datetime.fromisoformat(data['due_date']) if data['due_date'] else None

    try:
        db.session.commit()
        return jsonify({'success': True, 'data': _serialize_idea(idea)})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@marketing_calendar_bp.route('/ideas/<int:idea_id>', methods=['DELETE'])
def delete_content_idea(idea_id):
    idea = ContentIdea.query.get(idea_id)
    if not idea:
        return jsonify({'success': False, 'error': 'Content idea not found'}), 404
    try:
        db.session.delete(idea)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Content idea deleted'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ============ SOCIAL POST DRAFTS ============

@marketing_calendar_bp.route('/drafts', methods=['GET'])
def get_social_post_drafts():
    idea_id = request.args.get('content_idea_id')
    platform = request.args.get('platform')
    status = request.args.get('status')

    query = SocialPostDraft.query
    if idea_id:
        query = query.filter_by(content_idea_id=int(idea_id))
    if platform:
        query = query.filter_by(platform=platform)
    if status:
        query = query.filter_by(status=status)

    drafts = query.order_by(SocialPostDraft.scheduled_datetime.nullslast(), SocialPostDraft.created_at.desc()).all()
    return jsonify({'success': True, 'data': [_serialize_draft(d) for d in drafts]})


@marketing_calendar_bp.route('/drafts', methods=['POST'])
def create_social_post_draft():
    data = request.get_json() or {}
    required = ['content_idea_id', 'platform', 'post_format']
    if not all(data.get(field) for field in required):
        return jsonify({'success': False, 'error': 'content_idea_id, platform, and post_format are required'}), 400

    idea = ContentIdea.query.get(int(data['content_idea_id']))
    if not idea:
        return jsonify({'success': False, 'error': 'Content idea not found'}), 404

    draft = SocialPostDraft(
        content_idea_id=int(data['content_idea_id']),
        platform=data['platform'],
        post_format=data['post_format'],
        caption_body=data.get('caption_body'),
        hashtags=data.get('hashtags'),
        cta=data.get('cta'),
        link=data.get('link'),
        media_asset=data.get('media_asset'),
        status=data.get('status', 'draft'),
        scheduled_datetime=datetime.fromisoformat(data['scheduled_datetime']) if data.get('scheduled_datetime') else None,
        external_scheduler_name=data.get('external_scheduler_name'),
        external_scheduler_url=data.get('external_scheduler_url'),
        posted_url=data.get('posted_url'),
        notes=data.get('notes'),
        draft_origin=data.get('draft_origin', 'human'),
    )

    try:
        db.session.add(draft)
        db.session.commit()
        return jsonify({'success': True, 'data': _serialize_draft(draft)}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@marketing_calendar_bp.route('/drafts/<int:draft_id>', methods=['GET'])
def get_social_post_draft(draft_id):
    draft = SocialPostDraft.query.get(draft_id)
    if not draft:
        return jsonify({'success': False, 'error': 'Social post draft not found'}), 404
    return jsonify({'success': True, 'data': _serialize_draft(draft)})


@marketing_calendar_bp.route('/drafts/<int:draft_id>', methods=['PUT'])
def update_social_post_draft(draft_id):
    draft = SocialPostDraft.query.get(draft_id)
    if not draft:
        return jsonify({'success': False, 'error': 'Social post draft not found'}), 404

    data = request.get_json() or {}
    for field in ['content_idea_id', 'platform', 'post_format', 'caption_body', 'hashtags', 'cta', 'link', 'media_asset', 'status', 'external_scheduler_name', 'external_scheduler_url', 'posted_url', 'notes', 'draft_origin']:
        if field in data:
            setattr(draft, field, data[field])
    if 'scheduled_datetime' in data:
        draft.scheduled_datetime = datetime.fromisoformat(data['scheduled_datetime']) if data['scheduled_datetime'] else None

    try:
        db.session.commit()
        return jsonify({'success': True, 'data': _serialize_draft(draft)})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@marketing_calendar_bp.route('/drafts/<int:draft_id>', methods=['DELETE'])
def delete_social_post_draft(draft_id):
    draft = SocialPostDraft.query.get(draft_id)
    if not draft:
        return jsonify({'success': False, 'error': 'Social post draft not found'}), 404
    try:
        db.session.delete(draft)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Social post draft deleted'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ============ MANUAL TASKS ============

@marketing_calendar_bp.route('/manual-tasks', methods=['GET'])
def get_manual_tasks():
    brand = request.args.get('brand')
    status = request.args.get('status')
    task_type = request.args.get('task_type')

    query = ManualTask.query
    if brand:
        query = query.filter_by(related_brand_name=brand)
    if status:
        query = query.filter_by(status=status)
    if task_type:
        query = query.filter_by(task_type=task_type)

    tasks = query.order_by(ManualTask.due_date.nullslast(), ManualTask.created_at.desc()).all()
    return jsonify({'success': True, 'data': [_serialize_manual_task(t) for t in tasks]})


@marketing_calendar_bp.route('/manual-tasks', methods=['POST'])
def create_manual_task():
    data = request.get_json() or {}
    if not data.get('title'):
        return jsonify({'success': False, 'error': 'title is required'}), 400

    task = ManualTask(
        title=data['title'],
        description=data.get('description'),
        related_brand_name=data.get('related_brand_name'),
        related_campaign_id=data.get('related_campaign_id'),
        related_content_idea_id=data.get('related_content_idea_id'),
        related_social_post_id=data.get('related_social_post_id'),
        platform=data.get('platform'),
        task_type=data.get('task_type', 'manual_posting'),
        checklist_steps=data.get('checklist_steps', []),
        owner=data.get('owner'),
        status=data.get('status', 'not_started'),
        due_date=datetime.fromisoformat(data['due_date']) if data.get('due_date') else None,
        completed_date=datetime.fromisoformat(data['completed_date']) if data.get('completed_date') else None,
        notes=data.get('notes'),
        reference_url=data.get('reference_url'),
    )

    try:
        db.session.add(task)
        db.session.commit()
        return jsonify({'success': True, 'data': _serialize_manual_task(task)}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@marketing_calendar_bp.route('/manual-tasks/<int:task_id>', methods=['GET'])
def get_manual_task(task_id):
    task = ManualTask.query.get(task_id)
    if not task:
        return jsonify({'success': False, 'error': 'Manual task not found'}), 404
    return jsonify({'success': True, 'data': _serialize_manual_task(task)})


@marketing_calendar_bp.route('/manual-tasks/<int:task_id>', methods=['PUT'])
def update_manual_task(task_id):
    task = ManualTask.query.get(task_id)
    if not task:
        return jsonify({'success': False, 'error': 'Manual task not found'}), 404

    data = request.get_json() or {}
    for field in ['title', 'description', 'related_brand_name', 'related_campaign_id', 'related_content_idea_id', 'related_social_post_id', 'platform', 'task_type', 'checklist_steps', 'owner', 'status', 'notes', 'reference_url']:
        if field in data:
            setattr(task, field, data[field])
    if 'due_date' in data:
        task.due_date = datetime.fromisoformat(data['due_date']) if data['due_date'] else None
    if 'completed_date' in data:
        task.completed_date = datetime.fromisoformat(data['completed_date']) if data['completed_date'] else None

    try:
        db.session.commit()
        return jsonify({'success': True, 'data': _serialize_manual_task(task)})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@marketing_calendar_bp.route('/manual-tasks/<int:task_id>', methods=['DELETE'])
def delete_manual_task(task_id):
    task = ManualTask.query.get(task_id)
    if not task:
        return jsonify({'success': False, 'error': 'Manual task not found'}), 404
    try:
        db.session.delete(task)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Manual task deleted'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ============ ASSETS ============

@marketing_calendar_bp.route('/assets', methods=['GET'])
def get_assets():
    brand = request.args.get('brand')
    asset_type = request.args.get('asset_type')
    status = request.args.get('status')

    query = Asset.query
    if brand:
        query = query.filter_by(brand_name=brand)
    if asset_type:
        query = query.filter_by(asset_type=asset_type)
    if status:
        query = query.filter_by(status=status)

    assets = query.order_by(Asset.created_at.desc()).all()
    return jsonify({'success': True, 'data': [_serialize_asset(a) for a in assets]})


@marketing_calendar_bp.route('/assets', methods=['POST'])
def create_asset():
    data = request.get_json() or {}
    required = ['name', 'asset_type', 'file_or_url']
    if not all(data.get(field) for field in required):
        return jsonify({'success': False, 'error': 'name, asset_type, and file_or_url are required'}), 400

    asset = Asset(
        name=data['name'],
        asset_type=data['asset_type'],
        file_or_url=data['file_or_url'],
        brand_name=data.get('brand_name'),
        usage_notes=data.get('usage_notes'),
        alt_text=data.get('alt_text'),
        platform_suitability=data.get('platform_suitability', []),
        status=data.get('status', 'draft'),
    )

    try:
        db.session.add(asset)
        db.session.commit()
        return jsonify({'success': True, 'data': _serialize_asset(asset)}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@marketing_calendar_bp.route('/assets/<int:asset_id>', methods=['GET'])
def get_asset(asset_id):
    asset = Asset.query.get(asset_id)
    if not asset:
        return jsonify({'success': False, 'error': 'Asset not found'}), 404
    return jsonify({'success': True, 'data': _serialize_asset(asset)})


@marketing_calendar_bp.route('/assets/<int:asset_id>', methods=['PUT'])
def update_asset(asset_id):
    asset = Asset.query.get(asset_id)
    if not asset:
        return jsonify({'success': False, 'error': 'Asset not found'}), 404

    data = request.get_json() or {}
    for field in ['name', 'asset_type', 'file_or_url', 'brand_name', 'usage_notes', 'alt_text', 'platform_suitability', 'status']:
        if field in data:
            setattr(asset, field, data[field])

    try:
        db.session.commit()
        return jsonify({'success': True, 'data': _serialize_asset(asset)})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@marketing_calendar_bp.route('/assets/<int:asset_id>', methods=['DELETE'])
def delete_asset(asset_id):
    asset = Asset.query.get(asset_id)
    if not asset:
        return jsonify({'success': False, 'error': 'Asset not found'}), 404
    try:
        db.session.delete(asset)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Asset deleted'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ============ PERFORMANCE SNAPSHOTS ============

@marketing_calendar_bp.route('/performance-snapshots', methods=['GET'])
def get_performance_snapshots():
    platform = request.args.get('platform')
    related_social_post_id = request.args.get('related_social_post_id')

    query = PerformanceSnapshot.query
    if platform:
        query = query.filter_by(platform=platform)
    if related_social_post_id:
        query = query.filter_by(related_social_post_id=int(related_social_post_id))

    snapshots = query.order_by(PerformanceSnapshot.date_checked.desc()).all()
    return jsonify({'success': True, 'data': [_serialize_snapshot(s) for s in snapshots]})


@marketing_calendar_bp.route('/performance-snapshots', methods=['POST'])
def create_performance_snapshot():
    data = request.get_json() or {}
    required = ['platform', 'post_url', 'date_checked']
    if not all(data.get(field) for field in required):
        return jsonify({'success': False, 'error': 'platform, post_url, and date_checked are required'}), 400

    snapshot = PerformanceSnapshot(
        platform=data['platform'],
        related_social_post_id=data.get('related_social_post_id'),
        post_url=data['post_url'],
        date_checked=datetime.fromisoformat(data['date_checked']),
        impressions_views=data.get('impressions_views', 0),
        likes=data.get('likes', 0),
        comments=data.get('comments', 0),
        shares_reposts=data.get('shares_reposts', 0),
        saves=data.get('saves', 0),
        clicks=data.get('clicks', 0),
        follows_subscribers=data.get('follows_subscribers', 0),
        notes=data.get('notes'),
    )

    try:
        db.session.add(snapshot)
        db.session.commit()
        return jsonify({'success': True, 'data': _serialize_snapshot(snapshot)}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@marketing_calendar_bp.route('/performance-snapshots/<int:snapshot_id>', methods=['GET'])
def get_performance_snapshot(snapshot_id):
    snapshot = PerformanceSnapshot.query.get(snapshot_id)
    if not snapshot:
        return jsonify({'success': False, 'error': 'Performance snapshot not found'}), 404
    return jsonify({'success': True, 'data': _serialize_snapshot(snapshot)})


@marketing_calendar_bp.route('/performance-snapshots/<int:snapshot_id>', methods=['PUT'])
def update_performance_snapshot(snapshot_id):
    snapshot = PerformanceSnapshot.query.get(snapshot_id)
    if not snapshot:
        return jsonify({'success': False, 'error': 'Performance snapshot not found'}), 404

    data = request.get_json() or {}
    for field in ['platform', 'related_social_post_id', 'post_url', 'impressions_views', 'likes', 'comments', 'shares_reposts', 'saves', 'clicks', 'follows_subscribers', 'notes']:
        if field in data:
            setattr(snapshot, field, data[field])
    if 'date_checked' in data:
        snapshot.date_checked = datetime.fromisoformat(data['date_checked']) if data['date_checked'] else snapshot.date_checked

    try:
        db.session.commit()
        return jsonify({'success': True, 'data': _serialize_snapshot(snapshot)})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@marketing_calendar_bp.route('/performance-snapshots/<int:snapshot_id>', methods=['DELETE'])
def delete_performance_snapshot(snapshot_id):
    snapshot = PerformanceSnapshot.query.get(snapshot_id)
    if not snapshot:
        return jsonify({'success': False, 'error': 'Performance snapshot not found'}), 404
    try:
        db.session.delete(snapshot)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Performance snapshot deleted'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ============ AI CONTENT GENERATION ============

@marketing_calendar_bp.route('/generate-content', methods=['POST'])
def generate_content():
    """Use AI to generate content for a task or a whole content plan"""
    data = request.get_json() or {}
    brand_name = data.get('brand_name', '')
    content_type = data.get('content_type', 'social_post')  # social_post, blog, email, content_plan
    platform = data.get('platform', 'twitter')
    topic = data.get('topic', '')
    campaign_id = data.get('campaign_id')
    num_items = min(data.get('num_items', 5), 30)

    if not brand_name:
        return jsonify({'success': False, 'error': 'brand_name is required'}), 400

    brand = Brand.query.filter_by(name=brand_name).first()
    if not brand:
        return jsonify({'success': False, 'error': 'Brand not found'}), 404

    # Get AI config from SystemConfig
    ai_cfg = _resolve_ai_runtime_config()
    ai_provider = ai_cfg['provider']
    ai_url = ai_cfg['url']
    ai_model = ai_cfg['model'] or 'gpt-4o-mini'
    ai_token = ai_cfg.get('token', '')

    if content_type == 'content_plan':
        return _generate_content_plan(
            brand,
            ai_url,
            ai_model,
            topic,
            num_items,
            campaign_id,
            ai_provider=ai_provider,
            ai_token=ai_token,
        )
    else:
        return _generate_single_content(
            brand,
            ai_url,
            ai_model,
            content_type,
            platform,
            topic,
            ai_provider=ai_provider,
            ai_token=ai_token,
        )


def _generate_single_content(brand, ai_url, ai_model, content_type, platform, topic, ai_provider='ollama', ai_token=''):
    """Generate a single piece of content"""
    type_prompts = {
        'social_post': f"Write a {platform} post for {brand.display_name}. Topic: {topic or 'brand awareness'}. "
                       f"Brand description: {brand.description or 'technology company'}. "
                       f"Keep it concise, engaging, include relevant hashtags. Return ONLY the post text.",
        'blog': f"Write a blog post outline for {brand.display_name} about: {topic or 'industry trends'}. "
                f"Brand: {brand.description or 'technology company'}. "
                f"Return a JSON object with keys: title, summary, sections (array of heading+points), cta.",
        'email': f"Write a marketing email for {brand.display_name} about: {topic or 'product update'}. "
                 f"Brand: {brand.description or 'technology company'}. "
                 f"Return a JSON object with keys: subject, preview_text, body, cta_text, cta_url_placeholder.",
    }

    prompt = type_prompts.get(content_type, type_prompts['social_post'])

    try:
        if ai_provider in {'do_agent', 'digitalocean', 'openai'}:
            content, _ = _call_do_agent_chat(ai_url, prompt, model=ai_model, token=ai_token)
        else:
            resp = ext_requests.post(f'{ai_url}/api/generate', json={
                'model': ai_model,
                'prompt': prompt,
                'stream': False,
                'options': {'temperature': 0.7, 'num_predict': 1500}
            }, timeout=120)

            if resp.status_code != 200:
                return jsonify({'success': False, 'error': f'AI returned {resp.status_code}'}), 502

            content = resp.json().get('response', '').strip()

        if content:
            return jsonify({'success': True, 'content': content, 'model': ai_model})
        return jsonify({'success': False, 'error': 'AI did not return content'}), 502
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 502


def _generate_content_plan(brand, ai_url, ai_model, topic, num_items, campaign_id, ai_provider='ollama', ai_token=''):
    """Generate a multi-item content plan with scheduled tasks"""
    prompt = f"""Create a {num_items}-item content calendar plan for {brand.display_name}.
Brand: {brand.description or 'technology company'}
Website: {brand.website_url or ''}
Topic/theme: {topic or 'brand growth and awareness'}

Return ONLY a valid JSON array. Each item must have these exact keys:
- "task_name": short descriptive name (max 60 chars)
- "platform": one of: TWITTER, LINKEDIN, REDDIT, YOUTUBE, DEVTO, WEBSITE, EMAIL
- "task_type": one of: SOCIAL_POST, ARTICLE, VIDEO, EMAIL
- "title": the content title or headline
- "body": brief content description or draft (2-3 sentences)
- "priority": one of: LOW, MEDIUM, HIGH
- "day_offset": number of days from today to schedule (0 = today, 1 = tomorrow, etc.)

Example: [{{"task_name":"LinkedIn thought leadership","platform":"LINKEDIN","task_type":"SOCIAL_POST","title":"Why AI changes everything","body":"Draft content...","priority":"HIGH","day_offset":1}}]

Return ONLY the JSON array, no extra text."""

    try:
        if ai_provider in {'do_agent', 'digitalocean', 'openai'}:
            raw, _ = _call_do_agent_chat(ai_url, prompt, model=ai_model, token=ai_token)
        else:
            resp = ext_requests.post(f'{ai_url}/api/generate', json={
                'model': ai_model,
                'prompt': prompt,
                'stream': False,
                'options': {'temperature': 0.7, 'num_predict': 3000}
            }, timeout=180)

            if resp.status_code != 200:
                return jsonify({'success': False, 'error': f'AI returned {resp.status_code}'}), 502

            raw = resp.json().get('response', '').strip()

        # Try to extract JSON from the response
        items = _extract_json_array(raw)
        if not items:
            return jsonify({'success': False, 'error': 'AI did not return valid JSON', 'raw': raw[:500]}), 422

        # If a campaign_id is provided, create the tasks in the database
        created = []
        if campaign_id:
            for item in items:
                try:
                    offset = int(item.get('day_offset', 0))
                    scheduled = datetime.utcnow() + timedelta(days=offset)
                    platform_str = item.get('platform', 'TWITTER').upper()
                    task_type_str = item.get('task_type', 'SOCIAL_POST').upper()

                    task = MarketingTask(
                        calendar_id=campaign_id,
                        brand_name=brand.name,
                        task_name=item.get('task_name', 'AI Generated Task')[:100],
                        task_slug=item.get('task_name', 'ai-task').lower().replace(' ', '-')[:100],
                        task_type=TaskType[task_type_str] if task_type_str in TaskType.__members__ else TaskType.SOCIAL_POST,
                        platform=PlatformType[platform_str] if platform_str in PlatformType.__members__ else PlatformType.TWITTER,
                        scheduled_date=scheduled,
                        status=TaskStatus.DRAFT,
                        priority=TaskPriority[item.get('priority', 'MEDIUM').upper()] if item.get('priority', 'MEDIUM').upper() in TaskPriority.__members__ else TaskPriority.MEDIUM,
                        title=item.get('title', ''),
                        body=item.get('body', ''),
                        is_automated=True
                    )
                    db.session.add(task)
                    db.session.flush()
                    created.append({'id': task.id, 'task_name': task.task_name, 'platform': task.platform.value})
                except Exception as te:
                    continue

            db.session.commit()

        return jsonify({
            'success': True,
            'items': items,
            'created_count': len(created),
            'created_tasks': created,
            'model': ai_model
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 502


def _extract_json_array(text):
    """Try to extract a JSON array from AI response text"""
    # Try direct parse first
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass

    # Try to find [...] in the text
    start = text.find('[')
    end = text.rfind(']')
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass

    return None

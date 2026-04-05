#!/usr/bin/env python3
"""
OpenBuild Training Blog Article Generator
Connects to Ollama service to generate daily technical articles
"""

import os
import json
import requests
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
import logging
from typing import Dict, List, Optional
import hashlib

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/blog_generator.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class BlogArticleGenerator:
    @staticmethod
    def _get_config(key, default=None):
        """Get config from DB (if Flask context available) or fall back to env var."""
        try:
            from config.config_loader import ConfigLoader
            return ConfigLoader().get_system_config(key, default)
        except Exception:
            return os.getenv(key, default)

    def __init__(self):
        # Configuration from DB (with env var fallback)
        self.ollama_host = self._get_config("OLLAMA_HOST", "http://localhost:11434")
        self.ollama_model = self._get_config("ai_model", "llama3.2:1b")
        self.blog_enabled = os.getenv("BLOG_ENABLED", "true").lower() == "true"
        
        # Blog settings
        self.articles_dir = Path("blog/articles")
        self.articles_dir.mkdir(parents=True, exist_ok=True)
        
        # Database for tracking articles and learning
        self.db_path = "blog_articles.db"
        self.init_database()
        
        # Load reference content
        self.load_reference_content()
        
        # Article categories and business use cases
        self.business_use_cases = [
            {
                "category": "E-commerce",
                "title": "Building a Product Catalog Microservice",
                "business_problem": "Managing thousands of products with real-time inventory",
                "technical_focus": "Microservices, API Gateway, Database Design",
                "ai_assistance": "Code generation, API endpoint creation, database schema optimization"
            },
            {
                "category": "Healthcare",
                "title": "Patient Data Management System",
                "business_problem": "Secure, compliant patient record management with HIPAA compliance",
                "technical_focus": "Security, Encryption, Audit Trails",
                "ai_assistance": "Security pattern implementation, compliance checking, audit log generation"
            },
            {
                "category": "FinTech",
                "title": "Real-time Payment Processing Service",
                "business_problem": "Processing thousands of transactions per second with fraud detection",
                "technical_focus": "Event Streaming, Async Processing, Monitoring",
                "ai_assistance": "Event handler generation, monitoring setup, performance optimization"
            },
            {
                "category": "Education",
                "title": "Learning Management Platform",
                "business_problem": "Scalable course delivery with progress tracking and analytics",
                "technical_focus": "Video Streaming, Analytics, User Management",
                "ai_assistance": "Analytics dashboard creation, user flow optimization, content delivery setup"
            },
            {
                "category": "IoT",
                "title": "Smart Building Management System",
                "business_problem": "Real-time monitoring and control of building systems and energy usage",
                "technical_focus": "Time Series Data, Real-time Analytics, Device Management",
                "ai_assistance": "Data pipeline creation, real-time processing logic, alert system setup"
            }
        ]

    def init_database(self):
        """Initialize SQLite database for article tracking and learning"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Articles table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                category TEXT NOT NULL,
                business_use_case TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                performance_score REAL DEFAULT 0,
                feedback_count INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                published BOOLEAN DEFAULT FALSE
            )
        """)
        
        # Learning feedback table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS article_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                article_id INTEGER,
                feedback_type TEXT,
                feedback_data TEXT,
                created_at TEXT,
                FOREIGN KEY (article_id) REFERENCES articles (id)
            )
        """)
        
        # Generation prompts evolution table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS prompt_evolution (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prompt_version TEXT NOT NULL,
                prompt_content TEXT NOT NULL,
                performance_metrics TEXT,
                created_at TEXT NOT NULL
            )
        """)
        
        conn.commit()
        conn.close()
        logger.info("Database initialized successfully")

    def load_reference_content(self):
        """Load reference content from buildly.io and radicaltherapy.dev"""
        # This would ideally fetch from the actual sites
        # For now, we'll use predefined reference content
        
        self.buildly_reference = {
            "core_concepts": [
                "Microservice orchestration with Buildly Core",
                "API Gateway configuration and routing",
                "Service mesh integration",
                "Container deployment strategies",
                "Data pipeline automation"
            ],
            "tools": [
                "Buildly Core - Microservice orchestration platform",
                "Buildly UI - Frontend component library", 
                "Buildly CLI - Command line development tools",
                "Buildly Marketplace - Pre-built service components"
            ],
            "patterns": [
                "Event-driven architecture",
                "CQRS (Command Query Responsibility Segregation)",
                "Saga pattern for distributed transactions",
                "Circuit breaker pattern for resilience",
                "API versioning strategies"
            ]
        }
        
        self.radical_therapy_reference = {
            "principles": [
                "Rapid prototyping with AI assistance",
                "Test-driven development with AI-generated tests",
                "Continuous learning and adaptation",
                "Focus on business value over technical complexity",
                "Collaborative AI-human development workflows"
            ],
            "process_steps": [
                "1. Problem Analysis - Understanding business context",
                "2. AI-Assisted Design - Generate architecture with AI",
                "3. Rapid Prototyping - Build MVP with AI tools",
                "4. Iterative Enhancement - Learn and improve",
                "5. Production Deployment - Scale and monitor"
            ],
            "ai_integration": [
                "Code generation for boilerplate and patterns",
                "Test case generation and validation",
                "Documentation and API spec creation", 
                "Performance optimization suggestions",
                "Security review and compliance checking"
            ]
        }

    def generate_article_prompt(self, use_case: Dict, day_number: int) -> str:
        """Generate comprehensive prompt for article creation using saved prompt template"""
        
        # Load the comprehensive prompt template from the documentation file
        try:
            prompt_file = Path(__file__).parent.parent / "devdocs" / "BLOG_PROMPTS.md"
            with open(prompt_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Also load the real documentation reference
            real_docs_file = Path(__file__).parent.parent / "devdocs" / "BUILDLY_REAL_DOCS.md"
            real_docs_content = ""
            try:
                with open(real_docs_file, 'r', encoding='utf-8') as f:
                    real_docs_content = f.read()
            except Exception as e:
                logger.warning(f"Could not load real docs reference: {e}")
                real_docs_content = ""
            
            # Extract the comprehensive prompt section
            start_marker = "### Complete Daily Article Generation Prompt"
            end_marker = "### Article Structure Framework"
            
            start_idx = content.find(start_marker)
            end_idx = content.find(end_marker)
            
            if start_idx != -1 and end_idx != -1:
                # Extract the prompt template
                prompt_template = content[start_idx:end_idx].strip()
                
                # Remove the markdown formatting
                prompt_template = prompt_template.replace("### Complete Daily Article Generation Prompt", "")
                prompt_template = prompt_template.replace("```", "").strip()
                
                # Substitute variables in the template
                formatted_prompt = prompt_template.format(
                    day_number=day_number,
                    category=use_case['category'],
                    title=use_case['title'],
                    business_problem=use_case['business_problem'],
                    technical_focus=use_case['technical_focus'],
                    ai_assistance=use_case['ai_assistance']
                )
                
                # Append the real documentation reference for technical accuracy
                if real_docs_content:
                    formatted_prompt += f"\n\n## CRITICAL: TECHNICAL ACCURACY REQUIREMENTS\n\n{real_docs_content}\n\nYou MUST use only the verified technical information above. Do not fabricate CLI commands, features, or workflows that are not documented in the real sources."
                
                return formatted_prompt
            
        except Exception as e:
            logger.warning(f"Could not load prompt template: {e}")
        
        # Fallback to a comprehensive inline prompt if file loading fails
        base_prompt = f"""
# COMPREHENSIVE TRAINING BLOG ARTICLE GENERATION

## CONTEXT AND MISSION
You are writing a technical training article for the Open Build foundry training blog that teaches developers and product managers how to build cloud native services using AI assistance. The core principle is to show how AI removes boring, repetitive work so professionals can focus on creative challenges and unique business logic.

## ARTICLE REQUIREMENTS

### Article Details:
- **Day Number**: {day_number}
- **Industry**: {use_case['category']}
- **Business Title**: {use_case['title']}
- **Business Problem**: {use_case['business_problem']}
- **Technical Focus**: {use_case['technical_focus']}
- **AI Assistance Areas**: {use_case['ai_assistance']}

### Target Audience:
- **Developers**: Learn AI-assisted development techniques
- **Product Managers**: Understand how AI accelerates delivery and improves quality
- **Both**: Focus on creative challenges rather than boilerplate code

### Required Source Integration:
You MUST reference and integrate practical examples from these VERIFIED sources:
- **Buildly.io Platform**: https://www.buildly.io (main platform)
- **Buildly.io Documentation**: https://docs.buildly.io (technical documentation - VERIFIED)
- **Buildly CLI Repository**: https://github.com/buildlyio/buildly-cli (actual CLI commands - VERIFIED)
- **Radical Therapy Process**: https://radicaltherapy.dev (development methodology)
- **Open Source Tools**: https://github.com/buildlyio (community tools)
- **Buildly Labs Platform**: https://labs.buildly.io (deployment platform)

## CRITICAL: USE ONLY REAL TECHNICAL INFORMATION

### Actual Buildly CLI Commands (VERIFIED):
- Setup: git clone https://github.com/buildlyio/buildly-cli.git && cd buildly-cli && chmod +x *.sh
- Development Environment: source dev.sh (interactive menu for Minikube/Helm/Buildly Core)
- Service Generation: ./django.sh (BabbleBeaver AI-powered Django API generation)
- Infrastructure: Auto-installs Docker, Kubernetes (Minikube), Helm, kubectl

### Real Buildly Product Labs Features (VERIFIED):
- Product management platform with AI tools powered by BabbleBeaver AI engine
- Account registration at organization's Buildly Product Labs instance
- AI-Powered Onboarding at https://labs-onboarding.buildly.io/ (Beta)
- Product Portfolio, Roadmap, Release Management, Analytics
- BabbleBeaver-powered intelligent project recommendations and automation
- Integration with open source developer tools (buildly-cli, Buildly Core)
- Team collaboration, notifications, integration management

### Architecture Facts (VERIFIED):
Buildly Labs (Product Management) ↔ Open Source Dev Tools
            ↓                              ↓
    BabbleBeaver AI Engine    →    buildly-cli + Buildly Core
            ↓                              ↓
Frontend (React) ↔ Buildly Core (Gateway) ↔ Microservices (Django)
                            ↓                        ↓
                  Kubernetes Deployment    Database (PostgreSQL)

### Code Generation Sources:
- **Open Source Tools:** buildly-cli and Buildly Core handle code generation
- **AI Engine:** BabbleBeaver powers intelligent code generation and recommendations
- **Infrastructure:** Kubernetes deployment and services monitoring
- **NO COMPETITOR NAMES:** Use generic terms like "AI models" or "LLM providers" instead of specific company names

DO NOT FABRICATE: CLI commands, features, workflows, or API endpoints that are not documented above

## ARTICLE STRUCTURE (FOLLOW EXACTLY)

### 1. Business Use Case Introduction (200-300 words)
Create a compelling narrative featuring a fictional professional facing the exact business challenge:
- Start with "Meet [Name], a [role] at [company type]..."
- Include concrete numbers (costs, time wasted, scale)
- Show why traditional approaches fail
- Demonstrate business impact and urgency
- Set up cloud native + AI as the solution

### 2. Buildly.io Platform Integration (400-500 words)
Demonstrate practical usage of Buildly.io tools with working examples:
- **Buildly Core**: Microservice orchestration (reference https://docs.buildly.io/core/)
- **Buildly Marketplace**: Pre-built components
- **Buildly CLI**: Development tools and automation
- **API Gateway**: Configuration and routing
- Include actual configuration files (YAML, JSON)
- CLI commands with expected output
- Code snippets showing integration

### 3. Radical Therapy Development Process (300-400 words)
Follow the exact methodology from https://radicaltherapy.dev:
1. **Problem Analysis**: Understanding business context and requirements
2. **AI-Assisted Design**: Generate architecture and patterns with AI
3. **Rapid Prototyping**: Build MVP using AI tools and templates
4. **Iterative Enhancement**: Learn from feedback and improve
5. **Production Deployment**: Scale and monitor with AI assistance

For each step, show what humans do vs what AI handles.

### 4. AI-Assisted Implementation (500-600 words)
Provide detailed, practical AI assistance examples:
- **The Boring Work AI Handles**: Boilerplate, tests, configs, documentation
- **Creative Work Humans Focus On**: Business logic, UX, architecture, security
- **Practical AI Prompts** (Include 2-3 working examples with expected output)
- **Quality Assurance**: How AI helps with testing, code review, compliance

### 5. Open Source Integration (200-300 words)
Highlight tools from https://github.com/buildlyio:
- Community-contributed components and extensions
- Integration examples and templates
- How to contribute and collaborate
- Pre-built solutions that accelerate development

### 6. Buildly Labs Platform Usage (200-300 words)
Demonstrate https://labs.buildly.io deployment and operations:
- **Deployment**: One-click deployment configurations
- **Scaling**: Auto-scaling and monitoring setup
- **DevOps**: CI/CD pipeline automation
- **Monitoring**: Performance analytics and alerting

### 7. Key Takeaways & Next Steps (150-200 words)
Summarize concrete learning outcomes:
- **For Developers**: Specific AI tools/techniques, time savings, quality improvements
- **For Product Managers**: Faster delivery, reduced costs, improved predictability
- **Next Article Preview**: Tomorrow's topic and how it builds on today's learning

## TECHNICAL REQUIREMENTS
- All code examples must be working and tested
- Include proper error handling and logging
- Reference actual documentation pages with working URLs
- Professional but approachable tone
- Target 2000-2500 words total
- Focus on practical value over theory
- Show, don't just tell - include working examples

Generate a complete article following this structure exactly, ensuring all requirements are met and all sources are properly referenced with working examples.
"""
        return base_prompt
    
    def save_prompt_version(self, prompt: str, performance_data: Dict = None):
        """Save prompt version for learning and evolution"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Generate version identifier
        prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()[:8]
        version = f"v{datetime.now().strftime('%Y%m%d')}_{prompt_hash}"
        
        cursor.execute("""
            INSERT INTO prompt_evolution (prompt_version, prompt_content, performance_metrics, created_at)
            VALUES (?, ?, ?, ?)
        """, (
            version,
            prompt,
            json.dumps(performance_data) if performance_data else None,
            datetime.now().isoformat()
        ))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Saved prompt version: {version}")

    def call_ollama(self, prompt: str, max_retries: int = 3) -> Optional[str]:
        """Make request to Ollama service with retries"""
        
        # Try both API endpoints (newer and older versions)
        api_endpoints = ["/api/generate", "/v1/generate", "/generate"]
        
        for endpoint in api_endpoints:
            payload = {
                "model": self.ollama_model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.7,
                    "top_p": 0.9,
                    "num_predict": 3000
                }
            }
            
            for attempt in range(max_retries):
                try:
                    logger.info(f"Calling Ollama {endpoint} (attempt {attempt + 1}/{max_retries})")
                    response = requests.post(
                        f"{self.ollama_host}{endpoint}",
                        json=payload,
                        timeout=180
                    )
                    
                    if response.status_code == 404:
                        logger.info(f"Endpoint {endpoint} not found, trying next...")
                        break
                    
                    response.raise_for_status()
                    
                    result = response.json()
                    if 'response' in result:
                        logger.info("Article generated successfully")
                        return result['response']
                    else:
                        logger.error(f"Unexpected response format: {result}")
                        
                except requests.exceptions.RequestException as e:
                    logger.error(f"Ollama request failed (attempt {attempt + 1}): {e}")
                    if attempt < max_retries - 1:
                        logger.info("Retrying in 10 seconds...")
                        import time
                        time.sleep(10)
        
        logger.error("Failed to generate article after all retries and endpoints")
        return None

    def generate_daily_article(self) -> Optional[Dict]:
        """Generate today's article"""
        today = datetime.now().strftime('%Y-%m-%d')
        
        # Check if article already exists for today
        if self.article_exists(today):
            logger.info(f"Article already exists for {today}")
            return self.get_existing_article(today)
        
        # Determine day number and use case
        day_number = self.get_day_number()
        use_case = self.business_use_cases[day_number % len(self.business_use_cases)]
        
        logger.info(f"Generating Day {day_number} article: {use_case['title']}")
        
        # Generate article prompt
        prompt = self.generate_article_prompt(use_case, day_number)
        
        # Save prompt version for learning
        self.save_prompt_version(prompt)
        
        # Call Ollama to generate content
        content = self.call_ollama(prompt)
        
        if not content:
            logger.error("Failed to generate article content")
            return None
        
        # Save article to database
        article_data = {
            'date': today,
            'title': use_case['title'],
            'category': use_case['category'],
            'business_use_case': use_case['business_problem'],
            'content': content,
            'day_number': day_number
        }
        
        article_id = self.save_article(article_data)
        article_data['id'] = article_id
        
        # Save to file system
        self.save_article_file(article_data)
        
        logger.info(f"Article generated and saved: Day {day_number} - {use_case['title']}")
        return article_data

    def article_exists(self, date: str) -> bool:
        """Check if article exists for given date"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM articles WHERE date = ?", (date,))
        exists = cursor.fetchone()[0] > 0
        conn.close()
        return exists

    def get_existing_article(self, date: str) -> Dict:
        """Get existing article for date"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, title, category, business_use_case, content_hash 
            FROM articles WHERE date = ?
        """, (date,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                'id': row[0],
                'date': date,
                'title': row[1],
                'category': row[2],
                'business_use_case': row[3]
            }
        return None

    def get_day_number(self) -> int:
        """Calculate day number since blog started"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM articles")
        count = cursor.fetchone()[0]
        conn.close()
        return count + 1

    def save_article(self, article_data: Dict) -> int:
        """Save article to database"""
        content_hash = hashlib.sha256(article_data['content'].encode()).hexdigest()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO articles (date, title, category, business_use_case, content_hash, created_at, published)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            article_data['date'],
            article_data['title'],
            article_data['category'],
            article_data['business_use_case'],
            content_hash,
            datetime.now().isoformat(),
            True
        ))
        
        article_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return article_id

    def save_article_file(self, article_data: Dict):
        """Save article as HTML file"""
        # Create article HTML
        html_content = self.create_article_html(article_data)
        
        # Save to file
        filename = f"day-{article_data['day_number']}-{article_data['date']}.html"
        filepath = self.articles_dir / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        logger.info(f"Article saved to {filepath}")

    def create_article_html(self, article_data: Dict) -> str:
        """Create HTML format for article"""
        return f"""<!DOCTYPE html>
<html lang="en" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="description" content="{article_data['title']} - Daily cloud native development training from Open Build">
    <title>{article_data['title']} - Open Build Training</title>
    
    <!-- Favicon -->
    <link rel="apple-touch-icon" sizes="180x180" href="../../assets/img/apple-touch-icon.png">
    <link rel="icon" type="image/png" sizes="32x32" href="../../assets/img/favicon.png">
    
    <!-- Fonts -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
    
    <!-- Tailwind CSS -->
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
        tailwind.config = {{
            darkMode: 'class',
            theme: {{
                extend: {{
                    fontFamily: {{
                        'sans': ['Inter', 'system-ui', 'sans-serif'],
                    }},
                    colors: {{
                        primary: {{
                            50: '#eff6ff',
                            100: '#dbeafe',
                            200: '#bfdbfe',
                            300: '#93c5fd',
                            400: '#60a5fa',
                            500: '#3b82f6',
                            600: '#2563eb',
                            700: '#1d4ed8',
                            800: '#1e40af',
                            900: '#1e3a8a',
                        }}
                    }},
                    animation: {{
                        'fadeInUp': 'fadeInUp 0.6s ease-out',
                        'pulse-slow': 'pulse 3s infinite',
                        'bounce-slow': 'bounce 2s infinite',
                    }},
                    keyframes: {{
                        fadeInUp: {{
                            '0%': {{ opacity: '0', transform: 'translateY(30px)' }},
                            '100%': {{ opacity: '1', transform: 'translateY(0)' }},
                        }},
                    }}
                }}
            }}
        }}
    </script>
    
    <!-- Font Awesome -->
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    
    <!-- Custom CSS -->
    <link rel="stylesheet" href="../../assets/css/animations.css">
</head>

<body class="bg-gray-50 dark:bg-gray-900 font-sans transition-colors duration-300">
    <!-- Navigation -->
    <nav class="bg-white dark:bg-gray-800 shadow-lg fixed w-full top-0 z-50 transition-all duration-300">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div class="flex justify-between items-center h-16">
                <div class="flex items-center">
                    <a href="../../index.html" class="flex items-center">
                        <img src="../../assets/img/OPEN-BUILD-LOGO.png" alt="Open Build" class="h-8 w-auto">
                        <span class="ml-2 text-xl font-bold text-gray-900 dark:text-white">Open Build</span>
                    </a>
                </div>
                
                <div class="hidden md:flex items-center space-x-8">
                    <a href="../../index.html" class="text-gray-700 dark:text-gray-300 hover:text-blue-600 dark:hover:text-blue-400 transition-colors">Home</a>
                    <a href="../../training-blog.html" class="text-blue-600 dark:text-blue-400 font-semibold">Training Blog</a>
                    <a href="../../portfolio.html" class="text-gray-700 dark:text-gray-300 hover:text-blue-600 dark:hover:text-blue-400 transition-colors">Portfolio</a>
                </div>
            </div>
        </div>
    </nav>

    <!-- Article Content -->
    <div class="pt-20 min-h-screen bg-gradient-to-br from-blue-50 to-purple-50 dark:from-gray-900 dark:to-gray-800 transition-colors duration-300">
        <div class="max-w-4xl mx-auto px-4 py-8">
            <nav class="mb-8">
                <a href="../../training-blog.html" class="inline-flex items-center text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300 transition-colors">
                    <i class="fas fa-arrow-left mr-2"></i>
                    Back to Training Blog
                </a>
            </nav>
            
            <article class="bg-white dark:bg-gray-800 rounded-lg shadow-xl p-8 animate-fadeInUp">
                <header class="mb-8">
                    <div class="text-sm text-blue-600 dark:text-blue-400 font-semibold mb-2 uppercase tracking-wider">
                        Day {article_data['day_number']} • {article_data['category']}
                    </div>
                    <h1 class="text-4xl font-bold text-gray-900 dark:text-white mb-4 leading-tight">{article_data['title']}</h1>
                    <div class="flex items-center text-gray-600 dark:text-gray-400">
                        <i class="far fa-calendar-alt mr-2"></i>
                        <time datetime="{article_data['date']}">{datetime.strptime(article_data['date'], '%Y-%m-%d').strftime('%B %d, %Y')}</time>
                        <span class="mx-2">•</span>
                        <i class="far fa-clock mr-2"></i>
                        <span>5 min read</span>
                    </div>
                </header>
                
                <div class="prose prose-lg max-w-none">
                    <div class="text-gray-900 dark:text-gray-100">
                        {self.format_article_content(article_data['content'])}
                    </div>
                </div>
                
                <footer class="mt-12 pt-8 border-t border-gray-200 dark:border-gray-700">
                    <div class="flex flex-col sm:flex-row items-start sm:items-center justify-between space-y-4 sm:space-y-0">
                        <div class="text-sm text-gray-500 dark:text-gray-400">
                            <p class="flex items-center mb-1">
                                <i class="fas fa-robot mr-2 text-blue-600 dark:text-blue-400"></i>
                                Generated with AI assistance using Ollama
                            </p>
                            <p class="flex items-center">
                                <i class="fas fa-graduation-cap mr-2 text-purple-600 dark:text-purple-400"></i>
                                Part of the Open Build daily training series
                            </p>
                        </div>
                        <div class="flex space-x-6">
                            <a href="https://www.buildly.io" target="_blank" rel="noopener noreferrer" class="flex items-center text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300 transition-colors">
                                <i class="fas fa-external-link-alt mr-1 text-xs"></i>
                                Buildly.io
                            </a>
                            <a href="https://radicaltherapy.dev" target="_blank" rel="noopener noreferrer" class="flex items-center text-purple-600 dark:text-purple-400 hover:text-purple-800 dark:hover:text-purple-300 transition-colors">
                                <i class="fas fa-external-link-alt mr-1 text-xs"></i>
                                Radical Therapy
                            </a>
                            <a href="https://labs.buildly.io" target="_blank" rel="noopener noreferrer" class="flex items-center text-green-600 dark:text-green-400 hover:text-green-800 dark:hover:text-green-300 transition-colors">
                                <i class="fas fa-external-link-alt mr-1 text-xs"></i>
                                Buildly Labs
                            </a>
                        </div>
                    </div>
                </footer>
            </article>
        </div>
    </div>
</body>
</html>"""

    def format_article_content(self, content: str) -> str:
        """Format AI-generated content for HTML display with proper markdown conversion"""
        import re
        
        # Clean up any existing HTML tags that might be malformed
        content = re.sub(r'<p[^>]*><p[^>]*>', '<p>', content)
        content = re.sub(r'</p></p>', '</p>', content)
        content = re.sub(r'<p[^>]*>\s*</p>', '', content)
        
        # Convert markdown-style formatting
        # Bold text: **text** -> <strong>text</strong>
        content = re.sub(r'\*\*([^*]+)\*\*', r'<strong class="font-bold text-gray-900 dark:text-white">\1</strong>', content)
        
        # Italic text: *text* -> <em>text</em>
        content = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'<em class="italic text-gray-800 dark:text-gray-200">\1</em>', content)
        
        # Headers
        content = re.sub(r'^### (.+)$', r'<h3 class="text-xl font-semibold mt-6 mb-3 text-gray-900 dark:text-white">\1</h3>', content, flags=re.MULTILINE)
        content = re.sub(r'^## (.+)$', r'<h2 class="text-2xl font-bold mt-8 mb-4 text-gray-900 dark:text-white">\1</h2>', content, flags=re.MULTILINE)
        content = re.sub(r'^# (.+)$', r'<h1 class="text-3xl font-bold mt-8 mb-6 text-gray-900 dark:text-white">\1</h1>', content, flags=re.MULTILINE)
        
        # Code blocks
        content = re.sub(r'```([\s\S]*?)```', r'<pre class="bg-gray-100 dark:bg-gray-800 p-4 rounded-lg overflow-x-auto mb-4"><code class="text-gray-900 dark:text-gray-100">\1</code></pre>', content)
        
        # Inline code
        content = re.sub(r'`([^`]+)`', r'<code class="bg-gray-100 dark:bg-gray-800 text-gray-900 dark:text-gray-100 px-2 py-1 rounded text-sm">\1</code>', content)
        
        # Process line by line for paragraphs and lists
        lines = content.split('\n')
        formatted_lines = []
        in_list = False
        
        for i, line in enumerate(lines):
            line = line.strip()
            
            # Skip empty lines
            if not line:
                if in_list:
                    formatted_lines.append('</ul>')
                    in_list = False
                continue
                
            # Handle list items
            if line.startswith('- ') or line.startswith('* '):
                if not in_list:
                    formatted_lines.append('<ul class="list-disc pl-6 mb-4 space-y-2">')
                    in_list = True
                formatted_lines.append(f'<li class="text-gray-700 dark:text-gray-300">{line[2:]}</li>')
            else:
                if in_list:
                    formatted_lines.append('</ul>')
                    in_list = False
                    
                # Skip lines that are already HTML tags
                if line.startswith('<') and line.endswith('>'):
                    formatted_lines.append(line)
                # Skip lines that are already wrapped in HTML
                elif '<p' in line or '<h' in line or '<pre' in line or '<ul' in line:
                    formatted_lines.append(line)
                # Wrap regular text in paragraphs
                else:
                    if line:
                        formatted_lines.append(f'<p class="mb-4 text-gray-700 dark:text-gray-300 leading-relaxed">{line}</p>')
        
        # Close any open list
        if in_list:
            formatted_lines.append('</ul>')
        
        return '\n'.join(formatted_lines)

    def get_recent_articles(self, limit: int = 5) -> List[Dict]:
        """Get recent articles for email inclusion"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT date, title, category, business_use_case 
            FROM articles 
            ORDER BY date DESC 
            LIMIT ?
        """, (limit,))
        
        articles = []
        for row in cursor.fetchall():
            articles.append({
                'date': row[0],
                'title': row[1],
                'category': row[2],
                'business_use_case': row[3]
            })
        
        conn.close()
        return articles

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate training blog articles")
    parser.add_argument("--generate", action="store_true", help="Generate today's article")
    parser.add_argument("--test-ollama", action="store_true", help="Test Ollama connection")
    
    args = parser.parse_args()
    
    generator = BlogArticleGenerator()
    
    if args.test_ollama:
        logger.info("Testing Ollama connection...")
        test_response = generator.call_ollama("Hello, this is a test. Please respond with 'Connection successful!'")
        if test_response:
            logger.info(f"Ollama test successful: {test_response}")
        else:
            logger.error("Ollama test failed")
    
    elif args.generate:
        logger.info("Starting daily article generation...")
        article = generator.generate_daily_article()
        if article:
            logger.info(f"Successfully generated article: {article['title']}")
        else:
            logger.error("Failed to generate article")
    
    else:
        print("Open Build Training Blog Article Generator")
        print("Use --generate to create today's article")
        print("Use --test-ollama to test connection")
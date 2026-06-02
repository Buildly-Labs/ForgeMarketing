#!/bin/bash

# ForgeMark Setup and Deployment Script
# This script handles environment setup, dependency installation, and server management
# Usage: ./ops/startup.sh [setup|start|stop|restart] [OPTIONS]

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${PROJECT_ROOT}/.venv"
PORT=8002
SKIP_VENV=false
CLEAN_MODE=false
PID_FILE="${PROJECT_ROOT}/ops/.server.pid"
LOG_FILE="${PROJECT_ROOT}/ops/server.log"
GUNICORN_WORKERS="${GUNICORN_WORKERS:-1}"

# Functions
print_header() {
    echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

run_marketing_migrations() {
    print_info "Running marketing database migrations..."
    local migration_output
    migration_output=$(bash "$PROJECT_ROOT/ops/run_marketing_migrations.sh" 2>&1)
    local migration_exit_code=$?

    if [ "$migration_exit_code" -eq 0 ]; then
        print_success "Marketing database migrations applied"
    else
        if echo "$migration_output" | grep -q "No such command 'db'"; then
            print_warning "Flask-Migrate CLI is unavailable; skipping migrations for local run"
            return 0
        fi
        print_error "Marketing database migration failed"
        echo "$migration_output"
        return 1
    fi
}

show_help() {
    cat << EOF
ForgeMark Setup and Deployment Script

Usage: ./ops/startup.sh [COMMAND] [OPTIONS]

Commands:
    setup               Set up environment and install dependencies
    start               Start the ForgeMark server
    stop                Stop the ForgeMark server
    restart             Restart the ForgeMark server (stop then start)

Options (for setup command):
    --port PORT         Specify port (default: 8002)
    --no-venv           Skip virtual environment creation
    --clean             Remove .venv and reinstall everything
    --help              Show this help message

Options (for start/restart):
    --port PORT         Specify port (default: 8002)
    
Examples:
    ./ops/startup.sh setup                    # Initial setup with defaults
    ./ops/startup.sh setup --port 9000        # Setup with custom port
    ./ops/startup.sh setup --clean            # Fresh installation
    ./ops/startup.sh start                    # Start server on default port
    ./ops/startup.sh start --port 9000        # Start server on custom port
    ./ops/startup.sh stop                     # Stop the server
    ./ops/startup.sh restart                  # Restart the server

Environment Variables:
    FLASK_ENV          Flask environment (development/production)
    OLLAMA_HOST        Ollama server address (default: localhost:11434)
    DATABASE_URL       Database connection string
    
EOF
}

# Get command
COMMAND="${1:-start}"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --help)
            show_help
            exit 0
            ;;
        --port)
            PORT="$2"
            shift 2
            ;;
        --no-venv)
            SKIP_VENV=true
            shift
            ;;
        --clean)
            CLEAN_MODE=true
            shift
            ;;
        setup|start|stop|restart)
            COMMAND="$1"
            shift
            ;;
        *)
            print_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Main execution based on command
case "$COMMAND" in
    setup)
        print_header "ForgeMark Setup and Deployment"
        
        # Change to project root
        cd "$PROJECT_ROOT"
        print_info "Working directory: $PROJECT_ROOT"
        
        # Step 1: Clean up if requested
        if [ "$CLEAN_MODE" = true ]; then
            print_header "Cleaning Up"
            if [ -d "$VENV_DIR" ]; then
                print_info "Removing existing virtual environment..."
                rm -rf "$VENV_DIR"
                print_success "Virtual environment removed"
            fi
            SKIP_VENV=false
        fi
        
        # Step 2: Check Python installation
        print_header "Checking Prerequisites"
        
        if ! command -v python3 &> /dev/null; then
            print_error "Python 3 is not installed. Please install Python 3.8 or higher."
            exit 1
        fi
        
        PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
        print_success "Python $PYTHON_VERSION found"
        
        if ! command -v git &> /dev/null; then
            print_warning "Git is not installed (optional)"
        else
            print_success "Git is installed"
        fi
        
        # Step 3: Set up virtual environment
        print_header "Setting Up Virtual Environment"
        
        if [ "$SKIP_VENV" = true ]; then
            print_info "Skipping virtual environment creation (--no-venv)"
            if [ ! -d "$VENV_DIR" ]; then
                print_error "Virtual environment not found and --no-venv was specified"
                exit 1
            fi
        else
            if [ -d "$VENV_DIR" ]; then
                print_info "Virtual environment already exists"
            else
                print_info "Creating virtual environment at $VENV_DIR..."
                python3 -m venv "$VENV_DIR"
                print_success "Virtual environment created"
            fi
        fi
        
        # Activate virtual environment
        source "$VENV_DIR/bin/activate"
        print_success "Virtual environment activated"
        
        # Step 4: Install/upgrade pip
        print_header "Installing Dependencies"
        
        print_info "Upgrading pip, setuptools, and wheel..."
        python3 -m pip install --upgrade pip setuptools wheel > /dev/null 2>&1
        print_success "Python package tools upgraded"
        
        # Step 5: Install requirements
        if [ ! -f requirements.txt ]; then
            print_error "requirements.txt not found in project root"
            exit 1
        fi
        
        print_info "Installing Python packages from requirements.txt..."
        pip install -r requirements.txt
        print_success "All dependencies installed"
        
        # Step 6: Check environment configuration
        print_header "Checking Configuration"
        
        # Create .env if it doesn't exist
        if [ ! -f .env ]; then
            if [ -f .env.example ]; then
                print_info "Creating .env from .env.example..."
                cp .env.example .env
                print_warning "Please update .env with your configuration"
            else
                print_warning ".env file not found"
            fi
        else
            print_success ".env file exists"
        fi
        
        # Check for required environment variables
        FLASK_ENV="${FLASK_ENV:-development}"
        OLLAMA_HOST="${OLLAMA_HOST:-localhost:11434}"
        
        print_info "FLASK_ENV: $FLASK_ENV"
        print_info "OLLAMA_HOST: $OLLAMA_HOST"
        print_info "Server port: $PORT"
        
        # Step 7: Check Ollama availability (warning, not error)
        print_header "Checking Optional Services"
        
        if command -v curl &> /dev/null; then
            if curl -s "http://${OLLAMA_HOST}/api/tags" > /dev/null 2>&1; then
                print_success "Ollama service is available at $OLLAMA_HOST"
            else
                print_warning "Ollama service not responding at $OLLAMA_HOST"
                print_info "Start Ollama with: ollama serve"
            fi
        else
            print_info "curl not available, skipping Ollama check"
        fi
        
        # Step 8: Initialize databases
        print_header "Initializing Databases"
        
        # Create data directory if it doesn't exist
        if [ ! -d "data" ]; then
            print_info "Creating data directory..."
            mkdir -p data
            print_success "Data directory created"
        else
            print_success "Data directory exists"
        fi
        
        # Initialize databases
        print_info "Initializing database schemas..."
        python3 -c "
from pathlib import Path
import sqlite3
import sys

project_root = Path('.')
data_dir = project_root / 'data'
data_dir.mkdir(exist_ok=True)

# List of databases to initialize
databases = [
    'marketing_dashboard.db',
    'unified_outreach.db',
    'unified_contacts.db',
    'influencer_discovery.db',
    'activity_tracker.db',
    'cron_management.db',
    'email_stats.db'
]

print('Initializing database files...')
for db_name in databases:
    db_path = data_dir / db_name
    if not db_path.exists():
        # Create empty database file
        conn = sqlite3.connect(str(db_path))
        conn.close()
        print(f'  ✓ Created {db_name}')
    else:
        print(f'  ✓ {db_name} exists')

print('Database initialization complete!')
"
        
        if [ $? -eq 0 ]; then
            print_success "Database files initialized"
        else
            print_error "Database initialization failed"
            exit 1
        fi

        if ! run_marketing_migrations; then
            exit 1
        fi
        
        # Step 9: Run smoke tests
        print_header "Running Smoke Tests"
        
        if [ -f tests/smoke_check.py ]; then
            print_info "Running smoke tests..."
            python3 tests/smoke_check.py
            if [ $? -eq 0 ]; then
                print_success "Smoke tests passed"
            else
                print_warning "Some smoke tests failed (non-blocking)"
            fi
        else
            print_warning "tests/smoke_check.py not found"
        fi
        
        print_header "Setup Complete"
        print_success "Environment is ready!"
        print_info "Start server with: ./ops/startup.sh start"
        ;;
        
    start)
        print_header "Starting ForgeMark Server"
        
        cd "$PROJECT_ROOT"
        
        # Check if server is already running
        if [ -f "$PID_FILE" ]; then
            EXISTING_PID=$(cat "$PID_FILE")
            if kill -0 "$EXISTING_PID" 2>/dev/null; then
                print_warning "Server is already running (PID: $EXISTING_PID)"
                exit 0
            else
                print_info "Cleaning up stale PID file..."
                rm -f "$PID_FILE"
            fi
        fi
        
        # Check if venv exists
        if [ ! -d "$VENV_DIR" ]; then
            print_error "Virtual environment not found. Please run: ./ops/startup.sh setup"
            exit 1
        fi
        
        # Activate virtual environment
        source "$VENV_DIR/bin/activate"
        print_success "Virtual environment activated"
        
        # Check environment configuration
        FLASK_ENV="${FLASK_ENV:-development}"
        OLLAMA_HOST="${OLLAMA_HOST:-localhost:11434}"
        
        print_info "FLASK_ENV: $FLASK_ENV"
        print_info "OLLAMA_HOST: $OLLAMA_HOST"
        print_info "Server port: $PORT"

        if ! run_marketing_migrations; then
            exit 1
        fi
        
        print_success "Configuration complete!"
        echo ""
        print_info "Starting server on port $PORT..."
        echo ""
        
        # Determine which app file to run
        if [ -f "dashboard/app.py" ]; then
            APP_FILE="dashboard.app"
            print_info "Using app from dashboard/app.py"
        elif [ -f "src/api/app.py" ]; then
            APP_FILE="src.api.app"
            print_info "Using app from src/api/app.py"
        else
            print_error "Could not find Flask app.py"
            exit 1
        fi
        
        # Export environment variables
        export FLASK_ENV="${FLASK_ENV}"
        export FLASK_APP="${APP_FILE}"
        export OLLAMA_HOST="${OLLAMA_HOST}"
        
        # Run the server in background
        print_info "╔════════════════════════════════════════╗"
        print_info "║     ForgeMark Server Starting           ║"
        print_info "║     Port: $PORT"
        print_info "║     URL: http://localhost:$PORT"
        print_info "║     Log: $LOG_FILE"
        print_info "║     Stop: ./ops/startup.sh stop        ║"
        print_info "╚════════════════════════════════════════╝"
        echo ""
        
        # Use gunicorn if available, fall back to flask run
        if python3 -c "import gunicorn" 2>/dev/null; then
            print_info "Using Gunicorn server..."
            nohup gunicorn --bind "0.0.0.0:$PORT" --workers "$GUNICORN_WORKERS" --timeout 120 --reload "${APP_FILE}:app" > "$LOG_FILE" 2>&1 &
        else
            print_info "Using Flask development server..."
            nohup python3 -m flask run --host 0.0.0.0 --port "$PORT" > "$LOG_FILE" 2>&1 &
        fi
        
        SERVER_PID=$!
        echo $SERVER_PID > "$PID_FILE"
        
        # Give it a moment to start and check if it's still running
        sleep 2
        if kill -0 "$SERVER_PID" 2>/dev/null; then
            print_success "Server started successfully (PID: $SERVER_PID)"
            print_info "View logs with: tail -f $LOG_FILE"
        else
            print_error "Server failed to start. Check logs at: $LOG_FILE"
            exit 1
        fi
        ;;
        
    stop)
        print_header "Stopping ForgeMark Server"
        
        if [ ! -f "$PID_FILE" ]; then
            print_warning "No PID file found. Server may not be running."
            exit 0
        fi
        
        SERVER_PID=$(cat "$PID_FILE")
        
        if kill -0 "$SERVER_PID" 2>/dev/null; then
            print_info "Stopping server (PID: $SERVER_PID)..."
            kill "$SERVER_PID"
            
            # Wait for graceful shutdown
            for i in {1..10}; do
                if ! kill -0 "$SERVER_PID" 2>/dev/null; then
                    print_success "Server stopped successfully"
                    rm -f "$PID_FILE"
                    exit 0
                fi
                sleep 1
            done
            
            # Force kill if necessary
            print_warning "Server did not stop gracefully, force killing..."
            kill -9 "$SERVER_PID" 2>/dev/null || true
            print_success "Server force stopped"
            rm -f "$PID_FILE"
        else
            print_warning "Server is not running (stale PID file)"
            rm -f "$PID_FILE"
        fi
        ;;
        
    restart)
        print_header "Restarting ForgeMark Server"
        
        # Stop the server
        if [ -f "$PID_FILE" ]; then
            SERVER_PID=$(cat "$PID_FILE")
            if kill -0 "$SERVER_PID" 2>/dev/null; then
                print_info "Stopping running server (PID: $SERVER_PID)..."
                kill "$SERVER_PID"
                
                # Wait for graceful shutdown
                for i in {1..10}; do
                    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
                        print_success "Server stopped"
                        rm -f "$PID_FILE"
                        break
                    fi
                    sleep 1
                done
                
                # Force kill if necessary
                if kill -0 "$SERVER_PID" 2>/dev/null; then
                    kill -9 "$SERVER_PID" 2>/dev/null || true
                    rm -f "$PID_FILE"
                fi
            fi
        fi
        
        # Wait a moment before restarting
        sleep 2
        
        # Start the server
        "$0" start --port "$PORT"
        ;;
        
    *)
        print_error "Unknown command: $COMMAND"
        show_help
        exit 1
        ;;
esac

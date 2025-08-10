#!/bin/bash

# 🚀 Wallet Monitor - One-Click Installation Script
# Download and execute: curl -fsSL https://raw.githubusercontent.com/haohaoi34/Wallet-monitoring/main/install.sh | bash

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
PURPLE='\033[0;35m'
NC='\033[0m'

# Banner
print_banner() {
    clear
    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║                🚀 WALLET MONITOR INSTALLER 🚀               ║"
    echo "║              Enterprise Multi-Chain Monitor                  ║"
    echo "║                     Version 2.1                             ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

# Logging functions
log() { echo -e "${BLUE}🔄 $1${NC}"; }
success() { echo -e "${GREEN}✅ $1${NC}"; }
warn() { echo -e "${YELLOW}⚠️  $1${NC}"; }
error() { echo -e "${RED}❌ $1${NC}"; }

# Detect OS
detect_os() {
    log "Detecting operating system..."
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        OS="linux"
        if command -v apt-get &> /dev/null; then
            DISTRO="debian"
        elif command -v yum &> /dev/null; then
            DISTRO="redhat"
        elif command -v pacman &> /dev/null; then
            DISTRO="arch"
        else
            DISTRO="unknown"
        fi
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        OS="macos"
        DISTRO="macos"
    elif [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "win32" ]]; then
        OS="windows"
        DISTRO="windows"
    else
        OS="unknown"
        DISTRO="unknown"
    fi
    success "Detected: $OS ($DISTRO)"
}

# Check and install Python
check_python() {
    log "Checking Python installation..."
    PYTHON_CMD=""
    
    for cmd in python3.11 python3.10 python3.9 python3.8 python3 python; do
        if command -v $cmd &> /dev/null; then
            VERSION=$($cmd --version 2>&1 | grep -oE '[0-9]+\.[0-9]+')
            MAJOR=$(echo $VERSION | cut -d. -f1)
            MINOR=$(echo $VERSION | cut -d. -f2)
            
            if [[ $MAJOR -eq 3 ]] && [[ $MINOR -ge 8 ]]; then
                PYTHON_CMD=$cmd
                PYTHON_VERSION=$VERSION
                break
            fi
        fi
    done
    
    if [[ -z "$PYTHON_CMD" ]]; then
        error "Python 3.8+ not found. Installing..."
        install_python
    else
        success "Found Python $PYTHON_VERSION"
    fi
}

# Install Python based on OS
install_python() {
    case $OS in
        "linux")
            case $DISTRO in
                "debian")
                    log "Installing Python on Debian/Ubuntu..."
                    sudo apt-get update
                    sudo apt-get install -y python3 python3-pip python3-venv curl wget git
                    ;;
                "redhat")
                    log "Installing Python on RedHat/CentOS..."
                    sudo yum install -y python3 python3-pip curl wget git
                    ;;
                "arch")
                    log "Installing Python on Arch Linux..."
                    sudo pacman -S python python-pip curl wget git
                    ;;
                *)
                    error "Unsupported Linux distribution. Please install Python 3.8+ manually."
                    exit 1
                    ;;
            esac
            PYTHON_CMD="python3"
            ;;
        "macos")
            if command -v brew &> /dev/null; then
                log "Installing Python via Homebrew..."
                brew install python@3.9 curl wget git
            else
                error "Homebrew not found. Please install Python 3.8+ from python.org"
                exit 1
            fi
            PYTHON_CMD="python3"
            ;;
        "windows")
            error "Please install Python 3.8+ from python.org and rerun this script"
            exit 1
            ;;
        *)
            error "Unsupported operating system. Please install Python 3.8+ manually."
            exit 1
            ;;
    esac
}

# Create project directory
setup_project() {
    log "Setting up project directory..."
    
    # Create project directory
    PROJECT_DIR="$HOME/wallet-monitor"
    mkdir -p "$PROJECT_DIR"
    cd "$PROJECT_DIR"
    
    success "Project directory: $PROJECT_DIR"
}

# Download project files
download_files() {
    log "Downloading project files..."
    
    # GitHub repository URL
    REPO_URL="https://raw.githubusercontent.com/haohaoi34/Wallet-monitoring/main"
    
    # Download main files
    curl -fsSL "$REPO_URL/wallet_monitor.py" -o wallet_monitor.py
    curl -fsSL "$REPO_URL/requirements.txt" -o requirements.txt
    curl -fsSL "$REPO_URL/config.env.template" -o config.env.template
    
    success "Project files downloaded"
}

# Setup virtual environment
setup_venv() {
    log "Setting up Python virtual environment..."
    
    if [[ ! -d "venv" ]]; then
        $PYTHON_CMD -m venv venv
        success "Virtual environment created"
    else
        success "Virtual environment already exists"
    fi
    
    # Activate virtual environment
    case $OS in
        "windows")
            source venv/Scripts/activate
            ;;
        *)
            source venv/bin/activate
            ;;
    esac
    
    success "Virtual environment activated"
}

# Install dependencies
install_dependencies() {
    log "Installing Python dependencies..."
    
    # Upgrade pip
    python -m pip install --upgrade pip -q
    
    # Install dependencies
    python -m pip install -r requirements.txt -q
    
    success "Dependencies installed successfully"
}

# Create configuration
create_config() {
    log "Creating configuration files..."
    
    # Create .env from template
    if [[ ! -f ".env" ]]; then
        cp config.env.template .env
        success "Configuration template created (.env)"
        warn "Please edit .env file with your API keys and settings"
    fi
    
    # Create logs directory
    mkdir -p logs
    success "Logs directory created"
}

# Show next steps
show_next_steps() {
    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║                    🎉 INSTALLATION COMPLETE! 🎉             ║"
    echo "║                                                              ║"
    echo "║  Next steps:                                                 ║"
    echo "║  1. Edit configuration: nano .env                           ║"
    echo "║  2. Add your API keys and target addresses                 ║"
    echo "║  3. Start the application: python wallet_monitor.py        ║"
    echo "║                                                              ║"
    echo "║  Project location: $PROJECT_DIR                            ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

# Launch application option
launch_app() {
    echo -e "${YELLOW}"
    read -p "Would you like to start the application now? (y/N): " -n 1 -r
    echo -e "${NC}"
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log "Starting Wallet Monitor..."
        python wallet_monitor.py
    else
        echo -e "${GREEN}You can start the application later with:${NC}"
        echo -e "${CYAN}cd $PROJECT_DIR && source venv/bin/activate && python wallet_monitor.py${NC}"
    fi
}

# Main installation function
main() {
    print_banner
    
    # Installation steps
    detect_os
    check_python
    setup_project
    download_files
    setup_venv
    install_dependencies
    create_config
    
    # Show completion
    show_next_steps
    launch_app
}

# Handle command line arguments
case "${1:-}" in
    --help|-h)
        echo "Wallet Monitor One-Click Installer"
        echo ""
        echo "Usage:"
        echo "  curl -fsSL https://raw.githubusercontent.com/haohaoi34/Wallet-monitoring/main/install.sh | bash"
        echo ""
        echo "Or download and run:"
        echo "  curl -fsSL https://raw.githubusercontent.com/haohaoi34/Wallet-monitoring/main/install.sh -o install.sh"
        echo "  chmod +x install.sh"
        echo "  ./install.sh"
        echo ""
        echo "Options:"
        echo "  --help, -h     Show this help message"
        echo ""
        exit 0
        ;;
    *)
        main "$@"
        ;;
esac 

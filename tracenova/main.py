"""
TraceNova - AI Digital Intelligence Platform
Entry point for the application
"""

import os
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app import create_app

if __name__ == "__main__":
    import uvicorn
    
    app = create_app()
    
    print("""
    ╔═══════════════════════════════════════╗
    ║       TraceNova Starting...           ║
    ║   AI Digital Intelligence Platform    ║
    ╚═══════════════════════════════════════╝
    """)
    print("🚀 Server: http://localhost:8000")
    print("📖 Docs: http://localhost:8000/docs")
    print("Press Ctrl+C to stop\n")
    
    uvicorn.run(app, host="0.0.0.0", port=8000)
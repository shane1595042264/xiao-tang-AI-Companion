"""
XiaoTang AI Companion

A modular AI streaming companion architecture:

src/
├── brain/       - Core reasoning, LLM, decision making
├── voice/       - Text-to-speech synthesis
├── vision/      - Screen reading, image analysis (future)
├── hands/       - Computer control, app launching
├── memory/      - MCP-style semantic memory storage
│   └── knowledge/  - Persistent knowledge files
├── senses/      - Input processing (danmaku, etc.)
├── overlay/     - OBS streaming output
├── config.py    - Configuration management
└── main.py      - Application entry point
"""

__version__ = "0.2.0"

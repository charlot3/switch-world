"""The Geek Room layer: Bifrost for model calls, Tavily for the real world.

The Flip edition keeps Switch as the core and Claude Code/OpenCode as the live cast.
The Geek Room edition adds two providers *around* the same world engine:

- Bifrost (Maxim AI) is the OpenAI-compatible gateway every character model call goes
  through. It owns per-character models, fallbacks, budgets and request logs.
- Tavily turns real news into shared world events and gives characters live retrieval
  when they are asked about the present.
"""

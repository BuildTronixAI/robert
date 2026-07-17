"""
Engine0 config — shared Precon configuration.

Previously a dangling symlink into OpenClaw. Re-export A-0 config so engine0
imports resolve inside the Robert workspace without external paths.
"""

from precon.a0.config import *  # noqa: F401,F403

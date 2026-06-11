"""Meet adapter — bidirectional simultaneous translation for Google Meet / Zoom / Teams.

Identical plumbing to the bridge adapter (two parallel pipelines over VB-Audio
Cable); only the user-facing instructions differ.

Setup:
  1. Install VB-Audio Cable: https://vb-audio.com/Cable/
  2. In Meet / Zoom, select "CABLE Output" as your microphone.
  3. Run: chasqui listen --adapter meet
"""

from .bridge import BridgeAdapter


class MeetAdapter(BridgeAdapter):
    """Bidirectional real-time translation for video calls."""

    header = "Meet mode (bidirectional)"
    app_label = "Meet / Zoom / Teams"

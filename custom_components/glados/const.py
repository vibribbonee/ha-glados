"""Constants for the GLaDOS integration."""

from __future__ import annotations

DOMAIN = "glados"

# Services
SERVICE_CLEAN_TEXT = "clean_text"
SERVICE_SAY = "say"
SERVICE_ANNOUNCE = "announce"
SERVICE_ROOM_CONTEXT = "room_context"
SERVICE_REMEMBER = "remember"
SERVICE_RECALL = "recall"
SERVICE_WHO = "who"

# Service fields
ATTR_TEXT = "text"
ATTR_FACTS = "facts"
ATTR_TASK = "task"
ATTR_REQUEST = "request"
ATTR_AREA = "area"
ATTR_IGNORE_SCHEDULE = "ignore_schedule"
ATTR_ANYWHERE = "anywhere"
ATTR_VOICE = "voice"
ATTR_GLADOS_AFTER = "glados_after"
ATTR_KEY = "key"
ATTR_VALUE = "value"
ATTR_PERSON = "person"

VOICE_GLADOS = "glados"
VOICE_ANNOUNCER = "announcer"

# Options (with their defaults, matching the helpers the scripts use today)
CONF_CHAT_AGENT = "chat_agent"
CONF_VOICE_AGENT = "voice_agent"
CONF_ANNOUNCER_VOICE = "announcer_voice"  # "tts.engine:voice"
CONF_BEEP_IN = "beep_in"
CONF_BEEP_OUT = "beep_out"
CONF_SCHEDULE = "speaking_schedule"
CONF_ROUTINE_MINUTES = "routine_minutes"

DEFAULTS: dict[str, str | int] = {
    CONF_CHAT_AGENT: "conversation.glados_extended",
    CONF_VOICE_AGENT: "conversation.glados_voice",
    CONF_ANNOUNCER_VOICE: "tts.piper_2:announcer",
    CONF_BEEP_IN: "media-source://media_source/local/portal-2-beep-in.mp3",
    CONF_BEEP_OUT: "media-source://media_source/local/beep-out.mp3",
    CONF_SCHEDULE: "schedule.glados_may_speak_up",
    CONF_ROUTINE_MINUTES: 35,
}

# Labels people put on their own devices
LABEL_GLADOS = "glados"
LABEL_QUIET = "glados_quiet"
LABEL_HEATING = "glados_heating"
LABEL_COOLING = "glados_cooling"
LABEL_OWN_CHIME = "glados_own_chime"

# Device classes that mean someone is in a room
PRESENCE_CLASSES = ("occupancy", "presence", "motion")
BED_CLASSES = ("occupancy", "presence")
BED_PATTERN = r"(^|[._])bed([._]|$)"
BEDROOM_NAME_PATTERN = r"bed|slaap"

# Per-person helpers, found by name: <prefix><person object id>
LEAVE_HELPER_PREFIX = "input_datetime.leave_home_"
ROUTINE_HELPER_PREFIX = "input_number.morning_routine_"
ROUTINE_DEFAULT_HELPER = "input_number.morning_routine_minutes"
# A person's own to-do list: todo.<person object id>_s_list ("Nico's list")
OWN_LIST_TEMPLATE = "todo.{slug}_s_list"
SHARED_LIST = "todo.to_do"

# Morning alarms count until this hour
MORNING_ENDS_HOUR = 13

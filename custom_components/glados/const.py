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
SERVICE_TEST_ANNOUNCEMENT = "test_announcement"
SERVICE_BRIEFING = "briefing"
SERVICE_GREET = "greet"

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
ATTR_SATELLITE = "satellite"
ATTR_CO2 = "co2"
ATTR_STYLE = "style"
ATTR_REMINDER = "reminder"
ATTR_MORNING = "morning"
ATTR_PLAIN = "plain"
ATTR_PRETEND_BIRTHDAY = "pretend_birthday"

VOICE_GLADOS = "glados"
VOICE_ANNOUNCER = "announcer"

# Options. Every one may be empty, so any home can start with only a chat agent.
CONF_CHAT_AGENT = "chat_agent"  # answers when you talk to her
CONF_PERSONALITY = "personality"  # send her persona as an extra system prompt
CONF_HOME_TOWN = "home_town"
CONF_VOICE_AGENT = "voice_agent"  # rewrites announcements; empty: the chat agent
CONF_ANNOUNCER_VOICE = "announcer_voice"  # "tts.engine:voice"; empty: her own voice
CONF_BEEP_IN = "beep_in"
CONF_BEEP_OUT = "beep_out"
CONF_SCHEDULE = "speaking_schedule"  # a schedule entity; empty: any time
CONF_ROUTINE_MINUTES = "routine_minutes"
CONF_CO2_ALERTS = "co2_alerts"  # announcer, glados or off
CONF_CO2_REMINDER = "co2_reminder_minutes"  # 0: no reminder
CONF_BEDTIME_SENSOR = "bedtime_sensor"  # optional timestamp sensor: when to be asleep
CONF_BEDTIME = "bedtime_nudges"  # per person: an hour before, bedtime, last call
CONF_SLEEP_GOAL = "sleep_goal_hours"
CONF_MIN_SLEEP = "minimum_sleep_hours"
CONF_USUAL_BEDTIME = "usual_bedtime"  # HH:MM, for nights without a morning alarm
CONF_MORNING = "morning_greeting"  # wake-up greeting, birthday, "in suspension for"
CONF_BIRTHDAY_SONG = "birthday_song"  # media id, played before the birthday line
CONF_BIRTHDAY_NAMES = "birthday_names"  # "nico: Sjors, Nico; byte: Bee"
CONF_LEAVE_HEADS_UP = "leave_heads_up_minutes"  # 0: only "leave now"
CONF_REMINDERS = "reminders"  # say due reminders (and keep the night's)
CONF_ALARM_BACKUP = "alarm_backup_minutes"  # a phone alarm not dismissed by then rings the room
CONF_COLD_OUTSIDE = "cold_outside_below"  # degrees: an open window counts as wasteful

DEFAULTS: dict[str, str | int | bool] = {
    CONF_CHAT_AGENT: "",
    CONF_PERSONALITY: True,
    CONF_HOME_TOWN: "",
    CONF_VOICE_AGENT: "",
    CONF_ANNOUNCER_VOICE: "",
    CONF_BEEP_IN: "",
    CONF_BEEP_OUT: "",
    CONF_SCHEDULE: "",
    CONF_ROUTINE_MINUTES: 35,
    CONF_CO2_ALERTS: "off",
    CONF_CO2_REMINDER: 30,
    CONF_COLD_OUTSIDE: 8,
    CONF_ALARM_BACKUP: 10,
    CONF_REMINDERS: True,
    CONF_BEDTIME_SENSOR: "",
    CONF_LEAVE_HEADS_UP: 15,
    CONF_MORNING: True,
    CONF_BEDTIME: True,
    CONF_SLEEP_GOAL: 8,
    CONF_MIN_SLEEP: 6,
    CONF_USUAL_BEDTIME: "",
    CONF_BIRTHDAY_SONG: "",
    CONF_BIRTHDAY_NAMES: "",
}

# Labels people put on their own devices
LABEL_GLADOS = "glados"
LABEL_QUIET = "glados_quiet"
LABEL_HEATING = "glados_heating"
LABEL_COOLING = "glados_cooling"
LABEL_OWN_CHIME = "glados_own_chime"
LABEL_BEDROOM = "glados_bedroom"  # on an area: a bedroom, whatever its name
LABEL_LEFT_ON = "glados_left_on"  # should not stay on when everyone leaves or sleeps

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

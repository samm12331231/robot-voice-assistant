import io
from contextlib import redirect_stdout
from unittest.mock import patch

import language_utils as lu
import live_info
import main


def mixed(label, text):
    print(f"--- {label} ---")
    print(repr(text))
    print(lu.event_mixed_live_request(text))
    print()


mixed("Paris/Rome two cities, explicit langs", "Tell me the time in Paris in Arabic, and the weather in Rome in Hindi.")
mixed("Dubai/Tokyo two cities, NO explicit lang", "Tell me the time in Dubai and the weather in Tokyo.")
mixed("Dubai/Tokyo, only 2nd clause has lang", "Tell me the time in Dubai and the weather in Tokyo in Arabic.")
mixed("Dubai/Tokyo, only 1st clause has lang", "Tell me the time in Dubai in Arabic and the weather in Tokyo.")
mixed("Mandarin spelled alone", "Tell me the time in Dubai in Mandarin, and the weather in Tokyo in Hindi.")
mixed("trailing please after language", "Tell me the time in Dubai in Arabic please, and the weather in Tokyo in Hindi please.")
mixed("joined by 'or'", "Tell me the time in Dubai in Arabic or the weather in Tokyo in Hindi.")
mixed("both clauses use 'there'", "What time is it there in Arabic, and what's the weather there in Hindi?")
mixed("forward reference there in first clause", "What time is it there in Arabic, and what's the weather in Dubai in Hindi?")
mixed("multi-word unknown city", "Tell me the time in Ras Al Khaimah in Arabic, and the weather in Tokyo in Hindi.")
mixed("weather then time with comma only, no connector word", "Tell me the weather in Dubai in Arabic, the time in Tokyo in Hindi.")
mixed("capitalbabetical language name case sensitivity", "Tell me the time in Dubai in ARABIC, and the weather in Tokyo in HINDI.")

print("=== live_info_kind + extract_explicit_location for two-city, no-lang sentence ===")
msg = "Tell me the time in Dubai and the weather in Tokyo."
print("kind:", live_info.live_info_kind(msg))
print("loc:", live_info.extract_explicit_location(msg))
print()


def end_to_end(label, prompt, weather_text, time_text):
    print(f"=== {label} ===")
    saved_state = dict(main.SESSION_STATE)
    try:
        main._reset_session()

        def fake_context(req, loc=None):
            return weather_text if "weather" in req else time_text

        with (
            patch.object(main, "_speak"),
            patch("live_info.get_live_context", side_effect=fake_context),
            patch.dict("os.environ", {"LANGUAGE_MODE": "event_en_ar_hi_zh"}),
        ):
            out = io.StringIO()
            with redirect_stdout(out):
                main.run_text_mode(prompt)
            print(out.getvalue())
    finally:
        main.SESSION_STATE.clear()
        main.SESSION_STATE.update(saved_state)


end_to_end(
    "mixed-city no explicit language (event mode)",
    "What's the weather in Tokyo and what time is it in Dubai?",
    "Live weather for Tokyo: 20°C, clear sky.",
    "Live time for Dubai: 03:00 PM.",
)

end_to_end(
    "mixed-city different languages but one clause missing language",
    "Tell me the time in Dubai and the weather in Tokyo in Arabic.",
    "Live weather for Tokyo: 20°C, clear sky.",
    "Live time for Dubai: 03:00 PM.",
)

end_to_end(
    "trailing please after language, two cities",
    "Tell me the time in Dubai in Arabic please, and the weather in Tokyo in Hindi please.",
    "Live weather for Tokyo: 20°C, clear sky.",
    "Live time for Dubai: 03:00 PM.",
)


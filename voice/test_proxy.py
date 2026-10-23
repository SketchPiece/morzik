"""Tests for the voice proxy's stream transform: python3 -m unittest voice/test_proxy.py"""

import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from proxy import (ERROR_LINE, LIMIT_LINE, SessionChains, frame_text,  # noqa: E402
                   speech_stream, transcript_key)

FILLER = "Секунду, гляну... "


def event(data, name=None):
    text = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    raw = ([f"event: {name}\n".encode()] if name else []) + [f"data: {text}\n".encode(), b"\n"]
    return name, text, raw


def chunk(delta=None, finish=None, **extra):
    return event({"id": "c1", "created": 1, "model": "morzik-voice",
                  "choices": [{"index": 0, "delta": delta or {}, "finish_reason": finish}], **extra})


def spoken(frames):
    """Text the caller would hear, plus the finish reason it gets."""
    text, finish = "", None
    for frame in frames:
        for line in frame.decode().splitlines():
            if line.startswith("data: ") and line != "data: [DONE]":
                choice = json.loads(line[6:])["choices"][0]
                text += choice["delta"].get("content", "")
                finish = choice["finish_reason"] or finish
    return text, finish


class SpeechStreamTest(unittest.TestCase):
    def test_plain_answer_passes_through(self):
        frames = list(speech_stream([chunk({"role": "assistant"}), chunk({"content": "Мур."}),
                                     chunk(finish="stop"), event("[DONE]")], FILLER))
        self.assertEqual(spoken(frames), ("Мур.", "stop"))
        self.assertEqual(frames[-1], b"data: [DONE]\n\n")

    def test_filler_when_tool_starts_before_any_words(self):
        progress = event({"tool": "web_search", "status": "running"}, "hermes.tool.progress")
        done = event({"tool": "web_search", "status": "completed"}, "hermes.tool.progress")
        frames = list(speech_stream([chunk({"role": "assistant"}), progress, done,
                                     chunk({"content": "Ясно, плюс девятнадцать."}),
                                     chunk(finish="stop"), event("[DONE]")], FILLER))
        self.assertEqual(spoken(frames), (FILLER + "Ясно, плюс девятнадцать.", "stop"))
        self.assertFalse(any(b"hermes.tool.progress" in f for f in frames))

    def test_no_filler_after_words(self):
        progress = event({"tool": "web_search", "status": "running"}, "hermes.tool.progress")
        frames = list(speech_stream([chunk({"content": "Ща гляну. "}), progress,
                                     chunk({"content": "Солнечно."}), chunk(finish="stop")], FILLER))
        self.assertEqual(spoken(frames)[0], "Ща гляну. Солнечно.")

    def test_rate_limit_text_is_replaced(self):
        frames = list(speech_stream([
            chunk({"role": "assistant"}),
            chunk({"content": "Claude Subscription DirectSDK rate-limited every one of 3 attempts"}),
            chunk(finish="error", error={"message": "HTTP 429: session limit", "type": "agent_error"}),
            event("[DONE]")], FILLER))
        self.assertEqual(spoken(frames), (" " + LIMIT_LINE, "stop"))

    def test_other_failure_is_replaced(self):
        frames = list(speech_stream([chunk({"content": "Traceback..."}),
                                     chunk(finish="error", error={"message": "boom"})], FILLER))
        self.assertEqual(spoken(frames), (" " + ERROR_LINE, "stop"))

    def test_hermes_status_events_are_dropped(self):
        frames = list(speech_stream([event({"kind": "wait"}, "hermes.status"),
                                     chunk({"content": "Да."}), chunk(finish="stop")], FILLER))
        self.assertEqual(spoken(frames), ("Да.", "stop"))
        self.assertFalse(any(b"hermes.status" in f for f in frames))


class TurnChainTest(unittest.TestCase):
    def test_next_turn_finds_the_session(self):
        chains = SessionChains()
        turn1 = [{"role": "system", "content": "Голос."}, {"role": "assistant", "content": "Мур, привет!"},
                 {"role": "user", "content": "Какая погода?"}]
        spoken = text_of(speech_stream([chunk({"content": "Плюс девять."}), chunk(finish="stop")], FILLER))
        chains.put(transcript_key(turn1 + [{"role": "assistant", "content": FILLER + spoken}]), "api-1")
        # ElevenLabs resends the call; spacing around the filler may differ.
        turn2 = turn1 + [{"role": "assistant", "content": "Секунду, гляну...  Плюс девять."},
                         {"role": "user", "content": "А послезавтра?"}]
        self.assertEqual(chains.get(transcript_key(turn2[:-1])), "api-1")

    def test_system_prompt_may_change_between_turns(self):
        chains = SessionChains()
        turn1 = [{"role": "system", "content": "Сейчас 16:28."}, {"role": "user", "content": "Погода?"}]
        chains.put(transcript_key(turn1 + [{"role": "assistant", "content": "Дождь."}]), "api-1")
        turn2 = [{"role": "system", "content": "Сейчас 16:29."}, {"role": "user", "content": "Погода?"},
                 {"role": "assistant", "content": "Дождь."}, {"role": "user", "content": "Точно?"}]
        self.assertEqual(chains.get(transcript_key(turn2[:-1])), "api-1")

    def test_transcript_without_audio_tags_matches(self):
        sent = [{"role": "user", "content": "Как дела?"},
                {"role": "assistant", "content": "[mischievously] Мрр, отлично!  А у тебя?"}]
        heard = [{"role": "user", "content": "Как дела?"},
                 {"role": "assistant", "content": "Мрр, отлично! А у тебя?"}]
        self.assertEqual(transcript_key(sent), transcript_key(heard))

    def test_other_call_starts_fresh(self):
        chains = SessionChains()
        chains.put(transcript_key([{"role": "user", "content": "Привет"},
                                   {"role": "assistant", "content": "Мур."}]), "api-1")
        self.assertIsNone(chains.get(transcript_key([{"role": "user", "content": "Привет"}])))
        self.assertIsNone(chains.get(transcript_key([{"role": "user", "content": "Привет"},
                                                     {"role": "assistant", "content": "Мяу."}])))


def text_of(frames):
    return "".join(frame_text(f) for f in frames)


if __name__ == "__main__":
    unittest.main()

"""Tests for the parts of HeySpeaky that need no microphone.

Most of this project is Win32 behaviour and live audio, which is awkward to
test in CI. These cover the pure logic underneath: audio maths, the segment
merging, the cloud request shapes, config merging and the capped log stream.

Run them:

    .venv\\Scripts\\python.exe -m unittest discover -s tests -v

They use only the standard library plus numpy, so CI can run them on a machine
with no sound card.
"""

import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from heyspeaky import config as config_module          # noqa: E402
from heyspeaky import dictionary as dictionary_module   # noqa: E402
from heyspeaky.transcribe import (                     # noqa: E402
    CloudBackend, _default_keywords, _default_prompt, _join_segments,
    _merge_spans, pcm_to_float, pcm_to_wav,
)

_real_dictionary = dictionary_module.PATH


def setUpModule():
    """Points the personal dictionary somewhere empty for the whole run.

    A request carries whatever words the person running the tests has had to
    correct, because that file is read fresh on every transcription. Left
    alone, the keyword tests pass on a clean CI runner and fail on the
    owner's machine - which is how this was found.
    """
    global _real_dictionary
    _real_dictionary = dictionary_module.PATH
    dictionary_module.PATH = os.path.join(tempfile.mkdtemp(), "none.json")


def tearDownModule():
    dictionary_module.PATH = _real_dictionary

RATE = 16000


def tone(seconds, freq=200.0, amplitude=0.4, rate=RATE):
    """A voiced-sounding buffer. Not speech, but not silence either."""
    t = np.arange(int(seconds * rate)) / rate
    wave = np.sin(2 * np.pi * freq * t) * amplitude
    return (wave * 32767).astype(np.int16).tobytes()


def silence(seconds, rate=RATE):
    return np.zeros(int(seconds * rate), dtype=np.int16).tobytes()


class AudioMaths(unittest.TestCase):
    def test_pcm_to_float_round_trips_scale(self):
        pcm = np.array([0, 16384, -16384], dtype=np.int16).tobytes()
        out = pcm_to_float(pcm)
        self.assertEqual(out.dtype, np.float32)
        self.assertAlmostEqual(out[0], 0.0, places=4)
        self.assertAlmostEqual(out[1], 0.5, places=3)
        self.assertAlmostEqual(out[2], -0.5, places=3)

    def test_pcm_to_float_handles_empty(self):
        self.assertEqual(len(pcm_to_float(b"")), 0)

    def test_pcm_to_wav_has_a_riff_header(self):
        wav = pcm_to_wav(tone(0.1), RATE)
        self.assertTrue(wav.startswith(b"RIFF"))
        self.assertIn(b"WAVE", wav[:16])
        # 16-bit mono at the rate we asked for.
        self.assertEqual(int.from_bytes(wav[24:28], "little"), RATE)
        self.assertEqual(int.from_bytes(wav[34:36], "little"), 16)


class MergeSpans(unittest.TestCase):
    """Whisper pads every piece to 30s, so segment count is what costs time."""

    def test_caps_the_number_of_segments(self):
        spans = [(i * RATE, i * RATE + RATE) for i in range(10)]
        merged = _merge_spans(spans, RATE, max_segments=3, min_keep=0.0)
        self.assertLessEqual(len(merged), 3)

    def test_absorbs_segments_that_are_too_short(self):
        spans = [(0, RATE * 2), (RATE * 3, RATE * 3 + RATE // 10)]
        merged = _merge_spans(spans, RATE, max_segments=5, min_keep=1.2)
        self.assertEqual(len(merged), 1, "a 0.1s span should not survive")

    def test_keeps_span_order_and_bounds(self):
        spans = [(0, RATE), (RATE * 2, RATE * 3), (RATE * 4, RATE * 5)]
        merged = _merge_spans(spans, RATE, max_segments=2, min_keep=0.0)
        self.assertEqual(merged[0][0], 0)
        self.assertEqual(merged[-1][1], RATE * 5)
        for lo, hi in merged:
            self.assertLess(lo, hi)

    def test_empty_input(self):
        self.assertEqual(_merge_spans([], RATE, 3, 1.2), [])


class JoinSegments(unittest.TestCase):
    def test_drops_trailing_ellipsis_except_on_the_last_piece(self):
        joined = _join_segments(["I said this...", "and then that..."])
        self.assertEqual(joined, "I said this and then that...")

    def test_skips_empty_pieces(self):
        self.assertEqual(_join_segments(["one", "  ", "two"]), "one two")

    def test_no_doubled_spaces(self):
        self.assertNotIn("  ", _join_segments([" one ", " two "]))


class CloudRequestShapes(unittest.TestCase):
    """The fallback ladder must degrade, never drop the languages list.

    Sending `languages` is what buys mid-sentence switching, so a bug that
    silently dropped it would look like a quality regression rather than a
    broken request.
    """

    def setUp(self):
        self.cfg = config_module.load()
        self.cfg["transcription"]["cloud"]["languages"] = ["en", "ru", "de"]
        self.cfg["transcription"]["cloud"]["keywords"] = ["Kubernetes"]
        self.backend = CloudBackend(self.cfg)

    def test_first_shape_sends_the_language_list(self):
        first = self.backend._field_variants("")[0]
        self.assertEqual(first.get("languages[]"), ["en", "ru", "de"])
        # Configured keywords are kept, with the glue words appended. See
        # GlueKeywords below for why they are there.
        self.assertIn("Kubernetes", first.get("keywords[]"))

    def test_ladder_degrades_to_a_singular_language(self):
        variants = self.backend._field_variants("")
        singular = [v for v in variants if "language" in v]
        self.assertTrue(singular, "no singular-language fallback in the ladder")
        self.assertEqual(singular[0]["language"], "en")

    def test_every_shape_names_the_model(self):
        for fields in self.backend._field_variants(""):
            self.assertIn("model", fields)

    def test_a_pinned_language_overrides_the_list(self):
        first = self.backend._field_variants("de")[0]
        self.assertEqual(first.get("languages[]"), ["de"])


class SteeringPrompt(unittest.TestCase):
    """Accented speech gets transliterated without this.

    A German phrase read in a Russian accent came back as Cyrillic gibberish
    on 6 attempts out of 6 with no prompt, and 0 out of 6 with one. The
    wording is deliberately short: a longer, more explicit version failed all
    6, so this is not a knob to elaborate on casually.
    """

    def test_names_every_configured_language(self):
        prompt = _default_prompt(["en", "ru", "de", "kk"])
        for name in ("English", "Russian", "German", "Kazakh"):
            self.assertIn(name, prompt)

    def test_reads_as_a_sentence(self):
        self.assertEqual(_default_prompt(["en", "ru", "de"]),
                         "The speaker mixes English, Russian and German.")

    def test_no_prompt_when_there_is_nothing_to_mix(self):
        self.assertEqual(_default_prompt(["en"]), "")
        self.assertEqual(_default_prompt([]), "")

    def test_unknown_codes_still_produce_something(self):
        self.assertIn("zz", _default_prompt(["en", "zz"]))

    def test_a_configured_prompt_wins(self):
        cfg = config_module.load()
        cfg["transcription"]["cloud"]["prompt"] = "my own wording"
        fields = CloudBackend(cfg)._field_variants("")[0]
        self.assertEqual(fields.get("prompt"), "my own wording")

    def test_generated_prompt_is_used_when_none_is_set(self):
        cfg = config_module.load()
        cfg["transcription"]["cloud"]["prompt"] = ""
        cfg["transcription"]["cloud"]["languages"] = ["en", "de"]
        fields = CloudBackend(cfg)._field_variants("")[0]
        self.assertEqual(fields.get("prompt"),
                         "The speaker mixes English and German.")


class GlueKeywords(unittest.TestCase):
    """Short German words vanish in connected speech without these.

    Nobody pronounces the final -r in "aber"; it reduces to a schwa, so the
    microphone hears roughly "aba". Straight after Cyrillic that either
    becomes "Абы" or disappears. Measured: "aber" survived 0 of 3 attempts
    without these keywords and 3 of 3 with them, while five clean clips in
    other languages were byte-identical either way.
    """

    def test_german_contributes_glue_words(self):
        words = _default_keywords(["en", "ru", "de", "kk"])
        self.assertIn("aber", words)
        self.assertIn("Aber", words)

    def test_nothing_for_languages_with_no_list(self):
        self.assertEqual(_default_keywords(["en", "ru"]), [])
        self.assertEqual(_default_keywords([]), [])

    def test_no_duplicates(self):
        words = _default_keywords(["de", "de"])
        self.assertEqual(len(words), len(set(words)))

    def test_configured_keywords_are_kept_alongside_the_glue(self):
        cfg = config_module.load()
        cfg["transcription"]["cloud"]["keywords"] = ["Kubernetes"]
        cfg["transcription"]["cloud"]["languages"] = ["en", "de"]
        sent = CloudBackend(cfg)._field_variants("")[0].get("keywords[]")
        self.assertIn("Kubernetes", sent)
        self.assertIn("aber", sent)

    def test_glue_is_absent_when_german_is_not_configured(self):
        cfg = config_module.load()
        cfg["transcription"]["cloud"]["keywords"] = []
        cfg["transcription"]["cloud"]["languages"] = ["en", "ru"]
        sent = CloudBackend(cfg)._field_variants("")[0].get("keywords[]")
        self.assertFalse(sent)


class ConfigMerge(unittest.TestCase):
    def test_user_values_win_but_defaults_survive(self):
        merged = config_module._deep_merge(
            config_module.DEFAULTS, {"model": {"final": "small"}}
        )
        self.assertEqual(merged["model"]["final"], "small")
        self.assertEqual(
            merged["model"]["beam_size"], config_module.DEFAULTS["model"]["beam_size"]
        )

    def test_merge_does_not_mutate_the_defaults(self):
        before = config_module.DEFAULTS["model"]["final"]
        config_module._deep_merge(config_module.DEFAULTS,
                                  {"model": {"final": "large-v3-turbo"}})
        self.assertEqual(config_module.DEFAULTS["model"]["final"], before)

    def test_defaults_that_were_chosen_by_measurement(self):
        # These were chosen by measurement. If you are
        # changing one, change it here too and say why in the pull request.
        rec = config_module.DEFAULTS["recording"]
        self.assertEqual(rec["vad_aggressiveness"], 1)
        self.assertEqual(rec["min_speech_run"], 12)
        self.assertTrue(rec["normalize_for_transcription"])
        self.assertIsNone(config_module.DEFAULTS["model"]["initial_prompt"])


class HardwareResolution(unittest.TestCase):
    def test_explicit_values_are_left_alone(self):
        from heyspeaky.hardware import resolve_hardware
        self.assertEqual(resolve_hardware("cpu", "int8"), ("cpu", "int8"))

    def test_auto_compute_type_follows_the_device(self):
        from heyspeaky.hardware import resolve_hardware
        self.assertEqual(resolve_hardware("cuda", "auto")[1], "float16")
        self.assertEqual(resolve_hardware("cpu", "auto")[1], "int8")

    def test_auto_device_resolves_to_something_usable(self):
        from heyspeaky.hardware import resolve_hardware
        device, compute = resolve_hardware("auto", "auto")
        self.assertIn(device, ("cpu", "cuda"))
        self.assertIn(compute, ("int8", "float16"))


class CappedLogStream(unittest.TestCase):
    """A runaway dependency once wrote 8.7 GB here. It must not happen twice."""

    def _stream_class(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "heyspeaky_run", ROOT / "run.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module._CappedStream

    def test_stops_writing_at_the_limit(self):
        capped = self._stream_class()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.log"
            stream = capped(path, "w", 1000)
            for i in range(500):
                stream.write("a traceback line {}\n".format(i))
            stream.flush()
            stream.close()
            self.assertLess(path.stat().st_size, 1500)
            self.assertIn("limit", path.read_text(encoding="utf-8"))

    def test_write_reports_the_full_length_even_when_dropping(self):
        capped = self._stream_class()
        with tempfile.TemporaryDirectory() as tmp:
            stream = capped(Path(tmp) / "out.log", "w", 10)
            stream.write("x" * 50)
            # print() checks the return value; lying about it breaks callers.
            self.assertEqual(stream.write("y" * 30), 30)
            stream.close()


class KeyFile(unittest.TestCase):
    """A rename must not lose anyone's saved key."""

    def _backend(self, appdata):
        import copy
        import os
        from unittest import mock

        cfg = copy.deepcopy(config_module.DEFAULTS)
        variable = cfg["transcription"]["cloud"]["api_key_env"]
        env = {k: v for k, v in os.environ.items() if k != variable}
        env["APPDATA"] = appdata
        return CloudBackend(cfg), mock.patch.dict(os.environ, env, clear=True)

    def _write(self, folder, key):
        folder.mkdir()
        (folder / "openai.key").write_text(key + "\n", encoding="utf-8")

    def test_reads_the_current_location(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write(Path(tmp) / "HeySpeaky", "test-key-new")
            backend, env = self._backend(tmp)
            with env:
                self.assertEqual(backend.api_key, "test-key-new")

    def test_falls_back_to_every_old_location(self):
        for old in ("SpeakIt", "VoiceType"):
            with tempfile.TemporaryDirectory() as tmp:
                self._write(Path(tmp) / old, "test-key-old")
                backend, env = self._backend(tmp)
                with env:
                    self.assertEqual(backend.api_key, "test-key-old", old)

    def test_the_key_file_default_uses_the_current_name(self):
        default = config_module.DEFAULTS["transcription"]["cloud"]["api_key_file"]
        self.assertIn("HeySpeaky", default)
        self.assertNotIn("SpeakIt", default)

    def test_current_location_wins_when_both_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write(Path(tmp) / "HeySpeaky", "test-key-new")
            self._write(Path(tmp) / "SpeakIt", "test-key-old")
            backend, env = self._backend(tmp)
            with env:
                self.assertEqual(backend.api_key, "test-key-new")


from heyspeaky import languages  # noqa: E402


class LanguageList(unittest.TestCase):
    """Adding and removing languages from the tray."""

    def _cfg(self, codes, pinned=""):
        import copy

        cfg = copy.deepcopy(config_module.DEFAULTS)
        cfg["transcription"]["cloud"]["languages"] = list(codes)
        cfg["model"]["language"] = pinned
        cfg["model"]["language_menu"] = languages.menu_for(codes)
        return cfg

    def test_adding_updates_both_lists(self):
        cfg = self._cfg(["en"])
        self.assertEqual(languages.toggle(cfg, "fr"), "added")
        # First, not last: see LanguagePriority below for why the order of
        # this list decides whether a language does anything at all.
        self.assertEqual(cfg["transcription"]["cloud"]["languages"],
                         ["fr", "en"])
        self.assertEqual(cfg["model"]["language_menu"],
                         {"Auto-detect": "", "English": "en", "French": "fr"})

    def test_removing_a_pinned_language_unpins_it(self):
        cfg = self._cfg(["en", "de"], pinned="de")
        self.assertEqual(languages.toggle(cfg, "de"), "removed")
        self.assertEqual(cfg["transcription"]["cloud"]["languages"], ["en"])
        self.assertEqual(cfg["model"]["language"], "")
        self.assertNotIn("German", cfg["model"]["language_menu"])

    def test_the_last_language_stays(self):
        cfg = self._cfg(["en"])
        self.assertEqual(languages.toggle(cfg, "en"), "kept")
        self.assertEqual(cfg["transcription"]["cloud"]["languages"], ["en"])

    def test_the_list_is_edited_in_place(self):
        # The tray keeps a reference to this list to draw its checkmarks.
        cfg = self._cfg(["en"])
        held = cfg["transcription"]["cloud"]["languages"]
        languages.toggle(cfg, "kk")
        self.assertIs(held, cfg["transcription"]["cloud"]["languages"])
        self.assertEqual(held, ["kk", "en"])

    def test_reconcile_keeps_what_either_list_named(self):
        cfg = self._cfg(["en"], pinned="es")
        cfg["model"]["language_menu"] = {
            "Auto-detect": "", "English": "en", "French": "fr"}
        self.assertTrue(languages.reconcile(cfg))
        self.assertEqual(cfg["transcription"]["cloud"]["languages"],
                         ["es", "fr", "en"])
        self.assertFalse(languages.reconcile(cfg))

    def test_the_defaults_already_agree(self):
        import copy

        cfg = copy.deepcopy(config_module.DEFAULTS)
        self.assertFalse(languages.reconcile(cfg))

    def test_unknown_codes_are_shown_as_codes(self):
        self.assertEqual(languages.name("xx"), "xx")
        self.assertIn("xx", languages.catalog(["en", "xx"]))
        self.assertEqual(languages.catalog([])[0], "af")


class LanguageGroups(unittest.TestCase):
    """The letter submenus under Add or remove languages."""

    def setUp(self):
        self.codes = languages.catalog(["en", "xx"])
        self.groups = languages.groups(self.codes)

    def test_every_language_is_in_exactly_one_group(self):
        flat = [code for _, codes in self.groups for code in codes]
        self.assertEqual(sorted(flat), sorted(self.codes))

    def test_no_group_runs_off_the_screen(self):
        for label, codes in self.groups:
            self.assertLessEqual(len(codes), languages.GROUP_SIZE, label)

    def test_a_letter_never_spans_two_groups(self):
        seen = set()
        for _, codes in self.groups:
            letters = {languages.name(code)[:1].upper() for code in codes}
            self.assertFalse(letters & seen)
            seen |= letters

    def test_labels_name_the_first_and_last_letter(self):
        for label, codes in self.groups:
            self.assertEqual(label[0], languages.name(codes[0])[0].upper())
            self.assertEqual(label[-1], languages.name(codes[-1])[0].upper())

    def test_only_codes_openai_accepts(self):
        self.assertIn("tl", languages.NAMES)
        self.assertNotIn("yue", languages.NAMES)
        self.assertTrue(all(len(code) == 2 for code in languages.NAMES))


from heyspeaky import diagnostics  # noqa: E402


class ProblemReport(unittest.TestCase):
    """The ZIP someone sends when HeySpeaky works worse on their PC."""

    # Built at runtime so the repository's secret scan has nothing to find.
    FAKE_KEY = "sk-proj-" + "a1" * 20

    def test_stats_for_a_tone(self):
        stats = diagnostics.audio_stats(tone(1.0, amplitude=0.5), RATE)
        self.assertAlmostEqual(stats["seconds"], 1.0, places=2)
        self.assertAlmostEqual(stats["peak_db"], -6.0, delta=0.2)
        self.assertAlmostEqual(stats["rms_db"], -9.0, delta=0.2)
        self.assertEqual(stats["clipped_pct"], 0.0)

    def test_stats_for_silence_and_clipping(self):
        self.assertEqual(diagnostics.audio_stats(silence(0.5), RATE)["peak_db"],
                         -120.0)
        loud = np.full(RATE, 32767, dtype=np.int16).tobytes()
        self.assertEqual(diagnostics.audio_stats(loud, RATE)["clipped_pct"],
                         100.0)
        self.assertEqual(diagnostics.audio_stats(b"", RATE)["seconds"], 0.0)

    def test_redact_removes_keys_only(self):
        text = "key {} and sk-short stay".format(self.FAKE_KEY)
        self.assertEqual(diagnostics.redact(text),
                         "key sk-...removed and sk-short stay")

    def test_keeps_only_the_newest(self):
        recent = diagnostics.Recent(keep=5)
        for index in range(8):
            recent.add(index)
        self.assertEqual(recent.items(), [3, 4, 5, 6, 7])

    def test_report_contents_and_no_key(self):
        import copy
        import zipfile

        cfg = copy.deepcopy(config_module.DEFAULTS)
        cfg["transcription"]["cloud"]["api_key"] = self.FAKE_KEY
        entry = {
            "time": "12:00:00", "pcm": tone(1.0), "rate": RATE, "held": 1.1,
            "stats": diagnostics.audio_stats(tone(1.0), RATE),
            "speech_run": 40, "language": "", "backend": "local",
            "fallback": "offline", "took": 1.5, "text": "Привет, world",
        }
        with tempfile.TemporaryDirectory() as tmp:
            logs = Path(tmp) / "logs"
            logs.mkdir()
            (logs / "heyspeaky.log").write_text(
                "sent with " + self.FAKE_KEY, encoding="utf-8")
            path = diagnostics.save_report(cfg, [entry, entry], logs,
                                           out_dir=tmp, check_network=False)
            with zipfile.ZipFile(path) as archive:
                names = set(archive.namelist())
                contents = b"".join(archive.read(name) for name in names)
                report = archive.read("report.txt").decode("utf-8")
        self.assertEqual(names, {"report.txt", "config.json",
                                 "logs/heyspeaky.log", "recordings/1.wav",
                                 "recordings/2.wav"})
        self.assertNotIn(self.FAKE_KEY.encode(), contents)
        self.assertIn("local (offline)", report)
        self.assertIn("Привет, world", report)


def _load_install_game():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "install_game", ROOT / "tools" / "install_game.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class InstallProgress(unittest.TestCase):
    """The bar in the game window the installer opens."""

    @classmethod
    def setUpClass(cls):
        cls.game = _load_install_game()

    def state(self, started):
        return {"state": "running", "label": "Installing packages",
                "started": started, "expected": 100.0,
                "finished_share": 0.2, "share": 0.5, "remaining_after": 60.0}

    def test_nothing_yet(self):
        self.assertEqual(self.game.progress(None, 0.0), (0.0, None))

    def test_a_step_starts_where_the_last_one_ended(self):
        fraction, left = self.game.progress(self.state(1000.0), 1000.0)
        self.assertAlmostEqual(fraction, 0.2)
        self.assertAlmostEqual(left, 160.0)

    def test_a_slow_step_never_passes_its_end(self):
        early, left_early = self.game.progress(self.state(0.0), 50.0)
        late, left_late = self.game.progress(self.state(0.0), 100000.0)
        self.assertGreater(early, 0.2)
        self.assertGreater(late, early)
        self.assertLessEqual(late, 0.7)
        self.assertLess(left_late, left_early)
        self.assertAlmostEqual(left_late, 60.0)

    def test_done_is_full(self):
        self.assertEqual(self.game.progress({"state": "done"}, 5.0), (1.0, 0.0))

    def test_time_left_stays_vague(self):
        self.assertEqual(self.game.time_left(None), "")
        self.assertEqual(self.game.time_left(30), "almost done")
        self.assertEqual(self.game.time_left(70), "about a minute left")
        self.assertEqual(self.game.time_left(300), "about 5 minutes left")


from PIL import Image  # noqa: E402

from heyspeaky import glass, theme  # noqa: E402


class GlassComposer(unittest.TestCase):
    """The correction composer's picture, which is plain PIL.

    The windows need Tk and a screen; tools/correction_check.py looks at
    those. What is checked here is the drawing and the arithmetic every part
    of it shares - above all that the typing widget, laid over the picture,
    lands on nothing but the field's own flat colour.
    """

    SCALES = (1.0, 1.25, 1.5, 2.0)

    def test_everything_sits_inside_the_capsule(self):
        for scale in self.SCALES:
            layout = glass.composer_layout(scale)
            box = layout["box"]
            parts = list(layout["buttons"].values()) + [layout["field"],
                                                        layout["entry"]]
            for part in parts:
                self.assertGreaterEqual(part[0], box[0])
                self.assertLessEqual(part[2], box[2])
                self.assertGreaterEqual(part[1], box[1])
                self.assertLessEqual(part[3], box[3])

    def test_cross_field_tick_in_that_order_and_apart(self):
        for scale in self.SCALES:
            layout = glass.composer_layout(scale)
            self.assertLess(layout["buttons"]["cancel"][2],
                            layout["field"][0])
            self.assertLess(layout["field"][2],
                            layout["buttons"]["accept"][0])

    def test_the_widget_lands_on_nothing_but_the_field_colour(self):
        """The widget is an opaque window of FIELD_FILL. If the ring or its
        glow reached under it, the widget would cut a flat rectangle out of
        the colour, and that seam is exactly what the old box had."""
        for scale in self.SCALES:
            composer = glass.composer(scale)
            entry = composer.layout["entry"]
            for turn in (0.0, 0.2, 0.45, 0.7):
                frame = glass.composer_frame(composer, turn=turn,
                                             strength=1.0)
                under = frame.crop(entry)
                colours = set(under.getdata())
                self.assertEqual(colours, {tuple(theme.FIELD_FILL) + (255,)},
                                 "at scale %s turn %s" % (scale, turn))

    def test_the_ring_turns(self):
        composer = glass.composer(1.25)
        first = glass.composer_frame(composer, turn=0.1)
        again = glass.composer_frame(composer, turn=0.1)
        later = glass.composer_frame(composer, turn=0.3)
        self.assertEqual(first.tobytes(), again.tobytes())
        self.assertNotEqual(first.tobytes(), later.tobytes())

    def test_the_ring_is_the_waveform_s_colours(self):
        ring = glass.composer(1.25).ring.render(0.0, 1.0)
        lit = [pixel for pixel in ring.getdata() if pixel[3] > 120]
        self.assertTrue(lit)
        self.assertTrue(any(p[2] > p[0] + 60 for p in lit))    # blue arc
        self.assertTrue(any(p[0] > p[2] + 60 for p in lit))    # warm arc

    def test_the_arcs_fade_out_rather_than_stop(self):
        """Measured as a CSS conic gradient does it, by the angle from the
        centre, the glow along a long thin field jumped by up to 23 levels
        from one pixel to the next and looked cut with scissors. Measured
        along the edge the worst step is 8."""
        for scale in (1.0, 1.25):
            composer = glass.composer(scale)
            field = composer.layout["field"]
            origin = composer.ring.origin
            row = field[1] - origin[1] - glass._px(3, scale)
            for turn in [step / 24.0 for step in range(24)]:
                alpha = np.asarray(composer.ring.render(turn, 1.0))[..., 3]
                steps = np.abs(np.diff(alpha[row].astype(int)))
                self.assertLessEqual(steps.max(), 10,
                                     "at scale %s turn %s" % (scale, turn))

    def test_the_corners_are_see_through(self):
        frame = glass.composer_frame(glass.composer(1.25))
        self.assertEqual(frame.getpixel((0, 0))[3], 0)
        width, height = frame.size
        self.assertEqual(frame.getpixel((width - 1, height - 1))[3], 0)

    def test_the_glass_is_the_pill_s_glass(self):
        composer = glass.composer(1.0)
        box = composer.layout["box"]
        middle = (box[1] + box[3]) // 2
        body = composer.shell.getpixel((box[0] + 6, middle))
        self.assertLess(max(abs(body[i] - theme.TINT[i]) for i in range(3)),
                        12)
        self.assertGreater(body[3], 200)

    def test_opening_draws_the_empty_glass_only(self):
        composer = glass.composer(1.25)
        box = composer.layout["box"]
        middle = (box[1] + box[3]) // 2
        opening = glass.composer_frame(composer, open_share=0.5)
        # The capsule is half as wide, so its old left end is bare desktop,
        # and there is no field and no ring yet in its middle.
        self.assertEqual(opening.getpixel((box[0] + 4, middle))[3], 0)
        centre = opening.getpixel(((box[0] + box[2]) // 2, middle))
        self.assertLess(max(abs(centre[i] - theme.TINT[i]) for i in range(3)),
                        16)

    def test_the_cross_turns_and_nothing_else_does(self):
        still = glass.button(34, "cancel", theme.CANCEL_FILL,
                             theme.CANCEL_GLYPH)
        turned = glass.button(34, "cancel", theme.CANCEL_FILL,
                              theme.CANCEL_GLYPH, turn=45)
        self.assertEqual(still.size, turned.size)
        self.assertNotEqual(still.tobytes(), turned.tobytes())
        # The shadow under the disc does not turn with the glyph.
        self.assertEqual(still.getpixel((still.size[0] // 2,
                                         still.size[1] - 1)),
                         turned.getpixel((turned.size[0] // 2,
                                          turned.size[1] - 1)))

    def test_a_label_is_as_wide_as_its_words(self):
        short = glass.chip([("Save", False)], 1.25)
        long = glass.chip([("Save", False), ("  Enter", True)], 1.25)
        self.assertGreater(long.size[0], short.size[0])
        self.assertEqual(long.size[1], short.size[1])

    def test_the_labels_fit_above_the_capsule(self):
        for scale in self.SCALES:
            layout = glass.composer_layout(scale)
            label = glass.chip([("heard  ", True), ("Маржан", False)], scale)
            gap = glass._px(theme.CHIP_GAP, scale)
            self.assertGreaterEqual(layout["box"][1] - gap - label.size[1], 0)


try:
    from heyspeaky import panel as panel_module
except Exception:           # no tkinter
    panel_module = None


@unittest.skipIf(panel_module is None, "tkinter is missing")
class TrayPanelLayout(unittest.TestCase):
    """The tray panel's layout and picture, which are arithmetic and PIL.

    The window itself is tools/panel_check.py's business: it found the one
    fault these could not, a panel styled on a window handle Tk then
    replaced, which drew nothing at all.
    """

    YOURS = ["kk", "ru", "en", "de"]

    def model(self, **changes):
        catalog = languages.catalog(self.YOURS)
        model = {"status": "Ready", "state": "ready", "paused": False,
                 "pinned": "", "yours": list(self.YOURS), "backend": "cloud",
                 "usage": "This month: $0.42", "update": "",
                 "catalog": list(catalog),
                 "names": dict((c, languages.name(c)) for c in catalog)}
        model.update(changes)
        return model

    def card_box(self, size, scale):
        margin = int(round(theme.PANEL_MARGIN * scale))
        return (margin, margin, margin + size[0], margin + size[1])

    def test_every_part_sits_inside_the_card(self):
        for scale in (1.0, 1.25, 1.5, 2.0):
            for page in ("main", "languages"):
                size, items = panel_module.layout(self.model(), scale, page)
                box = self.card_box(size, scale)
                for item in items:
                    left, top, right, bottom = item.rect
                    self.assertGreaterEqual(left, box[0], (scale, item))
                    self.assertLessEqual(right, box[2], (scale, item))
                    self.assertGreaterEqual(top, box[1], (scale, item))
                    self.assertLessEqual(bottom, box[3], (scale, item))

    def test_the_pinned_language_is_the_chosen_chip(self):
        _size, items = panel_module.layout(self.model(pinned="kk"), 1.25)
        chosen = [item.key for item in items
                  if item.kind == "chip" and item.extra]
        self.assertEqual(chosen, ["pin:kk"])
        _size, items = panel_module.layout(self.model(), 1.25)
        chosen = [item.key for item in items
                  if item.kind == "chip" and item.extra]
        self.assertEqual(chosen, ["pin:"])

    def test_chips_wrap_rather_than_run_off(self):
        many = ["kk", "ru", "en", "de", "fr", "es", "it", "tr", "uk"]
        _size, items = panel_module.layout(self.model(yours=many), 1.25)
        chips = [item for item in items if item.kind == "chip"]
        self.assertGreater(len(set(item.rect[1] for item in chips)), 1)

    def test_the_update_row_is_there_only_when_there_is_an_update(self):
        _size, items = panel_module.layout(self.model(), 1.0)
        self.assertNotIn("update", [item.key for item in items])
        _size, items = panel_module.layout(self.model(update="1.2.0"), 1.0)
        self.assertIn("update", [item.key for item in items])

    def test_the_two_halves_of_the_switch_between_engines(self):
        _size, items = panel_module.layout(self.model(), 1.25)
        control = [item for item in items if item.kind == "segmented"][0]
        left, top, right, bottom = control.rect
        middle = (top + bottom) // 2
        self.assertEqual(panel_module.hit(items, left + 4, middle)[1],
                         "backend:cloud")
        self.assertEqual(panel_module.hit(items, right - 4, middle)[1],
                         "backend:local")

    def test_labels_and_the_title_cannot_be_clicked(self):
        _size, items = panel_module.layout(self.model(), 1.25)
        for item in items:
            if item.kind in ("title", "label", "hint", "footer"):
                x = (item.rect[0] + item.rect[2]) // 2
                y = (item.rect[1] + item.rect[3]) // 2
                self.assertIsNone(panel_module.hit(items, x, y)[0])

    def test_your_languages_head_the_list(self):
        order = panel_module.language_order(self.model())
        self.assertEqual(order[:4], self.YOURS)
        rest = order[4:]
        names = [languages.name(code).lower() for code in rest]
        self.assertEqual(names, sorted(names))

    def test_a_scrolled_list_has_no_hole_at_the_top(self):
        """Scrolled by anything that is not a whole row, the half-hidden top
        row used to be left out, and the list opened with a gap."""
        for scale in (1.0, 1.25):
            for scroll in (10, 37, 85, 300):
                _size, items = panel_module.layout(self.model(), scale,
                                                   "languages", scroll)
                hint = [item for item in items if item.kind == "hint"][0]
                rows = [item for item in items if item.kind == "language"]
                self.assertLessEqual(rows[0].rect[1] - hint.rect[3],
                                     int(round(8 * scale)) + 1,
                                     (scale, scroll))

    def test_a_long_list_shows_a_scrollbar(self):
        _size, items = panel_module.layout(self.model(), 1.25, "languages")
        self.assertIn("scrollbar", [item.kind for item in items])

    def test_the_card_s_corners_are_see_through(self):
        size, items = panel_module.layout(self.model(), 1.25)
        card = glass.panel_card(size[0], size[1], 1.25)
        frame = glass.panel_frame(card, items, 1.25)
        self.assertEqual(frame.getpixel((0, 0))[3], 0)
        box = card[1]
        # Inside the card's rectangle but outside its rounded corner there
        # is only the faintest shadow; a square card would be solid there.
        self.assertLess(frame.getpixel((box[0] + 1, box[1] + 1))[3], 40)
        self.assertGreater(frame.getpixel((box[0] + 40, box[1] + 40))[3],
                           200)

    def test_a_hovered_row_changes_only_its_own_rectangle(self):
        from PIL import ImageChops
        size, items = panel_module.layout(self.model(), 1.25)
        card = glass.panel_card(size[0], size[1], 1.25)
        rest = glass.panel_frame(card, items, 1.25)
        lit = glass.panel_frame(card, items, 1.25, {"settings": 1.0})
        changed = ImageChops.difference(lit, rest).getbbox()
        row = [item for item in items if item.key == "settings"][0]
        self.assertIsNotNone(changed)
        self.assertGreaterEqual(changed[0], row.rect[0])
        self.assertLessEqual(changed[2], row.rect[2])
        self.assertGreaterEqual(changed[1], row.rect[1])
        self.assertLessEqual(changed[3], row.rect[3])

    def test_a_switch_that_is_on_carries_the_waveform_s_colour(self):
        on = glass.switch(48, 28, 1.0)
        off = glass.switch(48, 28, 0.0)
        blue_on = on.getpixel((8, 14))
        blue_off = off.getpixel((40, 14))
        self.assertGreater(blue_on[2], blue_on[0] + 80)
        self.assertLess(abs(blue_off[2] - blue_off[0]), 20)

    def test_the_setting_that_brings_the_menu_back_is_on_by_default(self):
        self.assertTrue(config_module.DEFAULTS["tray"]["panel"])


class GlassPill(unittest.TestCase):
    """The pill draws itself over a photograph of the desktop."""

    def window(self):
        return (theme.WIDTH, theme.HEIGHT + theme.SHADOW_MARGIN * 2)

    def test_a_frame_is_the_size_of_the_window(self):
        frame = glass.render(state="listening", levels=[0.5] * theme.BARS)
        self.assertEqual(frame.size, self.window())

    def test_a_frame_carries_an_alpha_channel(self):
        """Windows composites it over the live desktop through this."""
        frame = glass.render(state="listening", levels=[0.5] * theme.BARS)
        self.assertEqual(frame.mode, "RGBA")

    def test_the_corners_are_see_through(self):
        """Or the pill shows as a rectangle, which is the bug this fixes."""
        frame = glass.render(state="listening", levels=[0.5] * theme.BARS)
        self.assertEqual(frame.getpixel((0, 0))[3], 0)
        self.assertEqual(frame.getpixel((frame.width - 1, 0))[3], 0)

    def test_the_middle_of_the_pill_is_nearly_solid(self):
        frame = glass.render(state="listening", levels=[0.5] * theme.BARS)
        middle = frame.getpixel((frame.width // 2, frame.height // 2))
        self.assertGreater(middle[3], 200)

    def test_the_glass_is_built_once_and_painted_many_times(self):
        prepared = glass.prepare()
        first = glass.paint(prepared, state="done", text="hello")
        second = glass.paint(prepared, state="done", text="hello again")
        self.assertEqual(first.size, second.size)
        self.assertIsNot(first, prepared.image)

    def test_long_text_is_shortened_rather_than_spilling(self):
        sentence = "word " * 200
        frame = glass.render(state="error", status=sentence)
        self.assertEqual(frame.size, self.window())


from heyspeaky import usage  # noqa: E402


class Spending(unittest.TestCase):
    """The tally of what the OpenAI key is costing this month."""

    def setUp(self):
        import copy
        import os
        from unittest import mock

        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        patcher = mock.patch.dict(os.environ, {"APPDATA": self.folder.name})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.cfg = copy.deepcopy(config_module.DEFAULTS)

    def test_minutes_and_money_add_up(self):
        usage.record(60.0)
        usage.record(30.0)
        figures = usage.summary(self.cfg)
        self.assertEqual(figures["dictations"], 2)
        self.assertAlmostEqual(figures["minutes"], 1.5)
        self.assertAlmostEqual(figures["cost"], 1.5 * 0.006)
        self.assertIn("about $0.01", usage.describe(self.cfg))

    def test_nothing_sent_reads_plainly(self):
        self.assertIn("nothing sent", usage.describe(self.cfg))

    def test_the_warning_comes_once_a_month(self):
        self.cfg["transcription"]["cloud"]["monthly_warning_usd"] = 0.01
        usage.record(600.0)
        first = usage.warning(self.cfg)
        self.assertIsNotNone(first)
        self.assertIn("$", first)
        self.assertIsNone(usage.warning(self.cfg))

    def test_no_warning_below_the_threshold_or_when_it_is_off(self):
        usage.record(60.0)
        self.assertIsNone(usage.warning(self.cfg))
        self.cfg["transcription"]["cloud"]["monthly_warning_usd"] = 0
        usage.record(100000.0)
        self.assertIsNone(usage.warning(self.cfg))

    def test_the_tally_never_lands_in_the_project(self):
        usage.record(1.0)
        self.assertTrue(str(usage.path()).startswith(self.folder.name))
        self.assertTrue(usage.path().is_file())


from heyspeaky import updates  # noqa: E402


class Updates(unittest.TestCase):
    """Noticing that a newer HeySpeaky exists."""

    def setUp(self):
        import os
        from unittest import mock

        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        patcher = mock.patch.dict(os.environ, {"APPDATA": self.folder.name})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_version_order_is_by_number_not_by_text(self):
        self.assertTrue(updates.is_newer("1.10", "1.9"))
        self.assertTrue(updates.is_newer("v2.0", "1.9.9"))
        self.assertFalse(updates.is_newer("1.0.9", "1.1.0"))
        self.assertFalse(updates.is_newer("1.1.0", "1.1.0"))

    def test_nothing_is_offered_before_a_check(self):
        self.assertEqual(updates.known_newer(), "")

    def test_a_remembered_answer_is_offered_without_asking_again(self):
        updates._write({"checked": 0.0, "latest": "99.0"})
        self.assertEqual(updates.known_newer(), "99.0")

    def test_a_check_is_not_repeated_within_a_day(self):
        updates._write({"checked": 1000.0, "latest": "99.0"})
        # A network call here would raise, since the time has not passed.
        self.assertEqual(updates.check(now=1000.0 + 60), "99.0")


class PillButtons(unittest.TestCase):
    """The cross and the tick, and where a click has to land to hit them."""

    def window(self):
        return (theme.WIDTH, theme.HEIGHT + theme.SHADOW_MARGIN * 2)

    def prepared(self, **kwargs):
        return glass.prepare(**kwargs)

    def test_both_buttons_sit_inside_the_pill(self):
        boxes = glass.button_boxes(self.prepared())
        left, top, right, bottom = self.prepared().box
        for box in boxes.values():
            self.assertGreaterEqual(box[0], left)
            self.assertLessEqual(box[2], right)
            self.assertGreaterEqual(box[1], top)
            self.assertLessEqual(box[3], bottom)

    def test_the_two_buttons_do_not_overlap(self):
        boxes = glass.button_boxes(self.prepared())
        self.assertLess(boxes["cancel"][2], boxes["accept"][0])

    def test_buttons_are_square_and_the_size_the_theme_asks_for(self):
        box = glass.button_boxes(self.prepared())["cancel"]
        self.assertEqual(box[2] - box[0], box[3] - box[1])
        self.assertEqual(box[2] - box[0], theme.BUTTON)

    def test_the_waveform_never_reaches_the_buttons(self):
        """It used to run underneath the tick on a high-DPI screen.

        Every bar width and gap was a fixed pixel count scaled up and rounded
        up, and twenty-three roundings added up to more than the space.
        """
        for scale in (1.0, 1.25, 1.5, 2.0, 3.0):
            prepared = self.prepared(scale=scale)
            boxes = glass.button_boxes(prepared)
            layout = glass.wave_layout(prepared, theme.BARS)
            first = glass.bar_left(layout, 0)
            last = glass.bar_left(layout, theme.BARS - 1) + layout["width"]
            self.assertGreaterEqual(
                first, boxes["cancel"][2],
                "at scale %s the waveform starts under the cross" % scale)
            self.assertLessEqual(
                last, boxes["accept"][0],
                "at scale %s the waveform ends under the tick" % scale)

    def test_no_drawn_pixel_of_the_waveform_touches_a_button(self):
        """The arithmetic guard above misses the glow around each bar.

        Every bar is drawn with a bloom that reaches past its own edge, and
        that is what was actually visible under the tick. This compares a
        frame with a waveform against one without, and asks where the
        difference lies.
        """
        from PIL import ImageChops

        real = glass.button
        glass.button = lambda size, kind, fill, glyph, dim=1.0, turn=0: Image.new(
            "RGBA", (size, size), (0, 0, 0, 0))
        try:
            for scale in (1.0, 1.25, 1.5, 2.0):
                prepared = self.prepared(scale=scale)
                boxes = glass.button_boxes(prepared)
                empty = glass.paint(prepared, state="done")
                wave = glass.paint(prepared, state="listening",
                                   levels=[1.0] * theme.BARS)
                left, _top, right, _bottom = ImageChops.difference(
                    wave, empty).getbbox()
                self.assertGreater(
                    left, boxes["cancel"][2],
                    "at scale %s the waveform reaches the cross" % scale)
                self.assertLessEqual(
                    right, boxes["accept"][0],
                    "at scale %s the waveform reaches the tick" % scale)
        finally:
            glass.button = real

    def test_the_waveform_uses_the_space_it_has(self):
        """Fitting must not mean shrinking into a corner."""
        prepared = self.prepared()
        layout = glass.wave_layout(prepared, theme.BARS)
        span = (glass.bar_left(layout, theme.BARS - 1) + layout["width"]
                - glass.bar_left(layout, 0))
        self.assertGreater(span, (layout["right"] - layout["left"]) * 0.85)

    def test_a_pill_that_is_still_opening_draws_nothing_inside_it(self):
        opening = self.prepared(open_share=0.34)
        painted = glass.paint(opening, state="listening",
                              levels=[0.5] * theme.BARS)
        self.assertEqual(painted.tobytes(), opening.image.tobytes())

    def test_a_fully_open_pill_does_draw_something(self):
        full = self.prepared()
        painted = glass.paint(full, state="listening",
                              levels=[0.5] * theme.BARS)
        self.assertNotEqual(painted.tobytes(), full.image.tobytes())

    def test_a_pill_nobody_points_at_is_the_picture_it_always_was(self):
        """Hover was added after the pill had been measured and looked at
        live; at rest it must draw exactly what it drew before."""
        full = self.prepared()
        levels = [0.5] * theme.BARS
        plain = glass.paint(full, state="listening", levels=levels)
        at_rest = glass.paint(full, state="listening", levels=levels,
                              hover={"cancel": (1.0, 0, 0),
                                     "accept": (1.0, 0, 0)})
        self.assertEqual(plain.tobytes(), at_rest.tobytes())

    def test_a_button_under_the_pointer_grows_and_stays_clear_of_the_wave(self):
        """The waveform's own guard, with each button at its largest: a
        grown button may spread into the gap beside it, never onto a bar."""
        from PIL import ImageChops
        for scale in (1.0, 1.25, 2.0):
            prepared = self.prepared(scale=scale)
            layout = glass.wave_layout(prepared, theme.BARS)
            first = glass.bar_left(layout, 0)
            last = glass.bar_left(layout, theme.BARS - 1) + layout["width"]
            rest = glass.paint(prepared, state="done")
            for name, motion in (
                    ("cancel", (theme.HOVER_GROW, theme.HOVER_TURN, 0)),
                    ("accept", (theme.HOVER_GROW, 0,
                                theme.HOVER_LIFT * scale))):
                grown = glass.paint(prepared, state="done",
                                    hover={name: motion})
                changed = ImageChops.difference(grown, rest).getbbox()
                self.assertIsNotNone(changed, "%s at %s" % (name, scale))
                if name == "cancel":
                    self.assertLess(changed[2], first,
                                    "the cross reaches the wave at %s" % scale)
                else:
                    self.assertGreater(changed[0], last,
                                       "the tick reaches the wave at %s"
                                       % scale)


from heyspeaky import sound  # noqa: E402


class FinishSound(unittest.TestCase):
    """The small sound at the end, which is arithmetic rather than a file."""

    def test_every_voice_writes_a_playable_wav(self):
        import wave

        folder = tempfile.mkdtemp()
        for name in sound.VOICES:
            path = sound.write(name, os.path.join(folder, name + ".wav"))
            with wave.open(path, "rb") as handle:
                self.assertEqual(handle.getnchannels(), 1)
                self.assertEqual(handle.getsampwidth(), 2)
                self.assertEqual(handle.getframerate(), sound.RATE)
                self.assertGreater(handle.getnframes(), sound.RATE // 10)

    def test_the_sound_is_not_silence(self):
        folder = tempfile.mkdtemp()
        path = sound.write("drop", os.path.join(folder, "drop.wav"))
        with open(path, "rb") as handle:
            body = handle.read()[44:]
        self.assertTrue(any(byte for byte in body))

    def test_silence_is_never_played(self):
        self.assertFalse(sound.play("none"))
        self.assertFalse(sound.play("drop", volume=0.0))


try:
    from heyspeaky import hotkey                 # noqa: E402
    from heyspeaky.hotkey import HotkeyListener  # noqa: E402
except Exception:
    # The hook needs the keyboard package, which is not only sometimes absent
    # but can also fail to start on a machine with no real keyboard. Either
    # way that should skip the tests below, not stop the whole file from
    # importing and take the other eighty with it.
    hotkey = None
    HotkeyListener = None


class _Event(object):
    """What the keyboard library hands the hook."""

    def __init__(self, name, event_type):
        self.name = name
        self.event_type = event_type
        self.scan_code = 1


@unittest.skipIf(HotkeyListener is None, "the keyboard package is missing")
class DoubleTapGesture(unittest.TestCase):
    """Tap Ctrl+Alt twice and recording starts hands-free, as Wispr does."""

    def listener(self, engage_delay=10.0):
        self.latched = threading.Event()
        self.engaged = threading.Event()
        self.released = threading.Event()
        return HotkeyListener(
            {
                "engage_delay": engage_delay,
                "tap_max": 0.0,
                "accept_altgr": False,
                "cancel_on_other_key": True,
                "double_tap_gap": 0.5,
                "health_check_seconds": 0,
                "min_reinstall_seconds": 60,
            },
            on_engage=self.engaged.set,
            on_tap=lambda: None,
            on_hold_release=self.released.set,
            on_cancel=lambda: None,
            on_latch=self.latched.set,
        )

    def send(self, listener, *events):
        for name, kind in events:
            listener._on_key_event(_Event(name, kind))

    def tap(self, listener):
        """Press and release the whole chord, faster than the engage delay."""
        self.send(listener, ("ctrl", "down"), ("alt", "down"),
                  ("alt", "up"), ("ctrl", "up"))

    def test_two_taps_of_the_chord_go_hands_free(self):
        listener = self.listener()
        self.tap(listener)
        self.tap(listener)
        self.assertTrue(self.latched.wait(2.0))

    def test_one_tap_does_nothing(self):
        listener = self.listener()
        self.tap(listener)
        self.assertFalse(self.latched.wait(0.3))
        self.assertFalse(self.engaged.is_set())

    def test_two_taps_too_far_apart_do_nothing(self):
        listener = self.listener()
        listener._double_gap = 0.05
        self.tap(listener)
        time.sleep(0.12)
        self.tap(listener)
        self.assertFalse(self.latched.wait(0.3))

    def test_a_shortcut_being_typed_is_not_a_tap(self):
        """Ctrl+Alt+C twice is someone using their editor, not us."""
        listener = self.listener()
        for _ in range(2):
            self.send(listener, ("ctrl", "down"), ("alt", "down"),
                      ("c", "down"), ("c", "up"),
                      ("alt", "up"), ("ctrl", "up"))
        self.assertFalse(self.latched.wait(0.3))

    def test_a_hold_is_not_a_tap(self):
        listener = self.listener(engage_delay=0.05)
        self.send(listener, ("ctrl", "down"), ("alt", "down"))
        self.assertTrue(self.engaged.wait(2.0))
        self.send(listener, ("alt", "up"), ("ctrl", "up"))
        self.assertTrue(self.released.wait(2.0))
        self.assertFalse(self.latched.is_set())

    def test_one_tap_ends_a_hands_free_recording(self):
        listener = self.listener()
        listener.set_recording_latched(True)
        self.tap(listener)
        self.assertTrue(self.engaged.wait(2.0))
        self.assertFalse(self.latched.is_set())

    def test_the_gesture_can_be_turned_off(self):
        listener = self.listener()
        listener._double_gap = 0
        self.tap(listener)
        self.tap(listener)
        self.assertFalse(self.latched.wait(0.3))


from heyspeaky import levels  # noqa: E402


class QuietAudio(unittest.TestCase):
    """Speaking at arm's length from a laptop is what broke this.

    Recordings that came back empty from OpenAI peaked at 0.018 to 0.035 of
    full scale. The old ceiling of eight times left them at a quarter, which
    was still too quiet to hear.
    """

    def buffer(self, peak, seconds=1.0, rate=16000):
        t = np.arange(int(seconds * rate)) / rate
        wave = np.sin(2 * np.pi * 180 * t) * peak
        return (wave * 32767).astype(np.int16).tobytes()

    def peak_of(self, pcm):
        return float(np.max(np.abs(np.frombuffer(pcm, dtype=np.int16))))            / 32768.0

    def test_a_recording_like_the_ones_that_failed_is_made_audible(self):
        """The ceiling of 24 turns the quietest of them into -7 dB."""
        for quiet in (0.018, 0.029, 0.035):
            out = levels.normalise(self.buffer(quiet))
            self.assertGreater(self.peak_of(out), 0.35,
                               "%.3f was left too quiet" % quiet)

    def test_the_old_ceiling_would_not_have_been_enough(self):
        out = levels.normalise(self.buffer(0.018), {"normalize_max_gain": 8.0})
        self.assertLess(self.peak_of(out), 0.2)

    def test_a_loud_recording_is_left_alone(self):
        pcm = self.buffer(0.95)
        self.assertEqual(levels.normalise(pcm), pcm)

    def test_nothing_is_ever_driven_into_the_ceiling(self):
        out = levels.normalise(self.buffer(0.02))
        self.assertLessEqual(self.peak_of(out), 1.0)

    def test_one_loud_click_does_not_stop_the_boost(self):
        """A chair creak used to convince it the recording was loud."""
        quiet = np.frombuffer(self.buffer(0.02), dtype=np.int16).copy()
        quiet[len(quiet) // 2] = 30000
        before = self.peak_of(quiet.tobytes())
        out = levels.normalise(quiet.tobytes())
        self.assertGreater(self.peak_of(out), before)

    def test_silence_is_never_amplified(self):
        pcm = silence(1.0)
        self.assertEqual(levels.normalise(pcm), pcm)

    def test_it_can_be_turned_off(self):
        pcm = self.buffer(0.02)
        self.assertEqual(
            levels.normalise(pcm, {"normalize_for_transcription": False}),
            pcm)


class LanguagePriority(unittest.TestCase):
    """The order of the languages list is a priority order to the model.

    Measured over 24 recordings that change language mid-sentence: Kazakh
    fourth in the list gave 17% of words wrong and lost 35% of the Cyrillic;
    Kazakh first gave 11% and 22%. A language added from the tray used to go
    to the end, which is the place where it does the least.
    """

    def setUp(self):
        import copy
        self.cfg = copy.deepcopy(config_module.DEFAULTS)

    def test_a_language_added_from_the_tray_goes_first(self):
        languages.toggle(self.cfg, "fr")
        self.assertEqual(
            self.cfg["transcription"]["cloud"]["languages"][0], "fr")

    def test_the_shipped_default_does_not_lead_with_english(self):
        """The model leans English unasked; the front is worth more to
        whichever language it is most likely to mishear."""
        shipped = config_module.DEFAULTS["transcription"]["cloud"]["languages"]
        self.assertNotEqual(shipped[0], "en")
        self.assertIn("en", shipped)

    def test_removing_a_language_leaves_the_rest_in_order(self):
        before = list(self.cfg["transcription"]["cloud"]["languages"])
        languages.toggle(self.cfg, before[1])
        after = self.cfg["transcription"]["cloud"]["languages"]
        self.assertEqual(after, [c for c in before if c != before[1]])


dictionary = dictionary_module


class PersonalDictionary(unittest.TestCase):
    """The words one person keeps having to correct.

    The model cannot be taught how somebody sounds, so this is the substitute:
    the words go out with the audio as keywords, and what priming does not
    reach is replaced afterwards. The tests that matter most are the ones
    about what it must NOT replace - a dictionary that eats a real word is
    worse than the mistake it was written for.
    """

    NAME = "Мағжан"       # Magzhan
    WRONG = "Маржан"      # Marzhan

    def setUp(self):
        folder = tempfile.mkdtemp()
        self.path = os.path.join(folder, "dictionary.json")

    def test_a_correction_survives_a_round_trip(self):
        entries = dictionary.add(self.WRONG, self.NAME, entries=[])
        dictionary.save(entries, self.path)
        back = dictionary.load(self.path)
        self.assertEqual(back[0]["meant"], self.NAME)
        self.assertEqual(back[0]["heard"], self.WRONG)

    def test_the_word_is_offered_to_the_model(self):
        entries = dictionary.add(self.WRONG, self.NAME, entries=[])
        self.assertEqual(dictionary.words(entries), [self.NAME])

    def test_what_was_heard_is_replaced_by_what_was_meant(self):
        entries = dictionary.add(self.WRONG, self.NAME, entries=[])
        said = "{}, мен сені "               "сүйем.".format(self.WRONG)
        self.assertIn(self.NAME, dictionary.apply(said, entries))
        self.assertNotIn(self.WRONG, dictionary.apply(said, entries))

    def test_only_whole_words_are_replaced(self):
        entries = dictionary.add("cat", "cot", entries=[])
        self.assertEqual(dictionary.apply("concatenate", entries),
                         "concatenate")
        self.assertEqual(dictionary.apply("the cat.", entries), "the cot.")

    def test_a_word_somebody_meant_is_never_replaced_away(self):
        """Two names that sound alike, both real. Correcting one must not
        destroy the other every time it is said."""
        entries = dictionary.add(self.WRONG, self.NAME, entries=[])
        entries = dictionary.add("", self.WRONG, entries=entries)
        self.assertIn(self.WRONG, dictionary.apply(self.WRONG, entries))

    def test_a_word_can_be_declared_without_ever_being_wrong(self):
        entries = dictionary.add("", self.NAME, entries=[])
        self.assertEqual(dictionary.words(entries), [self.NAME])
        self.assertEqual(dictionary.apply("anything", entries), "anything")

    def test_correcting_the_same_thing_twice_does_not_duplicate_it(self):
        entries = dictionary.add(self.WRONG, self.NAME, entries=[])
        entries = dictionary.add(self.WRONG, self.NAME, entries=entries)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["hits"], 2)

    def test_the_newest_correction_leads(self):
        """What someone is fixing today is what they are saying today, and
        only the first so many words fit in a request."""
        entries = dictionary.add("", "first", entries=[])
        entries = dictionary.add("", "second", entries=entries)
        self.assertEqual(dictionary.words(entries), ["second", "first"])

    def test_the_number_of_words_sent_is_capped(self):
        entries = []
        for index in range(dictionary.KEYWORD_LIMIT + 10):
            entries = dictionary.add("", "word%d" % index, entries=entries)
        self.assertEqual(len(dictionary.words(entries)),
                         dictionary.KEYWORD_LIMIT)

    def test_a_capital_stays_a_capital(self):
        entries = dictionary.add("marzhan", "magzhan", entries=[])
        self.assertEqual(dictionary.apply("Marzhan said so", entries),
                         "Magzhan said so")

    def test_a_broken_file_does_not_stop_dictation(self):
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write("{ this is not json")
        self.assertEqual(dictionary.load(self.path), [])

    def test_a_missing_file_is_empty_rather_than_an_error(self):
        self.assertEqual(dictionary.load(self.path + ".nope"), [])

    def test_an_entry_with_no_meaning_is_ignored(self):
        dictionary.save([{"heard": "x"}, {"meant": "y"}], self.path)
        self.assertEqual(dictionary.words(dictionary.load(self.path)), ["y"])

    def test_empty_text_is_left_alone(self):
        entries = dictionary.add(self.WRONG, self.NAME, entries=[])
        self.assertEqual(dictionary.apply("", entries), "")

    def test_the_full_stop_selected_with_a_word_is_not_stored(self):
        """The owner selected the last word of a sentence, full stop and all,
        and "Мағжан." went to the model as a keyword with the dot on it."""
        entries = dictionary.add("", self.NAME + ".", entries=[])
        self.assertEqual(entries[0]["meant"], self.NAME)
        entries = dictionary.add("«{}»,".format(self.WRONG), self.NAME,
                                 entries=[])
        self.assertEqual(entries[0]["heard"], self.WRONG)

    def test_a_word_already_saved_with_its_dot_goes_out_without_it(self):
        """His file has one already. It has to stop steering the model now,
        not only after he happens to correct the same word again."""
        dictionary.save([{"meant": self.NAME + ".", "hits": 1},
                         {"meant": self.NAME, "heard": "Магжан", "hits": 1}],
                        self.path)
        self.assertEqual(dictionary.words(dictionary.load(self.path)),
                         [self.NAME])

    def test_punctuation_inside_a_word_is_part_of_it(self):
        for word in ("Жан-Поль", "rock'n'roll", "Node.js", "C#", "C++",
                     "т.е.", "e.g."):
            self.assertEqual(dictionary.add("", word, entries=[])[0]["meant"],
                             word)

    def test_only_a_one_letter_abbreviation_keeps_its_last_dot(self):
        """"т.е." ends in a dot because it is built of them. "Node.js" at the
        end of a sentence does not, and neither does a plain word."""
        for selected, stored in (("т.е.,", "т.е."), ("Node.js.", "Node.js"),
                                 ("etc.", "etc")):
            self.assertEqual(
                dictionary.add("", selected, entries=[])[0]["meant"], stored)

    def test_a_selection_of_nothing_but_punctuation_is_not_a_word(self):
        self.assertEqual(dictionary.add("", " … ", entries=[]), [])


class HandEditedFilesSurviveATypo(unittest.TestCase):
    """config.json and dictionary.json are both meant to be edited by hand.

    One comma out of place and the file reads as missing - on purpose, so
    dictation keeps working - but the next save then wrote over it: the next
    Ctrl+Alt+Space replaced a whole dictionary with one word, and the next
    language picked from the tray replaced config.json with the defaults.
    """

    def setUp(self):
        self.folder = tempfile.mkdtemp()

    def broken(self, name):
        path = os.path.join(self.folder, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write('{"words": [{"meant": "Мағжан"},]}')
        return path

    def kept_aside(self, name):
        return [entry for entry in os.listdir(self.folder)
                if entry.startswith(name + ".broken-")]

    def test_a_broken_dictionary_is_kept_before_it_is_written_over(self):
        path = self.broken("dictionary.json")
        entries = dictionary.add("", "Бағжан", path=path)
        self.assertTrue(dictionary.save(entries, path))
        aside = self.kept_aside("dictionary.json")
        self.assertEqual(len(aside), 1)
        with open(os.path.join(self.folder, aside[0]),
                  encoding="utf-8") as handle:
            self.assertIn("Мағжан", handle.read())
        self.assertEqual(dictionary.words(dictionary.load(path)), ["Бағжан"])

    def test_a_broken_config_is_kept_before_it_is_written_over(self):
        path = self.broken("config.json")
        original = config_module.CONFIG_PATH
        config_module.CONFIG_PATH = Path(path)
        self.addCleanup(setattr, config_module, "CONFIG_PATH", original)
        cfg = config_module.load()
        self.assertTrue(config_module.save(cfg))
        self.assertEqual(len(self.kept_aside("config.json")), 1)

    def test_a_readable_file_is_simply_replaced(self):
        path = os.path.join(self.folder, "dictionary.json")
        dictionary.save(dictionary.add("", "one", entries=[]), path)
        dictionary.save(dictionary.add("", "two", path=path), path)
        self.assertEqual(self.kept_aside("dictionary.json"), [])
        self.assertEqual(dictionary.words(dictionary.load(path)),
                         ["two", "one"])
        self.assertEqual(sorted(os.listdir(self.folder)), ["dictionary.json"])


class OldConfigsMoveForward(unittest.TestCase):
    """A measured default is worth nothing if it never reaches anyone.

    config.json is the user's file and the installer never touches it, so the
    owner was still running the old language order a day after it had been
    measured and replaced. These cover the upgrade that fixes that, and the
    line it must not cross: a list somebody chose stays theirs.
    """

    def config(self, languages):
        return {"transcription": {"cloud": {"languages": languages}}}

    def languages(self, cfg):
        return cfg["transcription"]["cloud"]["languages"]

    def test_the_superseded_order_is_replaced(self):
        cfg, changed = config_module._migrate(self.config(["en", "ru", "de",
                                                           "kk"]))
        self.assertTrue(changed)
        self.assertEqual(
            self.languages(cfg),
            config_module.DEFAULTS["transcription"]["cloud"]["languages"])

    def test_a_list_somebody_chose_is_left_alone(self):
        """One entry different and it is a person's own list, not a default."""
        mine = ["en", "ru", "de", "fr"]
        cfg, changed = config_module._migrate(self.config(mine))
        self.assertFalse(changed)
        self.assertEqual(self.languages(cfg), mine)

    def test_the_current_default_is_not_rewritten(self):
        current = list(
            config_module.DEFAULTS["transcription"]["cloud"]["languages"])
        cfg, changed = config_module._migrate(self.config(current))
        self.assertFalse(changed)
        self.assertEqual(self.languages(cfg), current)

    def test_a_config_without_the_setting_survives(self):
        cfg, changed = config_module._migrate({"audio": {"sample_rate": 16000}})
        self.assertFalse(changed)
        self.assertEqual(cfg, {"audio": {"sample_rate": 16000}})

    def test_an_empty_config_survives(self):
        cfg, changed = config_module._migrate({})
        self.assertFalse(changed)
        self.assertEqual(cfg, {})

    def test_the_old_correction_key_moves_to_the_new_one(self):
        """"space" was the shipped default, and it is another program's
        shortcut: a config saved while it was the default keeps it forever."""
        cfg, changed = config_module._migrate(
            {"hotkey": {"correct_key": "space"}})
        self.assertTrue(changed)
        self.assertEqual(cfg["hotkey"]["correct_key"],
                         config_module.DEFAULTS["hotkey"]["correct_key"])

    def test_a_correction_key_somebody_chose_is_left_alone(self):
        cfg, changed = config_module._migrate({"hotkey": {"correct_key": "f9"}})
        self.assertFalse(changed)
        self.assertEqual(cfg["hotkey"]["correct_key"], "f9")

    def test_no_superseded_order_is_still_the_current_default(self):
        """A guard for whoever edits the list next: retiring the order that is
        currently shipped would rewrite every config on every start."""
        current = config_module.DEFAULTS["transcription"]["cloud"]["languages"]
        self.assertNotIn(list(current), config_module.SUPERSEDED_LANGUAGES)


@unittest.skipIf(HotkeyListener is None, "the keyboard package is missing")
class CorrectionKey(unittest.TestCase):
    """Ctrl+Alt+Space asks what the words should have been.

    Space is the one key that had to be carved out of cancel_on_other_key,
    and only while nothing is being recorded. Getting that wrong in either
    direction is bad: cancelling a recording every time somebody corrects a
    word, or swallowing the shortcut somebody was actually typing.
    """

    def listener(self, correct_key="space", on_correct=True):
        self.corrected = threading.Event()
        self.cancelled = threading.Event()
        self.latched = threading.Event()
        return HotkeyListener(
            {
                "engage_delay": 10.0,
                "tap_max": 0.0,
                "accept_altgr": False,
                "cancel_on_other_key": True,
                "double_tap_gap": 0.5,
                "health_check_seconds": 0,
                "min_reinstall_seconds": 60,
                "correct_key": correct_key,
            },
            on_engage=lambda: None,
            on_tap=lambda: None,
            on_hold_release=lambda: None,
            on_cancel=self.cancelled.set,
            on_latch=self.latched.set,
            on_correct=self.corrected.set if on_correct else None,
        )

    def send(self, listener, *events):
        for name, kind in events:
            listener._on_key_event(_Event(name, kind))

    def test_space_inside_the_chord_asks_for_a_correction(self):
        listener = self.listener()
        self.send(listener, ("ctrl", "down"), ("alt", "down"),
                  ("space", "down"))
        self.assertTrue(self.corrected.wait(2.0))
        self.assertFalse(self.cancelled.is_set())

    def test_correcting_twice_does_not_go_hands_free(self):
        """Two corrections in a row are two chords released quickly, which is
        exactly the shape of the double tap that starts hands-free."""
        listener = self.listener()
        for _ in range(2):
            self.send(listener, ("ctrl", "down"), ("alt", "down"),
                      ("space", "down"), ("space", "up"),
                      ("alt", "up"), ("ctrl", "up"))
        self.assertTrue(self.corrected.wait(2.0))
        self.assertFalse(self.latched.wait(0.3))

    def test_space_during_a_recording_still_cancels(self):
        """Mid-recording it is somebody typing, not somebody correcting."""
        listener = self.listener()
        self.send(listener, ("ctrl", "down"), ("alt", "down"))
        listener._engaged = True
        listener._press_started = time.monotonic() - 5
        self.send(listener, ("space", "down"))
        self.assertTrue(self.cancelled.wait(2.0))
        self.assertFalse(self.corrected.is_set())

    def test_space_on_its_own_does_nothing(self):
        listener = self.listener()
        self.send(listener, ("space", "down"), ("space", "up"))
        self.assertFalse(self.corrected.wait(0.3))

    def test_holding_space_asks_once(self):
        """Windows repeats KEY_DOWN, and each repeat must not open a box."""
        listener = self.listener()
        fired = []
        listener._on_correct = lambda: fired.append(1)
        self.send(listener, ("ctrl", "down"), ("alt", "down"))
        for _ in range(5):
            self.send(listener, ("space", "down"))
        time.sleep(0.2)
        self.assertEqual(len(fired), 1)

    def test_the_key_can_be_turned_off(self):
        listener = self.listener(correct_key="")
        self.send(listener, ("ctrl", "down"), ("alt", "down"),
                  ("space", "down"))
        self.assertFalse(self.corrected.wait(0.3))
        self.assertFalse(self.cancelled.is_set())

    def test_the_other_spelling_of_the_key_counts(self):
        """The keyboard library names this key differently per layout."""
        listener = self.listener()
        self.send(listener, ("ctrl", "down"), ("alt", "down"),
                  ("spacebar", "down"))
        self.assertTrue(self.corrected.wait(2.0))

    def test_ctrl_alt_c_is_still_somebody_elses_shortcut(self):
        listener = self.listener()
        self.send(listener, ("ctrl", "down"), ("alt", "down"), ("c", "down"))
        self.assertFalse(self.corrected.wait(0.3))


@unittest.skipIf(HotkeyListener is None, "the keyboard package is missing")
class CorrectionOnTheWindowsKey(CorrectionKey):
    """Ctrl+Alt+Win, because Ctrl+Alt+Space belongs to another program.

    The owner pressed Ctrl+Alt+Space and a desktop assistant opened its own
    window: a global shortcut registered by another app gets the keys first,
    and a hook that only watches cannot stop it. Ctrl+Alt+Win is nobody's.
    Pressed on his machine, fast and slow and Win first, it did not open the
    Start menu either - Win alone did, which is how the check was checked.
    """

    def listener(self, correct_key="windows", on_correct=True):
        return CorrectionKey.listener(self, correct_key, on_correct)

    # The inherited tests press Space; with this key Space is just a key.
    test_space_inside_the_chord_asks_for_a_correction = None
    test_correcting_twice_does_not_go_hands_free = None
    test_holding_space_asks_once = None
    test_the_other_spelling_of_the_key_counts = None

    def test_it_is_the_default(self):
        self.assertEqual(config_module.DEFAULTS["hotkey"]["correct_key"],
                         "windows")

    def test_ctrl_alt_win_asks_for_a_correction(self):
        listener = self.listener()
        self.send(listener, ("ctrl", "down"), ("alt", "down"),
                  ("left windows", "down"))
        self.assertTrue(self.corrected.wait(2.0))
        self.assertFalse(self.cancelled.is_set())

    def test_the_right_win_key_counts_too(self):
        listener = self.listener()
        self.send(listener, ("ctrl", "down"), ("alt", "down"),
                  ("right windows", "down"))
        self.assertTrue(self.corrected.wait(2.0))

    def test_win_pressed_first_counts_too(self):
        """Three keys pressed "together" arrive in any order."""
        listener = self.listener()
        self.send(listener, ("left windows", "down"), ("ctrl", "down"),
                  ("alt", "down"))
        self.assertTrue(self.corrected.wait(2.0))

    def test_holding_the_chord_asks_once(self):
        listener = self.listener()
        fired = []
        listener._on_correct = lambda: fired.append(1)
        self.send(listener, ("ctrl", "down"), ("alt", "down"))
        for _ in range(5):
            self.send(listener, ("left windows", "down"))
        time.sleep(0.2)
        self.assertEqual(len(fired), 1)

    def test_correcting_twice_does_not_go_hands_free(self):
        listener = self.listener()
        for _ in range(2):
            self.send(listener, ("ctrl", "down"), ("alt", "down"),
                      ("left windows", "down"), ("left windows", "up"),
                      ("alt", "up"), ("ctrl", "up"))
        self.assertTrue(self.corrected.wait(2.0))
        self.assertFalse(self.latched.wait(0.3))

    def test_win_just_after_the_recording_started_is_still_a_correction(self):
        """Ctrl+Alt a little ahead of Win is enough to start a recording.
        That was one gesture, and what it asked for was the box."""
        listener = self.listener()
        self.send(listener, ("ctrl", "down"), ("alt", "down"))
        listener._engaged = True
        listener._press_started = time.monotonic() - 0.4
        self.send(listener, ("left windows", "down"))
        self.assertTrue(self.corrected.wait(2.0))
        self.assertTrue(self.cancelled.wait(2.0))    # the stray recording

    def test_space_is_now_just_another_key(self):
        """It is another program's shortcut now, and cancels as any key."""
        listener = self.listener()
        self.send(listener, ("ctrl", "down"), ("alt", "down"),
                  ("space", "down"))
        self.assertFalse(self.corrected.wait(0.3))


@unittest.skipIf(HotkeyListener is None, "the keyboard package is missing")
class ACancelledChordStaysCancelled(unittest.TestCase):
    """The owner's log, 22 September, 22:52:47: a recording cancelled by the
    Win key, and 0.37 seconds later "Recording started" again - and then the
    same once more. Ctrl and Alt were still down after Win came up, and the
    chord armed itself afresh as if they had just been pressed."""

    def test_releasing_the_other_key_does_not_start_another_recording(self):
        engaged = []
        listener = HotkeyListener(
            {
                "engage_delay": 0.1,
                "tap_max": 0.0,
                "accept_altgr": False,
                "cancel_on_other_key": True,
                "double_tap_gap": 0.5,
                "health_check_seconds": 0,
                "min_reinstall_seconds": 60,
                "correct_key": "",
            },
            on_engage=lambda: engaged.append(1),
            on_tap=lambda: None,
            on_hold_release=lambda: None,
            on_cancel=lambda: None,
        )
        for name, kind in (("ctrl", "down"), ("alt", "down")):
            listener._on_key_event(_Event(name, kind))
        time.sleep(0.3)
        self.assertEqual(len(engaged), 1)
        for name, kind in (("c", "down"), ("c", "up")):
            listener._on_key_event(_Event(name, kind))
        time.sleep(0.4)                  # Ctrl and Alt still held
        self.assertEqual(len(engaged), 1)


try:
    from heyspeaky import correct
except Exception:           # no tkinter or no Pillow
    correct = None

try:
    from heyspeaky import app as app_module
except Exception:           # CI does not install the audio stack
    app_module = None


@unittest.skipIf(correct is None, "tkinter or Pillow is missing")
class OneCorrectionAtATime(unittest.TestCase):
    """Ctrl+Alt+Space pressed again while a correction is already under way.

    From the owner's log, 22 September: "Correction asked for" twice, a
    second apart, then two "Correction cancelled" in the same millisecond -
    two boxes, one on top of the other, and it happened twice. Space pressed
    again inside a held chord is a fresh key-down, not a repeat, so the
    hotkey's own repeat guard never saw it.
    """

    def test_a_second_press_is_refused_while_the_first_is_running(self):
        guard = correct.OneAtATime()
        self.assertTrue(guard.begin())
        self.assertFalse(guard.begin())

    def test_the_next_one_is_allowed_once_the_box_has_closed(self):
        guard = correct.OneAtATime()
        guard.begin()
        guard.end()
        self.assertTrue(guard.begin())

    def test_a_correction_that_never_opened_a_box_does_not_block_forever(self):
        """Reading the selection is the only step without a box on screen,
        and it gives up after a few seconds. A claim older than that has been
        lost somewhere, and Ctrl+Alt+Space must not stay dead until restart."""
        guard = correct.OneAtATime()
        guard.begin(now=0.0)
        self.assertFalse(guard.begin(now=5.0))
        self.assertTrue(guard.begin(now=correct.OneAtATime.STALE + 1.0))

    def test_an_open_box_is_never_given_up_on(self):
        guard = correct.OneAtATime()
        guard.begin(now=0.0)
        guard.opened(object())
        self.assertFalse(guard.begin(now=3600.0))


@unittest.skipIf(app_module is None or correct is None,
                 "the app's own packages are not installed")
class CorrectionBoxIsNotDuplicated(unittest.TestCase):
    """The same, through the app's own handlers, with a fake box."""

    def setUp(self):
        import types
        self.boxes = []
        self.refuse_to_open = False
        test = self

        class FakeBox(object):
            def __init__(self, root, heard, on_done, scale=1.0,
                         look="glass"):
                if test.refuse_to_open:
                    raise RuntimeError("no display")
                self.heard = heard
                self.look = look
                self.on_done = on_done
                self.raised = 0
                test.boxes.append(self)

            def bring_forward(self):
                self.raised += 1

        def slow_copy(timeout):
            time.sleep(0.3)         # waiting for Ctrl and Alt to come up
            return "Магжан"

        for module, name, value in (
                (correct, "CorrectionBox", FakeBox),
                (correct, "foreground_window", lambda: None),
                (correct, "restore_foreground", lambda handle: False),
                (app_module.output, "copy_selection", slow_copy)):
            self.addCleanup(setattr, module, name, getattr(module, name))
            setattr(module, name, value)

        self.app = object.__new__(app_module.App)
        self.app.cfg = {"output": {"modifier_release_timeout": 1.0}}
        self.app.root = None
        self.app.overlay = types.SimpleNamespace(scale=1.0)
        self.app.post = lambda func, *args: func(*args)
        self.app._correction = correct.OneAtATime()

    def settle(self):
        time.sleep(0.8)

    def test_the_box_opens_in_the_pill_s_look(self):
        """Mono turns the correction box black too, not the pill alone."""
        self.app.cfg["overlay"] = {"style": "mono"}
        self.app._on_correct()
        self.settle()
        self.assertEqual([box.look for box in self.boxes], ["mono"])

    def test_two_presses_while_the_selection_is_read_open_one_box(self):
        self.app._on_correct()
        time.sleep(0.1)
        self.app._on_correct()
        self.settle()
        self.assertEqual(len(self.boxes), 1)

    def test_a_press_while_the_box_is_open_brings_it_forward(self):
        self.app._on_correct()
        self.settle()
        self.app._on_correct()
        self.settle()
        self.assertEqual(len(self.boxes), 1)
        self.assertEqual(self.boxes[0].raised, 1)

    def test_closing_the_box_lets_the_next_press_open_another(self):
        self.app._on_correct()
        self.settle()
        self.boxes[0].on_done(None)
        self.app._on_correct()
        self.settle()
        self.assertEqual(len(self.boxes), 2)

    def test_a_box_that_failed_to_open_does_not_block_the_next(self):
        self.refuse_to_open = True
        self.app._on_correct()
        self.settle()
        self.refuse_to_open = False
        self.app._on_correct()
        self.settle()
        self.assertEqual(len(self.boxes), 1)


@unittest.skipIf(HotkeyListener is None, "the keyboard package is missing")
class ReadingTheSelection(unittest.TestCase):
    """Ctrl+Alt+Win, and the selected words have to reach the box.

    The owner selected text, pressed the chord nine times on 23 September
    and got an empty box every time. Nothing in the log said why. These hold
    the parts of the path that can be held without a real keyboard: when the
    keys count as up, how Ctrl+C is sent and retried, and that the log says
    what happened without saying what the text was.
    """

    WORD = "Маржан"

    def setUp(self):
        from heyspeaky import output
        self.output = output
        self.clipboard = {"text": "what was there before", "seq": 1}
        self.sent = []
        self.answers = []       # what each Ctrl+C does to the clipboard

        def clear():
            self.clipboard.update(text="", seq=self.clipboard["seq"] + 1)
            return True

        def send():
            self.sent.append(1)
            answer = self.answers.pop(0) if self.answers else None
            if answer is not None:
                self.clipboard.update(text=answer,
                                      seq=self.clipboard["seq"] + 1)

        def put(text):
            self.clipboard.update(text=text, seq=self.clipboard["seq"] + 1)
            return True

        for name, value in (
                ("read_clipboard", lambda: self.clipboard["text"]),
                ("clear_clipboard", clear),
                ("copy_to_clipboard", put),
                ("_clipboard_sequence", lambda: self.clipboard["seq"]),
                ("_send_copy", send),
                ("_foreground_class", lambda: "Notepad"),
                ("wait_for_modifiers_released", lambda timeout: True)):
            self.addCleanup(setattr, output, name, getattr(output, name, None))
            setattr(output, name, value)

    def test_the_selection_comes_back_and_the_clipboard_is_restored(self):
        self.answers = [self.WORD]
        self.assertEqual(self.output.copy_selection(1.0, settle=0.2),
                         self.WORD)
        self.assertEqual(self.clipboard["text"], "what was there before")

    def test_a_copy_that_never_arrived_is_tried_again(self):
        """A Ctrl+C the window never acted on leaves the clipboard exactly as
        it was. One more try costs a fraction of a second; an empty box
        costs the whole correction."""
        self.answers = [None, self.WORD]
        self.assertEqual(self.output.copy_selection(1.0, settle=0.15),
                         self.WORD)
        self.assertEqual(len(self.sent), 2)

    def test_a_window_that_answered_with_nothing_is_not_asked_twice(self):
        """It copied, and there was no text: nothing was selected."""
        self.answers = [""]
        self.assertEqual(self.output.copy_selection(1.0, settle=0.15), "")
        self.assertEqual(len(self.sent), 1)

    def test_the_log_says_how_much_and_from_where_but_not_what(self):
        self.answers = [self.WORD]
        with self.assertLogs("heyspeaky.output", level="INFO") as logs:
            self.output.copy_selection(1.0, settle=0.2)
        said = "\n".join(logs.output)
        self.assertIn("6 chars", said)
        self.assertIn("Notepad", said)
        self.assertNotIn(self.WORD, said)

    def test_keys_count_as_up_when_windows_says_so(self):
        """Not when the keyboard library's own list says so. That list is
        kept from the events its hook has seen, and a release that never
        reached the hook - after Ctrl+Alt+Del or Win+L, or an injected event
        the library chose to drop - leaves a key held in it for good."""
        import keyboard
        stale = keyboard.is_pressed
        self.addCleanup(setattr, keyboard, "is_pressed", stale)
        keyboard.is_pressed = lambda name: True
        real = hotkey._key_down
        self.addCleanup(setattr, hotkey, "_key_down", real)
        hotkey._key_down = lambda vk: False
        started = time.monotonic()
        self.assertTrue(hotkey.wait_for_modifiers_released(1.0))
        self.assertLess(time.monotonic() - started, 0.5)

    def test_a_key_that_is_really_held_is_waited_for(self):
        held = {0x5B}                       # the left Win key
        real = hotkey._key_down
        self.addCleanup(setattr, hotkey, "_key_down", real)
        hotkey._key_down = lambda vk: vk in held
        threading.Timer(0.15, held.clear).start()
        started = time.monotonic()
        self.assertTrue(hotkey.wait_for_modifiers_released(2.0))
        self.assertGreaterEqual(time.monotonic() - started, 0.12)

    def test_giving_up_names_the_key(self):
        real = hotkey._key_down
        self.addCleanup(setattr, hotkey, "_key_down", real)
        hotkey._key_down = lambda vk: vk == 0x12      # Alt, for ever
        with self.assertLogs("heyspeaky.hotkey", level="WARNING") as logs:
            self.assertFalse(hotkey.wait_for_modifiers_released(0.1))
        self.assertIn("alt", "\n".join(logs.output))


@unittest.skipIf(HotkeyListener is None, "the keyboard package is missing")
class HookWatchdog(unittest.TestCase):
    """When the watchdog may replace the hook, and when it must not.

    The app's own log is the reason these exist: 455 refreshes in three days,
    every one of them a mouse being moved rather than a hook that had died.
    A refresh unhooks and rehooks, so each is a moment where Ctrl+Alt can land
    on nothing.
    """

    def listener(self):
        listener = HotkeyListener(
            {
                "engage_delay": 10.0,
                "tap_max": 0.0,
                "accept_altgr": False,
                "cancel_on_other_key": True,
                "double_tap_gap": 0.5,
                "health_check_seconds": 20,
                "min_reinstall_seconds": 60,
            },
            on_engage=lambda: None,
            on_tap=lambda: None,
            on_hold_release=lambda: None,
            on_cancel=lambda: None,
        )
        # Nothing has reached the hook for a long time, and the hook was never
        # replaced: the state every test below starts from.
        listener._last_event = time.monotonic() - 300
        listener._last_reinstall = time.monotonic() - 300
        return listener

    def system_idle(self, seconds):
        """Pretends Windows last saw input this many seconds ago."""
        original = hotkey._system_idle_seconds
        hotkey._system_idle_seconds = lambda: seconds
        self.addCleanup(setattr, hotkey, "_system_idle_seconds", original)

    def test_a_moving_mouse_is_not_a_dead_hook(self):
        """The 455 refreshes. Windows saw input, but it was the pointer."""
        listener = self.listener()
        self.system_idle(1)
        self.assertIsNone(listener._dead_hook_reason(moved=True,
                                                     resumed=False))

    def test_input_with_a_still_mouse_means_keys_we_missed(self):
        listener = self.listener()
        self.system_idle(1)
        self.assertIsNotNone(listener._dead_hook_reason(moved=False,
                                                        resumed=False))

    def test_waking_from_sleep_is_checked_even_with_the_mouse_moving(self):
        """Waking the screen moves the pointer, and a hook lost to sleep is
        exactly what this watchdog was written for."""
        listener = self.listener()
        self.system_idle(1)
        self.assertIsNotNone(listener._dead_hook_reason(moved=True,
                                                        resumed=True))

    def test_an_idle_machine_is_left_alone(self):
        """Both stale by the same amount: nothing is wrong, and the laptop is
        allowed to go to sleep."""
        listener = self.listener()
        self.system_idle(300)
        self.assertIsNone(listener._dead_hook_reason(moved=False,
                                                     resumed=False))

    def test_a_hook_that_is_seeing_keys_is_left_alone(self):
        listener = self.listener()
        listener._last_event = time.monotonic()
        self.system_idle(0)
        self.assertIsNone(listener._dead_hook_reason(moved=False,
                                                     resumed=False))

    def test_refreshes_stay_a_minute_apart(self):
        listener = self.listener()
        listener._last_reinstall = time.monotonic()
        self.system_idle(1)
        self.assertIsNone(listener._dead_hook_reason(moved=False,
                                                     resumed=False))

    def test_an_unreadable_pointer_falls_back_to_leaving_it_alone(self):
        """GetCursorPos can fail. Then nothing has moved as far as we know,
        and the old behaviour - trust the idle timer - is what is left."""
        listener = self.listener()
        original = hotkey._cursor_position
        hotkey._cursor_position = lambda: None
        self.addCleanup(setattr, hotkey, "_cursor_position", original)
        listener._last_cursor = (10, 10)
        self.assertFalse(listener._cursor_moved())
        self.assertIsNone(listener._last_cursor)

    def test_the_first_check_of_all_reports_no_movement(self):
        """With nothing to compare against, a position is not a movement."""
        listener = self.listener()
        original = hotkey._cursor_position
        hotkey._cursor_position = lambda: (5, 5)
        self.addCleanup(setattr, hotkey, "_cursor_position", original)
        self.assertFalse(listener._cursor_moved())
        self.assertTrue(listener._cursor_moved() is False)
        hotkey._cursor_position = lambda: (6, 5)
        self.assertTrue(listener._cursor_moved())

    def test_input_from_before_the_last_check_is_put_down_to_the_pointer(self):
        """16 of the 36 refreshes in the owner's log the day after the fix,
        sleep aside: Windows last saw input 22-47 seconds ago, longer than the
        20 between checks. That input came before the previous check, so
        comparing the pointer with where it was at the previous check could
        never account for it, whatever it was."""
        listener = self.listener()
        original = hotkey._cursor_position
        self.addCleanup(setattr, hotkey, "_cursor_position", original)
        hotkey._cursor_position = lambda: (5, 5)
        listener._cursor_moved()
        hotkey._cursor_position = lambda: (400, 300)
        self.assertTrue(listener._cursor_moved())     # seen moving here...
        listener._pointer_moved_at -= 20              # ...one check ago
        self.assertFalse(listener._cursor_moved())    # and still since
        self.system_idle(28)
        self.assertIsNone(listener._dead_hook_reason(moved=False,
                                                     resumed=False))

    def test_a_pointer_that_moved_long_before_the_input_explains_nothing(self):
        listener = self.listener()
        listener._pointer_moved_at = time.monotonic() - 100
        self.system_idle(28)
        self.assertIsNotNone(listener._dead_hook_reason(moved=False,
                                                        resumed=False))

    def test_a_refresh_that_changed_nothing_is_not_repeated_every_minute(self):
        """21 of the 36 were a brand-new hook that had heard no key in the
        whole time since the refresh before it - nine in a row, a minute
        apart. Whatever Windows was counting was almost certainly not keys,
        and replacing the hook once a minute changed nothing but the risk of
        a lost press."""
        listener = self.listener()
        self.system_idle(1)
        listener._count_refresh()
        listener._count_refresh()        # no key reached the hook in between
        listener._last_reinstall = time.monotonic() - 61
        self.assertIsNone(listener._dead_hook_reason(moved=False,
                                                     resumed=False))
        listener._last_reinstall = time.monotonic() - 121
        self.assertIsNotNone(listener._dead_hook_reason(moved=False,
                                                        resumed=False))

    def test_a_key_after_a_refresh_brings_the_minute_back(self):
        listener = self.listener()
        self.system_idle(1)
        for _ in range(4):
            listener._count_refresh()
        listener._on_key_event(_Event("a", "down"))
        listener._on_key_event(_Event("a", "up"))
        listener._last_event = time.monotonic() - 300
        listener._last_reinstall = time.monotonic() - 61
        self.assertIsNotNone(listener._dead_hook_reason(moved=False,
                                                        resumed=False))

    def test_the_wait_between_refreshes_has_a_ceiling(self):
        """A hook that really does die later still gets replaced within
        minutes, however long the machine was scrolled without a key."""
        listener = self.listener()
        self.system_idle(1)
        for _ in range(30):
            listener._count_refresh()
        listener._last_reinstall = (time.monotonic()
                                    - hotkey.MAX_REFRESH_GAP - 1)
        self.assertIsNotNone(listener._dead_hook_reason(moved=False,
                                                        resumed=False))

    def test_waking_from_sleep_is_not_made_to_wait_out_the_backoff(self):
        listener = self.listener()
        self.system_idle(1)
        for _ in range(6):
            listener._count_refresh()
        listener._last_reinstall = time.monotonic() - 61
        self.assertIsNotNone(listener._dead_hook_reason(moved=True,
                                                        resumed=True))



class _PanelModel(object):
    YOURS = ["kk", "ru", "en", "de"]

    def model(self, **changes):
        catalog = languages.catalog(self.YOURS)
        model = {"status": "Ready", "state": "ready", "paused": False,
                 "pinned": "", "yours": list(self.YOURS), "backend": "cloud",
                 "usage": "This month: $0.42", "update": "", "key": "saved",
                 "catalog": list(catalog),
                 "names": dict((c, languages.name(c)) for c in catalog)}
        model.update(changes)
        return model


@unittest.skipIf(panel_module is None, "tkinter is missing")
class ThePanelHasNoSlit(_PanelModel, unittest.TestCase):
    """The owner saw the desktop through a thin line across the panel."""

    def test_a_separator_is_laid_over_the_glass_not_cut_through_it(self):
        """The line was drawn straight onto the picture, which put its own
        faint alpha in place of the glass's. Laid over, the glass underneath
        stays as solid as it is either side of the line."""
        for scale in (1.0, 1.25):
            size, items = panel_module.layout(self.model(), scale)
            card = glass.panel_card(size[0], size[1], scale)
            frame = glass.panel_frame(card, items, scale)
            separators = [item for item in items if item.kind == "separator"]
            self.assertTrue(separators)
            for item in separators:
                x = (item.rect[0] + item.rect[2]) // 2
                y = int((item.rect[1] + item.rect[3]) / 2.0)
                line = frame.getpixel((x, y))[3]
                above = frame.getpixel((x, y - 4))[3]
                self.assertGreaterEqual(line, above - 2, (scale, line, above))


@unittest.skipIf(panel_module is None, "tkinter is missing")
class QuitAsksTwice(_PanelModel, unittest.TestCase):
    """The panel opens over the tray, and Quit was the row the pointer met
    first on its way up: the owner quit by accident, again and again."""

    def panel(self):
        import types
        panel = object.__new__(panel_module.TrayPanel)
        self.done, self.closed = [], []
        panel._quit_armed_at = None
        panel._refit = lambda: None
        panel._act = self.done.append
        panel.close = lambda *_: self.closed.append(1)
        panel.window = types.SimpleNamespace(after=lambda *_: None)
        return panel

    def test_one_click_on_quit_does_not_quit(self):
        panel = self.panel()
        panel.press("quit")
        self.assertEqual(self.done, [])
        self.assertEqual(self.closed, [])

    def test_a_second_click_soon_after_quits(self):
        panel = self.panel()
        panel.press("quit")
        panel.press("quit")
        self.assertEqual(self.done, ["quit"])

    def test_a_second_click_long_after_asks_again(self):
        panel = self.panel()
        panel.press("quit")
        panel._quit_armed_at -= theme.QUIT_ARMED + 0.5
        panel.press("quit")
        self.assertEqual(self.done, [])

    def test_the_row_says_what_the_next_click_does(self):
        _size, items = panel_module.layout(self.model(), 1.0,
                                           quit_armed=True)
        row = [item for item in items if item.key == "quit"][0]
        self.assertIn("again", row.label)
        self.assertEqual(row.extra, "danger")


@unittest.skipIf(panel_module is None, "tkinter is missing")
class FindingALanguageByTyping(_PanelModel, unittest.TestCase):
    """The owner asked to type his language instead of hunting for it."""

    def found(self, query):
        return panel_module.language_order(self.model(), query)

    def test_kazakh_answers_to_every_way_of_typing_it(self):
        for query in ("kaz", "Kaz", "каз", "қаз", "Қазақша", "kk"):
            self.assertEqual(self.found(query)[:1], ["kk"], query)

    def test_kazakh_letters_typed_on_a_russian_layout_still_find_it(self):
        """Қазақша typed without the Kazakh layout on is "казакша"."""
        self.assertEqual(self.found("казакша")[:1], ["kk"])

    def test_a_language_answers_to_its_russian_and_its_own_name(self):
        self.assertEqual(self.found("нем")[:1], ["de"])
        self.assertEqual(self.found("Deutsch")[:1], ["de"])
        self.assertEqual(self.found("орыс")[:1], ["ru"])
        self.assertEqual(self.found("farsi")[:1], ["fa"])

    def test_nothing_typed_leaves_the_whole_list(self):
        self.assertEqual(self.found(""), panel_module.language_order(
            self.model()))

    def test_the_list_shows_only_what_answers(self):
        _size, items = panel_module.layout(self.model(), 1.25, "languages",
                                           0.0, "каз")
        rows = [item.key for item in items if item.kind == "language"]
        self.assertEqual(rows, ["lang:kk"])
        hint = [item for item in items if item.kind == "hint"][0]
        self.assertIn("Kazakh", hint.label)
        search = [item for item in items if item.kind == "search"][0]
        self.assertEqual(search.label, "каз")

    def test_nothing_found_says_so(self):
        _size, items = panel_module.layout(self.model(), 1.25, "languages",
                                           0.0, "zzzz")
        self.assertEqual([i for i in items if i.kind == "language"], [])
        hint = [item for item in items if item.kind == "hint"][0]
        self.assertIn("No language", hint.label)

    def test_typing_on_the_first_page_opens_the_search(self):
        import types
        panel = object.__new__(panel_module.TrayPanel)
        panel._page, panel._query, panel._scroll = "main", "", 0.0
        panel._turn_goal, panel._flare_at, panel._caret_job = 0.0, None, None
        panel._hover_key = None
        panel._closing_at = None
        panel._model = self.model()
        panel._refit = lambda: None
        panel.window = types.SimpleNamespace(after=lambda *_: None,
                                             after_cancel=lambda *_: None)
        real = keymap.typed_char
        self.addCleanup(setattr, keymap, "typed_char", real)
        keymap.typed_char = lambda code, layout=None: "қ"
        panel._key(types.SimpleNamespace(keysym="Cyrillic_ka",
                                         keycode=0x30, char="?"))
        self.assertEqual((panel._page, panel._query), ("languages", "қ"))

    def test_a_search_field_is_drawn(self):
        size, items = panel_module.layout(self.model(), 1.25, "languages",
                                          0.0, "kaz")
        card = glass.panel_card(size[0], size[1], 1.25)
        frame = glass.panel_frame(card, items, 1.25)
        field = [item for item in items if item.kind == "search"][0]
        inside = frame.getpixel((field.rect[0] + field.rect[3] - field.rect[1],
                                 field.rect[1] + 3))
        self.assertEqual(frame.size, card[0].size)
        self.assertEqual(inside[3], 255)

    def test_a_tick_draws_itself_in(self):
        size, items = panel_module.layout(self.model(), 1.25, "languages")
        card = glass.panel_card(size[0], size[1], 1.25)
        row = [item for item in items if item.key == "lang:kk"][0]
        box = (row.rect[2] - 40, row.rect[1], row.rect[2], row.rect[3])

        def ink(share):
            frame = glass.panel_frame(card, items, 1.25, None,
                                      {"tick:lang:kk": share})
            crop = frame.crop(box).convert("L").tobytes()
            return sum(1 for value in crop if value > 160)

        self.assertEqual(ink(0.0), 0)
        self.assertLess(0, ink(0.4))
        self.assertLess(ink(0.4), ink(1.0))


try:
    import tkinter as _tk
    _tk_root = _tk.Tk()
    _tk_root.withdraw()
except Exception:                              # no display, no Tcl
    _tk_root = None

from heyspeaky import keymap  # noqa: E402


class _KeyEvent(object):
    def __init__(self, keycode, char):
        self.keycode = keycode
        self.char = char
        self.keysym = "??"


class TypingInTheLayoutInUse(unittest.TestCase):
    """Kazakh typed into the correction box came out as ³ and question
    marks: Tk decodes a key through a one-byte code page, and most of
    Kazakh is not in one."""

    def kazakh(self):
        import ctypes
        user32 = ctypes.windll.user32
        user32.LoadKeyboardLayoutW.restype = ctypes.c_void_p
        user32.GetKeyboardLayoutList.argtypes = [
            ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)]
        count = user32.GetKeyboardLayoutList(0, None)
        loaded = (ctypes.c_void_p * count)()
        user32.GetKeyboardLayoutList(count, loaded)
        for handle in loaded:
            if (handle or 0) & 0xFFFF == 0x043F:
                return handle
        # Not installed here: load it for the test, tell nobody, and put
        # things back as they were.
        handle = user32.LoadKeyboardLayoutW("0000043F", 0x80)
        if not handle:
            self.skipTest("the Kazakh layout cannot be loaded")
        user32.UnloadKeyboardLayout.argtypes = [ctypes.c_void_p]
        self.addCleanup(user32.UnloadKeyboardLayout, handle)
        return handle

    def test_the_number_row_of_the_kazakh_layout_is_kazakh(self):
        layout = self.kazakh()
        typed = "".join(keymap.typed_char(code, layout)
                        for code in (0x33, 0x34, 0x35, 0x38, 0x30))
        self.assertEqual(typed, "іңғүқ")

    def test_keys_that_are_not_text_type_nothing(self):
        layout = self.kazakh()
        for code in (0x08, 0x0D, 0x25, 0x1B):      # Backspace Enter Left Esc
            self.assertEqual(keymap.typed_char(code, layout), "", code)

    @unittest.skipIf(_tk_root is None, "no display for Tk")
    def test_a_field_types_what_the_layout_meant(self):
        entry = _tk.Entry(_tk_root)
        self.addCleanup(entry.destroy)
        real = keymap.typed_char
        self.addCleanup(setattr, keymap, "typed_char", real)
        keymap.typed_char = lambda code, layout=None: "ң"
        typed = keymap.fix_typing(entry)
        entry.insert(0, "Ма")
        self.assertEqual(typed(_KeyEvent(0x34, "?")), "break")
        self.assertEqual(entry.get(), "Маң")

    @unittest.skipIf(_tk_root is None, "no display for Tk")
    def test_a_selection_is_typed_over(self):
        entry = _tk.Entry(_tk_root)
        self.addCleanup(entry.destroy)
        real = keymap.typed_char
        self.addCleanup(setattr, keymap, "typed_char", real)
        keymap.typed_char = lambda code, layout=None: "і"
        typed = keymap.fix_typing(entry)
        entry.insert(0, "Marzhan")
        entry.select_range(0, "end")
        entry.icursor("end")
        typed(_KeyEvent(0x33, "³"))
        self.assertEqual(entry.get(), "і")

    @unittest.skipIf(_tk_root is None, "no display for Tk")
    def test_where_tk_already_agrees_it_is_left_alone(self):
        entry = _tk.Entry(_tk_root)
        self.addCleanup(entry.destroy)
        real = keymap.typed_char
        self.addCleanup(setattr, keymap, "typed_char", real)
        keymap.typed_char = lambda code, layout=None: "a"
        typed = keymap.fix_typing(entry)
        self.assertIsNone(typed(_KeyEvent(0x41, "a")))
        self.assertEqual(entry.get(), "")


from heyspeaky import apikey  # noqa: E402


class AddingTheKeyFromTheTray(unittest.TestCase):
    """Click the icon, click "Add your OpenAI key", paste, Save: the steps
    the owner described. No PowerShell, no reinstall."""

    KEY = "sk-proj-" + "Ab3_" * 12

    def flow(self, clipboard="", verdict="ok", has_key=False):
        self.clipboard = {"text": clipboard}
        self.saved, self.opened, self.told, self.checked = [], [], [], []
        self.have = {"key": has_key}

        def save(config, key):
            self.saved.append(key)
            self.have["key"] = True

        def checker(key):
            self.checked.append(key)
            return verdict

        return apikey.KeyFlow(
            {"transcription": {"cloud": {}}},
            has_key=lambda: self.have["key"],
            read_clipboard=lambda: self.clipboard["text"],
            clear_clipboard=lambda: self.clipboard.update(text=""),
            on_saved=lambda: self.told.append(1),
            open_page=self.opened.append, checker=checker, saver=save)

    def settle(self, flow):
        deadline = time.monotonic() + 2.0
        while flow.state() == "checking" and time.monotonic() < deadline:
            time.sleep(0.02)

    def test_what_a_key_looks_like(self):
        self.assertTrue(apikey.looks_like_key(self.KEY))
        self.assertTrue(apikey.looks_like_key("  " + self.KEY + "\n"))
        for text in ("", "hello", "sk-short", "sk-" + "a" * 10 + " b" * 10,
                     "Bearer " + self.KEY):
            self.assertFalse(apikey.looks_like_key(text), text)

    def test_a_pasted_key_is_checked_saved_and_taken_off_the_clipboard(self):
        flow = self.flow(clipboard=self.KEY)
        self.assertEqual(flow.state(), "missing")
        self.assertEqual(flow.submit(" " + self.KEY + "\n"), "checking")
        self.settle(flow)
        self.assertEqual(self.saved, [self.KEY])
        self.assertEqual(self.told, [1])
        self.assertEqual(self.clipboard["text"], "")
        self.assertEqual(flow.state(), "done")

    def test_a_clipboard_holding_something_else_is_left_alone(self):
        flow = self.flow(clipboard="a shopping list")
        flow.submit(self.KEY)
        self.settle(flow)
        self.assertEqual(self.saved, [self.KEY])
        self.assertEqual(self.clipboard["text"], "a shopping list")

    def test_something_that_is_not_a_key_is_turned_away_at_once(self):
        flow = self.flow()
        self.assertEqual(flow.submit("my password 123"), "invalid")
        self.assertEqual((self.checked, self.saved), ([], []))
        self.assertEqual(flow.state(), "invalid")

    def test_a_refused_key_is_not_saved(self):
        flow = self.flow(verdict="refused", has_key=True)
        flow.submit(self.KEY)
        self.settle(flow)
        self.assertEqual(self.saved, [])
        self.assertEqual(flow.state(), "refused")

    def test_a_key_that_could_not_be_checked_is_saved_anyway(self):
        flow = self.flow(verdict="offline")
        flow.submit(self.KEY)
        self.settle(flow)
        self.assertEqual(self.saved, [self.KEY])
        self.assertEqual(flow.state(), "offline")

    def test_the_key_never_reaches_the_log(self):
        flow = self.flow(clipboard=self.KEY)
        with self.assertLogs("heyspeaky.apikey", level="INFO") as logs:
            flow.submit(self.KEY)
            self.settle(flow)
        said = "\n".join(logs.output)
        self.assertNotIn(self.KEY, said)
        self.assertNotIn(self.KEY[:12], said)

    def test_the_row_under_the_field_opens_the_page_where_keys_are_made(self):
        flow = self.flow()
        flow.open_page()
        self.assertEqual(self.opened, [apikey.KEYS_PAGE])

    def test_the_file_holds_the_key_and_nothing_else(self):
        folder = tempfile.mkdtemp()
        path = os.path.join(folder, "HeySpeaky", "openai.key")
        apikey.save({"transcription": {"cloud": {"api_key_file": path}}},
                    self.KEY + "\n")
        with open(path, "rb") as handle:
            self.assertEqual(handle.read(), self.KEY.encode("ascii"))

    @unittest.skipIf(panel_module is None, "tkinter is missing")
    def test_a_missing_key_comes_first_in_the_panel(self):
        model = _PanelModel().model(key="missing")
        _size, items = panel_module.layout(model, 1.0)
        rows = [item for item in items if item.kind == "row"]
        self.assertEqual(rows[0].key, "key")
        self.assertEqual(rows[0].extra, "accent")
        model = _PanelModel().model(key="saved")
        _size, items = panel_module.layout(model, 1.0)
        rows = [item for item in items if item.kind == "row"]
        self.assertNotEqual(rows[0].key, "key")
        self.assertIn("key", [item.key for item in rows])


@unittest.skipIf(panel_module is None, "tkinter is missing")
class TheKeyPage(_PanelModel, unittest.TestCase):
    """The field the key is pasted into."""

    KEY = AddingTheKeyFromTheTray.KEY

    def page(self, key_text="", **model):
        _size, items = panel_module.layout(self.model(**model), 1.25, "key",
                                           key_text=key_text)
        return dict((item.kind, item) for item in items)

    def panel(self, clipboard):
        import types
        panel = object.__new__(panel_module.TrayPanel)
        self.acts, self.handed = [], []
        panel._page, panel._key_text, panel._query = "key", "", ""
        panel._turn_goal, panel._flare_at, panel._caret_job = 0.0, None, None
        panel._quit_armed_at, panel._closing_at = None, None
        panel._hover_key = None
        panel._refit = lambda: None
        panel._act = self.acts.append
        panel._submit_key = self.handed.append
        panel.window = types.SimpleNamespace(
            after=lambda *_: None, after_cancel=lambda *_: None,
            clipboard_get=lambda: clipboard)
        return panel

    def test_the_key_is_never_shown_whole(self):
        shown = self.page(self.KEY)["keyfield"].label
        self.assertNotIn(self.KEY, shown)
        self.assertTrue(shown.startswith(self.KEY[:7]))
        self.assertTrue(shown.endswith(self.KEY[-4:]))
        self.assertIn("•", shown)

    def test_save_is_ready_only_with_something_to_save(self):
        self.assertFalse(self.page("")["button"].extra)
        self.assertTrue(self.page(self.KEY)["button"].extra)
        self.assertFalse(self.page(self.KEY, key="checking")["button"].extra)

    def test_ctrl_v_pastes_and_enter_hands_it_over_but_not_through_act(self):
        import types
        panel = self.panel(" " + self.KEY + "\r\n")
        panel._key_into_field(types.SimpleNamespace(
            keysym="Cyrillic_em", keycode=0x56, state=0x4, char="\x16"))
        self.assertEqual(panel._key_text, self.KEY)
        panel._key_into_field(types.SimpleNamespace(
            keysym="Return", keycode=0x0D, state=0, char="\r"))
        self.assertEqual(self.handed, [self.KEY])
        self.assertEqual(panel._key_text, "")
        self.assertEqual(self.acts, [])

    def test_escape_empties_the_field_before_it_leaves_the_page(self):
        panel = self.panel("")
        panel._key_text = "sk-something"
        panel._escape()
        self.assertEqual((panel._page, panel._key_text), ("key", ""))
        panel._escape()
        self.assertEqual(panel._page, "main")

    def test_the_page_is_drawn(self):
        size, items = panel_module.layout(self.model(), 1.25, "key",
                                          key_text=self.KEY)
        card = glass.panel_card(size[0], size[1], 1.25)
        frame = glass.panel_frame(card, items, 1.25)
        button = [item for item in items if item.kind == "button"][0]
        middle = frame.getpixel(((button.rect[0] + button.rect[2]) // 2 - 30,
                                 (button.rect[1] + button.rect[3]) // 2))
        self.assertGreater(sum(middle[:3]), 600)        # white, ready


from heyspeaky import localmodels  # noqa: E402


class ChoosingTheModelOnThisLaptop(unittest.TestCase):
    """People choose: bigger hears better, and is slower and heavier."""

    def models(self, have=("base", "small"), fetch_ok=True):
        self.cfg = {"model": {"final": "base", "download_root": None}}
        self.saves, self.chosen, self.fetched = [], [], []
        self.release = threading.Event()
        self.on_disk = set(have)

        def fetch(name):
            self.fetched.append(name)
            self.release.wait(2.0)
            if not fetch_ok:
                raise IOError("no network")
            self.on_disk.add(name)

        return localmodels.LocalModels(
            self.cfg, on_chosen=self.chosen.append,
            save=lambda: self.saves.append(1),
            is_downloaded=lambda name, cache: name in self.on_disk,
            fetch=fetch)

    def wait_for(self, condition):
        deadline = time.monotonic() + 2.0
        while not condition() and time.monotonic() < deadline:
            time.sleep(0.02)

    def test_a_model_on_disk_is_switched_to_at_once(self):
        models = self.models()
        models.choose("small")
        self.assertEqual(self.cfg["model"]["final"], "small")
        self.assertEqual((self.chosen, self.saves, self.fetched),
                         (["small"], [1], []))

    def test_a_model_not_on_disk_is_downloaded_first(self):
        models = self.models()
        models.choose("medium")
        self.wait_for(lambda: self.fetched)
        self.assertEqual(models.state()["busy"], "medium")
        self.assertEqual(self.cfg["model"]["final"], "base")
        self.release.set()
        self.wait_for(lambda: self.chosen)
        self.assertEqual(self.chosen, ["medium"])
        self.assertEqual(self.cfg["model"]["final"], "medium")
        self.assertEqual(models.state()["busy"], "")

    def test_a_failed_download_changes_nothing_and_says_so(self):
        models = self.models(fetch_ok=False)
        models.choose("medium")
        self.release.set()
        self.wait_for(lambda: models.state()["failed"])
        self.assertEqual(models.state()["failed"], "medium")
        self.assertEqual(self.cfg["model"]["final"], "base")
        self.assertEqual(self.chosen, [])

    def test_only_models_it_knows_can_be_chosen(self):
        models = self.models()
        models.choose("../../somewhere")
        self.assertEqual((self.chosen, self.fetched), ([], []))

    def test_every_choice_says_how_big_it_is(self):
        for name, label, megabytes, note in localmodels.MODELS:
            self.assertGreater(megabytes, 10, name)
            self.assertTrue(note, name)
        self.assertEqual(localmodels.size_text(1622), "1.6 GB")
        self.assertEqual(localmodels.size_text(148), "148 MB")

    @unittest.skipIf(panel_module is None, "tkinter is missing")
    def test_the_panel_lists_them_with_what_they_cost(self):
        local = {"current": "base", "have": {"base": True, "small": True},
                 "busy": "medium", "progress": 0.42, "failed": ""}
        model = _PanelModel().model(local=local)
        _size, items = panel_module.layout(model, 1.25, "models")
        rows = dict((item.key, item) for item in items
                    if item.kind == "model")
        self.assertEqual(len(rows), len(localmodels.MODELS))
        self.assertEqual(rows["model:base"].extra, (True, "downloaded"))
        self.assertEqual(rows["model:small"].extra, (False, "downloaded"))
        self.assertEqual(rows["model:medium"].extra, (False,
                                                      "downloading 42%"))
        self.assertEqual(rows["model:large-v3-turbo"].extra, (False,
                                                              "1.6 GB"))
        _size, first = panel_module.layout(model, 1.25)
        row = [item for item in first if item.key == "models"][0]
        self.assertEqual(row.hint, "downloading 42%")


class TheShortcutsHaveAnIcon(unittest.TestCase):
    """The Start menu showed a blank window for HeySpeaky."""

    def test_the_icon_is_a_tile_with_the_waveform(self):
        image = glass.app_icon(64)
        self.assertEqual(image.size, (64, 64))
        self.assertEqual(image.getpixel((0, 0))[3], 0)
        middle = image.getpixel((32, 32))
        self.assertEqual(middle[3], 255)
        self.assertGreater(max(middle[:3]), 150)       # a coloured bar

    def test_the_file_carries_the_small_sizes_windows_asks_for(self):
        from PIL import Image
        path = os.path.join(tempfile.mkdtemp(), "heyspeaky.ico")
        glass.save_app_icon(path)
        with Image.open(path) as image:
            sizes = image.info.get("sizes", set())
        for size in ((16, 16), (32, 32), (48, 48), (256, 256)):
            self.assertIn(size, sizes)


@unittest.skipIf(HotkeyListener is None, "the keyboard package is missing")
class TheLogSaysWhyCtrlAltDidNothing(unittest.TestCase):
    """"I restarted it and Ctrl+Alt did nothing": the log could not say
    whether the keyboard was heard at all."""

    def listener(self):
        listener = HotkeyListener(
            {"engage_delay": 10.0, "tap_max": 0.0, "accept_altgr": False,
             "cancel_on_other_key": True, "double_tap_gap": 0.5,
             "health_check_seconds": 0, "min_reinstall_seconds": 60},
            on_engage=lambda: None, on_tap=lambda: None,
            on_hold_release=lambda: None, on_cancel=lambda: None)
        listener._installed_at = time.monotonic() - 3.0
        return listener

    def test_the_first_key_after_starting_is_noted_once(self):
        listener = self.listener()
        with self.assertLogs("heyspeaky.hotkey", level="INFO") as logs:
            listener._on_key_event(_Event("shift", "down"))
            listener._on_key_event(_Event("shift", "up"))
            listener._on_key_event(_Event("ctrl", "down"))
        said = [line for line in logs.output if "first key" in line]
        self.assertEqual(len(said), 1)

    def test_ctrl_alt_on_top_of_a_held_key_says_so_without_the_letter(self):
        listener = self.listener()
        listener._keys_seen = 5
        with self.assertLogs("heyspeaky.hotkey", level="INFO") as logs:
            listener._on_key_event(_Event("q", "down"))
            listener._on_key_event(_Event("ctrl", "down"))
            listener._on_key_event(_Event("alt", "down"))
        said = "\n".join(logs.output)
        self.assertIn("already held", said)
        self.assertIn("a character key", said)
        self.assertNotIn("'q'", said)
        self.assertNotIn(" q ", said)


def _tool(name):
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        name, str(ROOT / "tools" / (name + ".py")))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TheSessionBrief(unittest.TestCase):
    """What every session used to gather by hand, in twenty lines."""

    LOG = [
        "2026-09-20 10:00:00,000 INFO    heyspeaky          HeySpeaky running",
        "2026-09-25 09:00:00,000 INFO    heyspeaky          HeySpeaky running",
        "2026-09-25 09:01:00,000 INFO    heyspeaky          Final transcript "
        "(cloud): 40 chars",
        "2026-09-25 09:02:00,000 INFO    heyspeaky.output   Selection: 6 chars"
        " from claude.exe (Chrome_WidgetWin_1), 1 try; keys up after 0.20s;"
        " the window answered",
        "2026-09-25 09:03:00,000 INFO    heyspeaky.output   Selection: 0 chars"
        " from Chrome_WidgetWin_1, 2 tries; keys up after 0.14s; the window "
        "never answered",
        "2026-09-25 09:04:00,000 WARNING heyspeaky          Another instance "
        "is already running; exiting",
        "  a traceback line with no stamp",
    ]

    def test_it_counts_only_what_is_recent(self):
        import datetime
        brief = _tool("session_brief")
        facts = brief.summarise(self.LOG, datetime.datetime(2026, 9, 24))
        self.assertEqual(facts["counts"]["starts"], 1)
        self.assertEqual(facts["counts"]["dictations"], 1)
        self.assertEqual(facts["counts"]["second copy refused"], 1)
        self.assertEqual(dict(facts["read"]), {"claude.exe": 1})
        self.assertEqual(dict(facts["empty"]), {"Chrome_WidgetWin_1": 1})
        self.assertEqual(len(facts["warnings"]), 1)

    def test_line_endings_alone_are_not_a_difference(self):
        brief = _tool("session_brief")
        here, there = Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp())
        (here / "a.py").write_bytes(b"x = 1\ny = 2\n")
        (there / "a.py").write_bytes(b"x = 1\r\ny = 2\r\n")
        (here / "b.py").write_bytes(b"x = 1\n")
        (there / "b.py").write_bytes(b"x = 2\n")
        (here / "c.py").write_bytes(b"new\n")
        self.assertEqual(brief.drift(here, there, ["a.py", "b.py", "c.py"]),
                         (["b.py"], ["c.py"]))


class TheCommitCheckGuardsTheInstaller(unittest.TestCase):
    """install.ps1 is how everyone updates: a broken one breaks everyone."""

    @unittest.skipUnless(sys.platform == "win32", "needs PowerShell")
    def test_a_script_that_is_not_ascii_or_does_not_parse_is_stopped(self):
        precommit = _tool("precommit")
        folder = Path(tempfile.mkdtemp())
        (folder / "fine.ps1").write_text("Write-Host 'hello'\n")
        (folder / "cyrillic.ps1").write_text(
            "Write-Host 'привет'\n", encoding="utf-8")
        (folder / "broken.ps1").write_text("function f { if (\n")
        self.assertEqual(precommit.script_problems(folder / "fine.ps1"), [])
        self.assertIn("ASCII", precommit.script_problems(
            folder / "cyrillic.ps1")[0])
        self.assertIn("does not parse", precommit.script_problems(
            folder / "broken.ps1")[0])

    @unittest.skipUnless(sys.platform == "win32", "needs PowerShell")
    def test_the_real_installers_pass(self):
        precommit = _tool("precommit")
        for name in ("install.ps1", "uninstall.ps1"):
            self.assertEqual(precommit.script_problems(ROOT / name), [], name)


class TheMonoLook(unittest.TestCase):
    """The second look, from the reel the owner sent: a black capsule,
    eight bars, red listening, blue thinking, gone when the words land."""

    def test_the_capsule_has_the_reel_s_proportions(self):
        mono = glass.mono_prepare(1.0)
        left, top, right, bottom = mono.box
        self.assertEqual((right - left, bottom - top), (108, 58))
        self.assertAlmostEqual((right - left) / float(bottom - top), 1.86,
                               places=1)

    def vivid_runs(self, frame, y):
        runs, inside = 0, False
        for x in range(frame.size[0]):
            r, g, b, a = frame.getpixel((x, y))
            vivid = a > 200 and max(r, g, b) - min(r, g, b) > 90
            if vivid and not inside:
                runs += 1
            inside = vivid
        return runs

    def test_eight_bars_red_while_listening_blue_while_thinking(self):
        mono = glass.mono_prepare(2.0)
        middle = (mono.box[1] + mono.box[3]) // 2
        heard = glass.mono_paint(mono, "listening", 0.8, 0.3)
        thinking = glass.mono_paint(mono, "transcribing", 0.0, 0.3)
        self.assertEqual(self.vivid_runs(heard, middle), 8)
        self.assertEqual(self.vivid_runs(thinking, middle), 8)
        red = [heard.getpixel((x, middle)) for x in range(heard.size[0])]
        red = max(red, key=lambda p: p[0] - p[2])
        blue = [thinking.getpixel((x, middle))
                for x in range(thinking.size[0])]
        blue = max(blue, key=lambda p: p[2] - p[0])
        self.assertGreater(red[0], red[2] + 100)
        self.assertGreater(blue[2], blue[0] + 100)
        self.assertEqual(heard.getpixel((0, 0))[3], 0)
        inside = heard.getpixel((mono.box[0] + 8, middle))
        self.assertEqual(inside[:3], theme.MONO_FILL)
        self.assertEqual(inside[3], 255)

    def test_quiet_bars_are_short_but_never_dots(self):
        quiet = glass.mono_heights("listening", 0.0, 1.0)
        loud = glass.mono_heights("listening", 1.0, 1.0)
        self.assertLess(max(quiet), 0.3)
        self.assertGreater(theme.MONO_BAR_MIN, theme.MONO_BAR_WIDTH * 2)
        middle = len(loud) // 2
        self.assertGreater(loud[middle] + loud[middle - 1],
                           loud[0] + loud[-1] + 0.8)

    def test_it_shrinks_while_black_and_is_gone_at_the_end(self):
        mono = glass.mono_prepare(1.0)
        centre = ((mono.box[0] + mono.box[2]) // 2 - 30,
                  (mono.box[1] + mono.box[3]) // 2)
        half = glass.mono_paint(mono, "done", 0.0, 0.5, collapse=0.5)
        self.assertEqual(half.getpixel(centre)[3], 255)
        self.assertEqual(half.getpixel((mono.box[0] + 2, centre[1]))[3], 0)
        gone = glass.mono_paint(mono, "done", 0.0, 0.5, collapse=1.0)
        self.assertIsNone(gone.getchannel("A").getbbox())

    def test_a_message_widens_the_capsule(self):
        plain = glass.mono_prepare(1.0)
        said = glass.mono_prepare(1.0, "Loading speech models, one moment")
        self.assertGreater(said.box[2] - said.box[0],
                           plain.box[2] - plain.box[0])
        self.assertLessEqual(said.box[2], said.window[0])

    def test_the_glass_pill_is_untouched(self):
        """The mono look is added beside the glass, not over it."""
        pill = glass.render("listening", levels=[0.5] * theme.BARS)
        self.assertEqual(pill.size, (theme.WIDTH, theme.HEIGHT
                                     + 2 * theme.SHADOW_MARGIN))


class TheMonoSound(unittest.TestCase):
    """The reel's sound, rebuilt from numbers measured off it."""

    def test_two_notes_a_fourth_apart(self):
        from heyspeaky import sound
        pitches = sorted(set(round(tone[0]) for tone
                             in sound.VOICES["blip"]["tones"]))
        self.assertEqual(pitches, [500, 669, 670, 671])
        self.assertAlmostEqual(669 / 500.0, 4 / 3.0, places=1)

    def test_the_sound_follows_the_look_unless_one_was_chosen(self):
        from heyspeaky import sound
        self.assertEqual(sound.for_look("auto", "mono"), "blip")
        self.assertEqual(sound.for_look("auto", "glass"), "drip")
        self.assertEqual(sound.for_look("bowl", "mono"), "bowl")
        self.assertEqual(sound.for_look("none", "mono"), "none")

    def test_the_old_default_is_carried_forward(self):
        stored = {"sound": {"finish": "drip"}}
        config_module._migrate(stored)
        self.assertEqual(stored["sound"]["finish"], "auto")
        chosen = {"sound": {"finish": "bowl"}}
        config_module._migrate(chosen)
        self.assertEqual(chosen["sound"]["finish"], "bowl")


@unittest.skipIf(panel_module is None, "tkinter is missing")
class ChoosingTheLook(_PanelModel, unittest.TestCase):
    """Glass or mono, from the tray panel."""

    def look(self, **model):
        _size, items = panel_module.layout(self.model(**model), 1.25)
        return [item for item in items if item.key == "look"][0]

    def test_the_switch_shows_the_look_in_use(self):
        self.assertEqual(self.look().extra[1], 0)
        self.assertEqual(self.look(look="mono").extra[1], 1)

    def test_each_half_of_the_switch_chooses_its_look(self):
        _size, items = panel_module.layout(self.model(), 1.25)
        switch = [item for item in items if item.key == "look"][0]
        left, top, right, bottom = switch.rect
        middle = (top + bottom) // 2
        self.assertEqual(panel_module.hit(items, left + 4, middle)[1],
                         "look:glass")
        self.assertEqual(panel_module.hit(items, right - 4, middle)[1],
                         "look:mono")
        backend = [item for item in items if item.key == "backend"][0]
        self.assertEqual(panel_module.hit(items, backend.rect[2] - 4,
                                          middle - top + backend.rect[1])[1],
                         "backend:local")


@unittest.skipIf(panel_module is None, "tkinter is missing")
class MonoAppearsAtThePointer(unittest.TestCase):
    """In the reel the pill appears just above the mouse pointer, and stays
    where it appeared."""

    def overlay(self, anchor):
        import types
        from heyspeaky import overlay as overlay_module
        real = overlay_module._cursor_work_area
        self.addCleanup(setattr, overlay_module, "_cursor_work_area", real)
        overlay_module._cursor_work_area = lambda: (0, 0, 1920, 1040)
        pill = object.__new__(overlay_module.Overlay)
        pill._scale, pill._anchor = 1.0, anchor
        pill._cfg = {"style": "mono", "margin_bottom": 14}
        pill._root = types.SimpleNamespace(geometry=lambda text: None)
        return pill

    def test_just_above_the_pointer(self):
        pill = self.overlay((500, 500))
        pill._place()
        x, y, width, height = pill._geometry
        margin = theme.MONO_MARGIN
        self.assertEqual(x + width / 2.0, 500 + theme.MONO_POINTER_RIGHT)
        self.assertEqual(y + height - margin, 500 - theme.MONO_POINTER_ABOVE)

    def test_below_it_when_there_is_no_room_above(self):
        pill = self.overlay((500, 20))
        pill._place()
        _x, y, _width, _height = pill._geometry
        self.assertGreater(y + theme.MONO_MARGIN, 20)


@unittest.skipIf(panel_module is None, "tkinter is missing")
class EverythingChangesWithTheLook(_PanelModel, unittest.TestCase):
    """The owner liked mono and asked for the whole panel to change with it,
    and the correction box too - not the pill alone."""

    SOLID_BLACK = tuple(theme.MONO_FILL) + (255,)

    def centre(self, card):
        box = card[1]
        return card[0].getpixel(((box[0] + box[2]) // 2,
                                 (box[1] + box[3]) // 2))

    def test_the_mono_card_is_the_capsule_s_solid_black(self):
        size, _items = panel_module.layout(self.model(look="mono"), 1.25)
        card = glass.panel_card(size[0], size[1], 1.25, mono=True)
        self.assertEqual(self.centre(card), self.SOLID_BLACK)

    def test_the_open_panel_turns_black_when_the_look_changes(self):
        """Choosing Mono in the panel turns the panel itself, there and
        then: the card is made again when the look changes, not only when
        the size does."""
        panel = object.__new__(panel_module.TrayPanel)
        panel._model = self.model()
        panel.scale = 1.25
        panel._page, panel._scroll, panel._query = "main", 0, ""
        panel._key_text, panel._quit_armed_at = "", None
        panel._card = panel._card_look = None
        panel._motion = {}
        panel._relayout()
        self.assertNotEqual(self.centre(panel._card), self.SOLID_BLACK)
        panel._model = self.model(look="mono")
        panel._relayout()
        self.assertEqual(self.centre(panel._card), self.SOLID_BLACK)

    def test_a_switch_that_is_on_is_the_thinking_blue(self):
        size, items = panel_module.layout(
            self.model(look="mono", paused=True), 1.25)
        card = glass.panel_card(size[0], size[1], 1.25, mono=True)
        frame = glass.panel_frame(card, items, 1.25, mono=True)
        pause = [item for item in items if item.kind == "switch"][0]
        width = int(round(theme.SWITCH_WIDTH * 1.25))
        height = int(round(theme.SWITCH_HEIGHT * 1.25))
        # The middle of the track's left end: the knob is over on the right.
        x = pause.rect[2] - int(round(10 * 1.25)) - width + height // 2
        y = (pause.rect[1] + pause.rect[3]) // 2
        self.assertEqual(frame.getpixel((x, y))[:3], tuple(theme.MONO_ACCENT))

    def test_the_typing_widget_lands_on_the_mono_field_colour(self):
        """The widget over the field is a flat window of `field_fill`; the
        focus ring must not reach under it, at any strength."""
        self.assertEqual(glass.field_fill(True), theme.MONO_FIELD)
        for scale in (1.0, 1.25, 1.5, 2.0):
            composer = glass.composer(scale, mono=True)
            entry = composer.layout["entry"]
            for strength in (0.0, 0.72, 1.0):
                frame = glass.composer_frame(composer, strength=strength)
                self.assertEqual(set(frame.crop(entry).getdata()),
                                 {tuple(theme.MONO_FIELD) + (255,)},
                                 "at scale %s" % scale)


if __name__ == "__main__":
    unittest.main(verbosity=2)

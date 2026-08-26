import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call, mock_open, patch

import i18n
import desktop_cat
from i18n import LANGUAGE_AUTO, LANGUAGE_EN
from personality import CUSTOM_PERSONALITY, DEFAULT_PERSONALITY


class DesktopCatTests(unittest.TestCase):
    def test_new_cat_alert_uses_the_theme_the_user_is_running(self):
        alert = Mock()
        alert_class = Mock()
        alert_class.alloc.return_value.init.return_value = alert
        icon = Mock()
        image_class = Mock()
        image_class.alloc.return_value.initWithContentsOfFile_.return_value = icon

        with (
            patch.object(desktop_cat, "NSAlert", alert_class),
            patch.object(desktop_cat, "NSImage", image_class),
        ):
            created = desktop_cat.new_cat_alert()

        self.assertIs(created, alert)
        image_class.alloc.return_value.initWithContentsOfFile_.assert_called_once_with(
            desktop_cat.alert_icon_path()
        )
        alert.setIcon_.assert_called_once_with(icon)

    def test_new_cat_alert_still_returns_alert_when_icon_loading_fails(self):
        alert = Mock()
        alert_class = Mock()
        alert_class.alloc.return_value.init.return_value = alert
        image_class = Mock()
        image_class.alloc.return_value.initWithContentsOfFile_.side_effect = OSError(
            "missing icon"
        )

        with (
            patch.object(desktop_cat, "NSAlert", alert_class),
            patch.object(desktop_cat, "NSImage", image_class),
        ):
            created = desktop_cat.new_cat_alert()

        self.assertIs(created, alert)
        alert.setIcon_.assert_not_called()

    def test_config_env_override_is_used_for_default_reads_and_writes(self):
        override = "/tmp/memory-cat-demo-config.json"
        opened = mock_open(read_data='{"theme": "simple"}')
        with (
            patch.dict(
                "os.environ", {"MEMORY_CAT_CONFIG": override}, clear=False
            ),
            patch("builtins.open", opened),
        ):
            loaded = desktop_cat.load_config()
            self.assertTrue(desktop_cat.save_config(loaded))

        self.assertEqual(loaded["theme"], "simple")
        self.assertEqual(
            opened.call_args_list,
            [
                call(override, encoding="utf-8"),
                call(override, "w", encoding="utf-8"),
            ],
        )

    def test_config_defaults_to_existing_path_when_override_is_unset(self):
        opened = mock_open(read_data="{}")
        with (
            patch.dict("os.environ", {}, clear=True),
            patch.object(desktop_cat, "CONFIG", "/tmp/default-config.json"),
            patch("builtins.open", opened),
        ):
            desktop_cat.load_config()

        opened.assert_called_once_with(
            "/tmp/default-config.json", encoding="utf-8"
        )

    def test_empty_config_override_is_ignored(self):
        opened = mock_open()
        with (
            patch.dict(
                "os.environ", {"MEMORY_CAT_CONFIG": ""}, clear=False
            ),
            patch.object(desktop_cat, "CONFIG", "/tmp/default-config.json"),
            patch("builtins.open", opened),
        ):
            self.assertTrue(desktop_cat.save_config(desktop_cat.DEFAULT))

        opened.assert_called_once_with(
            "/tmp/default-config.json", "w", encoding="utf-8"
        )

    def test_disk_full_prompt_fires_once_per_session_at_92_percent(self):
        controller = desktop_cat.CatController.alloc().init()
        controller._disk_full_prompt_shown = False
        controller._show_disk_full_prompt = Mock()
        controller.diagnose_ = Mock()

        self.assertFalse(controller._maybe_prompt_disk_full(91.9))
        self.assertTrue(controller._maybe_prompt_disk_full(92.0))
        self.assertFalse(controller._maybe_prompt_disk_full(99.0))

        controller._show_disk_full_prompt.assert_called_once_with()
        controller.diagnose_.assert_not_called()

    def test_clicking_disk_full_notification_starts_existing_diagnosis_flow(self):
        controller = desktop_cat.CatController.alloc().init()
        controller.diagnose_ = Mock()
        center = Mock()
        notification = Mock()
        notification.userInfo.return_value = {
            "memory_cat_action": "diagnose"
        }

        controller.userNotificationCenter_didActivateNotification_(
            center, notification
        )

        center.removeDeliveredNotification_.assert_called_once_with(notification)
        controller.diagnose_.assert_called_once_with(None)

    def test_next_pet_theme_name_increments_existing_theme_folders(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            frames_dir = Path(temp_dir)
            self.assertEqual(
                desktop_cat.next_pet_theme_name(frames_dir), "mypet"
            )
            (frames_dir / "mypet").mkdir()
            self.assertEqual(
                desktop_cat.next_pet_theme_name(frames_dir), "mypet2"
            )
            (frames_dir / "mypet2").mkdir()
            self.assertEqual(
                desktop_cat.next_pet_theme_name(frames_dir), "mypet3"
            )

    def test_next_pet_theme_name_avoids_names_taken_in_either_root(self):
        # 번들에 mypet 이 있는데 사용자 폴더가 비었다고 mypet 을 다시 쓰면
        # 기본 테마를 가려 버린다. 두 폴더를 모두 봐야 한다.
        with tempfile.TemporaryDirectory() as temp_dir:
            bundled = Path(temp_dir) / "bundled"
            user = Path(temp_dir) / "user"
            bundled.mkdir()
            user.mkdir()
            (bundled / "mypet").mkdir()
            with (
                patch.object(desktop_cat, "FRAMES_BASE", str(bundled)),
                patch.object(desktop_cat, "USER_FRAMES_BASE", str(user)),
            ):
                self.assertEqual(desktop_cat.next_pet_theme_name(), "mypet2")

    def test_discover_themes_merges_bundled_and_user_folders(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            bundled = Path(temp_dir) / "bundled"
            user = Path(temp_dir) / "user"
            for root, names in ((bundled, ("cute", "simple")), (user, ("mypet3",))):
                for name in names:
                    theme = root / name
                    theme.mkdir(parents=True)
                    (theme / "cat_00.png").write_bytes(b"png")
            with (
                patch.object(desktop_cat, "FRAMES_BASE", str(bundled)),
                patch.object(desktop_cat, "USER_FRAMES_BASE", str(user)),
            ):
                self.assertEqual(
                    desktop_cat.discover_themes(), ["cute", "simple", "mypet3"]
                )

    def test_discover_themes_lists_a_shadowing_user_theme_only_once(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            bundled = Path(temp_dir) / "bundled"
            user = Path(temp_dir) / "user"
            for root in (bundled, user):
                theme = root / "cute"
                theme.mkdir(parents=True)
                (theme / "cat_00.png").write_bytes(b"png")
            with (
                patch.object(desktop_cat, "FRAMES_BASE", str(bundled)),
                patch.object(desktop_cat, "USER_FRAMES_BASE", str(user)),
            ):
                self.assertEqual(desktop_cat.discover_themes(), ["cute"])
                # 같은 이름이면 사용자가 만든 쪽을 쓴다.
                self.assertEqual(
                    desktop_cat.frame_path("cute", 0),
                    str(user / "cute" / "cat_00.png"),
                )

    def test_frame_path_reads_a_user_theme_from_the_user_folder(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            bundled = Path(temp_dir) / "bundled"
            user = Path(temp_dir) / "user"
            bundled.mkdir()
            theme = user / "mypet3"
            theme.mkdir(parents=True)
            for index in range(3):
                (theme / f"cat_{index:02d}.png").write_bytes(b"png")
            with (
                patch.object(desktop_cat, "FRAMES_BASE", str(bundled)),
                patch.object(desktop_cat, "USER_FRAMES_BASE", str(user)),
            ):
                self.assertEqual(desktop_cat.frame_count("mypet3"), 3)
                self.assertEqual(
                    desktop_cat.frame_path("mypet3", 9),
                    str(theme / "cat_02.png"),
                )

    def test_save_config_creates_the_user_data_folder(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "Application Support" / "Memory Cat" / "config.json"
            self.assertTrue(desktop_cat.save_config({"theme": "cute"}, str(target)))
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")),
                             {"theme": "cute"})

    def test_pet_theme_worker_returns_build_result_on_main_queue(self):
        callback = Mock()
        queue = Mock()
        queue.addOperationWithBlock_.side_effect = lambda block: block()
        queue_provider = Mock()
        queue_provider.mainQueue.return_value = queue
        generated = {"detected_stages": 6, "output_path": "/frames/mypet"}
        with (
            patch.object(
                desktop_cat, "build_pet_theme", return_value=generated
            ) as build,
            patch.object(desktop_cat, "NSOperationQueue", queue_provider),
        ):
            desktop_cat._pet_theme_worker(
                "/photos/pet.jpg", "mypet", callback
            )

        build.assert_called_once_with("/photos/pet.jpg", "mypet", "medium")
        queue.addOperationWithBlock_.assert_called_once()
        callback.assert_called_once_with(
            {
                "theme_name": "mypet",
                "detected_stages": 6,
                "output_path": "/frames/mypet",
            }
        )

    def test_pet_theme_worker_returns_readable_generation_error(self):
        callback = Mock()
        queue = Mock()
        queue.addOperationWithBlock_.side_effect = lambda block: block()
        queue_provider = Mock()
        queue_provider.mainQueue.return_value = queue
        with (
            patch.object(
                desktop_cat,
                "build_pet_theme",
                side_effect=desktop_cat.ThemeGenerationError("API request failed"),
            ),
            patch.object(desktop_cat, "NSOperationQueue", queue_provider),
        ):
            desktop_cat._pet_theme_worker("/photos/pet.jpg", "mypet", callback)

        callback.assert_called_once_with(
            {"theme_name": "mypet", "error": "API request failed"}
        )

    def test_finishing_pet_theme_applies_and_saves_it_immediately(self):
        controller = desktop_cat.CatController.alloc().init()
        controller.cfg = dict(desktop_cat.DEFAULT)
        controller.language = "ko"
        controller._pet_theme_running = True
        controller._notify = Mock(return_value=True)
        controller.refresh_ = Mock()

        with patch.object(desktop_cat, "save_config", return_value=True) as save:
            controller._finish_pet_theme(
                {
                    "theme_name": "mypet2",
                    "detected_stages": 6,
                    "output_path": "/frames/mypet2",
                }
            )

        self.assertFalse(controller._pet_theme_running)
        self.assertEqual(controller.cfg["theme"], "mypet2")
        save.assert_called_once_with(controller.cfg)
        controller.refresh_.assert_called_once_with(None)
        controller._notify.assert_called_once_with(
            "반려동물 테마 완성",
            "6단계를 감지해 mypet2 테마를 바로 적용했어요.",
        )

    def test_old_config_gets_default_personality(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.json"
            path.write_text(
                json.dumps({"theme": "cute", "size": "작게"}), encoding="utf-8"
            )
            config = desktop_cat.load_config(path)

        self.assertEqual(config["personality"], DEFAULT_PERSONALITY)
        self.assertEqual(config["custom_personality"], "")
        self.assertEqual(config["language"], LANGUAGE_AUTO)

    def test_language_override_round_trips_through_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.json"
            config = dict(desktop_cat.DEFAULT, language=LANGUAGE_EN)
            self.assertTrue(desktop_cat.save_config(config, path))
            loaded = desktop_cat.load_config(path)

        self.assertEqual(loaded["language"], LANGUAGE_EN)
        self.assertEqual(desktop_cat.theme_label("cute", LANGUAGE_EN), "Cute")
        self.assertEqual(desktop_cat.size_label("보통", LANGUAGE_EN), "Medium")

    def test_custom_personality_round_trips_through_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.json"
            config = dict(desktop_cat.DEFAULT)
            config["personality"] = CUSTOM_PERSONALITY
            config["custom_personality"] = "차분하게 숫자부터 말해줘"
            self.assertTrue(desktop_cat.save_config(config, path))
            loaded = desktop_cat.load_config(path)

        self.assertEqual(loaded["personality"], CUSTOM_PERSONALITY)
        self.assertEqual(loaded["custom_personality"], "차분하게 숫자부터 말해줘")

    def test_diagnose_action_starts_daemon_background_thread(self):
        controller = desktop_cat.CatController.alloc().init()
        controller.cfg = dict(desktop_cat.DEFAULT)
        controller._diagnosis_running = False
        controller._diagnosis_thread = None
        controller.language = LANGUAGE_EN
        controller._notify = Mock(return_value=True)
        thread = Mock()
        with patch.object(desktop_cat.threading, "Thread", return_value=thread) as ctor:
            controller.diagnose_(None)

        self.assertTrue(controller._diagnosis_running)
        ctor.assert_called_once()
        kwargs = ctor.call_args.kwargs
        self.assertIs(kwargs["target"], desktop_cat._diagnosis_worker)
        self.assertTrue(kwargs["daemon"])
        self.assertEqual(kwargs["name"], "memory-cat-diagnosis")
        self.assertEqual(
            controller._active_diagnosis_context,
            {
                "personality": DEFAULT_PERSONALITY,
                "personality_label": "Warm Auntie Cat",
                "language": LANGUAGE_EN,
            },
        )
        thread.start.assert_called_once_with()

    def test_worker_dispatches_result_on_main_queue(self):
        result = {
            "why_slow": ["디스크가 찼습니다."],
            "one_line_advice": "캐시부터 확인하세요.",
            "cleanup_recommendations": [],
        }
        callback = Mock()
        queue = Mock()
        queue.addOperationWithBlock_.side_effect = lambda block: block()
        queue_provider = Mock()
        queue_provider.mainQueue.return_value = queue
        with (
            patch.object(desktop_cat, "run_diagnosis", return_value=result) as diagnose,
            patch.object(desktop_cat, "NSOperationQueue", queue_provider),
        ):
            desktop_cat._diagnosis_worker(
                "무뚝뚝한 무사냥", "", LANGUAGE_EN, callback
            )

        diagnose.assert_called_once_with(
            personality="무뚝뚝한 무사냥",
            custom_personality="",
            language=LANGUAGE_EN,
        )
        queue.addOperationWithBlock_.assert_called_once()
        callback.assert_called_once_with(result)

    def test_worker_error_is_safe_offline_result_with_reason(self):
        callback = Mock()
        queue = Mock()
        queue.addOperationWithBlock_.side_effect = lambda block: block()
        queue_provider = Mock()
        queue_provider.mainQueue.return_value = queue
        with (
            patch.object(desktop_cat, "run_diagnosis", side_effect=RuntimeError("secret detail")),
            patch.object(desktop_cat, "NSOperationQueue", queue_provider),
        ):
            desktop_cat._diagnosis_worker("따뜻한 이모니냥", "", "ko", callback)

        result = callback.call_args.args[0]
        self.assertEqual(result["source"], "fallback")
        self.assertEqual(result["fallback_reason"], "worker_error")
        self.assertNotIn("secret detail", str(result))

    def test_notification_contains_causes_and_one_line_advice(self):
        text = desktop_cat.diagnosis_notification_text(
            {
                "why_slow": ["디스크가 찼습니다.", "RAM 압박이 높습니다."],
                "one_line_advice": "오래된 다운로드부터 확인하세요.",
            }
        )
        self.assertIn("디스크가 찼습니다.", text)
        self.assertIn("RAM 압박이 높습니다.", text)
        self.assertIn("오래된 다운로드부터 확인하세요.", text)

    def test_result_content_separates_causes_advice_source_and_reclaimable_size(self):
        content = desktop_cat.diagnosis_result_content(
            {
                "source": "openai",
                "why_slow": ["디스크가 많이 찼습니다.", "스왑 사용량이 높습니다."],
                "one_line_advice": "브라우저 캐시부터 살펴보세요.",
                "estimated_reclaimable": "2.5 GB",
                "cleanup_recommendations": [],
            },
            personality_label="따뜻함",
            language="ko",
        )

        self.assertEqual(content["title"], "따뜻한 뚱냥이가 배부른 이유예요.")
        self.assertNotIn("AI 진단", content["body"])
        self.assertNotIn("성격:", content["body"])
        self.assertNotIn("배부른 이유", content["body"])
        self.assertIn("• 디스크가 많이 찼습니다.", content["body"])
        self.assertIn("🐾 한 문장 조언", content["body"])
        self.assertIn("브라우저 캐시부터 살펴보세요.", content["body"])
        self.assertIn("예상 확보 용량: 2.5 GB", content["body"])
        self.assertFalse(content["can_review_cleanup"])

        english = desktop_cat.diagnosis_result_content(
            {
                "source": "openai",
                "why_slow": ["Disk usage is high."],
                "one_line_advice": "Review old downloads first.",
                "estimated_reclaimable": "2.5 GB",
                "cleanup_recommendations": [],
            },
            personality_label="Sassy Butler Cat",
            language="en",
        )
        self.assertEqual(
            english["title"],
            "Here’s why your sassy Memory Cat feels full.",
        )
        self.assertNotIn("AI diagnosis", english["body"])
        self.assertNotIn("Why so full?", english["body"])

    def test_each_personality_has_a_natural_combined_diagnosis_title(self):
        result = {
            "source": "openai",
            "why_slow": ["원인"],
            "one_line_advice": "조언",
            "cleanup_recommendations": [],
        }
        expected = {
            "냉소적": "냉소적인 뚱냥이가 배부른 이유예요.",
            "따뜻함": "따뜻한 뚱냥이가 배부른 이유예요.",
            "무뚝뚝": "무뚝뚝한 뚱냥이가 배부른 이유예요.",
        }

        for label, title in expected.items():
            with self.subTest(label=label):
                self.assertEqual(
                    desktop_cat.diagnosis_result_content(
                        result, personality_label=label, language="ko"
                    )["title"],
                    title,
                )

        english_expected = {
            "Sassy Butler Cat": "Here’s why your sassy Memory Cat feels full.",
            "Warm Auntie Cat": "Here’s why your warm Memory Cat feels full.",
            "Stoic Samurai Cat": "Here’s why your stoic Memory Cat feels full.",
        }
        for label, title in english_expected.items():
            with self.subTest(label=label):
                self.assertEqual(
                    desktop_cat.diagnosis_result_content(
                        result, personality_label=label, language="en"
                    )["title"],
                    title,
                )

    def test_fallback_result_says_personality_was_not_applied(self):
        content = desktop_cat.diagnosis_result_content(
            {
                "source": "fallback",
                "fallback_reason": "api_error",
                "why_slow": ["디스크 사용률이 높습니다."],
                "one_line_advice": "캐시부터 확인하세요.",
                "estimated_reclaimable": "1.0 GB",
                "cleanup_recommendations": [],
            },
            personality_label="냉소적",
            language="ko",
        )

        self.assertIn("오프라인 진단 · 성격 미적용 · API 연결 실패", content["body"])
        self.assertNotIn("성격: 냉소적", content["body"])
        self.assertEqual(content["title"], "뚱냥이가 배부른 이유예요.")

    def test_result_alert_returns_review_choice_and_renders_advice(self):
        controller = desktop_cat.CatController.alloc().init()
        alert = Mock()
        alert.runModal.return_value = desktop_cat.NSAlertSecondButtonReturn
        alert_class = Mock()
        alert_class.alloc.return_value.init.return_value = alert
        result = {
            "source": "openai",
            "why_slow": ["디스크가 많이 찼습니다."],
            "one_line_advice": "캐시부터 살펴보세요.",
            "estimated_reclaimable": "2.5 GB",
            "cleanup_recommendations": [
                {"category": "browser_cache", "items": [{"path": "/cache"}]}
            ],
        }
        context = {"personality_label": "따뜻함", "language": "ko"}

        with (
            patch.object(desktop_cat, "NSAlert", alert_class),
            patch.object(desktop_cat, "NSApp", Mock()),
        ):
            wants_cleanup = controller._show_diagnosis_result(
                result, context, allow_cleanup=True
            )

        self.assertTrue(wants_cleanup)
        alert.setMessageText_.assert_called_once_with(
            "따뜻한 뚱냥이가 배부른 이유예요."
        )
        self.assertIn("🐾 한 문장 조언", alert.setInformativeText_.call_args.args[0])
        self.assertIn("캐시부터 살펴보세요.", alert.setInformativeText_.call_args.args[0])
        self.assertEqual(
            [call.args[0] for call in alert.addButtonWithTitle_.call_args_list],
            ["닫기", "정리 후보 검토"],
        )

    def test_context_menu_reaches_appkit_popup_with_automatic_language(self):
        controller = desktop_cat.CatController.alloc().init()
        controller.cfg = dict(desktop_cat.DEFAULT)
        controller.language = LANGUAGE_EN
        controller.detail = ["Disk 50%"]
        controller._diagnosis_running = False
        controller.view = Mock()

        menu_class = Mock()
        menus = []

        def new_menu():
            menu = Mock()
            menus.append(menu)
            return menu

        menu_class.alloc.return_value.init.side_effect = new_menu
        item_class = Mock()
        item_class.alloc.return_value.initWithTitle_action_keyEquivalent_.side_effect = (
            lambda title, action, key: Mock(title=title)
        )
        item_class.separatorItem.side_effect = lambda: Mock(title="separator")
        event = Mock()

        with (
            patch.object(desktop_cat, "NSMenu", menu_class),
            patch.object(desktop_cat, "NSMenuItem", item_class),
            patch.object(desktop_cat, "discover_themes", return_value=["cute"]),
        ):
            controller.popUpMenu_(event)

        menu_class.popUpContextMenu_withEvent_forView_.assert_called_once_with(
            menus[0], event, controller.view
        )

        menu_calls = (
            item_class.alloc.return_value.initWithTitle_action_keyEquivalent_.call_args_list
        )
        self.assertIn(
            ("Make a theme from my pet…", b"makePetTheme:"),
            [(call.args[0], call.args[1]) for call in menu_calls],
        )

    def test_finishing_diagnosis_stores_start_context_and_close_skips_cleanup(self):
        controller = desktop_cat.CatController.alloc().init()
        controller.language = "en"
        controller._diagnosis_running = True
        controller._active_diagnosis_context = {
            "personality": "냉소적 집사냥",
            "personality_label": "냉소적",
            "language": "ko",
        }
        controller._notify = Mock(return_value=True)
        controller._show_diagnosis_result = Mock(return_value=False)
        controller._confirm_cleanup_review = Mock(return_value=False)
        result = {
            "source": "openai",
            "why_slow": ["디스크가 많이 찼습니다."],
            "one_line_advice": "캐시부터 살펴보세요.",
            "cleanup_recommendations": [
                {"category": "browser_cache", "items": [{"path": "/cache"}]}
            ],
        }

        controller._finish_diagnosis(result)

        self.assertFalse(controller._diagnosis_running)
        self.assertEqual(controller._last_diagnosis, result)
        self.assertEqual(
            controller._last_diagnosis_context["personality_label"], "냉소적"
        )
        controller._notify.assert_called_once_with(
            "냉소적인 뚱냥이가 배부른 이유예요.",
            "• 디스크가 많이 찼습니다.\n🐾 캐시부터 살펴보세요.",
        )
        controller._show_diagnosis_result.assert_called_once_with(
            result, controller._last_diagnosis_context, allow_cleanup=True
        )
        controller._confirm_cleanup_review.assert_not_called()

    def test_cleanup_flow_starts_only_after_result_review_is_selected(self):
        controller = desktop_cat.CatController.alloc().init()
        controller.language = "ko"
        controller._diagnosis_running = True
        controller._active_diagnosis_context = {
            "personality": "따뜻한 이모니냥",
            "personality_label": "따뜻함",
            "language": "ko",
        }
        controller._notify = Mock(return_value=True)
        controller._show_diagnosis_result = Mock(return_value=True)
        controller._confirm_cleanup_review = Mock(return_value=True)
        controller._confirm_cleanup_item = Mock(return_value=False)
        controller._show_cleanup_summary = Mock()
        recommendations = [
            {"category": "browser_cache", "items": [{"path": "/cache"}]}
        ]
        result = {
            "source": "openai",
            "why_slow": ["디스크가 많이 찼습니다."],
            "one_line_advice": "캐시부터 살펴보세요.",
            "cleanup_recommendations": recommendations,
        }
        summary = {"moved": 0, "already_in_trash": 0, "skipped": 1, "failed": 0}

        with patch.object(
            desktop_cat, "process_cleanup_recommendations", return_value=summary
        ) as cleanup:
            controller._finish_diagnosis(result)

        controller._confirm_cleanup_review.assert_called_once_with(recommendations)
        self.assertEqual(cleanup.call_args.args[0], recommendations)
        controller._show_cleanup_summary.assert_called_once_with(summary)

    def test_completed_diagnosis_adds_check_again_and_view_last_menu_items(self):
        controller = desktop_cat.CatController.alloc().init()
        controller.cfg = dict(desktop_cat.DEFAULT)
        controller.language = "ko"
        controller.detail = []
        controller._diagnosis_running = False
        controller._last_diagnosis = {"source": "openai"}
        controller._last_diagnosis_context = {
            "personality_label": "따뜻함",
            "language": "ko",
        }
        controller.view = Mock()
        menu_class = Mock()
        menu_class.alloc.return_value.init.return_value = Mock()
        item_class = Mock()
        item_class.alloc.return_value.initWithTitle_action_keyEquivalent_.side_effect = (
            lambda title, action, key: Mock(title=title, action=action)
        )
        item_class.separatorItem.side_effect = lambda: Mock(title="separator")

        with (
            patch.object(desktop_cat, "NSMenu", menu_class),
            patch.object(desktop_cat, "NSMenuItem", item_class),
            patch.object(desktop_cat, "discover_themes", return_value=[]),
        ):
            controller.popUpMenu_(Mock())

        title_actions = [
            (call.args[0], call.args[1])
            for call in item_class.alloc.return_value.initWithTitle_action_keyEquivalent_.call_args_list
        ]
        # 라벨 문구를 여기에 다시 적으면 i18n만 바꿨을 때 조용히 깨진다.
        self.assertIn((i18n.tr("ko", "menu_diagnose_again"), b"diagnose:"), title_actions)
        self.assertIn((i18n.tr("ko", "menu_last_diagnosis"), b"showLastDiagnosis:"), title_actions)

        controller._show_diagnosis_result = Mock(return_value=False)
        controller.showLastDiagnosis_(None)
        controller._show_diagnosis_result.assert_called_once_with(
            controller._last_diagnosis,
            controller._last_diagnosis_context,
            allow_cleanup=False,
        )

    def test_only_confirmed_cleanup_items_reach_safe_trash(self):
        recommendations = [
            {
                "category": "old_downloads",
                "items": [
                    {"path": "/Downloads/keep.zip"},
                    {"path": "/Downloads/trash.zip"},
                ],
            },
            {
                "category": "trash",
                "items": [{"path": "/.Trash/already.txt"}],
            },
        ]
        trash = Mock()
        summary = desktop_cat.process_cleanup_recommendations(
            recommendations,
            lambda recommendation, item: not item["path"].endswith("keep.zip"),
            trash_func=trash,
        )

        self.assertEqual(
            [call.args[0] for call in trash.call_args_list],
            ["/Downloads/trash.zip", "/.Trash/already.txt"],
        )
        self.assertEqual(
            summary,
            {"moved": 1, "already_in_trash": 1, "skipped": 1, "failed": 0},
        )

    def test_refresh_swallows_measurement_failure_so_the_timer_survives(self):
        controller = desktop_cat.CatController.alloc().init()
        controller._refresh_once = Mock(side_effect=OSError("swap unavailable"))

        # NSTimer 콜백에서 예외가 새어 나가면 run loop 가 끝나 앱이 종료된다.
        controller.refresh_(None)

        controller._refresh_once.assert_called_once_with()

    def test_refresh_uses_the_swap_tolerant_measurement(self):
        controller = desktop_cat.CatController.alloc().init()
        controller.cfg = dict(desktop_cat.DEFAULT)
        controller.language = "ko"
        controller.view = Mock()
        controller._maybe_prompt_disk_full = Mock()
        disk = SimpleNamespace(
            total=100, used=50, free=50, percent=50.0
        )
        vm = SimpleNamespace(total=8, used=4, percent=50.0)
        sw = SimpleNamespace(total=0, used=0, percent=0.0)

        with (
            patch.object(desktop_cat.mc, "disk_usage", return_value=disk),
            patch.object(
                desktop_cat.mc, "safe_pressure_score", return_value=(30.0, vm, sw)
            ) as measure,
            patch.object(desktop_cat.mc, "top_memory_apps", return_value=[]),
            patch.object(desktop_cat, "NSImage"),
        ):
            controller.refresh_(None)

        measure.assert_called_once_with()
        self.assertEqual(controller.score, 50.0)
        # 스왑을 못 읽은 경우 스왑 줄은 넣지 않는다.
        self.assertNotIn(
            "스왑", "".join(controller.detail)
        )

    def test_disk_full_warning_falls_back_to_an_alert_when_it_never_appears(self):
        controller = desktop_cat.CatController.alloc().init()
        controller.language = "ko"
        controller._show_disk_full_alert = Mock()
        # 알림센터가 아무것도 배달하지 않은 상태 = 알림이 표시되지 않은 것.
        controller._notification_center = Mock(
            **{"deliveredNotifications.return_value": []}
        )

        controller.verifyDiskFullPrompt_(None)

        controller._show_disk_full_alert.assert_called_once_with()

    def test_disk_full_warning_stays_quiet_when_the_notification_arrived(self):
        controller = desktop_cat.CatController.alloc().init()
        controller.language = "ko"
        controller._show_disk_full_alert = Mock()
        delivered = Mock()
        delivered.identifier.return_value = desktop_cat.DISK_FULL_NOTIFICATION_ID
        controller._notification_center = Mock(
            **{"deliveredNotifications.return_value": [delivered]}
        )

        controller.verifyDiskFullPrompt_(None)

        controller._show_disk_full_alert.assert_not_called()

    def test_stopping_the_review_leaves_every_remaining_item_untouched(self):
        recommendations = [
            {
                "category": "old_downloads",
                "items": [
                    {"path": "/Downloads/first.zip"},
                    {"path": "/Downloads/stop-here.zip"},
                ],
            },
            {"category": "trash", "items": [{"path": "/.Trash/never-asked.txt"}]},
        ]
        trash = Mock()
        asked = []

        def confirm(recommendation, item):
            asked.append(item["path"])
            if item["path"].endswith("stop-here.zip"):
                return desktop_cat.CLEANUP_ABORT
            return True

        summary = desktop_cat.process_cleanup_recommendations(
            recommendations, confirm, trash_func=trash
        )

        self.assertEqual(
            asked, ["/Downloads/first.zip", "/Downloads/stop-here.zip"]
        )
        self.assertEqual(
            [call.args[0] for call in trash.call_args_list],
            ["/Downloads/first.zip"],
        )
        self.assertEqual(
            summary,
            {"moved": 1, "already_in_trash": 0, "skipped": 2, "failed": 0},
        )

    def test_cleanup_item_alert_maps_its_third_button_and_escape_to_abort(self):
        controller = desktop_cat.CatController.alloc().init()
        controller.language = "ko"
        alert = Mock()
        stop_button = Mock()
        alert.addButtonWithTitle_.return_value = stop_button
        alert.runModal.return_value = desktop_cat.NSAlertThirdButtonReturn

        with (
            patch.object(desktop_cat, "new_cat_alert", return_value=alert),
            patch.object(desktop_cat, "NSApp", Mock()),
        ):
            decision = controller._confirm_cleanup_item(
                {"category": "old_downloads"}, {"path": "/Downloads/old.zip"}
            )

        self.assertEqual(decision, desktop_cat.CLEANUP_ABORT)
        self.assertIn(
            call(i18n.tr("ko", "stop_cleanup")),
            alert.addButtonWithTitle_.call_args_list,
        )
        stop_button.setKeyEquivalent_.assert_called_once_with("\033")


class CleanupSummaryDeliveryTests(unittest.TestCase):
    """정리 결과는 사용자가 방금 승인한 파일 작업의 보고서다. 조용히 사라지면 안 된다."""

    SUMMARY = {"moved": 2, "already_in_trash": 0, "skipped": 1, "failed": 0}

    def _controller(self):
        controller = desktop_cat.CatController.alloc().init()
        controller.language = "ko"
        return controller

    def _expected_body(self):
        # 문구를 여기에 다시 적으면 i18n만 바꿨을 때 조용히 깨진다.
        return " · ".join(
            (
                i18n.tr("ko", "summary_moved", count=2),
                i18n.tr("ko", "summary_skipped", count=1),
            )
        ) + i18n.tr("ko", "summary_reclaim_note")

    def test_cleanup_summary_tags_its_notification_and_schedules_the_check(self):
        controller = self._controller()
        notification = Mock()
        notification_class = Mock()
        notification_class.alloc.return_value.init.return_value = notification
        controller._notification_center = Mock()
        timer_class = Mock()

        with (
            patch.object(desktop_cat, "NSUserNotification", notification_class),
            patch.object(desktop_cat, "NSTimer", timer_class),
        ):
            controller._show_cleanup_summary(dict(self.SUMMARY))

        notification.setIdentifier_.assert_called_once_with(
            desktop_cat.CLEANUP_SUMMARY_NOTIFICATION_ID
        )
        controller._notification_center.deliverNotification_.assert_called_once_with(
            notification
        )
        timer_class.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_.assert_called_once_with(
            desktop_cat.NOTIFICATION_VERIFY_SEC,
            controller,
            b"verifyCleanupSummary:",
            None,
            False,
        )

    def test_cleanup_summary_falls_back_to_an_alert_when_it_never_appears(self):
        controller = self._controller()
        controller._show_information_alert = Mock()
        # 알림센터가 아무것도 배달하지 않은 상태 = 알림이 표시되지 않은 것.
        controller._notification_center = Mock(
            **{"deliveredNotifications.return_value": []}
        )

        with (
            patch.object(desktop_cat, "NSUserNotification", Mock()),
            patch.object(desktop_cat, "NSTimer", Mock()),
        ):
            controller._show_cleanup_summary(dict(self.SUMMARY))
        controller.verifyCleanupSummary_(None)

        controller._show_information_alert.assert_called_once_with(
            i18n.tr("ko", "cleanup_result_title"), self._expected_body()
        )

    def test_cleanup_summary_stays_quiet_when_the_notification_arrived(self):
        controller = self._controller()
        controller._show_information_alert = Mock()
        delivered = Mock()
        delivered.identifier.return_value = (
            desktop_cat.CLEANUP_SUMMARY_NOTIFICATION_ID
        )
        controller._notification_center = Mock(
            **{"deliveredNotifications.return_value": [delivered]}
        )

        with (
            patch.object(desktop_cat, "NSUserNotification", Mock()),
            patch.object(desktop_cat, "NSTimer", Mock()),
        ):
            controller._show_cleanup_summary(dict(self.SUMMARY))
        controller.verifyCleanupSummary_(None)

        controller._show_information_alert.assert_not_called()

    def test_cleanup_summary_opens_the_alert_at_once_when_delivery_raises(self):
        controller = self._controller()
        controller._show_information_alert = Mock()
        controller._notification_center = Mock(
            **{"deliverNotification_.side_effect": OSError("no center")}
        )
        timer_class = Mock()

        with (
            patch.object(desktop_cat, "NSUserNotification", Mock()),
            patch.object(desktop_cat, "NSTimer", timer_class),
        ):
            controller._show_cleanup_summary(dict(self.SUMMARY))

        controller._show_information_alert.assert_called_once_with(
            i18n.tr("ko", "cleanup_result_title"), self._expected_body()
        )
        timer_class.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_.assert_not_called()

    def test_disk_full_warning_keeps_its_own_identifier_and_check(self):
        # 두 알림이 같은 기계를 쓰지만 확인 콜백은 각자의 것이어야 한다.
        controller = self._controller()
        notification = Mock()
        notification_class = Mock()
        notification_class.alloc.return_value.init.return_value = notification
        controller._notification_center = Mock()
        timer_class = Mock()

        with (
            patch.object(desktop_cat, "NSUserNotification", notification_class),
            patch.object(desktop_cat, "NSTimer", timer_class),
        ):
            controller._show_disk_full_prompt()

        notification.setIdentifier_.assert_called_once_with(
            desktop_cat.DISK_FULL_NOTIFICATION_ID
        )
        timer_class.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_.assert_called_once_with(
            desktop_cat.NOTIFICATION_VERIFY_SEC,
            controller,
            b"verifyDiskFullPrompt:",
            None,
            False,
        )


class InstanceLockTests(unittest.TestCase):
    """뚱냥이는 한 마리만. 단, 잠금이 죽은 채 남아 앱을 못 켜게 만들면 안 된다."""

    def _lock_path(self, temp_dir):
        return str(Path(temp_dir) / desktop_cat.INSTANCE_LOCK_NAME)

    def test_a_second_launch_cannot_take_the_lock_while_the_first_holds_it(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = self._lock_path(temp_dir)
            first, busy = desktop_cat.acquire_instance_lock(path)
            self.addCleanup(first.close)

            self.assertIsNotNone(first)
            self.assertFalse(busy)
            self.assertEqual(
                desktop_cat.acquire_instance_lock(path), (None, True)
            )

    def test_the_lock_frees_itself_when_the_holder_goes_away(self):
        # flock 은 파일이 아니라 열린 fd 에 걸린다. 프로세스가 어떻게 죽든
        # (크래시·강제 종료 포함) 커널이 fd 를 닫으면서 잠금도 같이 풀린다.
        # 여기서는 그 "fd 가 닫힌다"를 그대로 재현한다. PID 파일이었다면
        # 이 시점에 죽은 잠금이 남아 다시는 못 켰을 것이다.
        with tempfile.TemporaryDirectory() as temp_dir:
            path = self._lock_path(temp_dir)
            first, _ = desktop_cat.acquire_instance_lock(path)
            first.close()

            second, busy = desktop_cat.acquire_instance_lock(path)
            self.addCleanup(second.close)

            self.assertIsNotNone(second)
            self.assertFalse(busy)

    def test_the_lock_file_records_the_holder_pid_for_the_log(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = self._lock_path(temp_dir)
            handle, _ = desktop_cat.acquire_instance_lock(path)
            self.addCleanup(handle.close)

            self.assertEqual(
                Path(path).read_text(encoding="utf-8").strip(), str(os.getpid())
            )

    def test_a_lock_we_cannot_even_create_never_blocks_startup(self):
        # 잠금을 못 거는 환경이면 두 마리가 뜰 수는 있어도, 한 마리도 안 뜨는
        # 일은 없어야 한다. 못 켜지는 앱이 두 마리보다 나쁘다.
        with tempfile.TemporaryDirectory() as temp_dir:
            path = str(Path(temp_dir) / "no-such-folder" / "memory-cat.lock")

            self.assertEqual(
                desktop_cat.acquire_instance_lock(path), (None, False)
            )

    def test_the_lock_lives_next_to_the_config_in_the_user_data_folder(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(
                "os.environ", {"MEMORY_CAT_HOME": temp_dir}, clear=False
            ):
                self.assertEqual(
                    desktop_cat.instance_lock_path(),
                    str(Path(temp_dir) / desktop_cat.INSTANCE_LOCK_NAME),
                )


class SecondLaunchTests(unittest.TestCase):
    """두 번째 실행은 새 고양이를 띄우는 대신 있던 고양이를 불러와야 한다."""

    def _app(self):
        app = Mock()
        return app, Mock(**{"sharedApplication.return_value": app})

    def _startup_patches(self):
        """main() 이 실제 창을 열지 않도록 막는 최소한의 대역들."""
        screen = Mock()
        screen.mainScreen.return_value.frame.return_value = SimpleNamespace(
            size=SimpleNamespace(width=1440.0, height=900.0)
        )
        return {
            "NSScreen": screen,
            "NSWindow": Mock(),
            "CatView": Mock(),
            "CatController": Mock(),
        }

    def test_second_launch_reveals_the_running_cat_instead_of_starting_another(self):
        app, app_class = self._app()
        parts = self._startup_patches()

        with (
            patch.object(desktop_cat, "NSApplication", app_class),
            patch.object(
                desktop_cat, "acquire_instance_lock", return_value=(None, True)
            ),
            patch.object(
                desktop_cat, "request_reveal", return_value=True
            ) as reveal,
            patch.object(desktop_cat, "show_already_running_alert") as alert,
            patch.object(desktop_cat, "NSWindow", parts["NSWindow"]),
            patch.object(desktop_cat, "CatController", parts["CatController"]),
        ):
            desktop_cat.main()

        reveal.assert_called_once_with()
        parts["NSWindow"].alloc.assert_not_called()
        parts["CatController"].alloc.assert_not_called()
        alert.assert_not_called()
        app.run.assert_not_called()

    def test_second_launch_starts_the_cat_when_the_lock_frees_up_first(self):
        # launchctl kickstart -k 처럼 앞 프로세스가 막 끝나는 순간과 겹쳤을 때.
        # 여기서 물러나 버리면 로그인해도 고양이가 아예 없는 상태가 된다.
        app, app_class = self._app()
        parts = self._startup_patches()
        handle = Mock()

        with (
            patch.object(desktop_cat, "NSApplication", app_class),
            patch.object(
                desktop_cat,
                "acquire_instance_lock",
                side_effect=[(None, True), (handle, False)],
            ),
            patch.object(desktop_cat, "request_reveal", return_value=False),
            patch.object(desktop_cat, "show_already_running_alert") as alert,
            patch.object(desktop_cat, "hold_instance_lock") as hold,
            patch.object(desktop_cat, "NSScreen", parts["NSScreen"]),
            patch.object(desktop_cat, "NSWindow", parts["NSWindow"]),
            patch.object(desktop_cat, "CatView", parts["CatView"]),
            patch.object(desktop_cat, "CatController", parts["CatController"]),
        ):
            desktop_cat.main()

        alert.assert_not_called()
        hold.assert_called_once_with(handle)
        parts["CatController"].alloc.assert_called_once_with()
        app.run.assert_called_once_with()

    def test_second_launch_explains_itself_when_the_running_cat_never_answers(self):
        # 조용히 사라지면 사용자는 앱이 고장 났다고 생각한다.
        app, app_class = self._app()
        parts = self._startup_patches()

        with (
            patch.object(desktop_cat, "NSApplication", app_class),
            patch.object(
                desktop_cat,
                "acquire_instance_lock",
                side_effect=[(None, True), (None, True)],
            ),
            patch.object(desktop_cat, "request_reveal", return_value=False),
            patch.object(desktop_cat, "show_already_running_alert") as alert,
            patch.object(desktop_cat, "NSWindow", parts["NSWindow"]),
            patch.object(desktop_cat, "CatController", parts["CatController"]),
        ):
            desktop_cat.main()

        alert.assert_called_once_with()
        parts["CatController"].alloc.assert_not_called()
        app.run.assert_not_called()

    def test_first_launch_holds_the_lock_and_never_calls_for_a_reveal(self):
        app, app_class = self._app()
        parts = self._startup_patches()
        handle = Mock()

        with (
            patch.object(desktop_cat, "NSApplication", app_class),
            patch.object(
                desktop_cat,
                "acquire_instance_lock",
                return_value=(handle, False),
            ),
            patch.object(desktop_cat, "request_reveal") as reveal,
            patch.object(desktop_cat, "hold_instance_lock") as hold,
            patch.object(desktop_cat, "NSScreen", parts["NSScreen"]),
            patch.object(desktop_cat, "NSWindow", parts["NSWindow"]),
            patch.object(desktop_cat, "CatView", parts["CatView"]),
            patch.object(desktop_cat, "CatController", parts["CatController"]),
        ):
            desktop_cat.main()

        reveal.assert_not_called()
        hold.assert_called_once_with(handle)
        app.run.assert_called_once_with()

    def test_already_running_alert_speaks_the_users_language(self):
        alert = Mock()

        with (
            patch.object(desktop_cat, "new_cat_alert", return_value=alert),
            patch.object(desktop_cat, "NSApp", Mock()),
        ):
            desktop_cat.show_already_running_alert("en")

        alert.setMessageText_.assert_called_once_with(
            i18n.tr("en", "already_running_title", pet="Memory Cat")
        )
        alert.setInformativeText_.assert_called_once_with(
            i18n.tr("en", "already_running_body", pet="Memory Cat")
        )

    def test_already_running_alert_uses_the_name_the_user_gave(self):
        alert = Mock()

        with (
            patch.object(desktop_cat, "new_cat_alert", return_value=alert),
            patch.object(desktop_cat, "NSApp", Mock()),
            patch.object(
                desktop_cat,
                "load_config",
                return_value={"language": "ko", "pet_name": "몽이"},
            ),
        ):
            desktop_cat.show_already_running_alert()

        title = alert.setMessageText_.call_args.args[0]
        self.assertIn("몽이", title)
        self.assertNotIn("뚱냥이", title)


class RevealTests(unittest.TestCase):
    """부름을 받은 고양이는 사용자 눈앞으로 나와야 한다."""

    def _window(self, x, y):
        window = Mock()
        window.frame.return_value = SimpleNamespace(
            origin=SimpleNamespace(x=x, y=y),
            size=SimpleNamespace(width=120.0, height=160.0),
        )
        return window

    def _screen(self):
        screen = Mock()
        screen.mainScreen.return_value.visibleFrame.return_value = SimpleNamespace(
            origin=SimpleNamespace(x=0.0, y=0.0),
            size=SimpleNamespace(width=1440.0, height=900.0),
        )
        return screen

    def test_revealing_pulls_an_off_screen_cat_back_into_view(self):
        controller = desktop_cat.CatController.alloc().init()
        controller.window = self._window(3000.0, -200.0)

        with patch.object(desktop_cat, "NSScreen", self._screen()):
            controller.revealCat()

        point = controller.window.setFrameOrigin_.call_args.args[0]
        self.assertEqual((point.x, point.y), (1320.0, 0.0))
        controller.window.orderFrontRegardless.assert_called_once_with()

    def test_revealing_leaves_a_visible_cat_where_the_user_put_it(self):
        controller = desktop_cat.CatController.alloc().init()
        controller.window = self._window(400.0, 300.0)

        with patch.object(desktop_cat, "NSScreen", self._screen()):
            controller.revealCat()

        controller.window.setFrameOrigin_.assert_not_called()
        controller.window.orderFrontRegardless.assert_called_once_with()

    def test_a_called_cat_answers_even_when_it_cannot_move(self):
        # 답장이 없으면 두 번째 실행은 "멈춘 고양이"로 보고 알럿을 띄운다.
        # 창을 못 옮기는 것과 죽은 것은 다르다.
        controller = desktop_cat.CatController.alloc().init()
        controller.revealCat = Mock(side_effect=RuntimeError("no window server"))
        controller._distributed_center = Mock()

        controller.revealRequested_(None)

        controller._distributed_center.postNotificationName_object_.assert_called_once_with(
            desktop_cat.REVEAL_ACK_NOTIFICATION, None
        )

    def test_the_reveal_handshake_really_travels_through_macos(self):
        """가짜 대역이 아니라 실제 알림센터로 신호와 응답을 주고받아 본다.

        가짜로만 확인하면 "코드를 썼다"만 증명된다. 이 왕복이 깨지면
        두 번째 실행이 매번 알럿을 띄우게 되므로 진짜로 태워 본다.
        """
        controller = desktop_cat.CatController.alloc().init()
        controller.window = self._window(400.0, 300.0)
        controller.listenForRevealRequests()
        center = desktop_cat.NSDistributedNotificationCenter.defaultCenter()
        self.addCleanup(center.removeObserver_, controller)

        with patch.object(desktop_cat, "NSScreen", self._screen()):
            acknowledged = desktop_cat.request_reveal(timeout=5.0)

        self.assertTrue(acknowledged)
        controller.window.orderFrontRegardless.assert_called_once_with()

    def test_pet_theme_asks_for_a_key_before_asking_for_a_photo(self):
        controller = desktop_cat.CatController.alloc().init()
        controller.language = "ko"
        controller._pet_theme_running = False
        controller._show_information_alert = Mock()
        panel_class = Mock()

        with (
            patch.object(desktop_cat, "_load_api_key", return_value=None),
            patch.object(desktop_cat, "NSOpenPanel", panel_class),
        ):
            controller.makePetTheme_(None)

        # 사진 선택기를 아예 열지 않는다 -- 고르고 나서 실패하면 헛수고다.
        panel_class.openPanel.assert_not_called()
        title, body = controller._show_information_alert.call_args.args
        self.assertEqual(title, "API 키가 필요해요")
        self.assertIn("OPENAI_API_KEY=sk-...", body)
        self.assertIn(".env", body)

    def test_diagnosis_tells_you_where_to_put_the_key_when_it_is_missing(self):
        content = desktop_cat.diagnosis_result_content(
            {
                "source": "fallback",
                "fallback_reason": "missing_api_key",
                "why_slow": ["디스크가 꽉 찼어요"],
                "one_line_advice": "정리해보세요",
                "estimated_reclaimable": "10 GB",
            },
            personality_label=DEFAULT_PERSONALITY,
            language="ko",
        )

        self.assertIn("OPENAI_API_KEY=sk-...", content["body"])
        self.assertIn(".env", content["body"])

    def test_other_fallbacks_do_not_nag_about_the_key(self):
        # 키가 있는데 API 가 실패한 경우다. 키 안내는 도움이 안 되고 방해만 된다.
        for reason in ("api_error", "worker_error"):
            with self.subTest(reason=reason):
                content = desktop_cat.diagnosis_result_content(
                    {
                        "source": "fallback",
                        "fallback_reason": reason,
                        "why_slow": ["디스크가 꽉 찼어요"],
                        "one_line_advice": "정리해보세요",
                        "estimated_reclaimable": "10 GB",
                    },
                    personality_label=DEFAULT_PERSONALITY,
                    language="ko",
                )
                self.assertNotIn("OPENAI_API_KEY=sk-...", content["body"])

    def test_the_alert_icon_follows_a_custom_pet_theme_and_its_current_size(self):
        # 반려동물 사진으로 테마를 만든 사람에게 기본 고양이가 말을 걸면 안 되고,
        # "배불러요" 라고 말하는 창에 홀쭉한 그림이 붙어 있어도 안 된다.
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "myotter").mkdir()
            for index in range(11):
                (root / "myotter" / f"cat_{index:02d}.png").write_bytes(b"png")

            cases = {0.0: "cat_00.png", 50.0: "cat_05.png", 91.0: "cat_09.png",
                     100.0: "cat_10.png"}
            for percent, expected in cases.items():
                with self.subTest(percent=percent):
                    with (
                        patch.object(desktop_cat, "USER_FRAMES_BASE", str(root)),
                        patch.object(desktop_cat, "load_config",
                                     return_value={"theme": "myotter"}),
                        patch.object(desktop_cat.mc, "disk_usage",
                                     return_value=SimpleNamespace(percent=percent)),
                    ):
                        chosen = desktop_cat.alert_icon_path()
                    self.assertEqual(chosen, str(root / "myotter" / expected))

    def test_the_alert_icon_still_appears_when_the_disk_cannot_be_measured(self):
        # 측정이 실패해도 그 테마의 얼굴은 보여 준다. 아이콘 때문에 알럿이
        # 안 뜨는 쪽이 나쁘다.
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "myotter").mkdir()
            (root / "myotter" / "cat_00.png").write_bytes(b"png")

            with (
                patch.object(desktop_cat, "USER_FRAMES_BASE", str(root)),
                patch.object(desktop_cat, "load_config", return_value={"theme": "myotter"}),
                patch.object(desktop_cat.mc, "disk_usage", side_effect=OSError("boom")),
            ):
                chosen = desktop_cat.alert_icon_path()

        self.assertEqual(chosen, str(root / "myotter" / "cat_00.png"))

    def test_the_cat_and_the_alert_icon_use_the_same_frame_maths(self):
        # 둘이 갈라지면 바탕화면과 대화상자의 몸집이 달라진다.
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "myotter").mkdir()
            for index in range(40):
                (root / "myotter" / f"cat_{index:02d}.png").write_bytes(b"png")

            with patch.object(desktop_cat, "USER_FRAMES_BASE", str(root)):
                for percent in (0.0, 37.5, 91.0, 100.0):
                    with self.subTest(percent=percent):
                        index = desktop_cat.frame_index_for("myotter", percent)
                        self.assertEqual(
                            desktop_cat.frame_path("myotter", index),
                            str(root / "myotter" / f"cat_{index:02d}.png"),
                        )

    def test_the_alert_icon_falls_back_when_the_theme_is_gone(self):
        # 테마 폴더를 지웠거나 config 가 깨졌어도 알럿은 떠야 한다.
        with patch.object(
            desktop_cat, "load_config", return_value={"theme": "deleted-theme"}
        ):
            self.assertEqual(
                desktop_cat.alert_icon_path(), desktop_cat.FALLBACK_ALERT_ICON_PATH
            )

    def test_the_alert_icon_survives_a_broken_config(self):
        with patch.object(desktop_cat, "load_config", side_effect=OSError("boom")):
            self.assertEqual(
                desktop_cat.alert_icon_path(), desktop_cat.FALLBACK_ALERT_ICON_PATH
            )

    def test_the_diagnosis_calls_the_pet_by_the_name_the_user_gave(self):
        result = {
            "source": "openai",
            "why_slow": ["디스크가 꽉 찼어요"],
            "one_line_advice": "정리해보세요",
            "estimated_reclaimable": "12 GB",
        }
        named = desktop_cat.diagnosis_result_content(
            result, personality_label="따뜻함", language="ko", pet="몽이"
        )
        self.assertIn("몽이", named["title"])
        self.assertNotIn("뚱냥이", named["title"])

        unnamed = desktop_cat.diagnosis_result_content(
            result, personality_label="따뜻함", language="ko", pet=""
        )
        self.assertIn("뚱냥이", unnamed["title"])

    def test_the_default_name_follows_the_language_of_the_message(self):
        # 진단이 도는 사이 언어를 바꾸면, 문장은 한국어인데 이름만 영어가 될
        # 수 있었다. 기본 호칭은 문장을 만드는 쪽 언어를 따라야 한다.
        result = {
            "source": "fallback",
            "fallback_reason": "api_error",
            "why_slow": ["x"],
            "one_line_advice": "y",
            "estimated_reclaimable": "1 GB",
        }
        for language, expected in (("ko", "뚱냥이"), ("en", "Memory Cat")):
            with self.subTest(language=language):
                content = desktop_cat.diagnosis_result_content(
                    result, personality_label="따뜻함", language=language, pet=None
                )
                self.assertIn(expected, content["title"])

    def test_naming_the_pet_stores_a_trimmed_name(self):
        controller = desktop_cat.CatController.alloc().init()
        controller.cfg = dict(desktop_cat.DEFAULT)
        controller.language = "ko"
        controller.refresh_ = Mock()
        controller._notify = Mock(return_value=True)
        alert = Mock()
        alert.runModal.return_value = desktop_cat.NSAlertFirstButtonReturn
        field = Mock()
        field.stringValue.return_value = "  몽이  "

        with (
            patch.object(desktop_cat, "new_cat_alert", return_value=alert),
            patch.object(desktop_cat, "NSApp", Mock()),
            patch.object(desktop_cat, "NSTextField", Mock(
                **{"alloc.return_value.initWithFrame_.return_value": field})),
            patch.object(desktop_cat, "save_config", return_value=True) as save,
        ):
            controller.setPetName_(None)

        self.assertEqual(controller.cfg["pet_name"], "몽이")
        save.assert_called_once_with(controller.cfg)

    def test_clearing_the_name_goes_back_to_the_default(self):
        # 이름을 지우는 것도 선택이다. 빈 칸이면 기본 호칭으로 돌아가야 한다.
        controller = desktop_cat.CatController.alloc().init()
        controller.cfg = dict(desktop_cat.DEFAULT, pet_name="몽이")
        controller.language = "ko"
        controller.refresh_ = Mock()
        controller._notify = Mock(return_value=True)
        alert = Mock()
        alert.runModal.return_value = desktop_cat.NSAlertFirstButtonReturn
        field = Mock()
        field.stringValue.return_value = "   "

        with (
            patch.object(desktop_cat, "new_cat_alert", return_value=alert),
            patch.object(desktop_cat, "NSApp", Mock()),
            patch.object(desktop_cat, "NSTextField", Mock(
                **{"alloc.return_value.initWithFrame_.return_value": field})),
            patch.object(desktop_cat, "save_config", return_value=True),
        ):
            controller.setPetName_(None)

        self.assertEqual(controller.cfg["pet_name"], "")
        self.assertEqual(controller.petName(), "뚱냥이")


if __name__ == "__main__":
    unittest.main()

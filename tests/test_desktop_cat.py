import json
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
    def test_new_cat_alert_uses_bundled_cat_frame_as_its_icon(self):
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
            desktop_cat.ALERT_ICON_PATH
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


if __name__ == "__main__":
    unittest.main()

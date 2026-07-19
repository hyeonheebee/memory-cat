import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import desktop_cat
from i18n import LANGUAGE_AUTO, LANGUAGE_EN
from personality import CUSTOM_PERSONALITY, DEFAULT_PERSONALITY


class DesktopCatTests(unittest.TestCase):
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
        self.assertIn(("🐾 다시 살펴보기", b"diagnose:"), title_actions)
        self.assertIn(("📋 마지막 진단 보기", b"showLastDiagnosis:"), title_actions)

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


if __name__ == "__main__":
    unittest.main()

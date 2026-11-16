import json
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.ai_recommendations.bmi_advice import bmi_advice
from apps.ai_recommendations.services import suggest_sisaket_places
from apps.community.models import EditorialEntry

PROFILE = {"bmi": 26.4, "bmr": 1500, "age": 45, "health_goal": "WEIGHT_MANAGEMENT", "weight_kg": 70, "height_cm": 163}


def deepseek_reply(rows):
    response = mock.Mock(status_code=200)
    response.json.return_value = {"choices": [{"message": {"content": "นี่คือรายการ:\n" + json.dumps(rows, ensure_ascii=False)}}]}
    return response


class BmiAdviceTests(TestCase):
    def test_bands_follow_asian_cut_offs(self):
        self.assertEqual(bmi_advice(17.9)["key"], "UNDER")
        self.assertEqual(bmi_advice(18.5)["key"], "NORMAL")
        self.assertEqual(bmi_advice(22.9)["key"], "NORMAL")
        self.assertEqual(bmi_advice(23.0)["key"], "OVER")
        self.assertEqual(bmi_advice(27)["key"], "OBESE1")
        self.assertEqual(bmi_advice(31)["key"], "OBESE2")

    def test_every_band_has_food_care_and_caution(self):
        for bmi in (16, 20, 24, 27, 35):
            advice = bmi_advice(bmi)
            self.assertTrue(advice["eat"] and advice["care"] and advice["caution"])
            self.assertIn("ไม่ใช่การวินิจฉัย", advice["disclaimer"])

    def test_bad_input_gives_no_advice(self):
        self.assertIsNone(bmi_advice(None))
        self.assertIsNone(bmi_advice("abc"))
        self.assertIsNone(bmi_advice(0))

    def test_assessment_page_ships_the_advice_for_live_display(self):
        page = self.client.get(reverse("ai_recommendations:assessment"))
        self.assertContains(page, 'id="bmi-advice"')
        self.assertContains(page, "คำแนะนำเบื้องต้นตามค่า BMI")


class AiPlacesTests(TestCase):
    def setUp(self):
        self.temple = EditorialEntry.objects.create(
            kind=EditorialEntry.Kind.ATTRACTION, title="วัดป่ามหาเจดีย์แก้ว (วัดล้านขวด)",
            location="อ.ขุนหาญ จ.ศรีสะเกษ", is_published=True, summary="วัดที่สร้างจากขวดแก้ว",
        )

    @override_settings(DEEPSEEK_API_KEY="test-key")
    def test_ai_suggestions_link_known_places_and_flag_the_rest(self):
        rows = [
            {"name": "วัดป่ามหาเจดีย์แก้ว", "district": "ขุนหาญ", "reason": "เดินชมวัดช่วงเช้า"},
            {"name": "สวนสมเด็จศรีนครินทร์", "district": "เมืองศรีสะเกษ", "reason": "เดินออกกำลังกายรอบบึง"},
        ]
        with mock.patch("apps.ai_recommendations.services.requests.post", return_value=deepseek_reply(rows)):
            places = suggest_sisaket_places(PROFILE)
        self.assertEqual(len(places), 2)
        self.assertTrue(places[0]["verified"])
        self.assertEqual(places[0]["url"], reverse("community:story_detail", args=[self.temple.id]))
        self.assertFalse(places[1]["verified"])
        self.assertEqual(places[1]["url"], "")
        self.assertEqual(places[1]["source"], "AI")

    @override_settings(DEEPSEEK_API_KEY="test-key")
    def test_unreadable_ai_reply_falls_back_to_site_attractions(self):
        bad = mock.Mock(status_code=200)
        bad.json.return_value = {"choices": [{"message": {"content": "ขออภัย ไม่สามารถตอบได้"}}]}
        with mock.patch("apps.ai_recommendations.services.requests.post", return_value=bad):
            places = suggest_sisaket_places(PROFILE)
        self.assertEqual([p["name"] for p in places], [self.temple.title])
        self.assertEqual(places[0]["source"], "WELLTRIP")

    @override_settings(DEEPSEEK_API_KEY="")
    def test_without_api_key_uses_site_attractions(self):
        places = suggest_sisaket_places(PROFILE)
        self.assertEqual(places[0]["name"], self.temple.title)

    @override_settings(DEEPSEEK_API_KEY="test-key")
    def test_result_page_shows_advice_and_places(self):
        rows = [{"name": "สวนสมเด็จศรีนครินทร์", "district": "เมือง", "reason": "เดินรอบบึง"}]
        analysis = mock.Mock(status_code=500)
        from apps.ai_recommendations.models import AIRecommendationLog
        with mock.patch("apps.ai_recommendations.services.requests.post", side_effect=[analysis, deepseek_reply(rows)]):
            with self.captureOnCommitCallbacks(execute=True):
                first = self.client.post(reverse("ai_recommendations:assess_htmx"), {
                    "weight_kg": "70", "height_cm": "163", "age": "45", "gender": "female", "health_goal": "WEIGHT_MANAGEMENT",
                })
        # Advice shows at once, before the AI job finishes
        self.assertContains(first, "คำแนะนำสุขภาพสำหรับ BMI")
        log = AIRecommendationLog.objects.latest("created_at")
        page = self.client.get(reverse("ai_recommendations:result_htmx", args=[log.id]))
        self.assertContains(page, "คำแนะนำสุขภาพสำหรับ BMI")
        self.assertContains(page, "สวนสมเด็จศรีนครินทร์")
        self.assertContains(page, "ควรตรวจสอบก่อนเดินทาง")
